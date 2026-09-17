from gc_stack_deploy.wizard.stack_secrets import build_redis_url, fill_if_blank


class TestFillIfBlank:
    def test_fills_when_blank_string(self):
        cfg = {"pass": ""}
        changed = fill_if_blank(cfg, "pass", generator=lambda: "NEW")
        assert changed is True
        assert cfg["pass"] == "NEW"

    def test_fills_when_none(self):
        cfg = {"pass": None}
        changed = fill_if_blank(cfg, "pass", generator=lambda: "NEW")
        assert changed is True
        assert cfg["pass"] == "NEW"

    def test_leaves_operator_supplied_value_untouched(self):
        cfg = {"pass": "my-real-secret"}
        changed = fill_if_blank(cfg, "pass", generator=lambda: "NEW")
        assert changed is False
        assert cfg["pass"] == "my-real-secret"


class TestBuildRedisUrl:
    def test_default_no_ssl(self):
        assert build_redis_url("secret") == "redis://:secret@srv-captain--redis:6379"

    def test_ssl(self):
        assert build_redis_url("secret", ssl=True) == "rediss://:secret@srv-captain--redis:6379"

    def test_custom_host_port(self):
        assert build_redis_url("secret", host="myhost", port=1234) == "redis://:secret@myhost:1234"
