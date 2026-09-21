"""Anchor-safe mutation of the loaded ruamel config, and writing it back out.

Config-mutation can be done in two separate functions:
- apply_auth0_client_results_to_config() writes Auth0 API results (auth0_domain, per-app client id/secret)
- apply_deployment_metadata_to_config() writes community_name/root_domain/admin_email
"""

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString

from .auth0.provisioning import ClientResult


def load_config(file_path):
    """Load a stack.yaml in round-trip mode (preserves comments/formatting)."""
    ryaml = YAML()
    ryaml.preserve_quotes = True
    with open(file_path, "r") as f:
        return ryaml.load(f)


def _anchored(value: str, anchor_name: str) -> PlainScalarString:
    """A scalar string that dumps as `&anchor_name value`, so every alias
    site assigned this same object re-serializes as `*anchor_name`.

    ruamel only preserves a shared anchor/alias if the *same object* is
    assigned at every aliased position: assigning a fresh (or even
    equal-valued) plain `str` to each site instead sets the values but drops
    the `&anchor`/`*alias` syntax on re-dump, since ruamel's round-trip
    representer can't attach an anchor to a bare `str`. Wrapping the value in
    `PlainScalarString` and anchoring it here, then assigning that one object
    everywhere it belongs, keeps the sharing intact.
    """
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


def dump_config(config, file_path) -> None:
    """Write the mutated config back out

    DRY: This is the same YAML()/.dump() pattern as apps_registry.py.
    """
    ryaml = YAML()
    ryaml.preserve_quotes = True
    with open(file_path, "w") as f:
        ryaml.dump(config, f)
