# Installing Caprover and Guardian Connector at the same time

## I. Prerequisite - Have a VM and SSH into it

1. 🖥️ Choose your cloud provider and deploy a VM running CapRover. See, for example, **[Azure Setup Guide](azure/README.md)** or **[DigitalOcean Setup Guide](digitalocean/README.md)**, or it may be on-premises.
    - the stack will use /mnt/persistent-data for warehouse file storage; make sure it exists!
    - DNS (for public servers) or `/etc/hosts` (for local servers) should be configured with a domain name for this server.
    - Caprover must not already be running. If it is, stop it as follows:
        ```sh
        docker swarm leave --force
        rm -rf /captain/*
        ```

2. SSH into your new VM:
    ```bash
    ssh -i ~/.ssh/your-secret-key YOUR_USERNAME@<alias>.guardianconnector.net
    ```
    (or use the IP address if your domain is not yet pointing to the VM)


## II. Install the tool

On most systems you can install directly with pip:

```sh
pip install "gen-backup @ git+https://github.com/ConservationMetrics/gc-deploy.git@main#subdirectory=caprover/gen-backup"
```

#### If pip is blocked (common on some VMs)

Some environments (like fresh Ubuntu VMs) restrict `pip install` into the system Python. In that case, use `pipx`
to install the tool:

```sh
sudo apt install pipx -y
pipx install "gen-backup @ git+https://github.com/ConservationMetrics/gc-deploy.git@main#subdirectory=caprover/gen-backup"
```

**Note**: pipx installs apps into `~/.local/bin`. If you see `gen-backup: command not found`, add it to your PATH:

```sh
export PATH=$HOME/.local/bin:$PATH
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
```

Then, restart your shell or run `exec $SHELL -l`. Now you can run `gen-backup` from any directory.

(Alternatively, you could create a venv to install the tool into, and then add it to your PATH.)

## III. Create a `stack.yaml` configuration file

You must create a `stack.yaml` configuration file of for your new deployment. The configuration
file lets you set secrets and API keys, and configure which apps you want.

See gc-stack-deploy. (TODO! Friction requiring another tool!)

## IV. Mock a "backup" file that contains your stack and install Caprover from it

```sh
gen-backup --config-file stack.yaml --out /captain/backup.tar
docker run -p 80:80 -p 443:443 -e BY_PASS_PROXY_CHECK='TRUE' -e ACCEPTED_TERMS=true -v /var/run/docker.sock:/var/run/docker.sock -v /captain:/captain caprover/caprover
```

Wait 10 minutes.


## V. enable SSL

Enable SSL for caprover itself, and also per app:
    - `POST /api/v2/user/apps/appDefinitions/enablebasedomainssl` (default subdomains)
    - `POST /api/v2/user/apps/appDefinitions/enablecustomdomainssl` (custom domains, e.g. gc-landing-page)


TODO: script this.
