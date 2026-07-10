"""Generate a CapRover restore tar from a template backup.

Takes an existing backup tar, applies a YAML config (root domain, user-supplied
credentials, deploy flags), rotates all auto-generated secrets, turns SSL off,
and writes a new tar ready to drop at /captain/backup.tar on a fresh CapRover.
"""

import argparse
import json
import secrets
import shutil
import tarfile
import tempfile
import uuid
from importlib import resources
from pathlib import Path
from typing import Any

import bcrypt
import yaml

OLD_ROOT = "cmistaging.guardianconnector.net"


def bundled_template() -> Path:
    """Path to the reference backup shipped inside this package.

    Resolves whether gen-backup was pip-installed or run from a source checkout,
    so callers don't need the repo on disk.
    """
    return Path(resources.files("gen_backup") / "template")


# Maps YAML config section names → app names in the template backup
# fmt:off
YAML_TO_APPS: dict[str, list[str]] = {
    "postgres":       ["postgres"],
    "redis":          ["redis"],
    "windmill-only":  ["windmill", "windmill-worker", "windmill-worker-native"],
    "superset-only":  ["superset"],
    "gc-landing-page":["gc-landing-page"],
    "gc-explorer":    ["explorer"],
    "comapeo-cloud":  ["comapeo"],
    "filebrowser":    ["files"],
    "nocodb":         ["nocodb"],
}
# fmt:on


def _rand(n: int = 16) -> str:
    return secrets.token_hex(n)


def _set_env(envvars: list, key: str, value: str) -> None:
    for e in envvars:
        if e["key"] == key:
            e["value"] = value
            return
    envvars.append({"key": key, "value": value})


def _deployed_image(app_def: dict) -> str:
    version = app_def.get("deployedVersion", 0)
    for v in app_def.get("versions", []):
        if v.get("version") == version:
            return v.get("deployedImageName") or ""
    return ""


def _is_local_image(image: str) -> bool:
    return not image or image.startswith("img-captain-")


def _config_section(cfg: dict, key: str) -> dict:
    """Return a section of the YAML config, defaulting to {} (i.e. deploy: true) if absent."""
    return cfg.get(key) or {}


def _config_str(section: dict, key: str) -> str:
    """Read a string field from a YAML config section, or '' if missing/blank."""
    v = section.get(key)
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        raise TypeError(
            f"YAML config field {key!r} expects a string but got a boolean ({v}); "
            f"quote it in the config if you meant a literal string"
        )
    return str(v)


def _config_bool(section: dict, key: str) -> str:
    """Read a boolean flag from a YAML config section as the string 'True'/'False'.

    Returns a string, not a bool, because CapRover env-var values are always strings.
    """
    v = section.get(key)
    if isinstance(v, bool):
        return "True" if v else "False"
    return "True" if str(v).lower() in ("true", "1", "yes") else "False"


def load_config(path: Path) -> dict[str, Any]:
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    if not cfg.get("rootDomain"):
        raise SystemExit("Error: config must include a non-empty 'rootDomain'")
    return cfg


