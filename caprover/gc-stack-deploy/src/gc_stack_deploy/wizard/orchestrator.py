"""Sequences Auth0 provisioning and the final YAML write. This is the only
place that knows the end-to-end wizard order; screens.py just calls
run_wizard() from a worker thread and reads the log.
"""

import logging

from .auth0.client import get_management_client
from .auth0.provisioning import (
    ClientResult,
    ensure_client,
    ensure_google_connection,
    ensure_m2m_client,
    ensure_management_api_grant,
    ensure_post_login_actions,
    ensure_roles,
)
from .yaml_writer import (
    apply_auth0_client_results_to_config,
    apply_deployment_metadata_to_config,
    dump_config,
)

logger = logging.getLogger("gc-stack-deploy.wizard")

# GC-Explorer and GC Landing Page scope lists are copied verbatim from
# auth0/README.md's RBAC "API Configuration" section.
EXPLORER_SCOPES = ["read:users", "read:user_idp_tokens", "read:roles", "read:role_members"]
LANDING_PAGE_SCOPES = [
    "read:users",
    "read:roles",
    "read:role_members",
    "create:role_members",
    "delete:role_members",
    "update:users_app_metadata",
    "delete:users",
]
METRICS_SCOPES = ["read:users", "read:stats"]

APP_DISPLAY_NAMES = {
    "superset-only": "Superset",
    "gc-explorer": "GC-Explorer",
    "gc-landing-page": "GC Landing Page",
}


def _client_spec_for_app(app_key: str, config: dict, root_domain: str) -> dict:
    """Callback/origin URLs for one app's Auth0 client.

    Assumes each app is reachable at "<app_name>.<root_domain>", except
    gc-landing-page, which (via its default redirect_to_root: true) is served
    directly at the root domain.
    """
    if app_key == "superset-only":
        app_name = config.get(app_key, {}).get("app_name", "superset")
        host = f"{app_name}.{root_domain}"
        return {
            "name": APP_DISPLAY_NAMES[app_key],
            "app_type": "regular_web",
            # Superset requires http:// (not https://) for its callback URL --
            # see https://github.com/ConservationMetrics/superset-deployment/issues/51.
            # Do not "fix" this to https://.
            "callbacks": [f"http://{host}/oauth-authorized/auth0"],
            "web_origins": [f"https://{host}/"],
            "allowed_origins": [f"https://{host}/"],
        }
    if app_key == "gc-explorer":
        app_name = config.get(app_key, {}).get("app_name", "explorer")
        host = f"{app_name}.{root_domain}"
        return {
            "name": APP_DISPLAY_NAMES[app_key],
            "app_type": "regular_web",
            "callbacks": [f"https://{host}/login"],
            "web_origins": [f"https://{host}"],
            "allowed_origins": [f"https://{host}"],
        }
    if app_key == "gc-landing-page":
        return {
            "name": APP_DISPLAY_NAMES[app_key],
            "app_type": "regular_web",
            "callbacks": [f"https://{root_domain}/login"],
            "web_origins": [f"https://{root_domain}"],
            "allowed_origins": [f"https://{root_domain}"],
        }
    raise ValueError(f"Unknown app key: {app_key!r}")


def _existing_secret(config: dict, app_key: str) -> str | None:
    """A non-blank auth0_client_secret already present in the target stack.yaml, if any."""
    return config.get(app_key, {}).get("auth0_client_secret") or None


def run_wizard(
    config: dict,
    config_file: str,
    *,
    domain: str,
    m2m_client_id: str,
    m2m_client_secret: str,
    selected_apps: list[str],
    root_domain: str,
    community_name: str,
    admin_email: str,
    gcp_client_id: str | None = None,
    gcp_client_secret: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run the full wizard: provision Auth0, generate secrets, write stack.yaml.

    Parameters
    ----------
    config
        The ruamel-loaded target stack.yaml document (mutated in place, then
        written back to `config_file`).
    config_file
        Path to write the mutated config to.
    selected_apps
        Subset of ("superset-only", "gc-explorer", "gc-landing-page") to
        provision Auth0 clients for.
    gcp_client_id, gcp_client_secret
        Google OAuth credentials for the social connection. If either is
        missing, ensure_google_connection is skipped entirely.
    """
    if dry_run:
        logger.info("DRY RUN: no Auth0 or stack.yaml changes will be made")
        return

    logger.info(f"Authenticating to Auth0 tenant {domain!r}")
    mgmt = get_management_client(domain, m2m_client_id, m2m_client_secret)

    if gcp_client_id and gcp_client_secret:
        logger.info("Provisioning google-oauth2 social connection")
        ensure_google_connection(mgmt, gcp_client_id, gcp_client_secret)
    else:
        logger.info("No GCP OAuth credentials given -- skipping Google social connection")

    logger.info("Ensuring Admin/Member/Guest/SignedIn roles")
    ensure_roles(mgmt)

    client_results: dict[str, ClientResult] = {}
    for app_key in selected_apps:
        spec = _client_spec_for_app(app_key, config, root_domain)
        logger.info(f"Ensuring Auth0 client for {spec['name']}")
        client_results[app_key] = ensure_client(
            mgmt,
            spec["name"],
            spec["app_type"],
            callbacks=spec["callbacks"],
            web_origins=spec["web_origins"],
            allowed_origins=spec["allowed_origins"],
            existing_secret=_existing_secret(config, app_key),
        )

    logger.info("Ensuring GC Metrics M2M client")
    metrics_result = ensure_m2m_client(mgmt, name="GC Metrics")
    if metrics_result.created and metrics_result.client_secret:
        logger.info(
            "GC Metrics M2M client created. There is no stack.yaml field for it -- "
            "note this secret now, it will not be shown again:\n"
            f"    client_id:     {metrics_result.client_id}\n"
            f"    client_secret: {metrics_result.client_secret}\n"
            "See auth0/README.md step 5 for wiring it into Windmill as a resource."
        )

    scope_grants = [
        (client_results.get("gc-explorer"), EXPLORER_SCOPES),
        (client_results.get("gc-landing-page"), LANDING_PAGE_SCOPES),
        (metrics_result, METRICS_SCOPES),
    ]
    for result, scopes in scope_grants:
        if result is None:
            continue
        ensure_management_api_grant(mgmt, domain, result.client_id, scopes)

    logger.info("Ensuring Post-Login Actions (Check Approval, Add Roles Claim)")
    ensure_post_login_actions(mgmt)

    apply_auth0_client_results_to_config(config, domain=domain, client_results=client_results)
    apply_deployment_metadata_to_config(
        config,
        community_name=community_name,
        root_domain=root_domain,
        admin_email=admin_email,
    )

    dump_config(config, config_file)
    logger.info(f"Wrote {config_file}")
