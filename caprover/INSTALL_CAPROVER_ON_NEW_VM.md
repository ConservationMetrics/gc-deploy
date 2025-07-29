# New VM running CapRover

This guide lists the high-level steps to get CapRover running on a new VM, so that you can then
install the Guardian Connector stack.

## Quick setup on popular cloud platforms

We highly recommend using one of our quick guides that will handle all this for you
in Azure or DigitalOcean — in which case **you may skip the rest of the document.**

- To do this in Azure using an ARM template, see [`azure/README.md`](../azure/README.md)
- To do this with a DigitalOcean Droplet one-click app, see [`digitalocean-vm/README.md`](../digitalocean-vm/README.md)

## Do-it-yourself

1. Create a VM on-premises or on the hosting provider of your choice.

    > [!IMPORTANT]
    > Your VM should be set up with sufficient CPU processing power, RAM, and disk storage.
    >
    > Our current default for the Guardian Connector stack is a VM with 2 vCPUs, 4 GB Memory, and a 35 GB Disk.
    >
    > Anything less than that may run into performance issues, or the applications may not start at all.

2. Docker Installed: Ensure that Docker is already installed with a version of **25.x or higher**.
    - This is often already done for you: You can check Docker’s version by running `docker --version`
    - For Docker installation instructions, [refer to the official Docker documentation.](https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository)

3. Domain Name: Ensure you have a domain name and subdomain ready (e.g., `mycommunity.guardianconnector.net`), which CapRover will use.
   - Set the A-Name record for your subdomain (e.g., `mycommunity.guardianconnector.net` and `*.mycommunity.guardianconnector.net`) to the VM's IP.
   - Apps will be accessible via sub-subdomains (e.g., `superset.mycommunity.guardianconnector.net`).

4. Optional: Set up an auth0 tenant, authorization flow (for example, an approval script for the `post-login` Trigger), and auth0 client applications for the apps that will be using auth0.

5. Optional: Set up a Volume Mount (such as Azure Files Share)

6. Optional: Schedule automatic updates of packages and OS

7. Set up CapRover on the VM

   - With the right amount of knowledge, you can follow CapRover's own [Getting Started](https://caprover.com/docs/get-started.html) guide to figure out how to deploy a VM on your hosting platform of choice.
   - For instructions on manual VM setup, see [`install-docs/MANUAL-SETUP.md`](install-docs/MANUAL-SETUP.md)
   - For instructions on setting up CapRover locally for development, see [`install-docs/LOCAL-DEVELOPMENT.md`](install-docs/LOCAL-DEVELOPMENT.md)
   - In the case of DigitalOcean, CapRover already comes deployed with the one-clik app method of setting up the VM. See [`../digitalocean-vm/README.md`](../digitalocean-vm/README.md)
