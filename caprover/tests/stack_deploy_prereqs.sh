#!/bin/bash
set -e

# This script sets up the Python virtual environment and installs dependencies
# required for stack_deploy.py, including a forked version of Caprover-API.

# Ensure we are in the script's directory to resolve paths correctly.
cd "$(dirname "$0")"

REPO_ROOT=$(git rev-parse --show-toplevel)
VENV_DIR="${1:-.venv}"   # take first arg, fallback to .venv

# 1. Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment at $VENV_DIR already exists."
fi

# Activate venv for this script's context
source "$VENV_DIR/bin/activate"

# Install dependencies from requirements.txt
pip install -r "$REPO_ROOT/caprover/requirements.txt"

# Install the forked Caprover-API and psycopg
echo "Cloning & Installing forked Caprover-API..."
CAPROVER_API_DIR=$(mktemp -d)
trap 'echo "Cleaning up temporary Caprover-API clone..." && rm -rf "$CAPROVER_API_DIR"' EXIT
git clone --depth 1 --branch fix-oneclick-repo https://github.com/IamJeffG/Caprover-API.git "$CAPROVER_API_DIR"
pip install "$CAPROVER_API_DIR"

echo "✅ Prerequisites setup complete."
