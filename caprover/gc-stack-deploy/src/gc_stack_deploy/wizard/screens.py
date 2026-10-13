"""Textual screens for `gc-stack-deploy wizard`, and the WizardApp entry point.

Five screens, pushed in sequence, each handing its collected answers forward
to the next: Auth0 login -> Google social login -> app selection ->
root domain -> run.
"""

import logging

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    RichLog,
    Static,
)
from textual.worker import get_current_worker

from ..gui import RichLogHandler
from .auth0.cli import (
    DeviceCode,
    install_cli,
    remove_cli,
    validate_tenant_domain,
)
from .auth0.client import get_m2m_access_token
from .auth0.m2m_app import TemporaryM2MApp, login_and_create_app
from .orchestrator import APP_DISPLAY_NAMES, client_spec_for_app, run_wizard
from .yaml_writer import AUTH0_DOMAIN_APPS, load_config

TOTAL_STEPS = 5


class WizardScreen(Screen):
    """Base class for the wizard's sequential screens.

    Sets the screen's sub_title to "Step N of TOTAL_STEPS" so Header shows
    progress through the sequence; subclasses just set STEP.
    """

    STEP: int = 0

    def on_mount(self) -> None:
        self.sub_title = f"Step {self.STEP} of {TOTAL_STEPS}"


