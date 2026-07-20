import logging
from enum import Enum

from textual import work
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
        # includes NOT_INSTALLED and FAILED
        return Action.INSTALL
    if not checked and is_installed:
        return Action.UNINSTALL
    return Action.NOOP


def _status_note(current: AppStatus, checked: bool) -> str:
    """Text shown next to a checkbox

    Describes what submitting the form will do (install/uninstall if that differs
    from current state), or otherwise describes current state as-is.

    Returns
    -------
    (display text, css class)
    """
    action = resolve_action(current, checked)
    if action is Action.INSTALL:
        return "will install", "will-install"
    if action is Action.UNINSTALL:
        return "will uninstall", "will-uninstall"
    # Action.NOOP: box matches current state, describe that state instead
    if current is AppStatus.FAILED:
        return AppStatus.FAILED.value.upper(), "failed"
    if current is AppStatus.INSTALLED:
        return f"currently: {current.value.replace('_', ' ')}", "currently-installed"
    return f"currently: {current.value.replace('_', ' ')}", "currently-not-installed"


def _apply_status_note(note: Label, current: AppStatus, checked: bool) -> None:
    text, css_class = _status_note(current, checked)
    note.update(text)
    note.set_classes(css_class)


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
        # Grid keeps every row the same width and height
        height: 3;
        width: 100%;
        layout: horizontal;
        content-align: left middle;
    }

    ChecklistScreen .will-install {
        color: $success;
        text-style: italic;
    }

    ChecklistScreen .will-uninstall {
        color: $warning;
        text-style: italic;
    }

    ChecklistScreen .currently-installed {
        color: $text-muted;
        text-style: dim italic;
    }

    ChecklistScreen .currently-not-installed {
        color: $text-muted;
        text-style: dim italic;
    }

    ChecklistScreen .failed {
        color: $error;
        text-style: bold italic;
    }
    """

    def __init__(self, apps_with_config: list[AppSpec], state: StateStore, **kwargs):
        super().__init__(**kwargs)
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
            for appspec in self.apps_with_config:
                app_id = appspec.one_click_app_name
                current = self.state.get(app_id)
                is_installed = current == AppStatus.INSTALLED
                note_text, note_class = _status_note(current, is_installed)

                with Horizontal(classes="app-row"):
                    yield Checkbox("", id=f"chk_{app_id}", value=is_installed)
                    with Vertical(classes="checkbox-lines"):
                        yield Label(Content.styled(appspec.app_name, "bold cyan"))
                        yield Label(
                            note_text,
                            id=f"note_{app_id}",
                            classes=note_class,
                        )

        yield Button("Go", id="go", variant="primary")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Recompute the status note annotation whenever a box is toggled."""
        app_name = event.checkbox.id.removeprefix("chk_")
        current = self.state.get(app_name)
        note = self.query_one(f"#note_{app_name}", Label)
        _apply_status_note(note, current, event.value)

    def sync_to_state(self) -> None:
        """Refresh the Checkboxes to match what's in self.state

        Re-read self.state for every app and refresh checkboxes/notes.
        """
        for appspec in self.apps_with_config:
            app_id = appspec.one_click_app_name
            status = self.state.get(app_id)
            chk = self.query_one(f"#chk_{app_id}", Checkbox)
            chk.value = status == AppStatus.INSTALLED
            note = self.query_one(f"#note_{app_id}", Label)
            _apply_status_note(note, status, chk.value)


class RichLogHandler(logging.Handler):
    """Adapts stdlib logging to a Textual RichLog widget."""

    def __init__(self, log_widget: RichLog):
        super().__init__()
        self.log_widget = log_widget

    def emit(self, record: logging.LogRecord) -> None:
        self.log_widget.write(self.format(record))


