# gc-stack-deploy wizard

Developer-facing code behind `gc-stack-deploy wizard`. To run it, see [auth0/README.md](/auth0/README.md).

- `orchestrator.py`: START HERE; the module docstring describes the end-to-end flow
- `screens.py`: Textual screens and the `WizardApp` entry point
- `auth0/`: Auth0 Management API client and `ensure_*` provisioning functions
  - `auth0/cli.py`: runs the official Auth0 CLI from Python (downloads it, drives the device-flow login, runs commands)
  - `auth0/client.py`: thin helpers over the Auth0 Python SDK (exchanges M2M credentials for an access token, builds the Management API client)
  - `auth0/m2m_app.py`: how the wizard gets its Management API access token (uses the CLI to create a temporary M2M app; the screen also accepts the credentials of an M2M app created by hand when the CLI can't be used)
- `yaml_writer.py`: comment-preserving updates to `stack.yaml`
