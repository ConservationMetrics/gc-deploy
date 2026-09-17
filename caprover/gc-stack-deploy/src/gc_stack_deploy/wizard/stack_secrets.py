"""Auto-generation of the non-Auth0 secrets otherwise typed by hand into
stack.yaml (Postgres/Redis/Filebrowser passwords).

stack.example.yaml ships these fields blank (like auth0_domain, root_domain,
etc.), so "fill-worthy" just means blank -- no placeholder literals to keep
in sync with the example.
"""

import secrets


def generate_secret(length: int = 16) -> str:
    """Generate a random secret, using the same primitive FilebrowserApp already does."""
    return secrets.token_urlsafe(length)


def fill_if_blank(cfg, key: str, generator=generate_secret) -> bool:
    """Fill cfg[key] with a freshly generated secret if it's blank.

    Leaves any operator-supplied value untouched. Returns True if the value
    was (re)generated, False if left as-is.
    """
    current = cfg.get(key)
    if current is None or current == "":
        cfg[key] = generator()
        return True
    return False


def build_redis_url(password: str, host: str = "srv-captain--redis", port: int = 6379, ssl: bool = False) -> str:
    scheme = "rediss" if ssl else "redis"
    return f"{scheme}://:{password}@{host}:{port}"
