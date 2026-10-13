import asyncio
import importlib.resources
import shutil
import threading
import time

import pytest
from gc_stack_deploy.wizard import screens
from gc_stack_deploy.wizard.auth0.cli import Auth0CliError, DeviceCode
from gc_stack_deploy.wizard.auth0 import m2m_app
from gc_stack_deploy.wizard.auth0.m2m_app import TemporaryM2MApp
from gc_stack_deploy.wizard.screens import (
    Auth0LoginScreen,
    GoogleSocialScreen,
    WizardApp,
)
from textual.widgets import Button, Input, Static

DOMAIN = "springfield.us.auth0.com"
CODE = DeviceCode(
    user_code="ABCD-EFGH",
    verification_uri="https://auth0.auth0.com/activate",
    verification_uri_complete="https://auth0.auth0.com/activate?user_code=ABCD-EFGH",
)


class FakeTempApp(TemporaryM2MApp):
    cleanups = 0  # counts deletions of the temporary app

    def cleanup(self, **kwargs):
        FakeTempApp.cleanups += 1
        return super().cleanup(run=lambda *a, **k: None)


class FakeLogin:
    """Stands in for CliLogin; `approve` gates wait_for_approval."""

    approve = threading.Event()
    error: Exception | None = None
    cancelled_by_screen = False

    def __init__(self, domain):
        assert domain == DOMAIN

    def wait_for_device_code(self, cancelled):
        return CODE

    def wait_for_approval(self, cancelled):
        for _ in range(100):  # bounded: a regression fails the asserts, not hangs
            if self.approve.wait(0.05):
                break
            if cancelled():
                raise Auth0CliError("Login cancelled.")
        if self.error:
            raise self.error

    def cancel(self):
        FakeLogin.cancelled_by_screen = True


@pytest.fixture(autouse=True)
def fake_cli(monkeypatch):
    FakeLogin.approve = threading.Event()
    FakeLogin.error = None
    FakeLogin.cancelled_by_screen = False
    FakeTempApp.cleanups = 0
    monkeypatch.setattr(m2m_app, "CliLogin", FakeLogin)
    monkeypatch.setattr(screens, "install_cli", lambda: None)
    monkeypatch.setattr(screens, "remove_cli", lambda: None)
    monkeypatch.setattr(
        m2m_app, "create_m2m_app", lambda domain: FakeTempApp(domain, "cid", "csecret")
    )
    monkeypatch.setattr(
        m2m_app, "get_m2m_access_token", lambda domain, cid, secret: "the-token"
    )
    monkeypatch.setattr(
        screens, "get_m2m_access_token", lambda domain, cid, secret: "the-token"
    )


@pytest.fixture
def config_file(tmp_path):
    example = (
        importlib.resources.files("gc_stack_deploy.example_configs")
        / "stack.example.yaml"
    )
    with importlib.resources.as_file(example) as path:
        shutil.copy(path, tmp_path / "stack.yaml")
    return str(tmp_path / "stack.yaml")


