import json
import tarfile
from pathlib import Path

import pytest
from gen_backup.cli import bundled_template, generate, load_config, old_root


def _config(out: Path) -> dict:
    with tarfile.open(out) as t:
        return json.load(t.extractfile("data/config-captain.json"))


def _meta(out: Path) -> dict:
    with tarfile.open(out) as t:
        return json.load(t.extractfile("meta/backup.json"))


def _env(config: dict, app: str, key: str):
    return next(
        (
            e["value"]
            for e in config["appDefinitions"][app]["envVars"]
            if e["key"] == key
        ),
        None,
    )


def _apps(config: dict) -> set:
    return set(config["appDefinitions"].keys())


def _tar_has_file(out: Path, name: str) -> bool:
    with tarfile.open(out) as t:
        return any(m.isfile() and m.name == name for m in t.getmembers())


def _files_under(out: Path, prefix: str) -> list[str]:
    with tarfile.open(out) as t:
        return [
            m.name for m in t.getmembers() if m.isfile() and m.name.startswith(prefix)
        ]


class TestLoadConfig:
    def test_missing_root_domain_raises(self, tmp_path):
        p = tmp_path / "cfg.yaml"
        p.write_text("caproverPassword: secret\n")
        with pytest.raises(SystemExit):
            load_config(p)

    def test_valid_config_returns_dict(self, tmp_path):
        p = tmp_path / "cfg.yaml"
        p.write_text("rootDomain: acme.example.com\ncaproverPassword: pass\n")
        cfg = load_config(p)
        assert cfg["rootDomain"] == "acme.example.com"
        assert cfg["caproverPassword"] == "pass"


def _run(template_dir, tmp_path, **cfg_overrides) -> tuple[Path, dict]:
    cfg = {"rootDomain": "new.example.com", **cfg_overrides}
    out = tmp_path / "out.tar"
    generate(template_dir, cfg, out)
    return out, _config(out)


class TestDeployBooleanAppFiltering:
    def test_deploy_false_drops_app(self, tmp_path):
        _, cfg = _run(
            bundled_template(), tmp_path, **{"gc-explorer": {"deploy": False}}
        )
        assert "explorer" not in _apps(cfg)

    def test_deploy_false_on_windmill_drops_all_three(self, tmp_path):
        # windmill-only maps to three template apps; need them in the template first
        _, cfg = _run(
            bundled_template(), tmp_path, **{"windmill-only": {"deploy": False}}
        )
        for name in ("windmill", "windmill-worker", "windmill-worker-native"):
            assert name not in _apps(cfg)
        assert "explorer" in _apps(cfg)


