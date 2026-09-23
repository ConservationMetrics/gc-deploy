"""Textual screens for `gc-stack-deploy wizard`, and the WizardApp entry point.

Four screens, pushed in sequence, each handing its collected answers forward
to the next: bootstrap credentials -> app selection -> deployment inputs -> run.
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
from .orchestrator import run_wizard
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
        self.app.push_screen(DeploymentInputsScreen())


class DeploymentInputsScreen(Screen):
    """Root domain, community name, admin email, and optional GCP OAuth creds."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Label("Root domain (e.g. your-captain-root.net)")
            yield Input(
                value=self.app.config.get("gc-landing-page", {}).get("root_domain")
                or "",
                id="root_domain",
            )
            yield Label("Community name (URL slug/alias)")
            yield Input(
                value=self.app.config.get("community_name") or "", id="community_name"
            )
            yield Label("Admin email")
            yield Input(
                value=self.app.config.get("superset-only", {}).get("admin_email") or "",
                id="admin_email",
            )
            yield Static(
                "Optional: GCP OAuth client for Google social login "
                "(leave blank to skip -- see auth0/README.md's GCP OAuth client section)."
            )
            yield Label("GCP OAuth client ID")
            yield Input(placeholder="(optional)", id="gcp_client_id")
            yield Label("GCP OAuth client secret")
            yield Input(placeholder="(optional)", password=True, id="gcp_client_secret")
            yield Button("Run", id="run", variant="primary")
        yield Footer(show_command_palette=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "run":
            return
        self.app.wizard_data.update(
            root_domain=self.query_one("#root_domain", Input).value.strip(),
            community_name=self.query_one("#community_name", Input).value.strip(),
            admin_email=self.query_one("#admin_email", Input).value.strip(),
            gcp_client_id=self.query_one("#gcp_client_id", Input).value.strip() or None,
            gcp_client_secret=self.query_one("#gcp_client_secret", Input).value.strip()
            or None,
        )
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
                community_name=data["community_name"],
                admin_email=data["admin_email"],
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
