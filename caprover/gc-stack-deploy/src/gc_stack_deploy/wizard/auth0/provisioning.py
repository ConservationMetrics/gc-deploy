"""Idempotent create-or-update helpers for each Auth0 resource the setup wizard provisions.

Every `ensure_*` function lists existing resources, finds a match by name (or another
identifying field), and updates-or-creates

This module encodes a lot of business logic directly from /auth0/README.md in this repo.
"""

import logging
from dataclasses import dataclass

from .client import find_by_name

logger = logging.getLogger(__name__)

# Matches the role-creation list in auth0/README.md's Role Setup section (Admin,
# Member, Guest, SignedIn). The prose earlier in that same doc ("Admin, Member,
# Viewer, Public") is stale; the Role Setup list is the ground truth.
ROLE_NAMES = ["Admin", "Member", "Guest", "SignedIn"]

# Verbatim copy from auth0/README.md's "Check Approval" Post-Login Action
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

# Verbatim copy from auth0/README.md's "Add Roles Claim" Post-Login Action.
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


def ensure_google_connection(mgmt, client_id: str, client_secret: str):
    """Create or update the tenant's google-oauth2 social connection."""
    connections = list(mgmt.connections.list(strategy="google-oauth2"))
    existing = connections[0] if connections else None

    options = {"client_id": client_id, "client_secret": client_secret}
    if existing:
        logger.info("Updating existing google-oauth2 connection")
        return mgmt.connections.update(existing.id, options=options)

    logger.info("Creating google-oauth2 connection")
    return mgmt.connections.create(
        name="google-oauth2", strategy="google-oauth2", options=options
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

    The Management API returns `client_secret` only on the *create* response, but not on later reads.
    To update, the caller must supply any already-known secret via `existing_secret`
    (e.g. read from the operator's target stack.yaml); when no secret is known,
    the returned `ClientResult.client_secret` is None and the caller should
    warn the operator.
    """
    existing = find_by_name(mgmt.clients.list(), name)

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
            mgmt.clients.update(existing.client_id, **fields)
        if existing_secret is None:
            logger.warning(
                f"Client {name!r} already exists in Auth0 but no known secret was "
                "found in the target stack.yaml. Leaving auth0_client_secret blank "
                "-- rotate it manually in the Auth0 dashboard if needed."
            )
        return ClientResult(
            client_id=existing.client_id,
            client_secret=existing_secret,
            created=False,
        )

    logger.info(f"Creating Auth0 client {name!r}")
    created = mgmt.clients.create(name=name, app_type=app_type, **fields)
    return ClientResult(
        client_id=created.client_id,
        client_secret=created.client_secret,
        created=True,
    )


def ensure_m2m_client(
    mgmt, name: str = "GC Metrics", existing_secret: str | None = None
) -> ClientResult:
    """Create or update the tenant-wide M2M application used for metrics scripts."""
    return ensure_client(
        mgmt, name, app_type="non_interactive", existing_secret=existing_secret
    )


def ensure_management_api_grant(mgmt, domain: str, client_id: str, scopes: list[str]):
    """Grant a client the given scopes against the tenant's own Management API."""
    audience = f"https://{domain}/api/v2/"
    grants = list(mgmt.client_grants.list(client_id=client_id, audience=audience))
    existing = grants[0] if grants else None

    if existing:
        logger.info(f"Updating Management API grant for client {client_id}")
        return mgmt.client_grants.update(existing.id, scope=scopes)

    logger.info(f"Creating Management API grant for client {client_id}")
    return mgmt.client_grants.create(
        client_id=client_id, audience=audience, scope=scopes
    )


def ensure_roles(mgmt) -> dict[str, str]:
    """Create Admin/Member/Guest/SignedIn roles if missing. Returns {name: role_id}."""
    existing = list(mgmt.roles.list())
    role_ids = {}
    for name in ROLE_NAMES:
        found = find_by_name(existing, name)
        if found:
            role_ids[name] = found.id
        else:
            logger.info(f"Creating role {name!r}")
            created = mgmt.roles.create(name=name)
            role_ids[name] = created.id
    return role_ids


def _ensure_post_login_action(mgmt, name: str, code: str):
    """Create-or-update one Post-Login Action by name, then deploy it.

    Auth0 requires an explicit deploy before a code change to an Action takes
    effect, so deploy is called unconditionally: a no-op when the code was
    already deployed, required when it changed.
    """
    existing = find_by_name(
        mgmt.actions.list(trigger_id=POST_LOGIN_TRIGGER_ID, action_name=name), name
    )

    fields = {
        "code": code,
        "supported_triggers": [{"id": POST_LOGIN_TRIGGER_ID, "version": "v3"}],
    }
    if existing:
        logger.info(f"Updating Post-Login Action {name!r}")
        action = mgmt.actions.update(existing.id, **fields)
    else:
        logger.info(f"Creating Post-Login Action {name!r}")
        action = mgmt.actions.create(name=name, **fields)

    mgmt.actions.deploy(action.id)
    return action


def ensure_post_login_actions(mgmt) -> None:
    """Create/update/deploy both Post-Login Actions, then bind them into the
    Login flow if not already bound.

    Existing bindings are modified in-place.
    """
    check_approval = _ensure_post_login_action(
        mgmt, CHECK_APPROVAL_ACTION_NAME, CHECK_APPROVAL_ACTION_CODE
    )
    add_roles_claim = _ensure_post_login_action(
        mgmt, ADD_ROLES_CLAIM_ACTION_NAME, ADD_ROLES_CLAIM_ACTION_CODE
    )

    # Every binding the post-login trigger returns is, by definition of that
    # endpoint, bound to an action -- no need to guard against a binding with
    # no action the way the old dict-shaped response required.
    existing_bindings = list(mgmt.actions.triggers.bindings.list(POST_LOGIN_TRIGGER_ID))
    bound_action_ids = {b.action.id for b in existing_bindings}

    # update_many replaces the entire binding list in a single call, and it
    # identifies each binding by a "ref" object -- a different shape than the
    # "action" object .list() returns. So every existing binding must be
    # translated from "action" to "ref" form before appending Check Approval
    # and Add Roles Claim, for whichever of the two isn't bound yet.
    new_bindings = [
        {
            "ref": {"type": "action_id", "value": b.action.id},
            "display_name": b.display_name or b.action.name,
        }
        for b in existing_bindings
    ]
    added_any = False
    for action, name in (
        (check_approval, CHECK_APPROVAL_ACTION_NAME),
        (add_roles_claim, ADD_ROLES_CLAIM_ACTION_NAME),
    ):
        if action.id not in bound_action_ids:
            logger.info(f"Binding Action {name!r} into the Post-Login flow")
            new_bindings.append(
                {
                    "ref": {"type": "action_id", "value": action.id},
                    "display_name": name,
                }
            )
            added_any = True

    if added_any:
        mgmt.actions.triggers.bindings.update_many(
            POST_LOGIN_TRIGGER_ID, bindings=new_bindings
        )
