# Set up CapRover on a DigitalOcean Droplet


## 🚀 Quick Deployment (10 minutes)

### I. Create a Droplet with the CapRover image

1. Create a Droplet with the **"CapRover in Ubuntu"** image from DigitalOcean's marketplace; we suggest to use the big blue "Create a Droplet" button on CapRover's own [Getting Started](https://caprover.com/docs/get-started.html) guide to preselect the right Image.
2. Pick an appropriate size for your Droplet such as a Shared CPU with 2 vCPUs, 4 GB Memory, and a 35 GB Disk.
3. For Authentication Method: **SSH Key** for best security.

### II. Set up DNS

1. Get your VM's IP address from the Azure Portal
2. In your domain provider's control panel, add an A record. Assuming you have a domain like `guardianconnector.net`, add a A record to your VM's public IP:
    ```
    TYPE: A record
    HOST: *.mycommunity (.guardianconnector.net)
    POINTS TO: (IP Address of your VM)
    TTL: 3600
    ```
3. Confirm: check if IP address resolves to the IP you set in your DNS.
    ```bash
    nslookup random123.mycommunity.guardianconnector.net
    ```

(Note that `random123` is needed because you set a wildcard entry in your DNS by setting `*.mycommunity` as your host, not `mycommunity`)

### III. Set up CapRover

These steps show how to configure CapRover using the CapRover CLI from the server itself.
CapRover's [Getting Started](https://caprover.com/docs/get-started.html#step-3-configure-and-initialize-caprover) guide shows other ways that can be done from a remote machine (e.g. your laptop).

1. SSH into your new VM:
    ```bash
    ssh -i ~/.ssh/your-secret-key YOUR_USERNAME@captain.mycommunity.guardianconnector.com
    ```
2. Install PNPM and the CapRover CLI:
    ```bash
    wget -qO- https://get.pnpm.io/install.sh | sh
    /root/.local/share/pnpm/pnpm install -g caprover
    ```
3. Run the CapRover setup:
    ```bash
    caprover serversetup
    ```
    - For "Root domain": enter your full domain (example: `mycommunity.guardianconnector.net`)

4. Close port 3000 in the firewall. Do this in the DigitalOcean web interface under "Networking".


### IV. Install the Guardian Connector software stacks and set up other services

- Install the app stack by following [`caprover/README.md`](../caprover/README.md).
- Set up auth0 by following [`auth0/README.md`](../auth0/README.md).

## 👩‍💻 Maintenance

### Upgrading the VM Kernel

DigitalOcean does not have direct access to any of your Droplets. This means that the kernel for the Droplet is not managed within the DigitalOcean control panel, and you have [root access and you are responsible for managing and updating your servers](https://www.digitalocean.com/community/questions/security-updates-for-my-ubuntu-droplet) and any services like CapRover, once set up.

You can upgrade the kernel from within the Droplet, as per [this guide](https://docs.digitalocean.com/products/droplets/how-to/kernel/).

The commands to upgrade the operating systems are:

**Upgrade all packages**
```
sudo apt-get update
sudo apt-get dist-upgrade

```

**Upgrade kernel only**
```
sudo apt-get update
sudo apt-get install linux-virtual
```

### Backups

It is possible to set up automated backups of a DigitalOcean Droplet, at a percentage of the total cost of your Droplet. See https://www.digitalocean.com/products/backups for more information.