class Deployer(App):
    CSS = """
    #main {
        height: 1fr;
    }
    ChecklistScreen {
        width: 40%;
        border-right: solid $panel;
    }
    RichLog {
        width: 1fr;
    }
    """

    def __init__(self, config: dict, ctx: DeploymentContext):
        super().__init__()
        self.config = config
        self.ctx = ctx
        self.state: StateStore = StateStore()

        # Apps in the registry that have a config block, in registry order
        self.apps_with_config = [
            cls(config[cls.one_click_app_name], ctx)  # instantiate!
            for cls in APPS_REGISTRY
            if cls.one_click_app_name in config
        ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            # pass the filtered app list and state store down
            yield ChecklistScreen(self.apps_with_config, self.state, id="checklist")
            yield RichLog(id="log", highlight=True, markup=True)

    def on_mount(self) -> None:
        """Wire up the log handler"""
        # Single scrolling log for the whole run (tabbed per-app logs come later).
        logwindow = self.query_one("#log", RichLog)
        handler = RichLogHandler(logwindow)
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        logger = logging.getLogger()
        logger.handlers.clear()  # An existing StreamHandler to stdout would garble the TUI output.
        logger.addHandler(handler)

    def _on_deploy_finished(self) -> None:
        """Runs on the main thread once _run_deploy returns."""
        self.query_one(ChecklistScreen).sync_to_state()

        # Unlock the Checklist items and Button
        for appspec in self.apps_with_config:
            app_id = appspec.one_click_app_name
            chk = self.query_one(f"#chk_{app_id}", Checkbox)
            chk.disabled = False
        self.query_one("#go", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Go was pressed: partition apps by resolve_action (same function
        the checklist notes used), instantiate only the ones with real work
        to do, and hand off to the run screen."""
        if event.button.id != "go":
            return
        checklist = self.query_one(ChecklistScreen)

        to_install: list[AppSpec] = []
        to_uninstall: list[AppSpec] = []
        for appspec in self.apps_with_config:
            app_id = appspec.one_click_app_name
            checked = checklist.query_one(f"#chk_{app_id}", Checkbox).value
            action = resolve_action(self.state.get(app_id), checked)
            if action is Action.NOOP:
                continue
            (to_install if action is Action.INSTALL else to_uninstall).append(appspec)

        # Lock the checklist so nothing changes mid-run.
        checklist.query_one("#go", Button).disabled = True
        for chk in checklist.query(Checkbox):
            chk.disabled = True

        self.query_one("#log", RichLog).clear()
        self._run_deploy(to_uninstall, to_install)

    @work(exclusive=True, thread=True)
    def _run_deploy(
        self,
        to_uninstall: list[AppSpec],
        to_install: list[AppSpec],
    ) -> None:
        """This Worker uninstalls and installs apps.

        @work(thread=True) moves the entire _run_deploy call onto a worker thread
        managed by Textual. This keeps the event loop free to render frames
        while app.install()/uninstall() block.
        https://textual.textualize.io/guide/workers/#thread-workers

        We are running on a worker thread, so:
        - Every call in this method is a plain synchronous call
        - Never touch app state or widgets directly from here.
          Textual widget/state mutation is only safe on the main thread, so
          we route state updates through call_from_thread.

        """
        # Uninstalls first: This supports the future (TODO) "retry" workflow of
        # uninstall then reinstall the same app in one go.
        for spec in to_uninstall:
            app_id = spec.one_click_app_name
            self.call_from_thread(self.state.set, app_id, AppStatus.UNINSTALLING)
            try:
                raise NotImplementedError()  # TODO spec.uninstall()
                self.call_from_thread(self.state.set, app_id, AppStatus.NOT_INSTALLED)
            except Exception:
                # Log and record FAILED rather than raising: one app's
                # failure shouldn't abort the rest of the batch.
                spec.logger.exception("uninstall failed")
                self.call_from_thread(self.state.set, app_id, AppStatus.FAILED)

        for spec in to_install:
            app_id = spec.one_click_app_name
            self.call_from_thread(self.state.set, app_id, AppStatus.INSTALLING)
            try:
                spec.install()  # Blocking call, runs directly on this worker thread
                self.call_from_thread(self.state.set, app_id, AppStatus.INSTALLED)
            except Exception:
                spec.logger.exception("install failed")
                self.call_from_thread(self.state.set, app_id, AppStatus.FAILED)

        self.call_from_thread(self._on_deploy_finished)
