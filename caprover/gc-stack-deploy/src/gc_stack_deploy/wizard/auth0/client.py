"""Thin helpers for talking to the Auth0 Management API.

Uses the 6.x auth0-python surface: real kwargs on `.create()`/`.update()`,
pydantic response models (attribute access, not dict access), and `.list()`
returning an auto-paginating, directly-iterable `SyncPager`.

Example:
    mgmt = get_management_client(domain, m2m_client_id, m2m_client_secret)
    existing = find_by_name(mgmt.clients.list(), "Superset")
    if existing:
        mgmt.clients.update(existing.client_id, callbacks=[...])
    else:
        mgmt.clients.create(name="Superset", app_type="regular_web")
"""

from auth0.authentication import GetToken
from auth0.management import Auth0


def get_management_client(
    domain: str, m2m_client_id: str, m2m_client_secret: str
) -> Auth0:
    """Authenticate the bootstrap M2M application and return a ready Management API client."""
    token_response = GetToken(
        domain, m2m_client_id, client_secret=m2m_client_secret
    ).client_credentials(f"https://{domain}/api/v2/")
    return Auth0(tenant_domain=domain, token=token_response["access_token"])


def find_by_name(items, name: str, key: str = "name"):
    """Return the first item whose `key` attribute equals `name`, or None."""
    # `mgmt.clients.list()` returns an auto-paginating `SyncPager` that is directly iterable.
    for item in items:
        if getattr(item, key, None) == name:
            return item
    return None