class Auth0LoginScreen(WizardScreen):
    """Get a Management API access token for the Auth0 tenant, in one of two ways.

    Preferred: download the Auth0 CLI and log in with it, approving in a browser on another
    computer; the wizard then has the CLI create a temporary M2M application (see
    auth0/m2m_app.py).

    Fallback: the user enters the credentials of an M2M application they
    created by hand (auth0/README.md's "Appendix: Bootstrap M2M application for the wizard").

    The form only appears once the CLI download has been attempted, so a failure is reported
    before the user types anything. On success the access token is kept in wizard_data
    (memory only) for RunScreen, along with the temporary M2M app (if any) to clean up.
    """

    # States Diagram:
    #
    #                             on_mount
    #                                |
    #                      _install (thread, form is hidden)
    #                                |
    #                        _show_login_form
    #          (or _install_failed: "Log in with browser" is disabled)
    #                                |
    #            +-------------------+-------------------+
    #            |                                       |
    #  "Log in with browser"                   "Use M2M credentials"
    #            |                                       |
    #    _start_cli_login                      _use_m2m_credentials
    #            |                                       |
    #    _login (thread):                      _fetch_token (thread):
    #      _show_code                            trade the entered client
    #      wait for approval                     ID and secret for a token
    #      create the temporary M2M app
    #      trade its credentials for a token
    #            |                                       |
    #            +-------------------+-------------------+
    #                                |
    #                _login_succeeded stores in wizard_data:
    #                  domain, access_token, temp_app (None for manual)
    #                                |
    #                      push GoogleSocialScreen
    #
    # Either lane can end in _login_failed instead, which re-enables the form to retry.
    # _set_busy disables the form while a request is in flight.
    # WizardApp.cleanup_temp_app later deletes temp_app and the downloaded CLI.
    STEP = 1
    cli_installed = True

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static(
                "First, create an Auth0 tenant if you don't have one yet. Do this in the auth0 web portal, then return to this app."
            )
            with Vertical(id="installing"):
                yield Static(
                    "Downloading the Auth0 CLI (`auth0`) to a temporary folder..."
                )
                yield LoadingIndicator()
            with Vertical(id="login_form"):
                yield Label("Auth0 tenant domain:")
                yield Input(placeholder="your-tenant.us.auth0.com", id="domain")
                yield Static(
                    "The wizard downloaded the Auth0 CLI (`auth0`) to a temporary folder to log in. You'll approve the login in a browser on any computer (e.g. your laptop or phone); the wizard then creates a temporary application to do the rest. It deletes both when done."
                )
                yield Button("Log in with browser", id="login", variant="primary")
                yield Static(
                    "Or, if you created the M2M application by hand (see auth0/README.md's "
                    "'Appendix: Bootstrap M2M application for the wizard'), enter its credentials:"
                )
                yield Label("M2M client ID")
                yield Input(placeholder="client id", id="m2m_client_id")
                yield Label("M2M client secret")
                yield Input(
                    placeholder="client secret", password=True, id="m2m_client_secret"
                )
                yield Button("Use M2M credentials", id="use_m2m")
            yield Static("", id="login_status")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#login_form").display = False
        if self.app.dry_run:
            self._show_login_form()
        else:
            self._install()

    @work(thread=True, group="install")
    def _install(self) -> None:
        try:
            install_cli()
        except Exception as exc:
            message = str(exc)
            self.app.call_from_thread(self._install_failed, message)
            return
        self.app.call_from_thread(self._show_login_form)

    def _install_failed(self, message: str) -> None:
        self.query_one("#installing").display = False
        self.query_one("#login_form").display = True
        self.cli_installed = False
        self.query_one("#login", Button).disabled = True
        self.query_one("#login_status", Static).update(
            Text.assemble(
                ("Could not set up the Auth0 CLI: ", "bold red"),
                message,
                "\nBootstrap M2M application for the wizard and enter its credentials below.",
            )
        )

    def _show_login_form(self) -> None:
        self.query_one("#installing").display = False
        self.query_one("#login_form").display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        domain = self.query_one("#domain", Input).value.strip()
        if event.button.id == "use_m2m":
            self._use_m2m_credentials(domain)
        elif event.button.id == "login":
            self._start_cli_login(domain)

    def _use_m2m_credentials(self, domain: str) -> None:
        client_id = self.query_one("#m2m_client_id", Input).value.strip()
        client_secret = self.query_one("#m2m_client_secret", Input).value.strip()
        if not (domain and client_id and client_secret):
            self.notify(
                "Enter the tenant domain and the M2M client ID and secret",
                severity="error",
            )
            return
        try:
            validate_tenant_domain(domain)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        if self.app.dry_run:
            self.notify("DRY RUN: skipping Auth0 token request")
            self._login_succeeded(domain, "", None)
            return
        self._set_busy(True)
        self._set_status("Contacting Auth0...")
        self._fetch_token(domain, client_id, client_secret)

    @work(exclusive=True, thread=True)
    def _fetch_token(self, domain: str, client_id: str, client_secret: str) -> None:
        try:
            access_token = get_m2m_access_token(domain, client_id, client_secret)
        except Exception as exc:
            self.app.call_from_thread(self._login_failed, str(exc))
            return
        self.app.call_from_thread(self._login_succeeded, domain, access_token, None)

    def _start_cli_login(self, domain: str) -> None:
        try:
            validate_tenant_domain(domain)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        if self.app.dry_run:
            self.notify("DRY RUN: skipping Auth0 login")
            self._login_succeeded(domain, "", None)
            return
        self._set_busy(True)
        self._set_status("Contacting Auth0...")
        self._login(domain)

    @work(exclusive=True, thread=True)
    def _login(self, domain: str) -> None:
        worker = get_current_worker()
        # Textual can't kill a thread, and waits for it on exit, so the CLI waits poll
        # `cancelled` (screen removed or app quitting).
        try:
            access_token, temp_app = login_and_create_app(
                domain,
                on_device_code=lambda code: self.app.call_from_thread(
                    self._show_code, domain, code
                ),
                on_approved=lambda: self.app.call_from_thread(
                    self._set_status, "Approved. Setting up access..."
                ),
                cancelled=lambda: worker.is_cancelled,
            )
        except Exception as exc:
            if not worker.is_cancelled:
                self.app.call_from_thread(self._login_failed, str(exc))
            return
        self.app.call_from_thread(self._login_succeeded, domain, access_token, temp_app)

    def _set_status(self, message: str) -> None:
        self.query_one("#login_status", Static).update(message)

    def _show_code(self, domain: str, code: DeviceCode) -> None:
        url = code.verification_uri_complete or code.verification_uri
        # Text, not markup, so nothing Auth0 returns can be parsed as markup.
        self.query_one("#login_status", Static).update(
            Text.assemble(
                "On any computer or phone, open this link:\n\n  ",
                (url, f"link {url}"),
                f"\n\n(or open {code.verification_uri} and enter the code)\n\n",
                "Check that the code shown there is:  ",
                (f" {code.user_code} ", "bold reverse"),
                "\n\nSign in with your Auth0 dashboard account (an Admin of "
                f'{domain}) and approve. The consent screen names the "Auth0 CLI" '
                "application; that is expected. Never approve a code you did not start "
                "yourself.\n\n",
                ("Waiting for approval...", "italic"),
            )
        )

    def _login_failed(self, message: str) -> None:
        self._set_busy(False)
        self.query_one("#login_status", Static).update(
            Text.assemble(
                ("Login failed: ", "bold red"),
                message,
                "\nCheck your entries and try again.",
            )
        )

    def _login_succeeded(
        self, domain: str, access_token: str, temp_app: TemporaryM2MApp | None
    ) -> None:
        self._set_busy(False)
        self.query_one("#login_status", Static).update("")
        self.app.wizard_data.update(
            domain=domain, access_token=access_token, temp_app=temp_app
        )
        self.app.push_screen(GoogleSocialScreen())

    def _set_busy(self, busy: bool) -> None:
        for selector in ("#domain", "#m2m_client_id", "#m2m_client_secret", "#use_m2m"):
            self.query_one(selector).disabled = busy
        self.query_one("#login").disabled = busy or not self.cli_installed


