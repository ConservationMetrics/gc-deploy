# Setting up an auth0 tenant for GuardianConnector

GuardianConnector uses [Auth0](https://auth0.com/) for authentication and user management. This guide outlines how to configure a new Auth0 tenant for production use.

## GCP OAuth client configuration

You will need a Google Cloud Platform (GCP) OAuth 2.0 Client in order to [avoid using development keys which is not recommended](https://community.auth0.com/t/confusing-dev-keys-error-message-when-using-production-keys/74273).

*  If you need to create a new Google Cloud Platform (GCP) OAuth 2.0 Client:
   * Create a project on GCP.
   * Navigage to "Clients", and create a Client for a web application.
* If you already have a GCP OAuth 2.0 Client, then you can add the authorized JavaScript origin and redirect URI for your new tenant (per the formats above).
   * You can find your client by navigating to **APIS & Services** -> **OAuth consent screen** -> **Clients**.
* Add the following settings:
     * Authorized JavaScript origins:
`https://{tenant}.us.auth0.com`
     * Authorized redirect URIs:
`https://{tenant}.us.auth0.com/login/callback`
* Copy down the Client ID and Secret for your client.

## Tenant configuration

1. In **Settings**, select “Production” as the Environment Tag.
2. In **Actions**, configure a Login Flow Action to handle user approval. (See [ User Approval Flow](#user-approval-flow) below.)
4. In **Authentication / Database**, ensure Sign Ups are enabled (they should be enabled by default).
5. In **Authentication / Social**, enable google-oauth2 under Social Connections. You will need to provide a Client ID and Secret (see [GCP OAuth client configuration](#gcp-oauth-client-configuration)).

1.  In **Applications**, create a separate Regular Web Application for each tool (e.g., Superset, GC-Explorer). Add appropriate production domain values under Callback URLs, Web Origins, and CORS.
    * For **Superset** (assuming Superset is hosted at the root of your subdomain; otherwise, use the appropriate subdomain i.e. `superset.{domain}`):
      * **Callback URL**: `http://{domain}.guardianconnector.net/oauth-authorized/auth0` # https://github.com/ConservationMetrics/superset-deployment/issues/51
      * **Allowed Web Origins**: `https://{domain}.guardianconnector.net/`
    * For **GC-Explorer**:
      * **Callback URL**: `https://explorer.{domain}.guardianconnector.net/login`
      * **Allowed Web Origins**: `https://explorer.{domain}.guardianconnector.net`
    * For **Windmill**:
      * **Callback URL**: `https://windmill.{domain}.guardianconnector.net/user/login_callback/auth0`
      * **Allowed Web Origins**: `https://windmill.{domain}.guardianconnector.net/`
2.  (Optional) in **Branding**, a few minor customizations like adding an organization logo and setting the background color to gray #F9F9F9 instead of standard black.

## Using Terraform

It is possible to use Terraform to automate much of the above process. Please see the [private `gc-forge` repo](https://github.com/ConservationMetrics/gc-forge/blob/main/terraform/modules/auth0-client/README.md) for more information.

## User approval flow

To restrict access until a user is approved, a Post-Login Trigger Action is used in Auth0. This action intercepts login attempts and denies access unless the user’s `app_metadata` includes `"approved": true`.

1. On the Auth0 Page, navigate to **Actions -> Triggers** page.
2. Modify the **Post Login** Flow.
3. Create a custom action using this trigger code (influenced by [the Common Use Cases in the auth0 documentation](https://auth0.com/docs/customize/actions/flows-and-triggers/login-flow#common-use-cases)):
  ```jsx
  exports.onExecutePostLogin = async (event, api) => {
    // Check if the user is approved
    if (event.user.app_metadata && event.user.app_metadata.approved) {
      // User is approved, continue without action
    } else {
      api.access.deny('Your approval to access the app is pending.');
    }
  };
  ```

4. Drag the new action into the flow, so it looks like this:
  ```mermaid
  graph TD
  A[Start: User Logged In] --> B["<> Check Approval"]
  B --> C[Complete: Token Issued]
  ```

## Setting up RBAC

Role-Based Access Control (RBAC) allows you to control user access to different features based on assigned roles. Several of the Guardian Connector applications (e.g. GC-Explorer and GC-Landing Page) use four roles: **Admin**, **Member**, **Viewer**, and **Public**.

### API Configuration

1. Go to **Dashboard > Applications > APIs** and find the "Auth0 Management API" API
2. For that API, go to the **"Machine to Machine Applications"** tab
3. Find your application in the list and **Authorize** it
4. For each application, select the required scopes:
   * `read:users` - to fetch user information
   * `read:user_idp_tokens` - to read user roles

### Role Setup

1. Navigate to **User Management > Roles** in the Auth0 dashboard
2. Click **"+ Create Role"** and create the following roles:
   * **Admin**: "can access anything a member can, plus `/config` (in GC Explorer) or user management (in GC Landing Page)"
   * **Member**: "can access both unrestricted and restricted routes"
   * **Viewer**: "can access only unrestricted routes"
   * **Public**: "can access only routes that are set to public"

**Note**: Users without any assigned roles are treated as having Public-level access.

## Auth0 approval process

1. A user signs up for one of the applications using Auth0, either by email/password or a third-party service (e.g., Google, GitHub).
2. If the user is not yet approved, they will encounter a message such as:
   * “Invalid login” (Superset)
   * “Your approval to access the app is pending” (GC-Explorer)
3. A tenant administrator approves the user:
   * Navigate to **User Management > Users**
   * Select the user
   * In the **App Metadata** section, add:
     ```json
     {
     "approved": true
     }
     ```
4. Once approved, the user can log in to GuardianConnector services.
5. For the GC-Explorer and GC-Landing Page applications: in the **Roles** tab for the user, assign the appropriate role. (Or, alternatively, on the **User Management > Roles** page, you can assign the user to the role.)
6. For Superset, the user is initially assigned the **Alpha** role by default (controlled via the `USER_ROLE` environment variable). A Superset admin can then upgrade the user’s role or share specific dashboards.

TODO: Figure out a more user-friendly way to approve new users that doesn't require logging in to auth0 and editing App Metadata JSON.