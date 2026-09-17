"""Thin helpers for talking to the Auth0 Management API.

Pinned to the classic (pre-5.0) auth0-python surface: `Auth0(domain,
token)`, and per-resource `.all()`/`.create()`/`.update()` methods that take and
return plain dicts.
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
    return Auth0(domain, token_response["access_token"])


def list_all(
    resource_client, list_method="all", items_key=None, **params
) -> list[dict]:
    """Page through a Management API collection, returning every item.

    Not every Management API collection supports server-side name search, so
    callers list everything and match client-side via `find_by_name`.

    Parameters
    ----------
    resource_client
        e.g. `mgmt.clients`, `mgmt.connections`.
    list_method
        Name of the listing method to call (e.g. "all", "list").
    items_key
        If the listing method returns a dict (paginated response) rather than
        a bare list, the key holding the item list (e.g. "roles").
    **params
        Extra keyword arguments passed to the listing method.
    """
    items = []
    page = 0
    per_page = 100
    method = getattr(resource_client, list_method)
    while True:
        result = method(page=page, per_page=per_page, **params)
        batch = result[items_key] if items_key is not None else result
        items.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return items


def find_by_name(items: list[dict], name: str, key: str = "name") -> dict | None:
    """Return the first item whose `key` field equals `name`, or None."""
    for item in items:
        if item.get(key) == name:
            return item
    return None
