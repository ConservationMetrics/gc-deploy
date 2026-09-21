"""Anchor-safe mutation of the loaded ruamel config, and writing it back out.

`stack.example.yaml` uses YAML anchors/aliases (`&auth0_domain`, `&community_name`)
so one value can be shared across several app blocks. ruamel only preserves that
sharing when the *same object* is assigned at every position -- assigning a fresh
plain string to just `config["auth0_domain"]` leaves the aliased sites
(already-loaded, independent objects) untouched, and even assigning that same
plain string everywhere only fixes the *values*, not the `&anchor`/`*alias`
syntax on re-dump (ruamel's round-trip representer only re-emits an anchor for
objects it recognizes as anchor-carrying, which a bare `str` is not). So the
shared value is wrapped in `PlainScalarString` with an explicit anchor name via
`yaml_set_anchor()`, and that exact object is assigned everywhere it belongs --
this keeps the output as real YAML anchors/aliases, not four duplicated literals.
"""

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString

from .auth0.provisioning import ClientResult
from .stack_secrets import build_redis_url, fill_if_blank


def load_config(file_path):
    """Load a stack.yaml in round-trip mode (preserves comments/formatting)."""
    ryaml = YAML()
    ryaml.preserve_quotes = True
    with open(file_path, "r") as f:
        return ryaml.load(f)


def _anchored(value: str, anchor_name: str) -> PlainScalarString:
    """A scalar string that dumps as `&anchor_name value`, so every alias
    site assigned this same object re-serializes as `*anchor_name`."""
    s = PlainScalarString(value)
    s.yaml_set_anchor(anchor_name)
    return s


# Apps that carry an `auth0_domain` field aliased to the shared top-level value.
AUTH0_DOMAIN_APPS = ("superset-only", "gc-landing-page", "gc-explorer")
# Apps that carry a `community_name` field aliased to the shared top-level value.
COMMUNITY_NAME_APPS = ("gc-landing-page", "gc-explorer")


def apply_auth0_client_results_to_config(
    config,
    *,
    domain: str,
    client_results: dict[str, ClientResult],
) -> None:
    """Mutate the loaded config in place with genuine Auth0 provisioning results:
    the tenant domain and each selected app's client id/secret.

    Deployment metadata that merely rides along on the same wizard screen
    (community_name, root_domain, admin_email) is NOT handled here -- see
    `apply_deployment_metadata_to_config` -- since none of it is actually an
    Auth0 API concept: it's never sent to the Management API, just written
    into plain (non `auth0_*`) stack.yaml fields.

    Parameters
    ----------
    config
        The ruamel-loaded target stack.yaml document.
    domain
        Auth0 tenant domain, written to `auth0_domain` everywhere it's aliased.
    client_results
        Maps one_click_app_name (e.g. "superset-only") -> ClientResult, for
        whichever apps were selected. Apps not selected are left untouched.
    """
    domain_value = _anchored(domain, "auth0_domain")
    config["auth0_domain"] = domain_value
    for app in AUTH0_DOMAIN_APPS:
        if app in config:
            config[app]["auth0_domain"] = domain_value

    for app, result in client_results.items():
        if app not in config:
            continue
        config[app]["auth0_client_id"] = result.client_id
        if result.client_secret is not None:
            config[app]["auth0_client_secret"] = result.client_secret


def apply_deployment_metadata_to_config(
    config,
    *,
    community_name: str,
    root_domain: str | None = None,
    admin_email: str | None = None,
) -> None:
    """Mutate the loaded config in place with deployment-inputs-screen values
    that aren't Auth0 API results -- they're written straight into plain
    (non `auth0_*`) stack.yaml fields, and the wizard just happens to collect
    them on the same screen as the Auth0-relevant inputs for convenience.

    Parameters
    ----------
    community_name
        Written to `community_name` everywhere it's aliased.
    root_domain, admin_email
        Written to gc-landing-page.root_domain and superset-only.admin_email
        respectively, if those apps are present.
    """
    community_name_value = _anchored(community_name, "community_name")
    config["community_name"] = community_name_value
    for app in COMMUNITY_NAME_APPS:
        if app in config:
            config[app]["community_name"] = community_name_value

    if root_domain is not None and "gc-landing-page" in config:
        config["gc-landing-page"]["root_domain"] = root_domain
    if admin_email is not None and "superset-only" in config:
        config["superset-only"]["admin_email"] = admin_email


def apply_secrets_to_config(config) -> None:
    """Fill in blank Postgres/Redis/Filebrowser secrets.

    Only touches blocks that are already present in the loaded config.
    """
    if "postgres" in config:
        fill_if_blank(config["postgres"], "pass")

    if "redis" in config:
        password_changed = fill_if_blank(config["redis"], "redis_password")
        # If the password wasn't touched, an operator-pointed-at-external-Redis
        # redis_url is already consistent with it by construction -- skip.
        if password_changed and "superset-only" in config:
            config["superset-only"]["redis_url"] = build_redis_url(
                config["redis"]["redis_password"]
            )

    if "filebrowser" in config:
        fill_if_blank(config["filebrowser"], "admin_password")


def dump_config(config, file_path) -> None:
    """Write the mutated config back out, same YAML()/.dump() pattern as apps_registry.py."""
    ryaml = YAML()
    ryaml.preserve_quotes = True
    with open(file_path, "w") as f:
        ryaml.dump(config, f)
