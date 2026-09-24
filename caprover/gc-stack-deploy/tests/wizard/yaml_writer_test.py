import importlib.resources
import io

from gc_stack_deploy.wizard.auth0.provisioning import ClientResult
from gc_stack_deploy.wizard.yaml_writer import (
    apply_auth0_client_results_to_config,
    apply_root_domain_to_config,
    load_config,
)
from ruamel.yaml import YAML


def load_example_config():
    example = (
        importlib.resources.files("gc_stack_deploy.example_configs")
        / "stack.example.yaml"
    )
    with importlib.resources.as_file(example) as path:
        return load_config(path)


def dump_to_dict(config):
    """Round-trip through YAML() dump+load to get a plain-ish structure back."""
    buf = io.StringIO()
    YAML().dump(config, buf)
    return YAML().load(buf.getvalue())


class TestApplyAuth0ClientResultsToConfig:
    def test_domain_identical_across_aliased_sites(self):
        config = load_example_config()
        client_results = {
            "superset-only": ClientResult("id-superset", "secret-superset", True),
            "gc-landing-page": ClientResult("id-landing", "secret-landing", True),
            "gc-explorer": ClientResult("id-explorer", "secret-explorer", True),
        }
        apply_auth0_client_results_to_config(
            config,
            domain="example.us.auth0.com",
            client_results=client_results,
        )

        assert config["auth0_domain"] == "example.us.auth0.com"
        for app in ("superset-only", "gc-landing-page", "gc-explorer"):
            assert config[app]["auth0_domain"] == "example.us.auth0.com"

        # Also survives a re-dump/re-load round trip.
        reloaded = dump_to_dict(config)
        assert reloaded["auth0_domain"] == "example.us.auth0.com"
        assert reloaded["superset-only"]["auth0_domain"] == "example.us.auth0.com"
        assert reloaded["gc-landing-page"]["auth0_domain"] == "example.us.auth0.com"
        assert reloaded["gc-explorer"]["auth0_domain"] == "example.us.auth0.com"

    def test_dumps_as_real_yaml_anchors_not_duplicated_literals(self):
        """Regression test for the anchor/alias gotcha: writing the same plain
        str to every site fixes the values but silently degrades the YAML into
        duplicated literals. Assert the dump keeps `&anchor`/`*alias` syntax."""
        config = load_example_config()
        apply_auth0_client_results_to_config(
            config,
            domain="example.us.auth0.com",
            client_results={},
        )

        buf = io.StringIO()
        YAML().dump(config, buf)
        dumped = buf.getvalue()

        assert "&auth0_domain example.us.auth0.com" in dumped
        assert (
            dumped.count("*auth0_domain") == 3
        )  # superset-only, gc-landing-page, gc-explorer

    def test_writes_client_id_and_secret_per_app(self):
        config = load_example_config()
        client_results = {"superset-only": ClientResult("cid", "csecret", True)}
        apply_auth0_client_results_to_config(
            config,
            domain="d",
            client_results=client_results,
        )
        assert config["superset-only"]["auth0_client_id"] == "cid"
        assert config["superset-only"]["auth0_client_secret"] == "csecret"

    def test_skips_secret_write_when_none(self):
        config = load_example_config()
        config["superset-only"]["auth0_client_secret"] = "preexisting"
        client_results = {"superset-only": ClientResult("cid", None, False)}
        apply_auth0_client_results_to_config(
            config,
            domain="d",
            client_results=client_results,
        )
        assert config["superset-only"]["auth0_client_id"] == "cid"
        assert config["superset-only"]["auth0_client_secret"] == "preexisting"


class TestApplyRootDomainToConfig:
    def test_writes_landing_page_root_domain(self):
        config = load_example_config()
        apply_root_domain_to_config(config, "springfield.guardianconnector.net")
        assert (
            dump_to_dict(config)["gc-landing-page"]["root_domain"]
            == "springfield.guardianconnector.net"
        )

    def test_skips_when_landing_page_absent(self):
        config = load_example_config()
        del config["gc-landing-page"]
        apply_root_domain_to_config(config, "springfield.guardianconnector.net")
        assert "gc-landing-page" not in config
