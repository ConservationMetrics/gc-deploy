from types import SimpleNamespace
from unittest.mock import MagicMock

from gc_stack_deploy.wizard.auth0.provisioning import (
    ADD_ROLES_CLAIM_ACTION_NAME,
    CHECK_APPROVAL_ACTION_NAME,
    ClientResult,
    ensure_client,
    ensure_google_connection,
    ensure_management_api_grant,
    ensure_post_login_actions,
    ensure_roles,
)


def make_mgmt():
    mgmt = MagicMock()
    mgmt.clients.list.return_value = []
    mgmt.connections.list.return_value = []
    mgmt.roles.list.return_value = []
    mgmt.client_grants.list.return_value = []
    mgmt.actions.list.return_value = []
    mgmt.actions.triggers.bindings.list.return_value = []
    # Auth0's update response reflects the (unchanged) id of the action updated.
    mgmt.actions.update.side_effect = lambda id, **kwargs: SimpleNamespace(id=id)
    return mgmt


class TestEnsureClient:
    def test_creates_when_not_found(self):
        mgmt = make_mgmt()
        mgmt.clients.create.return_value = SimpleNamespace(
            client_id="new-id", client_secret="new-secret"
        )

        result = ensure_client(
            mgmt,
            "Superset",
            "regular_web",
            callbacks=["http://superset.example.net/oauth-authorized/auth0"],
            web_origins=["https://superset.example.net/"],
            allowed_origins=["https://superset.example.net/"],
        )

        assert result == ClientResult("new-id", "new-secret", True)
        kwargs = mgmt.clients.create.call_args.kwargs
        assert kwargs["name"] == "Superset"
        assert kwargs["callbacks"] == ["http://superset.example.net/oauth-authorized/auth0"]
        mgmt.clients.update.assert_not_called()

    def test_updates_safe_fields_and_reuses_known_secret(self):
        mgmt = make_mgmt()
        mgmt.clients.list.return_value = [
            SimpleNamespace(client_id="existing-id", name="Superset")
        ]

        result = ensure_client(
            mgmt,
            "Superset",
            "regular_web",
            callbacks=["http://superset.example.net/oauth-authorized/auth0"],
            existing_secret="known-secret",
        )

        assert result == ClientResult("existing-id", "known-secret", False)
        mgmt.clients.create.assert_not_called()
        mgmt.clients.update.assert_called_once()
        assert mgmt.clients.update.call_args.args[0] == "existing-id"

    def test_no_known_secret_warns_and_leaves_blank(self, caplog):
        mgmt = make_mgmt()
        mgmt.clients.list.return_value = [
            SimpleNamespace(client_id="existing-id", name="Superset")
        ]

        with caplog.at_level("WARNING"):
            result = ensure_client(mgmt, "Superset", "regular_web", existing_secret=None)

        assert result.client_secret is None
        assert result.created is False
        assert any("no known secret" in r.message for r in caplog.records)


class TestEnsureGoogleConnection:
    def test_creates_when_absent(self):
        mgmt = make_mgmt()
        mgmt.connections.create.return_value = SimpleNamespace(id="conn-1")
        ensure_google_connection(mgmt, "gcp-id", "gcp-secret")
        mgmt.connections.create.assert_called_once()
        kwargs = mgmt.connections.create.call_args.kwargs
        assert kwargs["strategy"] == "google-oauth2"
        assert kwargs["options"] == {"client_id": "gcp-id", "client_secret": "gcp-secret"}
        mgmt.connections.update.assert_not_called()

    def test_updates_when_present(self):
        mgmt = make_mgmt()
        mgmt.connections.list.return_value = [
            SimpleNamespace(id="conn-1", strategy="google-oauth2")
        ]
        ensure_google_connection(mgmt, "gcp-id", "gcp-secret")
        mgmt.connections.update.assert_called_once_with(
            "conn-1", options={"client_id": "gcp-id", "client_secret": "gcp-secret"}
        )
        mgmt.connections.create.assert_not_called()


