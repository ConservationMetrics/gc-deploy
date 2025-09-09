SHELL := /bin/bash

# This preamble inspired by https://tech.davis-hansson.com/p/make/
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

REPO_ROOT := $(shell git rev-parse --show-toplevel)
BUILT_REPO_PATH := $(REPO_ROOT)/build/one-click-apps/v4/apps/
TOOL_DIR := $(REPO_ROOT)/caprover/stack-deploy-tool
VENV_DIR := $(REPO_ROOT)/tests/.venv
VENV_READY_FILE := $(VENV_DIR)/bin/stack-deploy

.PHONY: all quick-test-e2e test-e2e install-caprover uninstall-caprover build-one-click-apps-repo deploy-stack clean setup-venv

# Default target
all: test-e2e

# Main end-to-end test target
test-e2e: uninstall-caprover install-caprover quick-test-e2e uninstall-caprover
	@echo "✅ End-to-end test completed successfully"

# Quick stack deployment on already-running CapRover
# Can be run instead of `test-e2e` for faster testing
quick-test-e2e: setup-venv build-one-click-apps-repo deploy-stack
	@echo "✅ Quick deployment completed"

# CapRover setup and teardown targets (in order of invocation)
uninstall-caprover:
	@echo "# Uninstalling CapRover..."
	@./uninstall-caprover.sh
install-caprover:
	@echo "# Installing CapRover..."
	@./install-caprover.sh

# Set up Python virtual environment and dependencies.
# This target is idempotent and will also re-run if requirements.txt changes.
setup-venv: $(VENV_READY_FILE)
$(VENV_READY_FILE): $(TOOL_DIR)/pyproject.toml
	@echo "# Setting up Python virtual environment and dependencies..."
	@./stack_deploy_prereqs.sh "$(VENV_DIR)"
	@touch $@

# Build the one-click app repository
build-one-click-apps-repo:
	@echo "# Building one-click app repository..."
	@../one-click-apps/build-repo.sh

# Deploy the stack using your Python script
deploy-stack: setup-venv
	@echo "# Deploying Guardian Connector stack..."
	@echo "Using one-click repository at: file://$(BUILT_REPO_PATH)"
	@cd .. && $(VENV_DIR)/bin/gc-stack-deploy -c stack.test.yaml --repo "file://$(BUILT_REPO_PATH)"

# Optional cleanup of build artifacts
clean:
	@echo "🗑️ Cleaning build artifacts..."
	@rm -rf $(REPO_ROOT)/build/one-click-apps
	@rm -rf $(VENV_DIR)
