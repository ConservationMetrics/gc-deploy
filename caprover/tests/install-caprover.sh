#!/bin/bash
set -e

# Exit if any of the required commands are not found
for cmd in docker npm node; do
    if ! command -v $cmd &> /dev/null; then
        echo "Error: $cmd could not be found. Please install it before running this script."
        exit 1
    fi
done

# echo "🐳 Initializing Docker Swarm..."
# docker swarm init --advertise-addr 127.0.0.1 || echo "Swarm already initialized or failed to initialize. Continuing..."

# echo "📝 Adding CapRover domain to /etc/hosts..."
echo "127.0.0.1 captain.test-gc-deploy.localhost" | sudo tee -a /etc/hosts
echo "127.0.0.1 test-gc-deploy.localhost" | sudo tee -a /etc/hosts

# echo "📟 Installing CapRover CLI..."
# pnpm install -g caprover

echo "🚀 Installing CapRover server..."
sudo mkdir -p /captain/data
echo  "{\"skipVerifyingDomains\":\"true\"}" | sudo tee /captain/data/config-override.json > /dev/null
docker run -d \
  --name captain-captain \
  -e ACCEPTED_TERMS=true -e MAIN_NODE_IP_ADDRESS=127.0.0.1 \
  -p 80:80 -p 443:443 -p 3000:3000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /captain:/captain \
  caprover/caprover

echo "⏳ Waiting for CapRover to be ready..."
sleep 20
ready=0
for i in {1..10}; do
  # Don't try to view logs until the service exists.
  if docker service ls --format '{{.Name}}' | grep -q "^captain-captain$"; then
    # Check logs for initialization confirmation.
    if docker service logs captain-captain 2>&1 | grep -q "Captain is initialized"; then
      echo "CapRover is ready!"
      ready=1
      break
    fi
  fi
  echo "Waiting... ($i/10)"
  sleep 5
done

if [ "$ready" -ne 1 ]; then
  echo "❌ CapRover did not start in time."
  exit 1
fi
sleep 10  # Wait a bit more for the API to be fully available

echo "⚙️ Setting up CapRover..."
# Do not use `caprover serversetup` as it will try to require SSL on your local domain:
# https://caprover.com/docs/run-locally.html#setup
COOKIESTXT=`mktemp`
TOKEN=$(curl -s 'http://captain.test-gc-deploy.localhost:3000/api/v2/login' \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'x-namespace: captain' \
  -c "$COOKIESTXT" \
  --data '{"password":"captain42","otpToken":""}' | jq -r '.data.token')

curl -s 'http://captain.test-gc-deploy.localhost:3000/api/v2/user/system/changerootdomain' \
  -X POST \
  -H 'Content-Type: application/json' \
  -H "x-captain-auth: $TOKEN" \
  -H 'x-namespace: captain' \
  -b "$COOKIESTXT" \
  --data '{"rootDomain":"test-gc-deploy.localhost","force":false}'

rm "$COOKIESTXT" || true

echo "✅ CapRover setup complete."