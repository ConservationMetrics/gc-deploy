"""Textual screens for `gc-stack-deploy wizard`, and the WizardApp entry point.

Five screens, pushed in sequence, each handing its collected answers forward
to the next: bootstrap credentials -> Google social login -> app selection ->
root domain -> run.
"""

import logging

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
    RichLog,
    Static,
)

from ..gui import RichLogHandler
from .orchestrator import client_spec_for_app, run_wizard
from .yaml_writer import load_config

SELECTABLE_APPS = [
    ("superset-only", "Superset"),
    ("gc-landing-page", "GC Landing Page"),
    ("gc-explorer", "GC-Explorer"),
]


class BootstrapCredentialsScreen(Screen):
    """Collect the Auth0 tenant domain and bootstrap M2M credentials."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("First, create an Auth0 tenant if you don't have one yet.")
            yield Static(
                "Then create a Machine-to-Machine application named "
                "'gc-stack-deploy' in that tenant, authorized against the Auth0 "
                "Management API with the permissions listed in auth0/README.md's "
                "'Bootstrap M2M application for the wizard' section. You only "
                "need to do this once per tenant."
            )
            yield Static(
                "Finally, enter the tenant domain and that M2M application's "
                "credentials below."
            )
            yield Label("Auth0 tenant domain (e.g. your-tenant.us.auth0.com)")
            yield Input(placeholder="your-tenant.us.auth0.com", id="domain")
            yield Label("gc-stack-deploy M2M client ID")
            yield Input(placeholder="client id", id="bootstrap_client_id")
            yield Label("gc-stack-deploy M2M client secret")
            yield Input(
                placeholder="client secret", password=True, id="bootstrap_client_secret"
            )
            yield Button("Next", id="next", variant="primary")
        yield Footer(show_command_palette=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "next":
            return
        self.app.wizard_data.update(
            domain=self.query_one("#domain", Input).value.strip(),
            bootstrap_client_id=self.query_one(
                "#bootstrap_client_id", Input
            ).value.strip(),
            bootstrap_client_secret=self.query_one(
                "#bootstrap_client_secret", Input
            ).value.strip(),
        )
        self.app.push_screen(GoogleSocialScreen())


class GoogleSocialScreen(Screen):
    """Collect the optional GCP OAuth client for the google-oauth2 connection."""

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


class AppSelectionScreen(Screen):
    """Checklist of which apps to provision Auth0 clients for.

    Pre-checked from whichever keys already exist in the target config,
    mirroring how Deployer.__init__ derives checklist state from config.
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static(
                "Select the apps to provision Auth0 clients for.\n"
                "(Roles, the google-oauth2 connection, the GC Metrics M2M client, "
                "and the Post-Login Actions are tenant-wide and always provisioned.)"
            )
            with VerticalScroll():
                for app_key, display_name in SELECTABLE_APPS:
                    yield Checkbox(
                        display_name,
                        value=app_key in self.app.config,
                        id=f"chk_{app_key}",
                    )
                yield Checkbox(
                    "Windmill (no stack.yaml field -- id/secret are printed at the end for you"
                    " to wire in manually)",
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
            for app_key, _ in SELECTABLE_APPS
            if self.query_one(f"#chk_{app_key}", Checkbox).value
        ]
        self.app.wizard_data["selected_apps"] = selected
        self.app.wizard_data["provision_windmill"] = self.query_one(
            "#chk_windmill", Checkbox
        ).value
        self.app.push_screen(RootDomainScreen())


class RootDomainScreen(Screen):
    """Collect the root domain that the Auth0 clients' callback URLs are built from."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static(
                "Enter the root domain your Guardian Connector stack will be served "
                "at, e.g. springfield.guardianconnector.net. Just the domain name: "
                "no https://, no path."
            )
            yield Static(
                "GC Landing Page is served at the root domain itself, and every "
                "other app at its own subdomain of it. Each Auth0 client's "
                "callback URL and allowed origins are set to these addresses, so "
                "they must match where the apps will actually be reachable:"
            )
            yield Static("", id="hosts_preview", markup=False)
            yield Label("Root domain")
            yield Input(
                value=self.app.config.get("gc-landing-page", {}).get("root_domain")
                or "",
                placeholder="springfield.guardianconnector.net",
                id="root_domain",
            )
            yield Static(
                "This is also written to gc-landing-page.root_domain in your "
                "config file."
            )
            yield Button("Run", id="run", variant="primary")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
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
                "Enter a bare domain name, e.g. springfield.guardianconnector.net",
                severity="error",
            )
            return
        self.app.wizard_data["root_domain"] = root_domain
        self.app.push_screen(RunScreen())


class RunScreen(Screen):
    """Streams provisioning progress, then shows a completion summary."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="run-container"):
            yield RichLog(id="log", highlight=True, markup=True)
            yield Static("", id="summary")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
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
                bootstrap_client_id=data["bootstrap_client_id"],
                bootstrap_client_secret=data["bootstrap_client_secret"],
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
        self.push_screen(BootstrapCredentialsScreen())
