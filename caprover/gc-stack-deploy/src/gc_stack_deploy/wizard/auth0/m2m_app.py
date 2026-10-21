"""Get Management API access by creating a temporary M2M application with the Auth0 CLI.

How the wizard gets access to Auth0
-----------------------------------
The wizard provisions Auth0 with the Python SDK, authenticated as a Machine-to-Machine (M2M)
application that holds `MANAGEMENT_SCOPES`. Rather than make the admin click through creating
that application, the wizard drives Auth0's own command-line tool (see cli.py), which can sign
in a tenant admin and create it:

1. `cli.install_cli()` downloads the CLI, and `cli.CliLogin` has a tenant admin approve a login.
2. `create_m2m_app()` runs `auth0 apps create --type m2m` and `auth0 api post client-grants`
   to create a temporary M2M application authorized for exactly `MANAGEMENT_SCOPES`.
3. The wizard then uses that application's credentials with the Python SDK as it always did
   (see client.get_m2m_access_token). The client secret is held in memory only.
4. `TemporaryM2MApp.cleanup()` deletes the application and runs `auth0 logout`, then
   `cli.remove_cli()` deletes the temporary directory, so nothing is left behind in the tenant
   or on the machine.

If the CLI can't be used (no download for this machine, a custom tenant domain), the admin
creates the M2M application by hand instead and enters its credentials in the wizard
(auth0/README.md, "Appendix: Bootstrap M2M application for the wizard"). Both routes end in the same
place: an access token from `client.get_m2m_access_token`.
"""

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from .cli import Auth0CliError, CliLogin, DeviceCode, run_cli, run_json
from .client import get_m2m_access_token

TEMP_APP_NAME = "gc-stack-deploy (temporary)"

# KEEP IN SYNC with the permissions table in auth0/README.md's "Appendix: Create the M2M
# application by hand".
# What the temporary M2M app may do: create and update applications and their Management API
# grants, the google-oauth2 connection, the RBAC roles, and the Post-Login Actions (including
# deploying and binding them into the Login flow). Nothing that reads or modifies users.
MANAGEMENT_SCOPES = [
    "read:client_grants",
    "update:client_grants",
    "create:client_grants",
    "read:clients",
    "update:clients",
    "create:clients",
    "read:connections",
    "update:connections",
    "create:connections",
    "update:connections_options",
    "read:actions",
    "update:actions",
    "create:actions",
    "read:roles",
    "create:roles",
]


@dataclass
class TemporaryM2MApp:
    """An M2M application the wizard created in the tenant; call `cleanup()` when done."""

    domain: str
    client_id: str
    client_secret: str
    _cleaned_up: bool = False

    def cleanup(self, *, run=subprocess.run) -> list[str]:
        """Delete the application and log the CLI out; returns warnings (never raises).

        Safe to call more than once.
        """
        if self._cleaned_up:
            return []
        self._cleaned_up = True
        self.client_secret = ""
        warnings = []
        steps = [
            (
                f"Could not delete the temporary application {TEMP_APP_NAME!r} "
                f"(client ID {self.client_id}); delete it in the Auth0 dashboard under "
                "Applications -> Applications",
                ["apps", "delete", self.client_id, "--tenant", self.domain, "--force"],
            ),
            ("Could not log the Auth0 CLI out", ["logout", self.domain]),
        ]
        for failure, args in steps:
            try:
                run_cli(args, run=run)
            except Auth0CliError as exc:
                warnings.append(f"{failure}: {exc}")
        return warnings


def create_m2m_app(domain: str, *, run=subprocess.run) -> TemporaryM2MApp:
    """Create a temporary M2M application authorized for `MANAGEMENT_SCOPES` on `domain`.

    Requires an `auth0 login` to `domain` (see `cli.CliLogin`). On failure, anything already
    created is deleted again.
    """
    created = run_json(
        [
            "apps",
            "create",
            "--tenant",
            domain,
            "--name",
            TEMP_APP_NAME,
            "--type",
            "m2m",
            "--reveal-secrets",
            "--json",
        ],
        run=run,
    )
    client_id, client_secret = created.get("client_id"), created.get("client_secret")
    if not (client_id and client_secret):
        raise Auth0CliError(
            "The Auth0 CLI created an application but did not return its credentials."
        )
    app = TemporaryM2MApp(domain, client_id, client_secret)
    try:
        run_json(
            [
                "api",
                "post",
                "client-grants",
                "--tenant",
                domain,
                "--data",
                json.dumps(
                    {
                        "client_id": client_id,
                        "audience": f"https://{domain}/api/v2/",
                        "scope": MANAGEMENT_SCOPES,
                    }
                ),
            ],
            run=run,
        )
    except Auth0CliError:
        app.cleanup(run=run)
        raise
    return app


def login_and_create_app(
    domain: str,
    *,
    on_device_code: Callable[[DeviceCode], None],
    on_approved: Callable[[], None] = lambda: None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[str, TemporaryM2MApp]:
    """Have a tenant admin approve a CLI login, then return (access_token, temporary app).

    Blocks until the admin approves. `on_device_code` shows them the URL and code;
    `on_approved` runs once they have. `cancelled` is polled while waiting.
    On failure or cancellation it raises, having cancelled the login and deleted any
    application already created. On success the caller owns the app's `cleanup()`.
    Requires `cli.install_cli()`.
    """
    login = temp_app = None
    try:
        login = CliLogin(domain)
        on_device_code(login.wait_for_device_code(cancelled))
        login.wait_for_approval(cancelled)
        on_approved()
        temp_app = create_m2m_app(domain)
        access_token = get_m2m_access_token(
            domain, temp_app.client_id, temp_app.client_secret
        )
        if cancelled():
            raise Auth0CliError("Login cancelled.")
    except Exception:
        if login is not None:
            login.cancel()
        if temp_app is not None:
            temp_app.cleanup()
        raise
    return access_token, temp_app
