SHELL := /bin/bash

# This preamble inspired by https://tech.davis-hansson.com/p/make/
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

REPO_ROOT := $(shell git rev-parse --show-toplevel)
BUILT_REPO_PATH := $(REPO_ROOT)/build/one-click-apps/v4/apps/
VENV_DIR := $(REPO_ROOT)/caprover/.venv
VENV_READY_FILE := $(VENV_DIR)/.setup-complete
REQUIREMENTS_FILE := $(REPO_ROOT)/caprover/requirements.txt

.PHONY: all quick-test-e2e test-e2e install-caprover uninstall-caprover build-one-click-apps-repo deploy-stack clean setup-venv

all: test-e2e

# Quick stack deployment on already-running CapRover
quick-test-e2e: setup-venv build-one-click-apps-repo deploy-stack
	@echo "✅ Quick deployment completed"

# Main end-to-end test target
test-e2e: uninstall-caprover install-caprover quick-test-e2e
	@echo "✅ End-to-end test completed successfully"

# Set up fresh CapRover instance
install-caprover:
	@echo "# Installing CapRover..."
	@./install-caprover.sh

# Clean up CapRover installation
uninstall-caprover:
	@echo "# Uninstalling CapRover..."
	@./uninstall-caprover.sh

# Build the one-click app repository
build-one-click-apps-repo:
	@echo "# Building one-click app repository..."
	@../one-click-apps/build-repo.sh

# Set up Python virtual environment and dependencies.
# This target is idempotent and will also re-run if requirements.txt changes.
setup-venv: $(VENV_READY_FILE)
$(VENV_READY_FILE): $(REQUIREMENTS_FILE)
	@echo "# Setting up Python virtual environment and dependencies..."
	@./stack_deploy_prereqs.sh "$(VENV_DIR)"
	@touch $@

# Deploy the stack using your Python script
deploy-stack: setup-venv
	@echo "# Deploying Guardian Connector stack..."
	@echo "Using one-click repository at: $(BUILT_REPO_PATH)"
	@cd .. && $(VENV_DIR)/bin/python stack_deploy.py -c stack.test.yaml --repo "file://$(BUILT_REPO_PATH)"

# Clean up build artifacts
clean:
	@echo "🗑️ Cleaning build artifacts..."
	@rm -rf $(REPO_ROOT)/build/one-click-apps
	@rm -rf $(VENV_DIR)
