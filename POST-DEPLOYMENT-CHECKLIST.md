# Post-Deployment Checklist

Use this checklist to validate a successful Guardian Connector deployment before handoff.
It covers the manual steps that are not already automated through the scripts and workflows in this repo, and is meant to complement — not replace — the deployment guides.

## VM

- [ ] Did I set the A records in my DNS provider? (And can confirm it resolves to the VM's IP?)
- [ ] Did I add SSH keys to `~/.ssh/authorized_keys` for everyone who needs access to the VM?
- [ ] Did I enable auto-backups for the VM and/or the data warehouse?

## CapRover and services

### CapRover

- [ ] Did I set up the Guardian Connector 3rd party repository?
- [ ] Did I deploy all required apps?
- [ ] Did I configure environment variables and settings for each app correctly? (c.f. [caprover/INSTALL_GC_STACK.md#post-install-app-configuration](caprover/INSTALL_GC_STACK.md#post-install-app-configuration))
- [ ] Did I set the `<alias>.<domain>.net` to point to one of the applications (e.g. Superset or GC Landing Page)?
- [ ] Did I store the CapRover admin password in Keepass?

### Superset

- [ ] Did I set a Mapbox API key and a logo in the environment variables?
- [ ] Did I copy down the `SECRET_KEY` from the environment variables and store it in Keepass?
- [ ] Did I successfully log in as the initial admin account using auth0?
- [ ] Did I configure a database connection to `warehouse`?

### Filebrowser

- [ ] Did I get the Filebrowser admin password from the logs in CapRover, and change it?
- [ ] Did I store the updated admin credentials in Keepass?

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
  - [ ] CoMapeo archive server
  - [ ] Oauth client credentials (for metrics)
- [ ] Did I schedule the [`guardianconnector_metrics`](https://github.com/ConservationMetrics/gc-scripts-hub/blob/main/f/metrics/guardianconnector/README.md) script to run once a month?
- [ ] Did I invite other required admin users to the Windmill instance and workspace?
- [ ] Did I set up operator users with the appropriate permissions (e.g. [disable all settings except Runs and Schedules](https://docs.guardianconnector.net/reference/gc-toolkit/gc-scripts-hub/user-roles#configuring-operator-roles))?
- [ ] Did I add the group `g/all` to all of the folders containing the workspace scripts, flows, and apps (e.g. `export`, `connectors`, `apps`)?

### CoMapeo

- [ ] Did I set an appropriate project limit for the CoMapeo archive server in the `ALLOWED_PROJECTS` environment variable?

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
- [ ] Did I create a M2M application for metrics, and grant `read:users` and `read:stats` scopes to it?

### Mapbox

- [ ] Did I create a Mapbox account and set up an API key to use for the domain?
- [ ] Did I set up any maps required i.e. for the alerts dashboard?
- [ ] Did I store the credentials for Mapbox in Keepass?

### Uptime Robot

- [ ] Did I add monitors for each service URL?