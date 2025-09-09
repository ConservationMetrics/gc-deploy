#!/bin/bash
set -e

# This script installs the gc-stack-deploy tool into its own virtual environment.

TOOL_DIR="$(dirname "$0")/../stack-deploy-tool"
VENV_DIR="${1:-.venv}"   # take first arg, fallback to .venv

echo "Checking for uv..."
if ! command -v uv &> /dev/null
then
    echo "uv could not be found."
    exit 1
fi


echo "Creating virtual environment at ${VENV_DIR}..."
uv venv "${VENV_DIR}"

echo "Installing stack-deploy-tool..."
uv pip install -e "${TOOL_DIR}" --python "${VENV_DIR}/bin/python"

echo "✅ Installation complete. Run the tool with: ${VENV_DIR}/bin/stack-deploy"
