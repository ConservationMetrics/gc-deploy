# Set up CapRover on a DigitalOcean Droplet

## 🚀 Quick Deployment (10 minutes)

### I. Create a Droplet with the CapRover image

1. Create a Droplet with the **"CapRover in Ubuntu"** image from DigitalOcean's marketplace; we suggest to use the big blue "Create a Droplet" button on CapRover's own [Getting Started](https://caprover.com/docs/get-started.html) guide to preselect the right Image.
2. Pick an appropriate size for your Droplet such as a Shared CPU with 2 vCPUs, 4 GB Memory, and a 35 GB Disk.
3. For Authentication Method: **SSH Key** for best security.

> [!CAUTION]
>
> Currently, this guide does not leverage DigitalOcean's Network File Storage (NFS) Shares for the Guardian Connector data warehouse. This means that all files will need to be stored on the local disk of the Droplet (e.g. a local `/data` directory on the VM). This is not a good practice for production deployments. Please refer to [DigitalOcean's documentation on NFS Shares](https://docs.digitalocean.com/products/nfs/) for more information on how to set this up. You may also want to refer to [our Azure VM deployment guide](../azure/README.md) for an example of how to set up Azure Files Shares for the Guardian Connector data warehouse.

### II. Set up DNS

1. Get your VM's IP address from the DigitalOcan Portal
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
    ssh -i ~/.ssh/your-secret-key YOUR_USERNAME@captain.<alias>.guardianconnector.net
    ```
    (or use the IP address if your domain is not yet pointing to the VM)

2. Install PNPM and the CapRover CLI:
    ```bash
    wget -qO- https://get.pnpm.io/install.sh | sh
    /root/.local/share/pnpm/pnpm install -g caprover
    ```
3. Run the CapRover setup:
    ```bash
    caprover serversetup
    ```
    - Answer "y" to the question "have you already started CapRover container on your server?"
    - When asked for "IP address of server": type `127.0.0.1`.
    - For "Root domain": enter your full domain (`<alias>.guardianconnector.net`)
    - For "Valid email addresses": enter an admin email address from your organization.
    - For "Caprover machine name", enter your alias for the VM (`<alias>`)

    Note that it may take the server a few minutes to install CapRover. If, when running this command, you get an error that `caprover: command not found`, wait a few minutes and try again.

4. Close port 3000 in the firewall. Do this in the DigitalOcean web interface under "Networking".

### IV. Set up SSH keys and backups

Two additional steps you may wish to take to secure your deployment:

1. Add SSH keys to `~/.ssh/authorized_keys` for everyone who needs access to the VM.
2. Set up automatic backups for the VM.

### V. Install the Guardian Connector software stack

- Install the app stack by following [`../caprover/INSTALL_GC_STACK.md`](../caprover/INSTALL_GC_STACK.md).
- Set up auth0 by following [`../auth0/README.md`](../auth0/README.md).
- Set up a Mapbox account to provide the API key for the apps.

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

It is possible to set up automated backups of a VM hosted on a DigitalOcean Droplet at a percentage of the total cost of your Droplet. This protects against data loss from accidental deletion, corruption, or VM failure. See [DigitalOcean's documentation on backups](https://www.digitalocean.com/products/backups) for more information.


**What gets backed up:**
- The VM's OS disk. It contains the operating system, all Docker volumes, and CapRover configuration.
- Any attached data disks

**What does NOT get backed up via Droplet Backups:**
- Network interface settings: Most notably firewall rules
- Network File Storage 
- External database servers

#### Setting up backups

In the Droplet control panel, you can set up backups by navigating to the **Backups** tab and enabling backups. At the time of writing, there are two backup plans to choose from:

* weekly backups kept for 4 weeks, at 20% of the total cost of your Droplet.
* daily backups kept for 7 days, at 30% of the total cost of your Droplet.

You can schedule a 4 hour window during which the backups will be taken.

#### Recovery

See our ["Recover from Backup"](backup-recovery.md) documentation to recover from backup.