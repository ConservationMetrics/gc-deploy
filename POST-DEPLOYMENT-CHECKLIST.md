# Post-Deployment Checklist

Use this checklist to validate a successful Guardian Connector deployment before handoff.
It covers the manual steps that are not already automated through the scripts and workflows in this repo, and is meant to complement — not replace — the deployment guides.

## VM

- [ ] Did I set the A records in my DNS provider? (And can confirm it resolves to the VM's IP?)
- [ ] Did I add SSH keys to `~/.ssh/authorized_keys` for everyone who needs access to the VM?
- [ ] Did I enable auto-backups for the VM and/or the data warehouse?
- [ ] Azure: Can I confirm the VM shows an active backup policy (for example under **Backup + disaster recovery** → **Backup** for this VM)? How to configure backups is documented in [`azure/README.md`](azure/README.md#vm-backups); Azure Files shares are separate—see [`#file-share-backups`](azure/README.md#file-share-backups) if you use them.

## CapRover and services

### CapRover

- [ ] Did I set up the Guardian Connector 3rd party repository?
- [ ] Did I deploy all required apps?
- [ ] Did I configure environment variables and settings for each app correctly? (c.f. [caprover/INSTALL_GC_STACK.md#post-install-app-configuration](caprover/INSTALL_GC_STACK.md#post-install-app-configuration))
- [ ] Did I store the CapRover admin password in KeePass?
- [ ] Did I enable disk cleanup and set an appropriate cron schedule in the CapRover web UI?
- [ ] (CMI only) Did I add the Caprover root subdomain to the `.env` file for our CapRover batch deploy script?

### Landing Page

- [ ] If someone else will be the main Guardian Connector admin, did I have them sign in, approve their account, and upgrade their role to Admin?
- [ ] Did I set a custom background image and logo? (optional)

### Superset

- [ ] Did I set a Mapbox API key and a logo in the environment variables?
- [ ] Did I copy down the `SECRET_KEY` from the environment variables and store it in KeePass?
- [ ] Did I successfully log in as the initial admin account using auth0?
- [ ] If someone else will be the main Guardian Connector admin, did I have them sign in and upgrade their role to Admin? (Yes, this is distinct from the Landing Page / auth0 RBAC step above)
- [ ] Did I configure a database connection to `warehouse`?

### Filebrowser

- [ ] Did I get the Filebrowser admin password from the logs in CapRover, and change it?
- [ ] Did I store the updated admin credentials in KeePass?

### Windmill

- [ ] Did I set up auth0 for Windmill?
- [ ] Did I create a Windmill workspace?
- [ ] Did I push `gc-scripts-hub` content using the Windmill CLI (`wmill sync push`)?
- [ ] Did I add the Windmill workspace to `gc-scripts-hub/.env` to be able to batch push updates to this workspace?
- [ ] Did I create the standard Windmill resources (e.g. for alerts)?
  - [ ] Postgres database
  - [ ] Twilio message template
  - [ ] GFW API key
  - [ ] GCP service account
  - [ ] [Local Contexts](https://localcontextshub.org)
  - [ ] CoMapeo archive server
  - [ ] Oauth client credentials for metrics (**GC Metrics** M2M app in Auth0)
- [ ] Did I schedule the [`guardianconnector_metrics`](https://github.com/ConservationMetrics/gc-scripts-hub/blob/main/f/metrics/guardianconnector/README.md) script to run once a month?
- [ ] Did I invite other required admin users to the Windmill instance and workspace?
- [ ] Did I set up operator users with the appropriate permissions (e.g. [disable all settings except Runs and Schedules](https://docs.guardianconnector.net/reference/gc-toolkit/gc-scripts-hub/user-roles#configuring-operator-roles))?
- [ ] Did I add the group `g/all` to all of the folders containing the workspace scripts, flows, and apps (e.g. `export`, `connectors`, `apps`)?
- [ ] For Windmill connector and metrics resources, did I follow [**Setting up resources**](caprover/INSTALL_GC_STACK.md#setting-up-resources) in the stack install guide?

### CoMapeo

- [ ] Did I set an appropriate project limit for the CoMapeo archive server in the `ALLOWED_PROJECTS` environment variable?
- [ ] For Windmill `comapeo_server` resources, did I copy `server_url` / bearer token from this deployment’s CoMapeo archive server app in CapRover (`SERVER_BEARER_TOKEN` in App Configs / environment)?

### GC Explorer

_No manual steps required until datasets exist._

## Third-party services

### Auth0

- [ ] Did I add a GCP OAuth client for Google social login?
- [ ] Did I set up the user approval flow?
- [ ] Is RBAC set up and did I create the required roles?
- [ ] Did I assign the Admin role to my logged in user?
- [ ] Did I invite other required admins to the Auth0 tenant?
- [ ] Did I create applications for each GC Stack app?
- [ ] Did I create a M2M application for metrics (e.g. **GC Metrics**), and grant `read:users` and `read:stats` scopes to it?

### Mapbox

- [ ] Did I create a Mapbox account and set up an API key to use for the domain?
- [ ] Did I set up any maps required i.e. for the alerts dashboard?
- [ ] Did I store the credentials for Mapbox in KeePass?

### Uptime Robot

- [ ] Did I add monitors for each service URL?

## Handoff

- [ ] Did I manually verify each deployed app (e.g. Superset, Windmill, Filebrowser, Landing Page, Explorer, CoMapeo) loads, critical paths work, and configuration and assets have been set up properly, before handing off to the programmatic lead?