class TestEnsureManagementApiGrant:
    def test_creates_when_absent(self):
        mgmt = make_mgmt()
        ensure_management_api_grant(mgmt, "tenant.us.auth0.com", "client-1", ["read:users"])
        mgmt.client_grants.create.assert_called_once_with(
            client_id="client-1",
            audience="https://tenant.us.auth0.com/api/v2/",
            scope=["read:users"],
        )

    def test_updates_when_present(self):
        mgmt = make_mgmt()
        mgmt.client_grants.list.return_value = [SimpleNamespace(id="grant-1")]
        ensure_management_api_grant(mgmt, "tenant.us.auth0.com", "client-1", ["read:users"])
        mgmt.client_grants.update.assert_called_once_with("grant-1", scope=["read:users"])
        mgmt.client_grants.create.assert_not_called()


class TestEnsureRoles:
    def test_creates_missing_roles(self):
        mgmt = make_mgmt()
        mgmt.roles.create.side_effect = [SimpleNamespace(id=f"role-{i}") for i in range(4)]
        role_ids = ensure_roles(mgmt)
        assert set(role_ids) == {"Admin", "Member", "Guest", "SignedIn"}
        assert mgmt.roles.create.call_count == 4

    def test_reuses_existing_roles(self):
        mgmt = make_mgmt()
        mgmt.roles.list.return_value = [
            SimpleNamespace(id="existing-admin", name="Admin"),
            SimpleNamespace(id="existing-member", name="Member"),
            SimpleNamespace(id="existing-guest", name="Guest"),
            SimpleNamespace(id="existing-signedin", name="SignedIn"),
        ]
        role_ids = ensure_roles(mgmt)
        assert role_ids["Admin"] == "existing-admin"
        mgmt.roles.create.assert_not_called()


class TestEnsurePostLoginActions:
    def test_creates_deploys_and_binds_both_actions(self):
        mgmt = make_mgmt()
        mgmt.actions.create.side_effect = [
            SimpleNamespace(id="action-approval"),
            SimpleNamespace(id="action-roles"),
        ]

        ensure_post_login_actions(mgmt)

        assert mgmt.actions.create.call_count == 2
        names = [call.kwargs["name"] for call in mgmt.actions.create.call_args_list]
        assert names == [CHECK_APPROVAL_ACTION_NAME, ADD_ROLES_CLAIM_ACTION_NAME]
        assert mgmt.actions.deploy.call_count == 2
        mgmt.actions.triggers.bindings.update_many.assert_called_once()
        bindings = mgmt.actions.triggers.bindings.update_many.call_args.kwargs["bindings"]
        assert len(bindings) == 2
        assert {b["ref"]["value"] for b in bindings} == {"action-approval", "action-roles"}

    def test_does_not_rebind_already_bound_actions(self):
        mgmt = make_mgmt()
        mgmt.actions.list.return_value = [
            SimpleNamespace(id="action-approval", name=CHECK_APPROVAL_ACTION_NAME),
        ]
        mgmt.actions.triggers.bindings.list.return_value = [
            SimpleNamespace(
                action=SimpleNamespace(id="action-approval", name=CHECK_APPROVAL_ACTION_NAME),
                display_name=CHECK_APPROVAL_ACTION_NAME,
            )
        ]
        mgmt.actions.create.side_effect = [SimpleNamespace(id="action-roles")]

        ensure_post_login_actions(mgmt)

        mgmt.actions.triggers.bindings.update_many.assert_called_once()
        bindings = mgmt.actions.triggers.bindings.update_many.call_args.kwargs["bindings"]
        assert len(bindings) == 2
        values = {b["ref"]["value"] for b in bindings}
        assert values == {"action-approval", "action-roles"}

    def test_no_update_when_both_already_bound(self):
        mgmt = make_mgmt()
        mgmt.actions.list.return_value = [
            SimpleNamespace(id="action-approval", name=CHECK_APPROVAL_ACTION_NAME),
            SimpleNamespace(id="action-roles", name=ADD_ROLES_CLAIM_ACTION_NAME),
        ]
        mgmt.actions.triggers.bindings.list.return_value = [
            SimpleNamespace(
                action=SimpleNamespace(id="action-approval", name=CHECK_APPROVAL_ACTION_NAME),
                display_name=None,
            ),
            SimpleNamespace(
                action=SimpleNamespace(id="action-roles", name=ADD_ROLES_CLAIM_ACTION_NAME),
                display_name=None,
            ),
        ]

        ensure_post_login_actions(mgmt)

        mgmt.actions.triggers.bindings.update_many.assert_not_called()
