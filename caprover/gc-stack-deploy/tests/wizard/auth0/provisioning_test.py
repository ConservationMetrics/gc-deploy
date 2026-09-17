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
    mgmt.clients.all.return_value = []
    mgmt.connections.all.return_value = []
    mgmt.roles.list.return_value = {"roles": []}
    mgmt.client_grants.all.return_value = []
    mgmt.actions.get_actions.return_value = {"actions": []}
    mgmt.actions.get_trigger_bindings.return_value = {"bindings": []}
    # Auth0's update_action response reflects the (unchanged) id of the action updated.
    mgmt.actions.update_action.side_effect = lambda id, body: {"id": id}
    return mgmt


class TestEnsureClient:
    def test_creates_when_not_found(self):
        mgmt = make_mgmt()
        mgmt.clients.create.return_value = {"client_id": "new-id", "client_secret": "new-secret"}

        result = ensure_client(
            mgmt,
            "Superset",
            "regular_web",
            callbacks=["http://superset.example.net/oauth-authorized/auth0"],
            web_origins=["https://superset.example.net/"],
            allowed_origins=["https://superset.example.net/"],
        )

        assert result == ClientResult("new-id", "new-secret", True)
        created_body = mgmt.clients.create.call_args[0][0]
        assert created_body["name"] == "Superset"
        assert created_body["callbacks"] == ["http://superset.example.net/oauth-authorized/auth0"]
        mgmt.clients.update.assert_not_called()

    def test_updates_safe_fields_and_reuses_known_secret(self):
        mgmt = make_mgmt()
        mgmt.clients.all.return_value = [{"client_id": "existing-id", "name": "Superset"}]

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
        assert mgmt.clients.update.call_args[0][0] == "existing-id"

    def test_no_known_secret_warns_and_leaves_blank(self, caplog):
        mgmt = make_mgmt()
        mgmt.clients.all.return_value = [{"client_id": "existing-id", "name": "Superset"}]

        with caplog.at_level("WARNING"):
            result = ensure_client(mgmt, "Superset", "regular_web", existing_secret=None)

        assert result.client_secret is None
        assert result.created is False
        assert any("no known secret" in r.message for r in caplog.records)


class TestEnsureGoogleConnection:
    def test_creates_when_absent(self):
        mgmt = make_mgmt()
        mgmt.connections.create.return_value = {"id": "conn-1"}
        ensure_google_connection(mgmt, "gcp-id", "gcp-secret")
        mgmt.connections.create.assert_called_once()
        body = mgmt.connections.create.call_args[0][0]
        assert body["strategy"] == "google-oauth2"
        assert body["options"] == {"client_id": "gcp-id", "client_secret": "gcp-secret"}
        mgmt.connections.update.assert_not_called()

    def test_updates_when_present(self):
        mgmt = make_mgmt()
        mgmt.connections.all.return_value = [{"id": "conn-1", "strategy": "google-oauth2"}]
        ensure_google_connection(mgmt, "gcp-id", "gcp-secret")
        mgmt.connections.update.assert_called_once_with(
            "conn-1", {"options": {"client_id": "gcp-id", "client_secret": "gcp-secret"}}
        )
        mgmt.connections.create.assert_not_called()


class TestEnsureManagementApiGrant:
    def test_creates_when_absent(self):
        mgmt = make_mgmt()
        ensure_management_api_grant(mgmt, "tenant.us.auth0.com", "client-1", ["read:users"])
        mgmt.client_grants.create.assert_called_once_with(
            {
                "client_id": "client-1",
                "audience": "https://tenant.us.auth0.com/api/v2/",
                "scope": ["read:users"],
            }
        )

    def test_updates_when_present(self):
        mgmt = make_mgmt()
        mgmt.client_grants.all.return_value = [{"id": "grant-1"}]
        ensure_management_api_grant(mgmt, "tenant.us.auth0.com", "client-1", ["read:users"])
        mgmt.client_grants.update.assert_called_once_with("grant-1", {"scope": ["read:users"]})
        mgmt.client_grants.create.assert_not_called()


class TestEnsureRoles:
    def test_creates_missing_roles(self):
        mgmt = make_mgmt()
        mgmt.roles.create.side_effect = [{"id": f"role-{i}"} for i in range(4)]
        role_ids = ensure_roles(mgmt)
        assert set(role_ids) == {"Admin", "Member", "Guest", "SignedIn"}
        assert mgmt.roles.create.call_count == 4

    def test_reuses_existing_roles(self):
        mgmt = make_mgmt()
        mgmt.roles.list.return_value = {
            "roles": [
                {"id": "existing-admin", "name": "Admin"},
                {"id": "existing-member", "name": "Member"},
                {"id": "existing-guest", "name": "Guest"},
                {"id": "existing-signedin", "name": "SignedIn"},
            ]
        }
        role_ids = ensure_roles(mgmt)
        assert role_ids["Admin"] == "existing-admin"
        mgmt.roles.create.assert_not_called()


class TestEnsurePostLoginActions:
    def test_creates_deploys_and_binds_both_actions(self):
        mgmt = make_mgmt()
        mgmt.actions.create_action.side_effect = [
            {"id": "action-approval"},
            {"id": "action-roles"},
        ]

        ensure_post_login_actions(mgmt)

        assert mgmt.actions.create_action.call_count == 2
        names = [call.args[0]["name"] for call in mgmt.actions.create_action.call_args_list]
        assert names == [CHECK_APPROVAL_ACTION_NAME, ADD_ROLES_CLAIM_ACTION_NAME]
        assert mgmt.actions.deploy_action.call_count == 2
        mgmt.actions.update_trigger_bindings.assert_called_once()
        bindings = mgmt.actions.update_trigger_bindings.call_args[0][1]["bindings"]
        assert len(bindings) == 2
        assert {b["ref"]["value"] for b in bindings} == {"action-approval", "action-roles"}

    def test_does_not_rebind_already_bound_actions(self):
        mgmt = make_mgmt()
        mgmt.actions.get_actions.return_value = {
            "actions": [
                {"id": "action-approval", "name": CHECK_APPROVAL_ACTION_NAME},
            ]
        }
        mgmt.actions.get_trigger_bindings.return_value = {
            "bindings": [
                {
                    "action": {"id": "action-approval", "name": CHECK_APPROVAL_ACTION_NAME},
                    "display_name": CHECK_APPROVAL_ACTION_NAME,
                }
            ]
        }
        mgmt.actions.create_action.side_effect = [{"id": "action-roles"}]

        ensure_post_login_actions(mgmt)

        mgmt.actions.update_trigger_bindings.assert_called_once()
        bindings = mgmt.actions.update_trigger_bindings.call_args[0][1]["bindings"]
        assert len(bindings) == 2
        values = {b["ref"]["value"] for b in bindings}
        assert values == {"action-approval", "action-roles"}

    def test_no_update_when_both_already_bound(self):
        mgmt = make_mgmt()
        mgmt.actions.get_actions.return_value = {
            "actions": [
                {"id": "action-approval", "name": CHECK_APPROVAL_ACTION_NAME},
                {"id": "action-roles", "name": ADD_ROLES_CLAIM_ACTION_NAME},
            ]
        }
        mgmt.actions.get_trigger_bindings.return_value = {
            "bindings": [
                {"action": {"id": "action-approval", "name": CHECK_APPROVAL_ACTION_NAME}},
                {"action": {"id": "action-roles", "name": ADD_ROLES_CLAIM_ACTION_NAME}},
            ]
        }

        ensure_post_login_actions(mgmt)

        mgmt.actions.update_trigger_bindings.assert_not_called()
