SHELL := /bin/bash
REPO_ROOT := $(shell git rev-parse --show-toplevel)
BUILT_REPO_PATH := $(REPO_ROOT)/build/one-click-apps/v4/apps/

.PHONY: all quick-test-e2e test-e2e install-caprover uninstall-caprover build-one-click-apps-repo deploy-stack clean

all: test-e2e

# Quick stack deployment on already-running CapRover
quick-test-e2e: build-one-click-apps-repo deploy-stack
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

# Deploy the stack using your Python script
deploy-stack:
	@echo "# Deploying Guardian Connector stack..."
	@echo "Using one-click repository at: $(BUILT_REPO_PATH)"
	@cd .. && python3 stack_deploy.py --config-file tests/test-config.yml --repo "file://$(BUILT_REPO_PATH)"

# Clean up build artifacts
clean:
	@echo "🗑️ Cleaning build artifacts..."
	@rm -rf $(REPO_ROOT)/build
	@rm -rf $(REPO_ROOT)/temp-one-click-apps
