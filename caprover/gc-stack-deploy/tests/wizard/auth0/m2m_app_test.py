import json
import subprocess

import pytest

from gc_stack_deploy.wizard.auth0 import cli, m2m_app
from gc_stack_deploy.wizard.auth0.cli import Auth0CliError
from gc_stack_deploy.wizard.auth0.m2m_app import (
    TemporaryM2MApp,
    create_m2m_app,
    login_and_create_app,
)

DOMAIN = "springfield.us.auth0.com"


@pytest.fixture(autouse=True)
def installed_cli(monkeypatch):
    """Pretend install_cli() already ran, without touching the filesystem."""
    monkeypatch.setattr(cli, "_cli_dir", "/tmp/fake-cli-dir")


class Recorder:
    """Stands in for subprocess.run, answering by the CLI subcommand."""

    def __init__(self, responses=None, fail=()):
        self.calls = []
        self.responses = responses or {}
        self.fail = fail

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        key = " ".join(args[1:3])
        if key in self.fail:
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 1, "SECRET-OUT", "boom: denied\n")
        out = json.dumps(self.responses.get(key, {}))
        return subprocess.CompletedProcess(args, 0, out, "")


CREATED = {"client_id": "cid", "client_secret": "csecret"}


def test_failed_grant_deletes_the_app_again_and_hides_cli_output():
    run = Recorder({"apps create": CREATED}, fail={"api post"})
    with pytest.raises(Auth0CliError, match="denied") as exc_info:
        create_m2m_app(DOMAIN, run=run)
    assert "SECRET-OUT" not in str(exc_info.value)
    assert [c[1:3] for c in run.calls][-2:] == [["apps", "delete"], ["logout", DOMAIN]]


def test_cleanup_deletes_app_logs_out_and_is_idempotent():
    run = Recorder()
    app = TemporaryM2MApp(DOMAIN, "cid", "csecret")

    assert app.cleanup(run=run) == []
    assert app.client_secret == ""
    assert [c[1:3] for c in run.calls] == [["apps", "delete"], ["logout", DOMAIN]]

    assert app.cleanup(run=run) == []
    assert len(run.calls) == 2


def test_cleanup_warns_but_keeps_going_when_a_step_fails():
    run = Recorder(fail={"apps delete"})
    warnings = TemporaryM2MApp(DOMAIN, "cid", "csecret").cleanup(run=run)
    assert len(warnings) == 1 and "cid" in warnings[0]
    assert run.calls[-1][1] == "logout"


class FakeLogin:
    cancels = 0

    def __init__(self, domain):
        FakeLogin.cancels = 0

    def wait_for_device_code(self, cancelled):
        return "the-code"

    def wait_for_approval(self, cancelled):
        pass

    def cancel(self):
        FakeLogin.cancels += 1


class FakeApp:
    client_id, client_secret = "cid", "csecret"

    def __init__(self):
        self.cleanups = 0

    def cleanup(self):
        self.cleanups += 1


@pytest.fixture
def fake_login(monkeypatch):
    app = FakeApp()
    monkeypatch.setattr(m2m_app, "CliLogin", FakeLogin)
    monkeypatch.setattr(m2m_app, "create_m2m_app", lambda domain: app)
    monkeypatch.setattr(m2m_app, "get_m2m_access_token", lambda *args: "the-token")
    return app


def test_login_and_create_app_reports_progress_and_returns_the_app(fake_login):
    events = []
    token, app = login_and_create_app(
        DOMAIN,
        on_device_code=lambda code: events.append(code),
        on_approved=lambda: events.append("approved"),
    )
    assert (token, app) == ("the-token", fake_login)
    assert events == ["the-code", "approved"]
    assert fake_login.cleanups == 0  # the caller still needs it


def test_login_and_create_app_deletes_the_app_if_the_token_fails(
    fake_login, monkeypatch
):
    def fail(*args):
        raise RuntimeError("access_denied")

    monkeypatch.setattr(m2m_app, "get_m2m_access_token", fail)
    with pytest.raises(RuntimeError):
        login_and_create_app(DOMAIN, on_device_code=lambda code: None)
    assert fake_login.cleanups == 1
    assert FakeLogin.cancels == 1


def test_login_and_create_app_cleans_up_if_cancelled_at_the_end(fake_login):
    with pytest.raises(Auth0CliError, match="cancelled"):
        login_and_create_app(
            DOMAIN, on_device_code=lambda code: None, cancelled=lambda: True
        )
    assert fake_login.cleanups == 1
