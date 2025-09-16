# Deployment Checklist

Use this checklist to validate a successful Guardian Connector deployment before handoff.  
It covers the manual steps that are not already automated through the scripts and workflows in this repo, and is meant to complement — not replace — the deployment guides.

## VM

- [ ] Did I set a `*.alias` A record in my DNS provider? (And can confirm it resolves to the VM's IP?)
- [ ] Did I set an appropriate file quota (e.g. 1TB) for file shares?

## Auth0

- [ ] Did I add a GCP OAuth client for Google social login?
- [ ] Did I set up the user approval flow?
- [ ] Is RBAC set up?
- [ ] Did I assign the Admin role to my logged in user?
- [ ] Did I invite other required admins to the Auth0 tenant?
- [ ] Did I create applications for each GC Stack app?

## CapRover

- [ ] Did I set up the Guardian Connector 3rd party repository?
- [ ] Did I deploy all required apps?
- [ ] Did I configure environment variables and settings for each app correctly? (c.f. caprover/INSTALL_GC_STACK.md#post-install-app-configuration)

## Mapbox

- [ ] Did I create a Mapbox account and set up an API key to use for the domain?
- [ ] Did I set up any maps required i.e. for the alerts dashboard?

## Superset

- [ ] Did I set a Mapbox API key and a logo in the environment variables?
- [ ] Did I successfully log in as the initial admin account using auth0?
- [ ] Did I configure a database connection to `warehouse`?

## Filebrowser

- [ ] Did I change the Filebrowser admin password?
- [ ] Did I store the admin credentials in Keepass?

## Windmill

- [ ] Did I set up auth0 for Windmill?
- [ ] Did I create a Windmill workspace?
- [ ] Did I push `gc-scripts-hub` content using the Windmill CLI (`wmill sync push`)?
- [ ] Did I create the standard Windmill resources (e.g. for alerts)?
  - [ ] Postgres database
  - [ ] Twilio message template
  - [ ] GFW API key
  - [ ] GCP service account
  - [ ] CoMapeo archive server
- [ ] Did I invite other required admin users to the Windmill instance and workspace?

## CoMapeo

- [ ] Did I set an appropriate project limit for the CoMapeo archive server?