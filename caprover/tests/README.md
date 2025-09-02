# End-to-end Testing CapRover-facing deliverables

The stack deployment code, including `stack_deploy.py` and the custom one-click apps, has a hard
dependency on a running CapRover server. Since CapRover requires Docker Swarm, which is not
commonly available in hosted CI runners, we have developed a Makefile-based end-to-end testing
framework that can be run locally or on any machine with Docker.

Unfortunately, no assertions are made. The end-to-end test is merely a **smoketest** that
- ensures the repository of one-click-apps **can be built**;
- ensures **`stack_deploy.py` can install** all one-click apps against a CapRover server from a configuration file.

The `Makefile` includes targets for these, as well as for all prerequisities (e.g.
setting up and tearing down a CapRover server).

## Prerequisites

Before running the tests, ensure you have the following installed on your system:
- Docker
- Python 3.9+
- `make`

## Running E2E Tests

To run the full end-to-end test suite, which will:
1. Install a fresh CapRover instance locally.
2. Build the custom one-click app repository.
3. Deploy a minimal stack using `stack_deploy.py`.
4. Uninstall the local CapRover instance.

(WARNING: this will teardown any CapRover server you may already have running)

...run:
```bash
# `-C caprover/tests` tells Make to change directories. Omit if already in the correct directory.
make -C caprover/tests test-e2e
```

To skip the CapRover server setup and teardown, and deploy the minimal stack against
an already running CapRover:

```bash
make -C caprover/tests quick-test-e2e
```
