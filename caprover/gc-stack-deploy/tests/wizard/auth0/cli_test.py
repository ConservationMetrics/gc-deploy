import hashlib
import io
import json
import os
import tarfile

import pytest

from gc_stack_deploy.wizard.auth0 import cli
from gc_stack_deploy.wizard.auth0.cli import (
    Auth0CliError,
    CliLogin,
    install_cli,
    remove_cli,
    validate_tenant_domain,
)

DOMAIN = "springfield.us.auth0.com"
CLI_DIR = "/tmp/fake-cli-dir"
CLI_PATH = f"{CLI_DIR}/auth0"


@pytest.fixture(autouse=True)
def installed_cli(monkeypatch):
    """Pretend install_cli() already ran, without touching the filesystem."""
    monkeypatch.setattr(cli, "_cli_dir", CLI_DIR)


class FakeProc:
    def __init__(self, stdout_text="", stderr_text="", returncode=0):
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.terminated = True


def fake_popen(proc):
    def popen(args, **kwargs):
        return proc

    return popen


CODE_JSON = {
    "verification_uri": "https://auth0.auth0.com/activate",
    "user_code": "ABCD-EFGH",
    "expires_in": 900,
    "interval": 5,
}


def test_validate_tenant_domain():
    validate_tenant_domain(DOMAIN)
    for bad in ["", "login.springfield.org", "https://x.us.auth0.com", "a b.auth0.com"]:
        with pytest.raises(ValueError):
            validate_tenant_domain(bad)


def make_archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def fake_urlopen(archive: bytes, urls: list):
    def urlopen(url, timeout):
        urls.append(url)
        return io.BytesIO(archive)

    return urlopen


@pytest.fixture
def not_installed(monkeypatch):
    monkeypatch.setattr(cli, "_cli_dir", None)
    yield
    remove_cli()


@pytest.mark.parametrize(
    "machine,platform_name", [("x86_64", "Linux_x86_64"), ("aarch64", "Linux_arm64")]
)
def test_install_cli_downloads_checks_and_unpacks(
    not_installed, monkeypatch, machine, platform_name
):
    archive = make_archive({"LICENSE": b"license", "auth0": b"#!binary"})
    monkeypatch.setitem(
        cli.CLI_ARCHIVE_SHA256, platform_name, hashlib.sha256(archive).hexdigest()
    )
    urls = []

    install_cli(urlopen=fake_urlopen(archive, urls), system="Linux", machine=machine)

    assert urls == [
        "https://github.com/auth0/auth0-cli/releases/download/"
        f"v{cli.CLI_VERSION}/auth0-cli_{cli.CLI_VERSION}_{platform_name}.tar.gz"
    ]
    cli_dir = cli._cli_dir
    with open(os.path.join(cli_dir, "auth0"), "rb") as f:
        assert f.read() == b"#!binary"

    install_cli(urlopen=fake_urlopen(archive, urls))  # already installed: no download
    assert len(urls) == 1

    remove_cli()
    assert not os.path.exists(cli_dir)
    assert cli._cli_dir is None
    remove_cli()  # safe to repeat


def test_install_cli_rejects_an_archive_with_the_wrong_checksum(not_installed):
    tampered = fake_urlopen(make_archive({"auth0": b"#!tampered"}), [])
    with pytest.raises(Auth0CliError, match="checksum"):
        install_cli(urlopen=tampered, system="Linux", machine="x86_64")
    assert cli._cli_dir is None


def test_login_returns_code_then_waits_for_approval():
    out = json.dumps(CODE_JSON) + "\n" + json.dumps({"logged_in": True}) + "\n"
    login = CliLogin(DOMAIN, popen=fake_popen(FakeProc(out)))

    code = login.wait_for_device_code()
    assert (code.user_code, code.verification_uri) == (
        "ABCD-EFGH",
        "https://auth0.auth0.com/activate",
    )
    login.wait_for_approval()


@pytest.mark.parametrize(
    "stdout,match",
    [
        ("", "did not start: the code expired"),
        (json.dumps(CODE_JSON) + "\n", "not completed: the code expired"),
    ],
)
def test_login_that_exits_early_reports_stderr(stdout, match):
    proc = FakeProc(stdout, "line1\nthe code expired\n", returncode=1)
    login = CliLogin(DOMAIN, popen=fake_popen(proc))
    with pytest.raises(Auth0CliError, match=match):
        login.wait_for_device_code()
        login.wait_for_approval()


def test_cancelling_terminates_the_cli():
    proc = FakeProc()
    proc.poll = lambda: None  # still running
    login = CliLogin(DOMAIN, popen=fake_popen(proc))
    with pytest.raises(Auth0CliError, match="cancelled"):
        login.wait_for_device_code(cancelled=lambda: True)
    assert proc.terminated

