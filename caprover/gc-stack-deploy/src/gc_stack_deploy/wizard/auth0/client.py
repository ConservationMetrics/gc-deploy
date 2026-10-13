"""Thin helpers for talking to the Auth0 Management API.

Uses the 6.x auth0-python surface: real kwargs on `.create()`/`.update()`,
pydantic response models (attribute access, not dict access), and `.list()`
returning an auto-paginating, directly-iterable `SyncPager`.

Example:
    access_token = get_m2m_access_token(domain, client_id, client_secret)
    mgmt = get_management_client(domain, access_token)
    existing = find_by_name(mgmt.clients.list(), "Superset")
    if existing:
        mgmt.clients.update(existing.client_id, callbacks=[...])
    else:
        mgmt.clients.create(name="Superset", app_type="regular_web")
"""

from auth0.authentication import GetToken
from auth0.management import Auth0


def get_m2m_access_token(domain: str, client_id: str, client_secret: str) -> str:
    """Exchange an M2M application's credentials for a Management API access token."""
    token_response = GetToken(
        domain, client_id, client_secret=client_secret
    ).client_credentials(f"https://{domain}/api/v2/")
    return token_response["access_token"]


def get_management_client(domain: str, access_token: str) -> Auth0:
    """Return a ready Management API client that authenticates with `access_token`."""
    # The SDK retries 429s itself (honoring Retry-After / x-ratelimit-reset); default is 2.
    return Auth0(tenant_domain=domain, token=access_token, max_retries=3)


def find_by_name(items, name: str, key: str = "name"):
    """Return the first item whose `key` attribute equals `name`, or None."""
    # `mgmt.clients.list()` returns an auto-paginating `SyncPager` that is directly iterable.
    for item in items:
        if getattr(item, key, None) == name:
            return item
    return None