class TestDomainSubstitution:
    def test_top_level_custom_domain(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        assert cfg["customDomain"] == "new.example.com"
        assert old_root() not in cfg["customDomain"]

    def test_redirect_domain_updated(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        assert (
            cfg["appDefinitions"]["explorer"]["redirectDomain"]
            == "explorer.new.example.com"
        )

    def test_custom_domain_list_updated(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        cd = cfg["appDefinitions"]["gc-landing-page"]["customDomain"]
        assert cd[0]["publicDomain"] == "new.example.com"

    def test_env_var_url_updated(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        base_url = _env(cfg, "gc-landing-page", "NUXT_PUBLIC_BASE_URL")
        assert "new.example.com" in base_url
        assert old_root() not in base_url


class TestSsl:
    def test_root_ssl_off(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        assert cfg["hasRootSsl"] is False
        assert cfg["forceRootSsl"] is False

    def test_per_app_ssl_off(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        for app in cfg["appDefinitions"].values():
            assert app["hasDefaultSubDomainSsl"] is False
            assert app["forceSsl"] is False

    def test_custom_domain_ssl_off(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        for cd in cfg["appDefinitions"]["gc-landing-page"]["customDomain"]:
            assert cd["hasSsl"] is False


class TestPassword:
    def test_password_from_config(self, tmp_path):
        out = tmp_path / "out.tar"
        password = generate(
            bundled_template(),
            {"rootDomain": "x.com", "caproverPassword": "mypass"},
            out,
        )
        assert password == "mypass"

    def test_random_password_when_absent(self, tmp_path):
        out = tmp_path / "out.tar"
        password = generate(bundled_template(), {"rootDomain": "x.com"}, out)
        assert password  # non-empty
        assert password != "original"

    def test_hashed_password_differs_from_template(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        assert cfg["hashedPassword"] != "$2b$10$original"


class TestSecrets:
    def test_postgres_password_rotated(self, tmp_path):
        _, cfg = _run(bundled_template(), tmp_path)
        assert _env(cfg, "postgres", "POSTGRES_PASSWORD") != "TEMPLATE_PG_PASS"

    def test_pg_password_consistent_across_apps(self, tmp_path):
        """postgres, windmill and explorer must all use the same new pg password."""
        _, cfg = _run(bundled_template(), tmp_path)
        pg_pass = _env(cfg, "postgres", "POSTGRES_PASSWORD")
        windmill_db = _env(cfg, "windmill", "DATABASE_URL")
        assert pg_pass in windmill_db
        assert _env(cfg, "explorer", "NUXT_DB_PASSWORD") == pg_pass

    def test_salt_rotated(self, tmp_path):
        out = tmp_path / "out.tar"
        generate(bundled_template(), {"rootDomain": "x.com"}, out)
        assert _meta(out)["salt"] != "original-salt-uuid"


class TestUserSuppliedValues:
    def test_community_name(self, tmp_path):
        _, cfg = _run(
            bundled_template(),
            tmp_path,
            **{
                "gc-landing-page": {"community_name": "springfield"},
            },
        )
        assert (
            _env(cfg, "gc-landing-page", "NUXT_PUBLIC_COMMUNITY_NAME") == "springfield"
        )

    def test_auth0_creds_on_superset(self, tmp_path):
        _, cfg = _run(
            bundled_template(),
            tmp_path,
            **{
                "superset-only": {
                    "auth0_domain": "my.auth0.com",
                    "auth0_client_id": "client-id-123",
                    "auth0_client_secret": "secret-abc",
                },
            },
        )
        assert _env(cfg, "superset", "AUTH0_DOMAIN") == "my.auth0.com"
        assert _env(cfg, "superset", "AUTH0_CLIENTID") == "client-id-123"
        assert _env(cfg, "superset", "AUTH0_CLIENT_SECRET") == "secret-abc"

    def test_empty_config_value_not_written(self, tmp_path):
        """A blank auth0_domain in config must not overwrite the template value."""
        _, cfg = _run(
            bundled_template(),
            tmp_path,
            **{
                "superset-only": {"auth0_domain": ""},
            },
        )
        # Template had "example.auth0.example.com" already; it should stay ""
        assert _env(cfg, "superset", "AUTH0_DOMAIN") == "example.auth0.example.com"

    def test_email_address_override(self, tmp_path):
        _, cfg = _run(
            bundled_template(), tmp_path, emailAddress="admin@new.example.com"
        )
        assert cfg["emailAddress"] == "admin@new.example.com"

    def test_email_address_unchanged_when_absent(self, tmp_path):
        """FIXME: should email be required? especially since we don't enable SSL?"""
        _, cfg = _run(bundled_template(), tmp_path)
        assert cfg["emailAddress"] == "guardian@example.net"

    def test_feature_flag_false(self, tmp_path):
        _, cfg = _run(
            bundled_template(),
            tmp_path,
            **{
                "gc-landing-page": {"superset_enabled": False},
            },
        )
        assert _env(cfg, "gc-landing-page", "NUXT_PUBLIC_SUPERSET_ENABLED") == "False"

    def test_feature_flag_not_written_when_absent(self, tmp_path):
        """If the flag isn't in the config, the template's existing value is kept."""
        _, cfg = _run(
            bundled_template(), tmp_path, **{"gc-landing-page": {"NOT_A_REAL_NAME": 1}}
        )
        # Template didn't include NUXT_PUBLIC_SUPERSET_ENABLED, so it shouldn't appear
        val = _env(cfg, "gc-landing-page", "NOT_A_REAL_NAME")
        assert val is None


class TestTarContents:
    def test_config_override_json_present(self, tmp_path):
        out, _ = _run(bundled_template(), tmp_path)
        assert _tar_has_file(out, "data/config-override.json")

    def test_config_override_json_content(self, tmp_path):
        out, _ = _run(bundled_template(), tmp_path)
        with tarfile.open(out) as t:
            data = json.load(t.extractfile("data/config-override.json"))
        assert data == {"skipVerifyingDomains": "true"}

    def test_letsencrypt_dirs_empty(self, tmp_path):
        out, _ = _run(bundled_template(), tmp_path)
        for subdir in ("accounts", "archive", "live", "renewal"):
            files = _files_under(out, f"data/letencrypt/etc/{subdir}/")
            assert files == [], f"expected {subdir}/ to be empty, got {files}"
