"""Idempotent create-or-update helpers for each Auth0 resource the setup wizard provisions.

Every `ensure_*` function lists existing resources, finds a match by name (or another
identifying field), updates the fields that are safe to update if a match is found,
and creates the resource otherwise. A wizard run that resumes after a partial failure
therefore never duplicates a resource it already created.
"""

import logging
from dataclasses import dataclass

from .client import find_by_name, list_all

logger = logging.getLogger(__name__)

# Matches the role-creation list in auth0/README.md's Role Setup section (Admin,
# Member, Guest, SignedIn). The prose earlier in that same doc ("Admin, Member,
# Viewer, Public") is stale; the Role Setup list is the ground truth.
ROLE_NAMES = ["Admin", "Member", "Guest", "SignedIn"]

# Copied verbatim from auth0/README.md's "Check Approval" Post-Login Action, so a
# change to the wizard's behavior and a change to that manual-fallback
# documentation can't silently drift apart.
CHECK_APPROVAL_ACTION_NAME = "Check Approval"
CHECK_APPROVAL_ACTION_CODE = """\
exports.onExecutePostLogin = async (event, api) => {
  // Check if the user is approved
  if (event.user.app_metadata && event.user.app_metadata.approved) {
    // User is approved, continue without action
  } else {
    api.access.deny("Your approval to access the app is pending.");
  }
};
"""

# Copied verbatim from auth0/README.md's "Add Roles Claim" Post-Login Action.
ADD_ROLES_CLAIM_ACTION_NAME = "Add Roles Claim"
ADD_ROLES_CLAIM_ACTION_CODE = """\
exports.onExecutePostLogin = async (event, api) => {
  if (event.authorization) {
    api.idToken.setCustomClaim("urn:gc:roles", event.authorization.roles);
  }
};
"""

POST_LOGIN_TRIGGER_ID = "post-login"


@dataclass
class ClientResult:
    client_id: str
    client_secret: str | None
    created: bool


def ensure_google_connection(mgmt, client_id: str, client_secret: str) -> dict:
    """Create or update the tenant's google-oauth2 social connection."""
    connections = mgmt.connections.all(strategy="google-oauth2")
    existing = connections[0] if connections else None

    options = {"client_id": client_id, "client_secret": client_secret}
    if existing:
        logger.info("Updating existing google-oauth2 connection")
        return mgmt.connections.update(existing["id"], {"options": options})

    logger.info("Creating google-oauth2 connection")
    return mgmt.connections.create(
        {"name": "google-oauth2", "strategy": "google-oauth2", "options": options}
    )


def ensure_client(
    mgmt,
    name: str,
    app_type: str,
    callbacks: list[str] | None = None,
    web_origins: list[str] | None = None,
    allowed_origins: list[str] | None = None,
    existing_secret: str | None = None,
) -> ClientResult:
    """Create or update a single Auth0 Application (client), by name.

    The Management API returns `client_secret` only on the create response,
    not from later reads or list calls.
    On update, the caller must supply any already-known secret via `existing_secret`
    (e.g. read from the operator's target stack.yaml); when no secret is known,
    the returned `ClientResult.client_secret` is None and the caller should
    warn the operator.
    """
    clients = list_all(mgmt.clients)
    existing = find_by_name(clients, name)

    fields = {}
    if callbacks is not None:
        fields["callbacks"] = callbacks
    if web_origins is not None:
        fields["web_origins"] = web_origins
    if allowed_origins is not None:
        fields["allowed_origins"] = allowed_origins

    if existing:
        logger.info(f"Updating existing Auth0 client {name!r}")
        if fields:
            mgmt.clients.update(existing["client_id"], fields)
        if existing_secret is None:
            logger.warning(
                f"Client {name!r} already exists in Auth0 but no known secret was "
                "found in the target stack.yaml. Leaving auth0_client_secret blank "
                "-- rotate it manually in the Auth0 dashboard if needed."
            )
        return ClientResult(
            client_id=existing["client_id"],
            client_secret=existing_secret,
            created=False,
        )

    logger.info(f"Creating Auth0 client {name!r}")
    body = {"name": name, "app_type": app_type, **fields}
    created = mgmt.clients.create(body)
    return ClientResult(
        client_id=created["client_id"],
        client_secret=created.get("client_secret"),
        created=True,
    )


def ensure_m2m_client(
    mgmt, name: str = "GC Metrics", existing_secret: str | None = None
) -> ClientResult:
    """Create or update the tenant-wide M2M application used for metrics scripts."""
    return ensure_client(
        mgmt, name, app_type="non_interactive", existing_secret=existing_secret
    )


