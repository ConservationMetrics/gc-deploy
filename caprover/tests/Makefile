SHELL := /bin/bash

# This preamble inspired by https://tech.davis-hansson.com/p/make/
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

REPO_ROOT := $(shell git rev-parse --show-toplevel)
BUILT_REPO_PATH := $(REPO_ROOT)/build/one-click-apps/v4/apps/
TOOL_DIR := $(REPO_ROOT)/caprover/gc-stack-deploy
VENV_DIR := $(REPO_ROOT)/caprover/tests/.venv
VENV_READY_FILE := $(VENV_DIR)/bin/gc-stack-deploy

GEN_BACKUP_DIR := $(REPO_ROOT)/install-caprover-from-backup
GEN_BACKUP_VENV_DIR := $(GEN_BACKUP_DIR)/.venv
GEN_BACKUP_VENV_READY := $(GEN_BACKUP_VENV_DIR)/bin/gen-backup
TEMPLATE_TAR := $(GEN_BACKUP_DIR)/caprover-backup-2026_05_28-14_53_23-1779980003546-ip-127_0_0_1.tar
GENERATED_TAR := $(GEN_BACKUP_DIR)/tmp2/really-new-backup.tar

.PHONY: all quick-test-e2e test-e2e install-caprover uninstall-caprover build-one-click-apps-repo deploy-stack clean setup-venv \
        setup-gen-backup-venv generate-backup install-caprover-from-backup test-restore smoke-test

# Default target
all: test-e2e

# Main end-to-end test target
test-e2e: uninstall-caprover install-caprover quick-test-e2e
	@echo "✅ End-to-end test completed successfully"
	@# WARNING: does not uninstall-caprover AFTER launching the stack.
	@# It leaves the stack running.

# Quick stack deployment on already-running CapRover
# Can be run instead of `test-e2e` for faster testing
quick-test-e2e: setup-venv build-one-click-apps-repo deploy-stack
	@echo "✅ Quick deployment completed"

# CapRover setup and teardown targets (in order of invocation)
uninstall-caprover:
	@echo "# Uninstalling CapRover..."
	@./uninstall-caprover.sh
	@# Also drop data volumes, to avoid conflicting volumes next time.
	@# IMPORTANT: This regex depends on the `app_name` settings in `stack.test.yaml` to begin `test-`.
	@docker volume ls -q | grep '^captain--test-' | xargs --no-run-if-empty docker volume rm
install-caprover:
	@echo "# Installing CapRover..."
	@./install-caprover.sh

# Set up Python virtual environment and dependencies.
# This target is idempotent and will also re-run if requirements.txt changes.
setup-venv: $(VENV_READY_FILE)
$(VENV_READY_FILE): $(TOOL_DIR)/pyproject.toml
	@echo "# Setting up Python virtual environment and dependencies..."
	@python3 -m venv "$(VENV_DIR)"
	@"$(VENV_DIR)/bin/pip" install -e $(TOOL_DIR)
	@touch $@

# Build the one-click app repository
build-one-click-apps-repo:
	@echo "# Building one-click app repository..."
	@../one-click-apps/build-repo.sh

# Deploy the stack using your Python script
deploy-stack: setup-venv
	@echo "# Deploying Guardian Connector stack..."
	@echo "Using one-click repository at: file://$(BUILT_REPO_PATH)"
	@cd .. && $(VENV_DIR)/bin/gc-stack-deploy -c $(REPO_ROOT)/caprover/tests/stack.test.yaml --repo "file://$(BUILT_REPO_PATH)"

# Optional cleanup of build artifacts
clean:
	@echo "🗑️ Cleaning build artifacts..."
	@rm -rf $(REPO_ROOT)/build/one-click-apps
	@rm -rf $(VENV_DIR)

#
# gen-backup: PoC to exploit restore-from-backup
#

# Set up the gen-backup venv. Idempotent; re-runs if pyproject.toml changes.
setup-gen-backup-venv: $(GEN_BACKUP_VENV_READY)
$(GEN_BACKUP_VENV_READY): $(GEN_BACKUP_DIR)/pyproject.toml
	@echo "# Setting up gen-backup venv..."
	@python3.12 -m venv --without-pip "$(GEN_BACKUP_VENV_DIR)"
	@curl -sS https://bootstrap.pypa.io/get-pip.py | "$(GEN_BACKUP_VENV_DIR)/bin/python3.12"
	@"$(GEN_BACKUP_VENV_DIR)/bin/pip" install -e "$(GEN_BACKUP_DIR)" -q
	@touch $@

# Generate a new backup tar from the reference template.
generate-backup: setup-gen-backup-venv
	@echo "# Generating backup tar..."
	@mkdir -p "$(GEN_BACKUP_DIR)/tmp2"
	@"$(GEN_BACKUP_VENV_DIR)/bin/gen-backup" \
		--template "$(TEMPLATE_TAR)" \
		--root-domain test-gc-deploy.localhost \
		--out "$(GENERATED_TAR)"

# Install CapRover from the generated backup (runs after generate-backup).
install-caprover-from-backup: generate-backup
	@echo "# Installing CapRover from backup..."
	@BACKUP_TAR="$(GENERATED_TAR)" ./install-caprover.sh

# Full restore smoke-test: tear down, generate, restore, verify.
test-restore: uninstall-caprover install-caprover-from-backup smoke-test
	@echo "✅ Restore smoke-test complete — review output above."

# Basic reachability check: CapRover dashboard + one app subdomain.
smoke-test:
	@echo "# Smoke-testing restored CapRover..."
	@curl -sf --retry 5 --retry-delay 5 \
		http://captain.test-gc-deploy.localhost:3000 > /dev/null && \
		echo "  ✅ Dashboard reachable" || \
		{ echo "  ❌ Dashboard not reachable"; exit 1; }
	@curl -sf --retry 5 --retry-delay 5 --max-time 10 \
		http://nocodb.test-gc-deploy.localhost > /dev/null && \
		echo "  ✅ nocodb subdomain reachable" || \
		echo "  ⚠️  nocodb not yet reachable (container may still be starting)"
