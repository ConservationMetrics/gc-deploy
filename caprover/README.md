# CapRover Setup for Guardian Connector

## Installation Guides

1. [Install CapRover on New VM](INSTALL_CAPROVER_ON_NEW_VM.md)
2. [Install Guardian Connector Stack](INSTALL_GC_STACK.md)

## Developers Reference

* [Developing One-Click-Apps](./one-click-apps/README.md)

### End-to-end Testing

All the Stack deployment code — the suite of one-click app definitions, and also the stack_deploy.py "glue" code — is very high-level, and has a hard requirement of installing against a CapRover server.  Unfortunately CapRover requires Swarm, which GitHub Actions cannot run. This leaves a few alternate options for testing this repo's code:

1. Stub out the CapRover server with mock endpoints. CapRover accumulates so much state over the course of an install that I don't think it will be a very good test.
2. Find an alternate CI test runner that can run CapRover. Maybe CircleCI?
3. Run tests on any (non-CI) machine that can run CapRover.

Even if we find an adequate CapRover server, a secondary requirement is this repo's custom repository of one-click-apps needs to be
built before `stack_deploy.py` can use it.

We take the following approach to testing:
1. One big ol' end-to-end test, to cover both stack_deploy.py and the one-click apps.
2. Encapsulated with Makefile to handles pre-requisites:
    - build one-click repo to some other local destination (CircleCI does this on merge to main and also it's a pre-requisite to test stack_deploy)
    - Install a fresh CapRover locally (kinda a process)
    - Destroy the local CapRover server (also kinda a process)
    - Run stack_deploy.py against local CapRover server and using the built one-click repo. Assert non-failure exit.

Recommend to run this locally or on a fresh VM (for now), and this leaves open the possibility to run the test script on a CI worker if we find one that supports Swarm.
