import io
import json
import tarfile

import pytest

from gen_backup.cli import OLD_ROOT

# Minimal template backup — enough apps to exercise all injection paths.
# Uses the real OLD_ROOT so domain-substitution tests stay in sync with the code.

_APPS = {
    "postgres": {
        "envVars": [
            {"key": "POSTGRES_PASSWORD", "value": "original-pg-pass"},
            {"key": "POSTGRES_USER",     "value": "postgres"},
            {"key": "POSTGRES_DB",       "value": "postgres"},
        ],
        "versions": [{"version": 1, "deployedImageName": "postgres:17"}],
        "deployedVersion": 1,
        "customDomain": [],
        "hasDefaultSubDomainSsl": True,
        "redirectDomain": "",
        "forceSsl": True,
    },
    "gc-landing-page": {
        "envVars": [
            {"key": "NUXT_PUBLIC_COMMUNITY_NAME", "value": "original"},
            {"key": "NUXT_PUBLIC_BASE_URL",        "value": f"https://{OLD_ROOT}"},
            {"key": "NUXT_SESSION_PASSWORD",        "value": "original-session"},
            {"key": "NUXT_OAUTH_AUTH0_DOMAIN",      "value": ""},
        ],
        "versions": [{"version": 1, "deployedImageName": "communityfirst/guardianconnector-landing-page:latest"}],
        "deployedVersion": 1,
        "customDomain": [{"publicDomain": OLD_ROOT, "hasSsl": True}],
        "hasDefaultSubDomainSsl": True,
        "redirectDomain": OLD_ROOT,
        "forceSsl": True,
    },
    "explorer": {
        "envVars": [
            {"key": "NUXT_DB_PASSWORD", "value": "original-pg-pass"},
            {"key": "NUXT_DATABASE",    "value": "warehouse"},
        ],
        "versions": [{"version": 1, "deployedImageName": "communityfirst/guardianconnector-explorer:latest"}],
        "deployedVersion": 1,
        "customDomain": [],
        "hasDefaultSubDomainSsl": True,
        "redirectDomain": f"explorer.{OLD_ROOT}",
        "forceSsl": True,
    },
    "superset": {
        "envVars": [
            {"key": "SECRET_KEY",   "value": "original-secret"},
            {"key": "AUTH0_DOMAIN", "value": ""},
        ],
        "versions": [{"version": 1, "deployedImageName": "communityfirst/superset-deployment:latest"}],
        "deployedVersion": 1,
        "customDomain": [],
        "hasDefaultSubDomainSsl": True,
        "redirectDomain": f"superset.{OLD_ROOT}",
        "forceSsl": True,
    },
    "nocodb": {
        "envVars": [
            {"key": "NC_DB_JSON", "value": json.dumps({
                "client": "pg",
                "connection": {"host": "srv-captain--postgres", "port": 5432,
                               "user": "postgres", "password": "original-pg-pass",
                               "database": "noco"},
            })},
            {"key": "NC_AUTH_JWT_SECRET", "value": "original-jwt"},
        ],
        "versions": [{"version": 1, "deployedImageName": "nocodb/nocodb:latest"}],
        "deployedVersion": 1,
        "customDomain": [],
        "hasDefaultSubDomainSsl": True,
        "redirectDomain": "",
        "forceSsl": True,
    },
    # App with a locally-built image — must always be stripped.
    "local-app": {
        "envVars": [],
        "versions": [{"version": 1, "deployedImageName": "img-captain-custom:1"}],
        "deployedVersion": 1,
        "customDomain": [],
        "hasDefaultSubDomainSsl": False,
        "redirectDomain": "",
        "forceSsl": False,
    },
}

TEMPLATE_CONFIG = {
    "namespace": "captain",
    "customDomain": OLD_ROOT,
    "emailAddress": "original@example.com",
    "hasRootSsl": True,
    "forceRootSsl": True,
    "hashedPassword": "$2b$10$original",
    "pro": {"installationId": "original-uuid"},
    "appDefinitions": _APPS,
}

TEMPLATE_META = {
    "salt": "original-salt-uuid",
    "nodes": [{"nodeId": "abc123", "type": "manager", "isLeader": True, "ip": "127.0.0.1"}],
}


@pytest.fixture()
def template_tar(tmp_path):
    tar_path = tmp_path / "template.tar"
    with tarfile.open(tar_path, "w") as t:
        for arcname, data in [
            ("data/config-captain.json", json.dumps(TEMPLATE_CONFIG).encode()),
            ("meta/backup.json",         json.dumps(TEMPLATE_META).encode()),
        ]:
            info = tarfile.TarInfo(arcname)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return tar_path
