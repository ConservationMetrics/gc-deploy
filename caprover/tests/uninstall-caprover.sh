#!/bin/bash
set -e

# echo "🛑 Stopping and removing CapRover container..."
# docker stop captain-captain >/dev/null 2>&1 || echo "captain-captain container not running."
# docker rm captain-captain >/dev/null 2>&1 || echo "captain-captain container not found."

echo "Leaving Docker Swarm..."
docker swarm leave --force >/dev/null 2>&1 || echo "Not part of a swarm or already left."

echo "Removing CapRover domain from /etc/hosts..."
sudo sed -i.bak '/test-gc-deploy.localhost/d' /etc/hosts

echo "Removing CapRover data..."
sudo rm -rf /captain/*

echo "🗑️ CapRover uninstalled."