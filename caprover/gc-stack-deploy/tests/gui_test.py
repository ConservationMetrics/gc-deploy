import pytest
from gc_stack_deploy.base import AppStatus
from gc_stack_deploy.gui import _derive_status_note


class TestStatusNoteTransientPrecedence:
    """INSTALLING/UNINSTALLING must win regardless of checked, since the
    checkbox can't retroactively change an action already in flight."""

    @pytest.mark.parametrize("checked", [True, False])
    def test_installing_state_ignores_checked(self, checked):
        text, css_class = _derive_status_note(AppStatus.INSTALLING, checked)
        assert text == "installing…"
        assert css_class == "in-progress"

    @pytest.mark.parametrize("checked", [True, False])
    def test_uninstalling_ignores_checked(self, checked):
        text, css_class = _derive_status_note(AppStatus.UNINSTALLING, checked)
        assert text == "uninstalling…"
        assert css_class == "in-progress"


class TestStatusNoteSettledStates:
    """Only settled states (INSTALLED, NOT_INSTALLED, FAILED) should vary
    their note text based on `checked`."""

    def test_installed_checked_is_noop(self):
        text, css_class = _derive_status_note(AppStatus.INSTALLED, True)
        assert text == "currently: installed"
        assert css_class == "currently-installed"

    def test_installed_unchecked_will_uninstall(self):
        text, css_class = _derive_status_note(AppStatus.INSTALLED, False)
        assert text == "will uninstall"
        assert css_class == "will-uninstall"

    def test_not_installed_checked_will_install(self):
        text, css_class = _derive_status_note(AppStatus.NOT_INSTALLED, True)
        assert text == "will install"
        assert css_class == "will-install"

    def test_not_installed_unchecked_is_noop(self):
        text, css_class = _derive_status_note(AppStatus.NOT_INSTALLED, False)
        assert text == "currently: not installed"
        assert css_class == "currently-not-installed"

    def test_failed_checked_will_install(self):
        # Current behavior: FAILED + checked routes through resolve_action's
        # INSTALL branch, same as NOT_INSTALLED. If Problem 1's REINSTALL
        # action is added, this test's expected action changes.
        text, css_class = _derive_status_note(AppStatus.FAILED, True)
        assert text == "will install"
        assert css_class == "will-install"

    def test_failed_unchecked_shows_failed(self):
        text, css_class = _derive_status_note(AppStatus.FAILED, False)
        assert text == AppStatus.FAILED.value.upper()
        assert css_class == "failed"
