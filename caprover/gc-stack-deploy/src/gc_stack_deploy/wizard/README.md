# gc-stack-deploy wizard

Developer-facing code behind `gc-stack-deploy wizard`. To run it, see [auth0/README.md](/auth0/README.md).

- `orchestrator.py`: START HERE; the module docstring describes the end-to-end flow
- `screens.py`: Textual screens and the `WizardApp` entry point
- `auth0/`: Auth0 Management API client and `ensure_*` provisioning functions
- `yaml_writer.py`: comment-preserving updates to `stack.yaml`