class GoogleSocialScreen(WizardScreen):
    """Collect the optional GCP OAuth client for the google-oauth2 connection."""

    STEP = 2

    def compose(self) -> ComposeResult:
        domain = self.app.wizard_data.get("domain") or "<tenant>.us.auth0.com"
        yield Header()
        with Vertical(id="form"):
            yield Static(
                "Optional: to enable Google social login, Auth0 needs a Google Cloud "
                "Platform (GCP) OAuth 2.0 Client. Without one, Auth0 falls back to "
                "development keys, which are not recommended for production."
            )
            yield Static(
                "In the GCP console, create a project if needed, then create a "
                "Client for a web application (or reuse an existing one under "
                "APIs & Services -> OAuth consent screen -> Clients) and add:"
            )
            yield Static(
                f"  Authorized JavaScript origin:  https://{domain}\n"
                f"  Authorized redirect URI:       https://{domain}/login/callback",
                markup=False,
            )
            yield Static(
                "Then enter that client's ID and secret below, or leave them blank "
                "to skip. See auth0/README.md's 'GCP OAuth client configuration' "
                "section for details."
            )
            yield Label("GCP OAuth client ID")
            yield Input(placeholder="(optional)", id="gcp_client_id")
            yield Label("GCP OAuth client secret")
            yield Input(placeholder="(optional)", password=True, id="gcp_client_secret")
            yield Button("Next", id="next", variant="primary")
        yield Footer(show_command_palette=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "next":
            return
        self.app.wizard_data.update(
            gcp_client_id=self.query_one("#gcp_client_id", Input).value.strip() or None,
            gcp_client_secret=self.query_one("#gcp_client_secret", Input).value.strip()
            or None,
        )
        self.app.push_screen(AppSelectionScreen())


class AppSelectionScreen(WizardScreen):
    """Checklist of which apps to provision Auth0 clients for.

    Pre-checked from whichever keys already exist in the target config,
    mirroring how Deployer.__init__ derives checklist state from config.
    """

    STEP = 3

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static(
                "Select the apps to provision Auth0 clients for.\n"
                "(Roles, the google-oauth2 connection, the GC Metrics M2M client, "
                "and the Post-Login Actions are tenant-wide and always provisioned.)"
            )
            with VerticalScroll():
                for app_key in AUTH0_DOMAIN_APPS:
                    yield Checkbox(
                        APP_DISPLAY_NAMES[app_key],
                        value=app_key in self.app.config,
                        id=f"chk_{app_key}",
                    )
                yield Checkbox(
                    "Windmill",
                    value="windmill-only" in self.app.config,
                    id="chk_windmill",
                )
            yield Button("Next", id="next", variant="primary")
        yield Footer(show_command_palette=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "next":
            return
        selected = [
            app_key
            for app_key in AUTH0_DOMAIN_APPS
            if self.query_one(f"#chk_{app_key}", Checkbox).value
        ]
        self.app.wizard_data["selected_apps"] = selected
        self.app.wizard_data["provision_windmill"] = self.query_one(
            "#chk_windmill", Checkbox
        ).value
        self.app.push_screen(RootDomainScreen())


class RootDomainScreen(WizardScreen):
    """Collect the root domain after the community alias."""

    STEP = 4

    def compose(self) -> ComposeResult:
        alias = self.app.config.get("community_name") or "<alias>"
        yield Header()
        with Vertical(id="form"):
            yield Static(
                f"Enter the root domain your Guardian Connector stack will be served at, after the community alias {alias}, "
                "without an https:// prefix."
            )
            yield Static(
                f"The landing page is served at {alias}.<root domain>, and every "
                f"other app at <app>.{alias}.<root domain>. Auth0 callback URLs "
                "are set to these addresses:"
            )
            yield Static("", id="hosts_preview", markup=False)
            yield Label("Root domain")
            yield Input(
                value=self.app.config.get("gc-landing-page", {}).get("root_domain")
                or "",
                placeholder="guardianconnector.net",
                id="root_domain",
            )
            yield Button("Run", id="run", variant="primary")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        super().on_mount()
        self._update_hosts_preview(self.query_one("#root_domain", Input).value)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_hosts_preview(event.value)

    def _update_hosts_preview(self, root_domain: str) -> None:
        root_domain = root_domain.strip() or "<root domain>"
        data = self.app.wizard_data
        app_keys = list(data.get("selected_apps", []))
        if data.get("provision_windmill"):
            app_keys.append("windmill-only")
        lines = [
            f"  {spec['name']:<16} {spec['web_origins'][0].rstrip('/')}"
            for spec in (
                client_spec_for_app(key, self.app.config, root_domain)
                for key in app_keys
            )
        ]
        self.query_one("#hosts_preview", Static).update(
            "\n".join(lines) or "  (no app clients selected)"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "run":
            return
        root_domain = self.query_one("#root_domain", Input).value.strip()
        if not root_domain or any(c in root_domain for c in "/: "):
            self.notify(
                "Enter a bare domain name, e.g. example.net",
                severity="error",
            )
            return
        self.app.wizard_data["root_domain"] = root_domain
        self.app.push_screen(RunScreen())


class RunScreen(WizardScreen):
    """Streams provisioning progress, then shows a completion summary."""

    STEP = 5

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="run-container"):
            yield RichLog(id="log", highlight=True, markup=True)
            yield Static("", id="summary")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        super().on_mount()
        handler = RichLogHandler(self.query_one("#log", RichLog))
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        logger = logging.getLogger()
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        self._run()

    @work(exclusive=True, thread=True)
    def _run(self) -> None:
        data = self.app.wizard_data
        error = None
        try:
            run_wizard(
                self.app.config,
                self.app.config_file,
                domain=data["domain"],
                # pop: drop the token from memory once used.
                access_token=data.pop("access_token"),
                selected_apps=data["selected_apps"],
                root_domain=data["root_domain"],
                gcp_client_id=data.get("gcp_client_id"),
                gcp_client_secret=data.get("gcp_client_secret"),
                provision_windmill=data.get("provision_windmill", False),
                dry_run=self.app.dry_run,
            )
        except Exception as exc:
            logging.getLogger("gc-stack-deploy.wizard").exception("Wizard run failed")
            error = exc
        self.app.cleanup_temp_app()
        self.app.call_from_thread(self._on_finished, error)

    def _on_finished(self, error: Exception | None) -> None:
        summary = self.query_one("#summary", Static)
        if error is not None:
            summary.update(f"[bold red]Wizard failed:[/bold red] {error}")
        else:
            summary.update(
                f"[bold green]Done.[/bold green] Wrote {self.app.config_file}. "
                "Review it, then run `gc-stack-deploy deploy -c <file>`."
            )


class WizardApp(App):
    CSS = """
    #form {
        padding: 1 2;
        height: auto;
    }
    #form Input {
        margin-bottom: 1;
    }
    #form Static {
      margin-bottom: 1;
    }
    #run-container {
        height: 1fr;
    }
    #log {
        height: 1fr;
    }
    #summary {
        height: auto;
        padding: 1 2;
        border-top: solid $panel;
    }
    """

    def __init__(self, config_file: str, dry_run: bool = False):
        super().__init__()
        self.config_file = config_file
        self.dry_run = dry_run
        self.config = load_config(config_file)
        self.wizard_data: dict = {}

    def on_mount(self) -> None:
        self.push_screen(Auth0LoginScreen())

    def cleanup_temp_app(self) -> None:
        """Delete the temporary M2M app (if the Auth0 CLI login created one), log the CLI out,
        and delete the downloaded CLI.

        Called as soon as provisioning finishes (so the credential doesn't outlive its use
        while the summary stays on screen) and again on exit, so quitting early also cleans
        up. `TemporaryM2MApp.cleanup` is safe to repeat.
        """
        temp_app = self.wizard_data.pop("temp_app", None)
        if temp_app is not None:
            for warning in temp_app.cleanup():
                logging.getLogger("gc-stack-deploy.wizard").warning(warning)
        remove_cli()

    def on_unmount(self) -> None:
        self.cleanup_temp_app()
