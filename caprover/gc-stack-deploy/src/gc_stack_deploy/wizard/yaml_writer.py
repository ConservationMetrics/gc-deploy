"""Anchor-safe mutation of the loaded ruamel config, and writing it back out.

`stack.example.yaml` uses YAML anchors/aliases (`&auth0_domain`, `&community_name`)
so one value can be shared across several app blocks. ruamel only preserves that
sharing when the *same object* is assigned at every position -- assigning a fresh
string to just `config["auth0_domain"]` leaves the aliased sites (already-loaded,
independent objects) untouched. So every function here computes each shared value
once and assigns that exact object everywhere it belongs.
"""

from ruamel.yaml import YAML

from .auth0.provisioning import ClientResult


def load_config(file_path):
    """Load a stack.yaml in round-trip mode (preserves comments/formatting)."""
    ryaml = YAML()
    ryaml.preserve_quotes = True
    with open(file_path, "r") as f:
        return ryaml.load(f)


# Apps that carry an `auth0_domain` field aliased to the shared top-level value.
AUTH0_DOMAIN_APPS = ("superset-only", "gc-landing-page", "gc-explorer")
# Apps that carry a `community_name` field aliased to the shared top-level value.
COMMUNITY_NAME_APPS = ("gc-landing-page", "gc-explorer")


def apply_auth0_results_to_config(
    config,
    *,
    domain: str,
    community_name: str,
    client_results: dict[str, ClientResult],
    root_domain: str | None = None,
    admin_email: str | None = None,
) -> None:
    """Mutate the loaded config in place with Auth0 provisioning results.

    Parameters
    ----------
    config
        The ruamel-loaded target stack.yaml document.
    domain
        Auth0 tenant domain, written to `auth0_domain` everywhere it's aliased.
    community_name
        Written to `community_name` everywhere it's aliased.
    client_results
        Maps one_click_app_name (e.g. "superset-only") -> ClientResult, for
        whichever apps were selected. Apps not selected are left untouched.
    root_domain, admin_email
        Deployment-inputs screen values, written to gc-landing-page.root_domain
        and superset-only.admin_email respectively, if those apps are present.
    """
    config["auth0_domain"] = domain
    for app in AUTH0_DOMAIN_APPS:
        if app in config:
            config[app]["auth0_domain"] = domain

    config["community_name"] = community_name
    for app in COMMUNITY_NAME_APPS:
        if app in config:
            config[app]["community_name"] = community_name

    for app, result in client_results.items():
        if app not in config:
            continue
        config[app]["auth0_client_id"] = result.client_id
        if result.client_secret is not None:
            config[app]["auth0_client_secret"] = result.client_secret

    if root_domain is not None and "gc-landing-page" in config:
        config["gc-landing-page"]["root_domain"] = root_domain
    if admin_email is not None and "superset-only" in config:
        config["superset-only"]["admin_email"] = admin_email


def dump_config(config, file_path) -> None:
    """Write the mutated config back out, same YAML()/.dump() pattern as apps_registry.py."""
    ryaml = YAML()
    ryaml.preserve_quotes = True
    with open(file_path, "w") as f:
        ryaml.dump(config, f)
