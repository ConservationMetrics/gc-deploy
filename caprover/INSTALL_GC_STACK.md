# Guardian Connector Software Stack Setup on CapRover

This guide walks you through setting up your custom Guardian Connector software stack on a fresh virtual machine (VM) using CapRover.

## Prerequisite: Install CapRover

See [INSTALL_CAPROVER_ON_NEW_VM.md](INSTALL_CAPROVER_ON_NEW_VM.md) if you haven't already configured a new VM running CapRover.

## Set Up PostgreSQL Database

You have two options for the PostgreSQL database

### Option 1: Install PostgreSQL via CapRover:

From the CapRover, navigate to **Apps** and "One-Click Apps/Database". Find the **PostgreSQL** one-click app from the available list.

- Version: 17-alpine
- Set a database username and password

> [!NOTE]
> Your PostgreSQL app is internally available as `srv-captain--postgres` (assuming your app is called "postgres") to other apps as the hostname for a database connection.

#### Expose database to the public internet (⚠️ Optional & Not recommended):

If you plan to expose the database to applications not hosted on this VM's CapRover,
you will need to take some additional steps after installing the one-click-app:
- Uncheck "Do not expose as web-app externally".
- Enable and force HTTPS.
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

### Option 2: Use External PostgreSQL

If you already have an external PostgreSQL instance (e.g., cloud-hosted), simply configure the apps in your stack to connect to this external instance by setting the appropriate environment variables when installing those apps as described below.

# Add apps to CapRover

## Runtime Prerequisite

1. In your CapRover web dashboard, navigate to **Apps** → **Create A New App** → **One-Click Apps/Databases**.
2. At the very bottom of the Apps list, find **3rd party repositories**. Enter the URL:
    > `https://conservationmetrics.github.io/gc-deploy/one-click-apps`
3. **Connect New Repostory** and refresh the page. You can now browse and install Guardian Connector apps directly from CapRover.

## Different ways to install apps

You have two options to install apps:

1. install the entire stack in one script: **`gc-stack-deploy`**
2. install apps one-at-a-time through the CapRover UI

### Option 1. Installing the entire stack with **`gc-stack-deploy`**

If you don't want to sweat the details, it's much quicker to deploy the Guardian Connector stack of apps using the `gc-stack-deploy`.

Unless your SQL database is on another host, the tool must be run on the same machine where CapRover is running. 

#### Install the tool

On most systems you can install directly with pip:

```sh
$ pip install "gc-stack-deploy @ git+https://github.com/ConservationMetrics/gc-deploy.git@main#subdirectory=caprover/gc-stack-deploy"
```

#### If pip is blocked (common on some VMs)

Some environments (like fresh Ubuntu VMs) restrict `pip install` into the system Python. In that case, use `pipx`
to install the tool:

```sh
$ sudo apt install pipx -y
$ pipx install "gc-stack-deploy @ git+https://github.com/ConservationMetrics/gc-deploy.git@main#subdirectory=caprover/gc-stack-deploy"
```

**Note**: pipx installs apps into `~/.local/bin`. If you see `gc-stack-deploy: command not found`, add it to your PATH:

```sh
$ export PATH=$HOME/.local/bin:$PATH
$ echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
```

Then, restart your shell or run `exec $SHELL -l`. Now you can run `gc-stack-deploy` from any directory.

(Alternatively, you could create a venv to install the tool into, and then add it to your PATH.)

#### Create a `stack.yaml` configuration file

You must create a `stack.yaml` configuration file of for your new deployment. The configuration
file lets you set secrets and API keys, and configure which apps you want.  Write an example template
to your local directory by running `gc-stack-deploy init --config-file «destination.yaml»`.

```sh
$ gc-stack-deploy init --config-file stack.yaml
```
Then open the file and fill in the blanks.

Finally you are ready to use this same configuration file to deploy the apps to CapRover,
running on the same machine.

```sh
# First, dry-run to check for misconfigurations
$ gc-stack-deploy --config-file stack.yaml --dry-run
# Then repeat without --dry-run
```

### Option 2. Install One-Click Apps through the CapRover UI

From the CapRover, navigate to **Apps** and "One-Click Apps/Database".

