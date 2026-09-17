import importlib.resources

from gc_stack_deploy.wizard.auth0.provisioning import ClientResult
from gc_stack_deploy.wizard.yaml_writer import apply_auth0_results_to_config, load_config
from ruamel.yaml import YAML


def load_example_config():
    example = importlib.resources.files("gc_stack_deploy.example_configs") / "stack.example.yaml"
    with importlib.resources.as_file(example) as path:
        return load_config(path)


def dump_to_dict(config):
    """Round-trip through YAML() dump+load to get a plain-ish structure back."""
    import io

    buf = io.StringIO()
    YAML().dump(config, buf)
    return YAML().load(buf.getvalue())


class TestApplyAuth0ResultsToConfig:
    def test_domain_and_community_name_identical_across_aliased_sites(self):
        config = load_example_config()
        client_results = {
            "superset-only": ClientResult("id-superset", "secret-superset", True),
            "gc-landing-page": ClientResult("id-landing", "secret-landing", True),
            "gc-explorer": ClientResult("id-explorer", "secret-explorer", True),
        }
        apply_auth0_results_to_config(
            config,
            domain="example.us.auth0.com",
            community_name="springfield",
            client_results=client_results,
            root_domain="springfield.example.net",
            admin_email="admin@example.net",
        )

        assert config["auth0_domain"] == "example.us.auth0.com"
        for app in ("superset-only", "gc-landing-page", "gc-explorer"):
            assert config[app]["auth0_domain"] == "example.us.auth0.com"

        assert config["community_name"] == "springfield"
        for app in ("gc-landing-page", "gc-explorer"):
            assert config[app]["community_name"] == "springfield"

        # Also survives a re-dump/re-load round trip.
        reloaded = dump_to_dict(config)
        assert reloaded["auth0_domain"] == "example.us.auth0.com"
        assert reloaded["superset-only"]["auth0_domain"] == "example.us.auth0.com"
        assert reloaded["gc-landing-page"]["auth0_domain"] == "example.us.auth0.com"
        assert reloaded["gc-explorer"]["auth0_domain"] == "example.us.auth0.com"

    def test_writes_client_id_and_secret_per_app(self):
        config = load_example_config()
        client_results = {"superset-only": ClientResult("cid", "csecret", True)}
        apply_auth0_results_to_config(
            config,
            domain="d",
            community_name="c",
            client_results=client_results,
        )
        assert config["superset-only"]["auth0_client_id"] == "cid"
        assert config["superset-only"]["auth0_client_secret"] == "csecret"

    def test_skips_secret_write_when_none(self):
        config = load_example_config()
        config["superset-only"]["auth0_client_secret"] = "preexisting"
        client_results = {"superset-only": ClientResult("cid", None, False)}
        apply_auth0_results_to_config(
            config,
            domain="d",
            community_name="c",
            client_results=client_results,
        )
        assert config["superset-only"]["auth0_client_id"] == "cid"
        assert config["superset-only"]["auth0_client_secret"] == "preexisting"

    def test_root_domain_and_admin_email(self):
        config = load_example_config()
        apply_auth0_results_to_config(
            config,
            domain="d",
            community_name="c",
            client_results={},
            root_domain="root.example.net",
            admin_email="admin@example.net",
        )
        assert config["gc-landing-page"]["root_domain"] == "root.example.net"
        assert config["superset-only"]["admin_email"] == "admin@example.net"
