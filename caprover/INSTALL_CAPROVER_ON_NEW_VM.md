# New VM running CapRover

This guide lists the high-level steps to get CapRover running on a new VM, so that you can then
install the Guardian Connector stack.

## Quick setup on popular cloud platforms

We highly recommend using one of our quick guides that will handle all this for you
in Azure or DigitalOcean — in which case **you may skip the rest of the document.**

- To do this in Azure using an ARM template, see [`azure/README.md`](../azure/README.md)
- To do this with a DigitalOcean Droplet one-click app, see [`digitalocean/README.md`](../digitalocean/README.md)

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
   - Optional: After Docker is installed, reboot once (`sudo shutdown -r now`). On fresh VMs this sometimes avoids flaky Docker behavior; teams have also seen fewer CapRover oddities (including **NodeID is not assigned**) after a reboot before installing CapRover.

3. Domain Name: Ensure you have a domain name and subdomain ready (e.g., `mycommunity.guardianconnector.net`), which CapRover will use.
   - Add 2 new A-Name records for your subdomain to the VM's IP: `mycommunity.guardianconnector.net` and `*.mycommunity.guardianconnector.net`.
   - Apps will be accessible via sub-subdomains (e.g., `superset.mycommunity.guardianconnector.net`).
   - If the DNS settings already contains other A-Name records for other hosts (e.g. staging), leave those alone unless you intend to repoint traffic.

4. Optional: Set up an auth0 tenant, authorization flow (for example, an approval script for the `post-login` Trigger), and auth0 client applications for the apps that will be using auth0.

5. Optional: Set up a Mapbox account to provide the API key for the apps.
   - CMI's convention is a **new** Mapbox account per community, with **new** access tokens for that deployment. Sign up using `guardianconnector+<instance>@conservationmetrics.com` (plus-alias on the shared inbox so mail still routes to the team).

6. Optional: Set up a Volume Mount (such as Azure Files Share)

7. Optional: Schedule automatic updates of packages and OS

8. Optional: Add SSH keys to `~/.ssh/authorized_keys` for everyone who needs access to the VM.  

9. Set up CapRover on the VM

   - With the right amount of knowledge, you can follow CapRover's own [Getting Started](https://caprover.com/docs/get-started.html#caprover-setup) guide to figure out how to install CapRover when the hosting platform didn't already do it for you.

10. Once CapRover is installed, configure disk cleanup and set an appropriate cron schedule in the CapRover web UI.
    - We recommend setting disk cleanup to run daily at 3:00 AM e.g. `0 3 * * *` at the timezone most likely to be used by the VM's users
    - We recommend keeping the 2 most recent images. (2 images allows you to revert the latest deployment, whereas 1 does not.)
