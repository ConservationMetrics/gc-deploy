# CapRover Setup for Guardian Connector

## Installation Guides

1. [Install CapRover on New VM](INSTALL_CAPROVER_ON_NEW_VM.md)
2. [Install Guardian Connector Stack](INSTALL_GC_STACK.md)

## Developers Reference

* [Developing One-Click-Apps](./one-click-apps/README.md)

### End-to-end Testing

The stack deployment code, including `stack_deploy.py` and the custom one-click apps, has a hard
dependency on a running CapRover server. Since CapRover requires Docker Swarm, which is not
commonly available in hosted CI runners, we have developed a Makefile-based end-to-end testing
framework that can be run locally or on any machine with Docker.

This approach encapsulates all prerequisites and test steps into simple `make` targets.

#### Prerequisites

Before running the tests, ensure you have the following installed on your system:
- Docker
- Python 3.11+ and `pip`
- `make`

You will also need to install the Python dependencies for the deployment script:
```bash
cd caprover
pip install -r requirements.txt
```

#### Running the Tests

To run the full end-to-end test suite, which will:
1. Install a fresh CapRover instance locally.
2. Build the custom one-click app repository.
3. Deploy a minimal stack using `stack_deploy.py`.
4. Uninstall the local CapRover instance.

(WARNING: this will teardown any caprover you already have running)

...run:
```bash
make -C caprover/tests test-e2e
```

To skip the CapRover server setup and teardown, and deploy the minimal stack against
an already running CapRover:

```bash
make -C caprover/tests quick-test-e2e
```
