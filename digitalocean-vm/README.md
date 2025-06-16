# Set up CapRover on a DigitalOcean Droplet

As mentioned in CapRover's own [Getting Started](https://caprover.com/docs/get-started.html) guide, the recommended method to install CapRover is via DigitalOcean one-click app. CapRover is available as a One-Click app in DigitalOcean marketplace.

To install CapRover on DigitalOcean, simply click the "Create a Droplet" button on that page. A "CapRover on Ubuntu" image will be selected for you for the VM. 

Pick an appropriate size for your Droplet such as a Shared CPU with 2 vCPUs, 4 GB Memory, and a 35 GB Disk.

Follow the remainder of the instructions on CapRover's Getting Started page to set up a subdomain and SSL using the Caprover CLI.

## Upgrading the VM Kernel

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

## Backups

It is possible to set up automated backups of a DigitalOcean Droplet, at a percentage of the total cost of your Droplet. See https://www.digitalocean.com/products/backups for more information.