async def wait_until(pilot, condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        await pilot.pause(0.05)


async def start_login(pilot, domain=DOMAIN):
    form = pilot.app.screen.query_one("#login_form")
    await wait_until(pilot, lambda: form.display)
    pilot.app.screen.query_one("#domain", Input).value = domain
    await pilot.click("#login")


def status_text(app) -> str:
    return str(app.screen.query_one("#login_status", Static).render())


def test_login_shows_code_then_continues_with_token_in_memory(config_file, monkeypatch):
    removed_cli = []
    monkeypatch.setattr(screens, "remove_cli", lambda: removed_cli.append(True))

    async def scenario():
        app = WizardApp(config_file)
        async with app.run_test(size=(120, 50)) as pilot:
            await start_login(pilot)
            await wait_until(pilot, lambda: "ABCD-EFGH" in status_text(app))
            assert CODE.verification_uri_complete in status_text(app)
            assert app.screen.query_one("#login", Button).disabled

            FakeLogin.approve.set()
            await wait_until(pilot, lambda: isinstance(app.screen, GoogleSocialScreen))
            assert app.wizard_data["domain"] == DOMAIN
            assert app.wizard_data["access_token"] == "the-token"
            assert app.wizard_data["temp_app"].client_id == "cid"
            assert FakeTempApp.cleanups == 0  # still needed for provisioning

    asyncio.run(scenario())
    # Quitting before provisioning still removes the temporary app and the CLI.
    assert FakeTempApp.cleanups == 1
    assert removed_cli


def raiser(exc):
    def fail(*args, **kwargs):
        raise exc

    return fail


@pytest.mark.parametrize(
    "fail_at,expected_message,expected_app_deletions",
    [
        ("approval", "access denied", 0),
        ("token", "access_denied", 1),  # the temporary app was already created
    ],
)
def test_login_failure_is_shown_can_be_retried_and_leaves_no_app(
    config_file, monkeypatch, fail_at, expected_message, expected_app_deletions
):
    if fail_at == "approval":
        FakeLogin.error = Auth0CliError("Auth0 login was not completed: access denied")
    else:
        error = RuntimeError("Unauthorized: access_denied")
        monkeypatch.setattr(m2m_app, "get_m2m_access_token", raiser(error))
    FakeLogin.approve.set()

    async def scenario():
        app = WizardApp(config_file)
        async with app.run_test(size=(120, 50)) as pilot:
            await start_login(pilot)
            await wait_until(pilot, lambda: "Login failed" in status_text(app))
            assert expected_message in status_text(app)
            assert isinstance(app.screen, Auth0LoginScreen)
            assert not app.screen.query_one("#login", Button).disabled
            assert "access_token" not in app.wizard_data

    asyncio.run(scenario())
    assert FakeTempApp.cleanups == expected_app_deletions


def test_quitting_while_waiting_for_approval_does_not_hang(config_file):
    """The waiting thread must notice cancellation, or exiting waits for the CLI to time out."""

    async def scenario():
        app = WizardApp(config_file)
        async with app.run_test(size=(120, 50)) as pilot:
            await start_login(pilot)
            await wait_until(pilot, lambda: "ABCD-EFGH" in status_text(app))
            await app.action_quit()

    started = time.monotonic()
    # asyncio.run waits for the default executor's threads, including the waiter.
    asyncio.run(scenario())
    assert time.monotonic() - started < 3
    assert FakeLogin.cancelled_by_screen
    assert FakeTempApp.cleanups == 0  # nothing was created yet


def test_failed_cli_download_is_shown_and_offers_manual_credentials(
    config_file, monkeypatch
):
    error = Auth0CliError("Could not download the Auth0 CLI")
    monkeypatch.setattr(screens, "install_cli", raiser(error))

    async def scenario():
        app = WizardApp(config_file)
        async with app.run_test(size=(120, 50)) as pilot:
            await wait_until(pilot, lambda: "Could not download" in status_text(app))
            assert not app.screen.query_one("#installing").display
            assert app.screen.query_one("#login_form").display
            assert app.screen.query_one("#login", Button).disabled
            assert not app.screen.query_one("#use_m2m", Button).disabled

    asyncio.run(scenario())


async def use_m2m_credentials(pilot, domain=DOMAIN, client_id="mid", secret="msecret"):
    form = pilot.app.screen.query_one("#login_form")
    await wait_until(pilot, lambda: form.display)
    pilot.app.screen.query_one("#domain", Input).value = domain
    pilot.app.screen.query_one("#m2m_client_id", Input).value = client_id
    pilot.app.screen.query_one("#m2m_client_secret", Input).value = secret
    await pilot.click("#use_m2m")


def test_manual_m2m_credentials_give_a_token_without_a_temporary_app(
    config_file, monkeypatch
):
    calls = []

    def get_token(domain, client_id, secret):
        calls.append((domain, client_id, secret))
        return "the-token"

    monkeypatch.setattr(screens, "get_m2m_access_token", get_token)

    async def scenario():
        app = WizardApp(config_file)
        async with app.run_test(size=(120, 50)) as pilot:
            await use_m2m_credentials(pilot, domain=DOMAIN)
            await wait_until(pilot, lambda: isinstance(app.screen, GoogleSocialScreen))
            assert app.wizard_data["domain"] == DOMAIN
            assert app.wizard_data["access_token"] == "the-token"
            assert app.wizard_data["temp_app"] is None

    asyncio.run(scenario())
    assert calls == [(DOMAIN, "mid", "msecret")]
    assert FakeTempApp.cleanups == 0


def test_manual_m2m_credentials_are_not_sent_to_a_non_auth0_domain(
    config_file, monkeypatch
):
    monkeypatch.setattr(
        screens, "get_m2m_access_token", raiser(AssertionError("secret was sent"))
    )

    async def scenario():
        app = WizardApp(config_file)
        async with app.run_test(size=(120, 50)) as pilot:
            await use_m2m_credentials(pilot, domain="auth.example.org")
            await pilot.pause()
            assert isinstance(app.screen, Auth0LoginScreen)
            assert "access_token" not in app.wizard_data

    asyncio.run(scenario())


def test_manual_m2m_credentials_rejected_by_auth0_can_be_corrected(
    config_file, monkeypatch
):
    monkeypatch.setattr(
        screens, "get_m2m_access_token", raiser(RuntimeError("access_denied"))
    )

    async def scenario():
        app = WizardApp(config_file)
        async with app.run_test(size=(120, 50)) as pilot:
            await use_m2m_credentials(pilot)
            await wait_until(pilot, lambda: "Login failed" in status_text(app))
            assert "access_denied" in status_text(app)
            assert isinstance(app.screen, Auth0LoginScreen)
            assert not app.screen.query_one("#use_m2m", Button).disabled
            assert "access_token" not in app.wizard_data

    asyncio.run(scenario())