Install each of the following apps in turn, paying attention to the **App-specific notes** at the links:

- [PostgreSQL](#postgresql)
- [CoMapeo Archive Server](#comapeo-archive-server)
- [Filebrowser](#filebrowser)
- [GuardianConnector Explorer](#guardianconnector-explorer)
- [Redis](#redis)
- [Windmill](#windmill)
- [Superset](#superset)

## Post-install app configuration

### PostgreSQL

If you haven't already (i.e. through `gc-stack-deploy`), create the `warehouse` database.

### CoMapeo Archive Server

No additional steps needed, but you can ensure that **Websocket Support** is enabled.

### Filebrowser

Install - for Docker image tag, just use `v2`.

#### After Install

Carefully follow the post-installation instructions.

Find the admin password in the CapRover web portal under Files > Logs. Then change the password inside 
Filebrowser app. This has to be done immediately after installing the app. If the app restarts,
the log message showing the password will not be shown again.

When logging into Filebrowser app, you may see "This location can't be reached".
This is because Filebrowser is configured to show files in a folder called "datalake"
and that folder hasnt been created yet. You may do any of the following:
- create that folder in Azure Storage Explorer, or
- upload any file anyway - this will implictly create the necessary folder. Then you can delete it.

### GuardianConnector Explorer

GuardianConnector Explorer installation involves some separate PostgreSQL setup:
creating a `guardianconnector` database. The `gc-stack-deploy` handles this for you.

### GuardianConnector Landing Page

No additional steps needed.

### Redis

If you plan to install Superset, install the Redis application from the one-click app install menu.

Your redis connection string can then be: `redis://:«password»@srv-captain--redis:6379` (assuming your app is called "redis").

### Windmill

We use `one-click-apps/windmill-only.yml` in this repo, instead of the Windmill app from
the public CapRover one-click-apps repo. This is to share a database with the other apps,
instead of installing separate database servers for each app in the stack.

#### Before Install

Windmill installation involves some separate PostgreSQL setup. The `gc-stack-deploy`
handles this for you: you will need to set a second PostgreSQL username and password for Windmill,
in addition to the admin password at the top of `stack.yaml`.

If you want to set up Windmill manually, you must execute the necessary SQL commands directly on your PostgreSQL instance.
They include creating the Windmill database, roles, and granting privileges. Specific commands can
be found inside the one-click-app's preamble.

#### After Install


##### Code assistants

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

##### For first-time login:

Instance Settings Page

* **Core** tab > Default timeout = 30 Min

* **Telemetry** tab > Disable telemetry

* **Auth/OAuth** tab > If you plan to use SSO, enable auth0 (or your
  provider of choice) and enter your organization and app client variables.

  Note: after a domain-approved user has registered with SSO, they must be
  manually added to workspaces by an instance admin.

#### Setting up superadmin users

After you set up your Instance, you can navigate back to the Instance Settings page to the **Users** tab, and add any users you want to have access to Windmill with the superadmin role.

##### Persistent Directories

- For the `windmill-worker` and `windmill-worker-native` apps' CapRover "App Configs", change the Persistent Directory for `/persistent-storage` to specific host path, and then the local path of your datalake on the VM.

### Superset

#### First-time admin login

You can log in with the email and password you set as ADMIN_EMAIL and ADMIN_PASSWORD. If you are using Auth0, you can log in with the email account (either as username/password or as a social login) - the ADMIN_PASSWORD is not used in this case.

#### After Install

Consider following the post-install instructions of adding the following lines
to the new `-worker` and `-init-and-beat` services.

```yaml
    HealthCheck:
      Test: ["NONE"]
```
See [`./one-click-apps/README.md`](./one-click-apps/README.md) for full example.

## Upgrade Apps

Most apps allow you to simply update the underlying image from the CapRover webapp
using [**Method 6: Deploy via ImageName**](https://caprover.com/docs/one-click-apps.html#simple-image-update).  You can confirm this applies to you in CapRover under
**Deployment > Version History**. If the latest "Image Name" is the official image,
you can use Method 6 and paste the new official image.

But if the latest "Image Name" is something like `img-captain-...` then you may need
to use one of the other methods. See the app's documentation.

If an app comprises multiple services you will need to Deploy the new image on each one.
