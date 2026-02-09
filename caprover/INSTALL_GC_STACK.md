# Guardian Connector Software Stack Setup on CapRover

This guide walks you through setting up your custom Guardian Connector software stack on a fresh virtual machine (VM) using CapRover.

## Prerequisite: Install CapRover

See [INSTALL_CAPROVER_ON_NEW_VM.md](INSTALL_CAPROVER_ON_NEW_VM.md) if you haven't already configured a new VM running CapRover.

## Add apps to CapRover

**You have two options to install apps:**

1. install the entire stack using one script: **`gc-stack-deploy`**
2. install apps one-at-a-time through the CapRover UI

### Option 1. Installing the entire stack with **`gc-stack-deploy`**

If you don't want to sweat the details, it's much quicker to deploy the Guardian Connector stack of apps using the `gc-stack-deploy`.

Unless your SQL database is on another host, the tool must be run on the same machine where CapRover is running. 

#### Install the tool

On most systems you can install directly with pip:

```sh
pip install "gc-stack-deploy @ git+https://github.com/ConservationMetrics/gc-deploy.git@main#subdirectory=caprover/gc-stack-deploy"
```

#### If pip is blocked (common on some VMs)

Some environments (like fresh Ubuntu VMs) restrict `pip install` into the system Python. In that case, use `pipx`
to install the tool:

```sh
sudo apt install pipx -y
pipx install "gc-stack-deploy @ git+https://github.com/ConservationMetrics/gc-deploy.git@main#subdirectory=caprover/gc-stack-deploy"
```

**Note**: pipx installs apps into `~/.local/bin`. If you see `gc-stack-deploy: command not found`, add it to your PATH:

```sh
export PATH=$HOME/.local/bin:$PATH
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
```

Then, restart your shell or run `exec $SHELL -l`. Now you can run `gc-stack-deploy` from any directory.

(Alternatively, you could create a venv to install the tool into, and then add it to your PATH.)

#### Create a `stack.yaml` configuration file

You must create a `stack.yaml` configuration file of for your new deployment. The configuration
file lets you set secrets and API keys, and configure which apps you want.  Write an example template
to your local directory by running `gc-stack-deploy init --config-file «destination.yaml»`.

```sh
gc-stack-deploy init --config-file stack.yaml
```
Then open the file (you could use `nano` or `vi`) and fill in the blanks.

Finally you are ready to use this same configuration file to deploy the apps to CapRover,
running on the same machine.

```sh
# First, dry-run to check for misconfigurations
gc-stack-deploy --config-file stack.yaml --dry-run
# Then repeat without --dry-run
```

