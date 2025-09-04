#!/bin/bash
set -e

# This script builds the custom one-click-app repository.
# It clones the official CapRover repo, injects our custom apps,
# and builds the static site, placing it in the project's /build directory.

# Ensure we are in the script's directory to resolve paths correctly.
cd "$(dirname "$0")"

# Create a temporary directory that will be cleaned up on script exit
TEMP_DIR=$(mktemp -d)
trap 'echo "Cleaning up temporary directory..." && rm -rf "$TEMP_DIR"' EXIT

# Set up paths
REPO_ROOT_DIR=$(git rev-parse --show-toplevel)
BUILD_OUTPUT_DIR="$REPO_ROOT_DIR/build/one-click-apps"
CUSTOM_APPS_DIR="$REPO_ROOT_DIR/caprover/one-click-apps/v4"

echo "Cleaning up previous builds..."
rm -rf "$BUILD_OUTPUT_DIR"
mkdir -p "$(dirname "$BUILD_OUTPUT_DIR")"

echo "Cloning official CapRover one-click-apps repository..."
git clone --depth 1 https://github.com/caprover/one-click-apps.git "$TEMP_DIR"

echo "Injecting custom apps..."
rm -rf "$TEMP_DIR/public"
mkdir -p "$TEMP_DIR/public"
cp -R "$CUSTOM_APPS_DIR" "$TEMP_DIR/public/"
# The CNAME is for GitHub pages
echo "conservationmetrics.github.io/gc-deploy/one-click-apps" > "$TEMP_DIR/public/CNAME"

echo "Installing dependencies and building..."
cd "$TEMP_DIR"
npm ci
npm run validate_apps
npm run formatter-write
npm run build

echo "Moving built repository to $BUILD_OUTPUT_DIR..."
mv "$TEMP_DIR/dist" "$BUILD_OUTPUT_DIR"

echo "✅ One-click app repository built successfully at $BUILD_OUTPUT_DIR"
