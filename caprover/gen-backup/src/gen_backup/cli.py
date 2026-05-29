"""Generate a CapRover restore tar from a template backup.

Takes an existing backup tar, replaces secrets and root domain, strips
locally-built images, turns SSL off, and writes a new tar ready to drop
at /captain/backup.tar on a fresh CapRover install.
"""

import argparse
import json
import secrets
import shutil
import tarfile
import tempfile
import uuid
from pathlib import Path

import bcrypt

OLD_ROOT = "cmistaging.guardianconnector.net"


def _deployed_image(app_def: dict) -> str:
    version = app_def.get("deployedVersion", 0)
    for v in app_def.get("versions", []):
        if v.get("version") == version:
            return v.get("deployedImageName") or ""
    return ""


def _is_local_image(image: str) -> bool:
    return not image or image.startswith("img-captain-")


def _rand(n: int = 16) -> str:
    return secrets.token_hex(n)


def _set_env(envvars: list, key: str, value: str) -> None:
    for e in envvars:
        if e["key"] == key:
            e["value"] = value
            return
    envvars.append({"key": key, "value": value})


def generate(template_tar: Path, root_domain: str, out_tar: Path) -> str:
    """Build the new backup tar and return the plaintext CapRover password."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # 1. Extract template
        with tarfile.open(template_tar) as t:
            t.extractall(tmp)

        data_dir = tmp / "data"
        meta_dir = tmp / "meta"
        config_path = data_dir / "config-captain.json"
        meta_path = meta_dir / "backup.json"

        with open(config_path) as f:
            config = json.load(f)
        with open(meta_path) as f:
            meta = json.load(f)

        # 2. New salt + password hash
        # CapRover enforces a 29-char max; 21 gives plenty of entropy.
        new_salt = str(uuid.uuid4())
        password = secrets.token_urlsafe(16)[:21]
        # CapRover: encryptionKey = salt + namespace, hash = bcrypt(encryptionKey + password)
        encryption_key = new_salt + "captain"
        hashed = bcrypt.hashpw(
            (encryption_key + password).encode(), bcrypt.gensalt(rounds=10)
        ).decode()

        # 3. Drop apps with locally-built images
        apps = config["appDefinitions"]
        to_drop = [n for n, a in apps.items() if _is_local_image(_deployed_image(a))]
        for name in to_drop:
            print(f"  dropping {name} (local image)")
            del apps[name]

        # 4. Generate fresh per-deploy secrets
        pg_pass = _rand()
        redis_pass = _rand()
        superset_key = _rand()
        nc_jwt = _rand()
        comapeo_token = _rand()
        nuxt_session_lp = _rand()
        nuxt_session_ex = _rand()
        nuxt_api_key_ex = _rand()

        pg_host = "srv-captain--postgres"
        redis_host = "srv-captain--redis"
        pg_user = "postgres"
        pg_url_base = f"postgres://{pg_user}:{pg_pass}@{pg_host}:5432"

        for name, app in apps.items():
            ev = app.get("envVars", [])
            if name == "postgres":
                _set_env(ev, "POSTGRES_PASSWORD", pg_pass)
            elif name in ("windmill", "windmill-worker", "windmill-worker-native"):
                _set_env(ev, "DATABASE_URL", f"{pg_url_base}/windmill")
            elif name == "redis":
                _set_env(ev, "REDIS_PASSWORD", redis_pass)
            elif name == "superset":
                _set_env(ev, "SECRET_KEY", superset_key)
                _set_env(ev, "REDIS_URL", f"redis://:{redis_pass}@{redis_host}:6379")
                _set_env(
                    ev,
                    "DATABASE_URI",
                    f"postgresql://{pg_user}:{pg_pass}@{pg_host}:5432/superset_metastore",
                )
            elif name == "gc-landing-page":
                _set_env(ev, "NUXT_SESSION_PASSWORD", nuxt_session_lp)
            elif name == "explorer":
                _set_env(ev, "NUXT_DB_PASSWORD", pg_pass)
                _set_env(ev, "NUXT_PUBLIC_APP_API_KEY", nuxt_api_key_ex)
                _set_env(ev, "NUXT_SESSION_PASSWORD", nuxt_session_ex)
            elif name == "comapeo":
                _set_env(ev, "SERVER_BEARER_TOKEN", comapeo_token)
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
                _set_env(ev, "NC_AUTH_JWT_SECRET", nc_jwt)

        # 5. Domain substitution
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

        # 6. SSL off everywhere
        config["hasRootSsl"] = False
        config["forceRootSsl"] = False
        for app in apps.values():
            app["hasDefaultSubDomainSsl"] = False
            app["forceSsl"] = False
            for cd in app.get("customDomain", []):
                cd["hasSsl"] = False

        # 7. New password hash + installationId
        config["hashedPassword"] = hashed
        config["pro"] = {"installationId": str(uuid.uuid4())}

        # 8. Write updated config and meta
        with open(config_path, "w") as f:
            json.dump(config, f, indent="\t")

        meta["salt"] = new_salt
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        # 9. Wipe letsencrypt (accounts, archive, live, renewal); leave renewal-hooks
        le_base = data_dir / "letencrypt" / "etc"
        for d in ("accounts", "archive", "live", "renewal"):
            p = le_base / d
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True, exist_ok=True)

        # 10. Include config-override.json so skipVerifyingDomains survives the restore
        with open(data_dir / "config-override.json", "w") as f:
            json.dump({"skipVerifyingDomains": "true"}, f)

        # 11. Repack
        out_tar.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out_tar, "w") as t:
            t.add(data_dir, arcname="data")
            t.add(meta_dir, arcname="meta")

    return password


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a CapRover restore tar from a template backup."
    )
    parser.add_argument("--template", required=True, help="Source backup tar")
    parser.add_argument(
        "--root-domain",
        required=True,
        help="New root domain (e.g. test-gc-deploy.localhost)",
    )
    parser.add_argument("--out", required=True, help="Output tar path")
    args = parser.parse_args()

    print("Generating backup tar...")
    password = generate(
        template_tar=Path(args.template),
        root_domain=args.root_domain,
        out_tar=Path(args.out),
    )
    print(f"CapRover password: {password}")
    print(f"Output: {args.out}")
