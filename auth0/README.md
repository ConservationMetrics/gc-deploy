# Setting up an auth0 tenant for GuardianConnector

GuardianConnector uses [Auth0](https://auth0.com/) for authentication and user management. This guide outlines how to configure a new Auth0 tenant for production use.

## GCP OAuth client configuration

> [!IMPORTANT]
>
> Before you start, make sure that you have access to the right project with the OAuth 2.0 Client on GCP.

You will need a Google Cloud Platform (GCP) OAuth 2.0 Client in order to [avoid using development keys which is not recommended](https://community.auth0.com/t/confusing-dev-keys-error-message-when-using-production-keys/74273).

- If you need to create a new Google Cloud Platform (GCP) OAuth 2.0 Client:
  - Create a project on GCP.
  - Navigage to "Clients", and create a Client for a web application.
- If you already have a GCP OAuth 2.0 Client, then you can add the authorized JavaScript origin and redirect URI for your new tenant (per the formats above).
  - You can find your client by navigating to **APIS & Services** -> **OAuth consent screen** -> **Clients**.
- Add the following settings:
  _ Authorized JavaScript origins:
  `https://<tenant>.us.auth0.com`
  _ Authorized redirect URIs:
  `https://<tenant>.us.auth0.com/login/callback`
- Copy down the Client ID and Secret for your client.

## Auth0 tenant configuration, step by step

1. When creating a new Auth0 tenant, you will need to provide a **Tenant Name** for the tenant, which should match the alias chosen by the community.
    - Additionally, select a **Region** (CMI uses US) and **Environment Tag**: "Production".
2. In **Authentication / Social**, enable google-oauth2 under Social Connections. You will need to provide a Client ID and Secret (see [GCP OAuth client configuration](#gcp-oauth-client-configuration)).
3. In **Settings** → **Tenant Members**, add the email addresses of the desired tenant administrators (for example, CMI engineering team members and programmatic lead(s)).
4. In **Applications**, create a separate Regular Web Application for each tool (e.g., Superset, GC-Explorer). 
   - For each application, give a human readable name (e.g. "Superset", "GC-Explorer", "Windmill", "GC Landing Page").
   - Add appropriate production domain values under Callback URLs, Web Origins, and CORS:
   - For **Superset** (assuming Superset is hosted at the root of your subdomain; otherwise, use the appropriate subdomain i.e. `superset.<domain>.guardianconnector.net`):
     - **Callback URL**: `http://superset.<domain>.guardianconnector.net/oauth-authorized/auth0`
       - 🚨 Yes, you are reading that correctly - Superset requires `http://` instead of `https://` for the callback URL. [See this issue for more details](https://github.com/ConservationMetrics/superset-deployment/issues/51).
     - **Allowed Web Origins**: `https://superset.<domain>.guardianconnector.net/`
   - For **GC-Explorer**:
     - **Callback URL**: `https://explorer.<domain>.guardianconnector.net/login`
     - **Allowed Web Origins**: `https://explorer.<domain>.guardianconnector.net`
   - For **Windmill**:
     - **Callback URL**: `https://windmill.<domain>.guardianconnector.net/user/login_callback/auth0`
     - **Allowed Web Origins**: `https://windmill.<domain>.guardianconnector.net/`
   - For **GC Landing Page**:
     - **Callback URL**: `https://<domain>.guardianconnector.net/login`
     - **Allowed Web Origins**: `https://<domain>.guardianconnector.net`
5. Create a M2M application for metrics with a name like **GC Metrics**, and grant `read:users` and `read:stats` scopes to it.
6. In **Actions**, configure a Login Flow Action to handle user approval. (See [ User Approval Flow](#user-approval-flow) below.)
7. Set up **Role-Based Access Control** for the applications that use it. (See [RBAC Configuration](#rbac-configuration) below.)
8. **Sign in** to an auth0 application with at least one user, who will serve as the initial admin user and can manage approval and roles for others using GC Landing Page. This user should be given the **Admin** role, and be approved (see [Auth0 approval process](#auth0-approval-process) below.)
9. (Optional) in **Branding**, a few minor customizations like adding an organization logo and setting the background color to gray #F9F9F9 instead of standard black.

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
        api.access.deny("Your approval to access the app is pending.");
      }
    };
    ```
4. Name the action "Check Approval".
5. Drag the new action into the flow, so it looks like this:

    ```mermaid
    graph TD
    A[Start: User Logged In] --> B["<> Check Approval"]
    B --> C[Complete: Token Issued]
    ```

## Setting up RBAC

Role-Based Access Control (RBAC) allows you to control user access to different features based on assigned roles. Several of the Guardian Connector applications (e.g. GC-Explorer and GC-Landing Page) use four roles: **Admin**, **Member**, **Viewer**, and **Public**.

### API Configuration

1. Go to **Dashboard > Applications > APIs** and find the "Auth0 Management API" API
2. For that API, go to the **"Application Access"** tab
3. Find your application in the list and click edit navigating to **Client Credentials** tab.
4. For each application, select the required scopes:
   - **GC-Explorer** (read-only access):
     - `read:users` - to fetch user information
     - `read:user_idp_tokens` - to read user roles
     - `read:roles` and `read:role_members` - to read user roles
   - **GC Landing Page** (user management):
     - `read:users` - to fetch user information
     - `read:roles` - to read available roles
     - `read:role_members` - to read which roles users have
     - `create:role_members` - to assign roles to users
     - `delete:role_members` - to remove roles from users
     - `update:users_app_metadata` - to update user approval status

### Role Setup

1. Navigate to **User Management > Roles** in the Auth0 dashboard
2. Click **"+ Create Role"** and create the following roles:
   - **Admin**: "All routes including `/config`"
   - **Member**: "Restricted routes (cannot access `/config`)"
   - **Guest**: "Guest and unrestricted routes only"
   - **SignedIn**: "can access only routes that are set to public"

**Note**: Users without any assigned roles are assigned the **SignedIn** role by GC Explorer and GC Landing Page.

See the GC Explorer [RBAC documentation](https://github.com/ConservationMetrics/gc-explorer/blob/main/docs/auth.md) for more details on role setup.

## Auth0 approval process

1. A user signs up for one of the applications using Auth0, either by email/password or a third-party service (e.g., Google, GitHub).
2. If the user is not yet approved, they will encounter a message such as:
   - “Invalid login” (Superset)
   - “Your approval to access the app is pending” (GC-Explorer)
3. A tenant administrator approves the user:
   - Navigate to **User Management > Users**
   - Select the user
   - In the **App Metadata** section, add:
     ```json
     {
       "approved": true
     }
     ```
4. Once approved, the user can log in to GuardianConnector services.
5. For the GC-Explorer and GC-Landing Page applications: in the **Roles** tab for the user, assign the appropriate role. (Or, alternatively, on the **User Management > Roles** page, you can assign the user to the role.)
6. For Superset, the user is initially assigned the **Alpha** role by default (controlled via the `USER_ROLE` environment variable). A Superset admin can then upgrade the user’s role or share specific dashboards.

## Using Terraform

It is possible to use Terraform to automate much of the above process. Please see the [private `gc-forge` repo](https://github.com/ConservationMetrics/gc-forge/blob/main/terraform/modules/auth0-client/README.md) for more information.