def generate(template_dir: Path, cfg: dict, out_tar: Path) -> str:
    """Build the new backup tar and return the plaintext CapRover password."""
    root_domain: str = cfg["rootDomain"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # 1. Copy template tree
        shutil.copytree(template_dir, tmp, dirs_exist_ok=True)

        data_dir = tmp / "data"
        meta_dir = tmp / "meta"
        config_path = data_dir / "config-captain.json"
        meta_path = meta_dir / "backup.json"

        with open(config_path) as f:
            config = json.load(f)
        with open(meta_path) as f:
            meta = json.load(f)

        # 2. New salt + password
        new_salt = str(uuid.uuid4())
        password = cfg.get("caproverPassword") or secrets.token_urlsafe(16)[:21]
        # CapRover: hash = bcrypt(salt + namespace + password)
        hashed = bcrypt.hashpw(
            (new_salt + "captain" + password).encode(), bcrypt.gensalt(rounds=10)
        ).decode()

        # 3. Drop apps with locally-built images (non-pullable)
        apps = config["appDefinitions"]
        to_drop = [n for n, a in apps.items() if _is_local_image(_deployed_image(a))]
        for name in to_drop:
            print(f"  dropping {name} (local image)")
            del apps[name]

        # 4. Drop apps explicitly disabled in config
        for yaml_key, app_names in YAML_TO_APPS.items():
            if _config_section(cfg, yaml_key).get("deploy") is False:
                for name in app_names:
                    if name in apps:
                        print(f"  dropping {name} (deploy: false)")
                        del apps[name]

        # 5. Values reused across apps — config value if provided, else auto-generated.
        #    Per-app one-off secrets are generated inline below, at their point of use.
        # fmt:off
        pg_cfg       = _config_section(cfg, "postgres")
        redis_cfg    = _config_section(cfg, "redis")
        superset_cfg = _config_section(cfg, "superset-only")
        lp_cfg       = _config_section(cfg, "gc-landing-page")
        explorer_cfg = _config_section(cfg, "gc-explorer")

        pg_pass    = _config_str(pg_cfg,    "pass")           or _rand()
        pg_user    = _config_str(pg_cfg,    "user")           or "postgres"
        pg_db      = _config_str(pg_cfg,    "database")       or "postgres"
        redis_pass = _config_str(redis_cfg, "redis_password") or _rand()

        pg_host    = "srv-captain--postgres"
        redis_host = "srv-captain--redis"
        pg_url_base = f"postgres://{pg_user}:{pg_pass}@{pg_host}:5432"
        # fmt:on

        for name, app in apps.items():
            ev = app.get("envVars", [])

            if name == "postgres":
                _set_env(ev, "POSTGRES_PASSWORD", pg_pass)
                _set_env(ev, "POSTGRES_USER", pg_user)
                _set_env(ev, "POSTGRES_DB", pg_db)

            elif name in ("windmill", "windmill-worker", "windmill-worker-native"):
                _set_env(ev, "DATABASE_URL", f"{pg_url_base}/windmill")

            elif name == "redis":
                _set_env(ev, "REDIS_PASSWORD", redis_pass)

            elif name == "superset":
                # fmt:off
                _set_env(ev, "SECRET_KEY",    _rand())
                _set_env(ev, "REDIS_URL",     f"redis://:{redis_pass}@{redis_host}:6379")
                _set_env(ev, "DATABASE_URI",
                         f"postgresql://{pg_user}:{pg_pass}@{pg_host}:5432/superset_metastore")
                for cfg_key, env_key in [
                    ("admin_email",        "ADMIN_EMAIL"),
                    ("auth0_domain",       "AUTH0_DOMAIN"),
                    ("auth0_client_id",    "AUTH0_CLIENTID"),
                    ("auth0_client_secret","AUTH0_CLIENT_SECRET"),
                    ("mapbox_api_key",     "MAPBOX_API_KEY"),
                    ("app_icon",           "APP_ICON"),
                    ("app_title",          "APP_NAME"),
                ]:
                    if v := _config_str(superset_cfg, cfg_key):
                        _set_env(ev, env_key, v)
                # fmt:on

            elif name == "gc-landing-page":
                _set_env(ev, "NUXT_SESSION_PASSWORD", _rand())
                # fmt:off
                for cfg_key, env_key in [
                    ("community_name",      "NUXT_PUBLIC_COMMUNITY_NAME"),
                    ("auth0_domain",        "NUXT_OAUTH_AUTH0_DOMAIN"),
                    ("auth0_client_id",     "NUXT_OAUTH_AUTH0_CLIENT_ID"),
                    ("auth0_client_secret", "NUXT_OAUTH_AUTH0_CLIENT_SECRET"),
                    ("logo_url",            "NUXT_PUBLIC_LOGO_URL"),
                ]:
                    if v := _config_str(lp_cfg, cfg_key):
                        _set_env(ev, env_key, v)
                # fmt:on

                # Boolean feature flags — write only when explicitly set in config
                for cfg_key, env_key in [
                    ("superset_enabled", "NUXT_PUBLIC_SUPERSET_ENABLED"),
                    ("filebrowser_enabled", "NUXT_PUBLIC_FILEBROWSER_ENABLED"),
                    ("windmill_enabled", "NUXT_PUBLIC_WINDMILL_ENABLED"),
                    ("explorer_enabled", "NUXT_PUBLIC_EXPLORER_ENABLED"),
                ]:
                    if cfg_key in lp_cfg:
                        _set_env(ev, env_key, _config_bool(lp_cfg, cfg_key))

            elif name == "explorer":
                _set_env(ev, "NUXT_DB_PASSWORD", pg_pass)
                _set_env(ev, "NUXT_PUBLIC_APP_API_KEY", _rand())
                _set_env(ev, "NUXT_SESSION_PASSWORD", _rand())
                # fmt:off
                for cfg_key, env_key in [
                    ("postgres_database",   "NUXT_DATABASE"),
                    ("auth0_domain",        "NUXT_OAUTH_AUTH0_DOMAIN"),
                    ("auth0_client_id",     "NUXT_OAUTH_AUTH0_CLIENT_ID"),
                    ("auth0_client_secret", "NUXT_OAUTH_AUTH0_CLIENT_SECRET"),
                ]:
                    if v := _config_str(explorer_cfg, cfg_key):
                        _set_env(ev, env_key, v)
                # fmt:on

            elif name == "comapeo":
                _set_env(ev, "SERVER_BEARER_TOKEN", _rand())

            elif name == "nocodb":
                _set_env(
                    ev,
                    "NC_DB_JSON",
                    json.dumps(
                        {
                            "client": "pg",
                            "connection": {
                                "host": pg_host,
                                "port": 5432,
                                "user": pg_user,
                                "password": pg_pass,
                                "database": "noco",
                            },
                        }
                    ),
                )
                _set_env(ev, "NC_AUTH_JWT_SECRET", _rand())

            # filebrowser ("files"): admin password lives in filebrowser's internal DB,
            # not an env var — cannot be injected here.

        # 6. Domain substitution
        def sub(s: str) -> str:
            return s.replace(OLD_ROOT, root_domain)

        config["customDomain"] = sub(config.get("customDomain", ""))
        for app in apps.values():
            if app.get("redirectDomain"):
                app["redirectDomain"] = sub(app["redirectDomain"])
            for cd in app.get("customDomain", []):
                if cd.get("publicDomain"):
                    cd["publicDomain"] = sub(cd["publicDomain"])
            for ev in app.get("envVars", []):
                if isinstance(ev.get("value"), str) and OLD_ROOT in ev["value"]:
                    ev["value"] = sub(ev["value"])

        # 7. SSL off everywhere (Phase 4 will add a config flag to re-enable)
        config["hasRootSsl"] = False
        config["forceRootSsl"] = False
        for app in apps.values():
            app["hasDefaultSubDomainSsl"] = False
            app["forceSsl"] = False
            for cd in app.get("customDomain", []):
                cd["hasSsl"] = False

        # 8. Top-level config-captain.json fields
        config["hashedPassword"] = hashed
        config["pro"] = {"installationId": str(uuid.uuid4())}
        if email := cfg.get("emailAddress"):
            config["emailAddress"] = email

        # 9. Write updated config and meta
        with open(config_path, "w") as f:
            json.dump(config, f, indent="\t")

        meta["salt"] = new_salt
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        # 10. Wipe letsencrypt folder (accounts, archive, live, renewal); keep renewal-hooks
        le_base = data_dir / "letencrypt" / "etc"
        for d in ("accounts", "archive", "live", "renewal"):
            p = le_base / d
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True, exist_ok=True)

        # 11. config-override.json: force skipVerifyingDomains on the restore
        with open(data_dir / "config-override.json", "w") as f:
            json.dump({"skipVerifyingDomains": "true"}, f)

        # 12. Repack
        out_tar.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out_tar, "w") as t:
            t.add(data_dir, arcname="data")
            t.add(meta_dir, arcname="meta")

    return password


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a CapRover restore tar from a template backup."
    )
    parser.add_argument("--config-file", required=True, help="YAML config file")
    parser.add_argument("--out", required=True, help="Output tar path")
    args = parser.parse_args()

    template_dir = bundled_template()
    cfg = load_config(Path(args.config_file))
    print(f"Generating backup tar from {template_dir}...")
    password = generate(
        template_dir,
        cfg=cfg,
        out_tar=Path(args.out),
    )
    print(f"CapRover password: {password}")
    print(f"Output: {args.out}")
