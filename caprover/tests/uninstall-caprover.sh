#!/bin/bash
set -e

echo "Leaving Docker Swarm..."
docker swarm leave --force >/dev/null 2>&1 || echo "Not part of a swarm or already left."

echo "Removing CapRover domain from /etc/hosts..."
sudo sed -i.bak '/test-gc-deploy.localhost/d' /etc/hosts

echo "Removing CapRover data..."
sudo rm -rf /captain/*

echo "🗑️ CapRover uninstalled."