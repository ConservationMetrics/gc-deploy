import logging
from enum import Enum

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Button, Checkbox, Header, Label, RichLog, Static

from .apps_registry import APPS_REGISTRY
from .base import AppSpec, DeploymentContext


class AppStatus(str, Enum):
    NOT_INSTALLED = "not installed"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    UNINSTALLING = "uninstalling"


class Action(Enum):
    INSTALL = "install"
    UNINSTALL = "uninstall"
    NOOP = "noop"


def resolve_action(current: AppStatus, checked: bool) -> Action:
    """The single source of truth for what a checkbox state means, given
    where the app currently stands. Both the UI note and the actual
    install/uninstall dispatch read from this, so they can't disagree."""
    is_installed = current == AppStatus.INSTALLED
    if checked and not is_installed:
        return Action.INSTALL
    if not checked and is_installed:
        return Action.UNINSTALL
    return Action.NOOP


class StateStore:
    """In-memory per-app status tracking."""

    def __init__(self):
        self._data: dict[str, AppStatus] = {}

    def get(self, name: str) -> AppStatus:
        """Status for an app, defaulting to NOT_INSTALLED if never touched."""
        return self._data.get(name, AppStatus.NOT_INSTALLED)

    def set(self, name: str, status: AppStatus) -> None:
        """Record a new status for an app."""
        self._data[name] = status


class ChecklistScreen(Vertical):
    """Shows one row per app-with-config; each row is a checkbox plus a
    state-change annotation ('will install', 'will uninstall', or blank
    if the checkbox matches current state)."""

    # Grid keeps every row the same width; CSS below caps row height at 2 lines.
    DEFAULT_CSS = """
    ChecklistScreen {
        height: auto;
    }
    #app_grid {
        grid-size: 1;
        grid-gutter: 0;
        height: auto;
    }
    .app-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        content-align: left middle;
    }
    """

    def __init__(self, apps_with_config: list[type[AppSpec]], state: StateStore):
        super().__init__()
        # Only apps with a config block reach the UI; others are skipped entirely,
        # so there's no way to check a box for an app that can't actually run.
        self.apps_with_config = apps_with_config
        self.state = state

    def compose(self) -> ComposeResult:
        """Build one row per installable app, then a Go button."""
        yield Static(
            "Check the apps you want installed. "
            # TODO: "Unchecking an app that is currently installed will uninstall it. "
            "Nothing changes until you press Go.",
            id="instructions",
        )
        with VerticalScroll():
            for cls in self.apps_with_config:
                current = self.state.get(cls.one_click_app_name)
                is_installed = current == AppStatus.INSTALLED
                with Horizontal(classes="app-row"):
                    yield Checkbox(
                        "",
                        id=f"chk_{cls.one_click_app_name}",
                    )
                    with Vertical(classes="checkbox-lines"):
                        yield Label(Content.styled(cls.one_click_app_name, "bold cyan"))
                        yield Label(
                            Content.styled(
                                self._status_note(current, is_installed), "dim italic"
                            ),
                            id=f"note_{cls.one_click_app_name}",
                        )
        yield Button("Go", id="go", variant="primary")

    def _status_note(self, current: AppStatus, checked: bool) -> str:
        """Text shown next to a checkbox

        Describes what submitting the form will do (install/uninstall if that differs
        from current state), or otherwise describes current state as-is.
        """
        action = resolve_action(current, checked)
        if action is Action.INSTALL:
            return "will install"
        if action is Action.UNINSTALL:
            return "will uninstall"
        # Action.NOOP: box matches current state, describe that state instead
        return f"currently: {current.value.replace('_', ' ')}"

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Recompute the status note annotation whenever a box is toggled."""
        app_name = event.checkbox.id.removeprefix("chk_")
        current = self.state.get(app_name)
        note = self.query_one(f"#note_{app_name}", Static)
        note.update(self._status_note(current, event.value))


class RichLogHandler(logging.Handler):
    """Adapts stdlib logging to a Textual RichLog widget."""

    def __init__(self, log_widget: RichLog):
        super().__init__()
        self.log_widget = log_widget

    def emit(self, record: logging.LogRecord) -> None:
        self.log_widget.write(self.format(record))


class Deployer(App):
    def __init__(self, config: dict, ctx: DeploymentContext):
        super().__init__()
        self.config = config
        self.ctx = ctx
        self.state: StateStore = StateStore()

        # Apps in the registry that have a config block, in registry order
        self.apps_with_config = [
            cls for cls in APPS_REGISTRY if cls.one_click_app_name in config
        ]

    def compose(self) -> ComposeResult:
        """Entry screen: pass the filtered app list and state store down
        so the checklist can render current-state annotations."""
        yield Header()
        yield ChecklistScreen(self.apps_with_config, self.state)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Go was pressed: partition apps by resolve_action (same function
        the checklist notes used), instantiate only the ones with real work
        to do, and hand off to the run screen."""
        if event.button.id != "go":
            return
        checklist = self.query_one(ChecklistScreen)

        to_install: list[AppSpec] = []
        to_uninstall: list[AppSpec] = []
        for cls in self.apps_with_config:
            app_name = cls.one_click_app_name
            checked = checklist.query_one(f"#chk_{app_name}", Checkbox).value
            action = resolve_action(self.state.get(app_name), checked)
            if action is Action.NOOP:
                continue
            appspec = cls(app_config=self.config[app_name], ctx=self.ctx)
            (to_install if action is Action.INSTALL else to_uninstall).append(appspec)

        self.run_worker(self._run_deploy(to_uninstall, to_install), exclusive=True)

    async def _run_deploy(
        self,
        to_uninstall: list[AppSpec],
        to_install: list[AppSpec],
    ) -> None:
        """Run uninstalls first, then installs."""
        await self.query_one(ChecklistScreen).remove()

        # Single scrolling log for the whole run (tabbed per-app logs come later).
        # Mounting this is what was missing — without it there's nothing on
        # screen after the checklist is removed, and no visible output at all.
        log = RichLog()
        await self.mount(log)
        handler = RichLogHandler(log)
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        logging.getLogger("deploy").addHandler(handler)

        # Uninstalls first: This supports the future (TODO) "retry" workflow of
        # uninstall then reinstall the same app in one go.
        for spec in to_uninstall:
            self.state.set(spec.one_click_app_name, AppStatus.UNINSTALLING)
            try:
                raise NotImplementedError()  # TODO spec.uninstall()
                self.state.set(spec.one_click_app_name, AppStatus.NOT_INSTALLED)
            except Exception:
                # Log and record FAILED rather than raising: one app's
                # failure shouldn't abort the rest of the batch.
                spec.logger.exception("uninstall failed")
                self.state.set(spec.one_click_app_name, AppStatus.FAILED)

        for spec in to_install:
            self.state.set(spec.one_click_app_name, AppStatus.INSTALLING)
            try:
                spec.install()
                self.state.set(spec.one_click_app_name, AppStatus.INSTALLED)
            except Exception:
                spec.logger.exception("install failed")
                self.state.set(spec.one_click_app_name, AppStatus.FAILED)