def ensure_management_api_grant(
    mgmt, domain: str, client_id: str, scopes: list[str]
) -> dict:
    """Grant a client the given scopes against the tenant's own Management API."""
    audience = f"https://{domain}/api/v2/"
    grants = mgmt.client_grants.all(client_id=client_id, audience=audience)
    existing = grants[0] if grants else None

    if existing:
        logger.info(f"Updating Management API grant for client {client_id}")
        return mgmt.client_grants.update(existing["id"], {"scope": scopes})

    logger.info(f"Creating Management API grant for client {client_id}")
    return mgmt.client_grants.create(
        {"client_id": client_id, "audience": audience, "scope": scopes}
    )


def ensure_roles(mgmt) -> dict[str, str]:
    """Create Admin/Member/Guest/SignedIn roles if missing. Returns {name: role_id}."""
    existing = list_all(
        mgmt.roles, list_method="list", items_key="roles", include_totals=True
    )
    role_ids = {}
    for name in ROLE_NAMES:
        found = find_by_name(existing, name)
        if found:
            role_ids[name] = found["id"]
        else:
            logger.info(f"Creating role {name!r}")
            created = mgmt.roles.create({"name": name})
            role_ids[name] = created["id"]
    return role_ids


def _ensure_post_login_action(mgmt, name: str, code: str) -> dict:
    """Create-or-update one Post-Login Action by name, then deploy it.

    Auth0 requires an explicit deploy before a code change to an Action takes
    effect, so deploy_action is called unconditionally: a no-op when the code
    was already deployed, required when it changed.
    """
    existing_page = mgmt.actions.get_actions(
        trigger_id=POST_LOGIN_TRIGGER_ID, action_name=name
    )
    existing = find_by_name(existing_page.get("actions", []), name)

    code_body = {
        "code": code,
        "supported_triggers": [{"id": POST_LOGIN_TRIGGER_ID, "version": "v3"}],
    }
    if existing:
        logger.info(f"Updating Post-Login Action {name!r}")
        action = mgmt.actions.update_action(existing["id"], code_body)
    else:
        logger.info(f"Creating Post-Login Action {name!r}")
        action = mgmt.actions.create_action({"name": name, **code_body})

    mgmt.actions.deploy_action(action["id"])
    return action


def ensure_post_login_actions(mgmt) -> None:
    """Create/update/deploy both Post-Login Actions, then bind them into the
    Login flow if not already bound.

    Existing bindings are preserved and appended to, not replaced.
    This way, the wizard won't clobber bindings a tenant admin added by hand.
    """
    check_approval = _ensure_post_login_action(
        mgmt, CHECK_APPROVAL_ACTION_NAME, CHECK_APPROVAL_ACTION_CODE
    )
    add_roles_claim = _ensure_post_login_action(
        mgmt, ADD_ROLES_CLAIM_ACTION_NAME, ADD_ROLES_CLAIM_ACTION_CODE
    )

    current = mgmt.actions.get_trigger_bindings(POST_LOGIN_TRIGGER_ID)
    existing_bindings = current.get("bindings", [])
    bound_action_ids = {b["action"]["id"] for b in existing_bindings if "action" in b}

    # update_trigger_bindings replaces the entire binding list in a single call,
    # and it identifies each binding by a "ref" object -- a different shape than
    # the "action" object get_trigger_bindings returns. So every existing binding
    # must be translated from "action" to "ref" form before appending Check
    # Approval and Add Roles Claim, for whichever of the two isn't bound yet.
    new_bindings = [
        {
            "ref": {"type": "action_id", "value": b["action"]["id"]},
            "display_name": b.get("display_name", b["action"].get("name", "")),
        }
        for b in existing_bindings
        if "action" in b
    ]
    added_any = False
    for action, name in (
        (check_approval, CHECK_APPROVAL_ACTION_NAME),
        (add_roles_claim, ADD_ROLES_CLAIM_ACTION_NAME),
    ):
        if action["id"] not in bound_action_ids:
            logger.info(f"Binding Action {name!r} into the Post-Login flow")
            new_bindings.append(
                {
                    "ref": {"type": "action_id", "value": action["id"]},
                    "display_name": name,
                }
            )
            added_any = True

    if added_any:
        mgmt.actions.update_trigger_bindings(
            POST_LOGIN_TRIGGER_ID, {"bindings": new_bindings}
        )
