import pytest
from ruamel.yaml import YAML

from gc_stack_deploy.apps_registry import disable_healthcheck, set_yaml_value


def load_yaml(s):
    return YAML().load(s)


class TestSetYamlValue:
    def test_creates_nested_keys_from_scratch(self):
        result = set_yaml_value(None, "A.B.C", 42)
        assert load_yaml(result) == {"A": {"B": {"C": 42}}}

    def test_sets_value_in_existing_document(self):
        existing = (
            "A:\n"
            "  B:\n"
            "    C: 1\n"
        )
        result = set_yaml_value(existing, "A.B.C", 99)
        assert load_yaml(result)["A"]["B"]["C"] == 99

    def test_preserves_sibling_keys(self):
        existing = (
            "A:\n"
            "  X: kept\n"
            "  B:\n"
            "    C: 1\n"
        )
        result = set_yaml_value(existing, "A.B.C", 2)
        data = load_yaml(result)
        assert data["A"]["X"] == "kept"
        assert data["A"]["B"]["C"] == 2

    def test_accepts_list_key(self):
        result = set_yaml_value(None, ["A", "B"], "v")
        assert load_yaml(result) == {"A": {"B": "v"}}

    def test_empty_string_treated_as_empty(self):
        result = set_yaml_value("", "K", "v")
        assert load_yaml(result) == {"K": "v"}

    def test_list_value(self):
        result = set_yaml_value(None, "A.B", ["NONE"])
        assert load_yaml(result) == {"A": {"B": ["NONE"]}}


class TestDisableHealthcheck:
    HEALTHCHECK_ONLY = (
        "TaskTemplate:\n"
        "  ContainerSpec:\n"
        "    HealthCheck:\n"
        "      Test:\n"
        "      - NONE\n"
    )

    def test_none_input(self):
        assert disable_healthcheck(None) == self.HEALTHCHECK_ONLY

    def test_empty_string_input(self):
        assert disable_healthcheck("") == self.HEALTHCHECK_ONLY

    def test_disables_on_existing_suo(self):
        existing = "TaskTemplate:\n  Resources:\n    Limits:\n      MemoryBytes: 1024\n"
        expected = (
            "TaskTemplate:\n"
            "  Resources:\n"
            "    Limits:\n"
            "      MemoryBytes: 1024\n"
            "  ContainerSpec:\n"
            "    HealthCheck:\n"
            "      Test:\n"
            "      - NONE\n"
        )
        assert disable_healthcheck(existing) == expected