If the script ran successfully, you can proceed to the [Post-install app configuration section](#post-install-app-configuration).

> [!TIP]
> If something goes wrong in the middle of the `gc-stack-deploy` script, you have several options:
> - You can delete the app from CapRover and redeploy it using the `gc-stack-deploy` script. For any applications that were installed successfully, you can set `deploy: false` in the `stack.yaml` file to skip them in the next run. In doing so, please pay careful attention to any app-specific instructions (i.e., providing a host and port for Postgres).
> - You can manually install the apps using the one-click app install menu. See [Manually installing apps section](#manually-installing-apps) for more details.

#### What could go wrong?

It has been observed that...
- the script can time out before a Docker image successfully pulls and builds
- the script fails to enable SSL for a given webapp

In both cases, trying to run the script again typically fixes the issue. For the case of the Docker image building, you can actually monitor the build progress in the CapRover web portal under **Apps** → **Deployment**.

### Option 2. Install One-Click Apps through the CapRover UI

#### Runtime Prerequisite

1. In your CapRover web dashboard, navigate to **Apps** → **Create A New App** → **One-Click Apps/Databases**.
2. At the very bottom of the Apps list, find **3rd party repositories**. Enter the URL:
    > `https://conservationmetrics.github.io/gc-deploy/one-click-apps`
3. **Connect New Repostory** and refresh the page. You can now browse and install Guardian Connector apps directly from CapRover.

#### Install apps as One-Click Apps

From the CapRover, navigate to **Apps** and "One-Click Apps/Database".

Install each of the following apps in turn, paying attention to the **App-specific notes** in the [Manually installing apps section](#manually-installing-apps), followed by the post-install instructions in [Post-install app configuration section](#post-install-app-configuration).

## Post-install app configuration

> [!NOTE]
> These post-install instructions are relevant no matter which option you used to install the apps.

### PostgreSQL

> [!TIP]
> Your PostgreSQL app is internally available as `srv-captain--postgres` (assuming your app is called "postgres") to other apps as the hostname for a database connection.

If you haven't already (i.e. through `gc-stack-deploy`), create the `warehouse` database.

#### Expose database to the public internet (⚠️ Optional & Not recommended):

If you plan to expose the database to applications not hosted on this VM's CapRover,
you will need to take some additional steps after installing the one-click-app:
- Set a port mapping `5432:5432` for server to container.
- Enable SSL by using the certs that come installed with `ssl-cert` on the Postgres Docker image. Modify the Service Update Override as follows:
    ```yaml
    TaskTemplate:
        ContainerSpec:
            User: "postgres"
            Command:
            - "postgres"
            - "-c"
            - "ssl=on"
            - "-c"
            - "ssl_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem"
            - "-c"
            - "ssl_key_file=/etc/ssl/private/ssl-cert-snakeoil.key"
    ```

     **TODO**: figure out how to use trusted certs for Postgres (for example, using Let's Encrypt for which CapRover has built-in support).

- Make sure your hosting provider’s firewall or network security settings allow inbound traffic on port **5432** using the **TCP** protocol. For example, on **Azure**, inbound traffic on port 5432 is blocked by default and must be explicitly allowed through a Network Security Group (NSG) rule.
- Now, you will be able to connect to the database using the hostname of your VM (no subdomain needed), port 5432, and SSL enabled.

### CoMapeo Archive Server

No additional steps needed, but you may want to check if the `ALLOWED_PROJECTS` environment variable is set correctly for your community.

### Filebrowser

#### Find and change the admin password

Find the admin password in the CapRover web portal under **Files** → **Logs**. Example log message:

```
2026-01-22T20:56:44.221575561Z 2026/01/22 20:56:44 Using database: /database/filebrowser.db
2026-01-22T20:56:44.250493277Z 2026/01/22 20:56:44 Using config file: /config/settings.json
2026-01-22T20:56:44.263320528Z 2026/01/22 20:56:44 Randomly generated password for user 'admin': A6U9k-spVr9XgiRh
2026-01-22T20:56:44.357124503Z 2026/01/22 20:56:44 Listening on [::]:80
```

Then change the password inside 
Filebrowser app. **This has to be done immediately after installing the app**. If the app restarts,
the log message showing the password will not be shown again.

> [!TIP]
> If you are too late in retrieving the password, you can delete the app in the CapRover UI and redeploy it using the one-click app install menu. If you go this route, make sure you manually map the `/persistent-storage` directory in the app to your volume mount path (usually `/mnt/persistent-storage`).

#### Accessing the datalake folder

 When logging into Filebrowser app, you may see "This location can't be reached".
 This is because Filebrowser is configured to show files in a folder called "datalake"
 and that folder hasnt been created yet. You may do any of the following:
 - create that folder in Azure Storage Explorer, or
 - upload any file anyway - this will implictly create the necessary folder. Then you can delete it.

### GuardianConnector Explorer

GuardianConnector Explorer installation involves some separate PostgreSQL setup:
creating a `guardianconnector` database. 

The `gc-stack-deploy` handles this for you, but if you are setting up the app using the one-click app install menu, you will need to create the database manually.

### GuardianConnector Landing Page

No additional steps needed, but you may want to check if all of the environmental variables (like `NUXT_COMMUNITY_NAME`, `NUXT_PUBLIC_LOGO_URL`) are set correctly post-installation.

### Redis

No additional steps needed.

### Windmill

#### For first-time login:

Instance Settings Page

* **Core** tab
  
  * Default timeout = 30 Min
  * Retention period in secs= 2592000 (30 Days)

* **Telemetry** tab > Disable telemetry

* **Auth/OAuth** tab > If you plan to use SSO, enable auth0 (or your
  provider of choice) and enter your organization and app client variables.

  Note: after a domain-approved user has registered with SSO, they must be
  manually added to workspaces by an instance admin.

#### Setting up superadmin users

After you set up your Instance, you can navigate back to the Instance Settings page to the **Users** tab, and add any users you want to have access to Windmill with the superadmin role.

#### Setting up a workspace

1. As a superadmin, access **+ Workspace** in the top left corner and add a new workspace. The convention CMI uses to name workspaces is `gc-<alias>`, where `<alias>` is the alias chosen by the community.
2. Push the [`gc-scripts-hub`](https://github.com/conservationMetrics/gc-scripts-hub) content to the workspace. See [Guardian Connector Scripts Hub README](https://github.com/ConservationMetrics/gc-scripts-hub/blob/main/README.md#deploying-the-code-to-windmill-workspaces) for more details.

#### Setting up operator users

You may want to set up operator users to execute scripts and monitor their progress. See [Guardian Connector Scripts Hub README](https://github.com/ConservationMetrics/gc-scripts-hub/blob/main/README.md#user-roles) for more details on setting up operator users.

#### Persistent Directories

If you are using the `gc-stack-deploy` tool, this is done automatically. If you are setting up the app using the one-click app install menu, you will need to manually set the persistent directories:

- For the `windmill-worker` and `windmill-worker-native` apps' CapRover "App Configs", change the Persistent Directory for `/persistent-storage` to specific host path, and then the local path of your datalake on the VM.

#### Code assistants (⚠️ Optional)

To enable [code assistants](https://www.windmill.dev/docs/code_editor/assistants),
you will need to install the Language Server Protocol (LSP):

1. Deploy a new Caprover App, the Windmill LSP: `ghcr.io/windmill-labs/windmill-lsp:1.518.2`
2. Route Windmill HTTP requests intended for LSP:
    1. Go to the settings for the core windmill web server
    2. Ensure **Websocket Support** is enabled.
    3. Ensure **Force HTTPS** is enabled.
    4. Click on **Edit Default Nginx Configurations** and paste the following content before the last closing bracket "}" (Change `windmill-lsp` in the codeblock to the app name you gave it):
        ```
        location /ws/ {
            proxy_pass http://srv-captain--windmill-lsp:3001/ws/;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
        ```

### Superset

#### First-time admin login

You can log in with the email and password you set as `ADMIN_EMAIL` and `ADMIN_PASSWORD`, which `superset-init-and-beat` service uses to initialize the database with a first admin user. 

If you are using Auth0, you can log in with the email account (either as username/password or as a social login) - the `ADMIN_PASSWORD` is not used in this case.

#### Disabling the healthcheck for worker and init-and-beat services

Consider following the post-install instructions of adding the following lines
to the new `-worker` and `-init-and-beat` services.

```yaml
    HealthCheck:
      Test: ["NONE"]
```
See [`./one-click-apps/README.md`](./one-click-apps/README.md) for full example.

## Upgrade Apps

Please see the [Service Upgrades](SERVICE_UPGRADES.md) guide for instructions on how to upgrade the apps.

## Manually installing apps

> [!NOTE]
> If you are using the `gc-stack-deploy` tool, you can skip this section.
> This section provides instructions for manually installing apps using the one-click app install menu.

### PostgreSQL

You have two options for the PostgreSQL database

#### Option 1: Install PostgreSQL via CapRover:

From the CapRover, navigate to **Apps** and "One-Click Apps/Database". Find the **PostgreSQL** one-click app from the available list.

- Version: 17-alpine
- Set a database username and password

#### Option 2: Use External PostgreSQL

If you already have an external PostgreSQL instance (e.g., cloud-hosted), simply configure the apps in your stack to connect to this external instance by setting the appropriate environment variables when installing.

### Filebrowser

For Docker image tag, just use `v2`.

### Redis

If you plan to install Superset, first install the Redis application from the one-click app install menu.

Your redis connection string can then be: `redis://:«password»@srv-captain--redis:6379` (assuming your app is called "redis").

### Windmill

> [!NOTE]
> We use `one-click-apps/windmill-only.yml` in this repo, instead of the Windmill app from
the public CapRover one-click-apps repo. This is to share a database with the other apps,
instead of installing separate database servers for each app in the stack.

Windmill installation involves some separate PostgreSQL setup. If you want to set up Windmill manually, you must execute the necessary SQL commands directly on your PostgreSQL instance. They include creating the Windmill database, roles, and granting privileges. 

Specific commands can
be found inside the one-click-app's preamble.