# Set up CapRover in Azure

## 🚀 Quick Deployment (10 minutes)

> [!IMPORTANT]
>
> Before you start, make sure that you have access to the right Subscriptions for **both** VM deployment and managing the DNS.

### I. Launch a VM with Warehouse Storage

1. Click to deploy a new VM on Azure:
    > [<img src="https://aka.ms/deploytoazurebutton"/>](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fconservationmetrics.github.io%2Fgc-deploy%2Fazure%2Fnew-vm.arm.json)
2. Fill in required parameters:
    - **Subscription:** Select the subscription you want to use.
    - **Resource Group:** Recommend creating new, so the only thing in the resource group is this Guardian Deployment deployment. See also ["Prerequisites"](#prerequisites) below for discussion about permission requirements. 
      - CMI's convention is to use `guardian-<alias>` for the resource group name, where `<alias>` is the alias chosen by the community.
    - **Region:** Where will this stack be hosted? e.g. for data about Brazil, choose "`Brazil South`" to adhere to [Brazilian Data Protection Laws](https://www.gov.br/esporte/pt-br/acesso-a-informacao/lgpd). The Instance (VM) "Region" will be same as the Resource group's region.
    - **Create Storage Account / Storage Account Name:** See ["Configuring Azure Files"](#configuring-azure-files-optional) below.
      - CMI's convention is to use `guardian-<alias>` for the storage account name.
    - **Select SSH Public Key Source:** Select "Generate new key pair" to generate a new SSH key pair, or select "Use existing key pair stored in Azure" (which is what CMI does to avoid having to manage SSH keys in multiple places).
    - **Backup Vault Name / Backup Vault Resource Group:** (Optional) To enable automated disk backups, provide the name of an existing Recovery Services Vault and its resource group. The vault must be in the same region as the VM. To find existing vaults: [Azure Portal > Recovery Services vaults](https://portal.azure.com/#browse/Microsoft.RecoveryServices%2Fvaults), then note the vault's Name and Resource Group. Leave blank to skip automatic backup configuration. See also ["Backups"](#backups) below.
3. Click "Review + Create". Wait for deployment (about 2 minutes).

### II. Set up DNS

1. Get your VM's IP address from the Azure Portal
2. In your domain provider's control panel, add A records. Assuming you have a domain like `guardianconnector.net`, add two A records to your VM's public IP:
    ```
    TYPE: A record
    HOST: *.<alias> (.guardianconnector.net)
    POINTS TO: (IP Address of your VM)
    TTL: 3600 (1 hour)
    ```

    ```
    TYPE: A record
    HOST: <alias> (.guardianconnector.net)
    POINTS TO: (IP Address of your VM)
    TTL: 3600 (1 hour)
    ```

    Alias record set can be left blank.

3. Confirm: check if these domains resolve to the IPs you set in your DNS.
    ```bash
    nslookup random123.<alias>.guardianconnector.net  # for the wildcard
    nslookup <alias>.guardianconnector.net
    ```

   (Note that `random123` is needed because you set a wildcard entry in your DNS by setting `*.<alias>` as your host, not `<alias>`)

### III. Set up CapRover

You must configure CapRover using the CapRover CLI _from the server itself._
For security reasons, initial configuration from another machine is disabled, both via web interface or the CLI on a remote box _(due to Azure NSG blocking port 3000)_.

1. SSH into your new VM:
    ```bash
    ssh -i ~/.ssh/your-secret-key YOUR_USERNAME@captain.<alias>.guardianconnector.net
    ```
    (or use the IP address if your domain is not yet pointing to the VM)

2. Run the CapRover setup:
    ```bash
    caprover serversetup
    ```
    - Answer "y" to the question "have you already started CapRover container on your server?"
    - When asked for "IP address of server": type `127.0.0.1`.
    - For "Root domain": enter your full domain (`<alias>.guardianconnector.net`)
    - For "Valid email addresses": enter an admin email address from your organization.
    - For "Caprover machine name", enter your alias for the VM (`<alias>`)

    Note that it may take the server a few minutes to install CapRover. If, when running this command, you get an error that `caprover: command not found`, wait a few minutes and try again.

### IV. Set up SSH keys and backups

Two additional steps you may wish to take to secure your deployment:

1. Add SSH keys to `~/.ssh/authorized_keys` for everyone who needs access to the VM.
2. Set up automatic backups for the VM.

### V. Install the Guardian Connector software stack

> [!TIP]
> It is recommended to set up auth0 and Mapbox before you install the app stack, because you will need to input Client IDs, Client Secrets, and Mapbox API Keys in the app stack configuration.

- Set up auth0 by following [`../auth0/README.md`](../auth0/README.md).
- Set up a Mapbox account to provide the API key for the apps.
- Install the app stack by following [`../caprover/INSTALL_GC_STACK.md`](../caprover/INSTALL_GC_STACK.md).

## 📖 More Information

The ARM template creates a complete environment ready to host a Guardian Connector stack in Azure.

Infrastructure:
- Ubuntu VM in your chosen region
- Public IP address with static allocation
- Virtual network with subnet
- Network security group with ports 22 (SSH), 80 (HTTP), and 443 (HTTPS) open
    - port 3000 is intentially not exposed for security; `caprover serversetup` must use loopback address `127.0.0.1`
- Optional Azure Files storage account and SMB share for your data warehouse

Software & Configuration:
- CapRover server installed and running on Docker Swarm
- CapRover CLI tool installed - needed for initial CapRover setup
- Azure Files is mounted to a local path (if storage account provided)

### Prerequisites

Your Azure user must have **Contributor** role on an existing Resource Group to deploy the stack,
or **Contributor** role on the Subscription to create a new Resource Group for the stack.

### Configuring Azure Files (Optional)

Many communities keep their data lake files on Azure Files. This is optional.

1. **To use Azure Files:**
   - Create the Storage Account and Files share beforehand, or do so while deploying the VM
   - The `cloud-config.yml` already contains the mount script with ARM parameter placeholders
   - You'll provide the storage account details as parameters during deployment
   - CMI uses the following naming conventions:
     - Storage Account Name: `<alias>`
     - Storage Account Folder: `<alias>-files`
   - **Note:** check the standard quota for the file share, and adjust as needed. (CMI typically sets 1024 GB, or 1 TB)

2. **To not use Azure Files:**
   - Delete the entire `write_files:` section from `cloud-config.yml`
   - When deploying, set `createStorageAccount` to `false`

### Backups

Azure Backup can automatically back up the VM's disks (OS disk and any data disks) to a Recovery Services Vault. This protects against data loss from accidental deletion, corruption, or VM failure.

**What gets backed up:**
- The VM's OS disk. It contains the operating system, all Docker volumes, and CapRover configuration.
- Any attached data disks

**What does NOT get backed up via Azure Backup:**
- Network interface settings: Most notably firewall rules
- Azure Files shares (these have their own backup/redundancy options)
- External database servers

**Setting up backups:**

It's recommended to use the ARM template to configure backup by providing a Recovery Services Vault during initial VM deployment. A vault must already exist in the same region as the VM.

All VMs in that region / subscription can share a vault and backup policy.

When expanding to a new region, one-time instructions to create a Recovery Services vault:
1. Azure Portal > Create a resource > Recovery Services vault
2. Choose the same region as your VMs
3. Recommended to create an Enhanced Policy called with a distinguishable name such as "GuardianConnectorPolicy"


## 🛠️ Building the Template

The ARM template needs to be built before deployment to inject the cloud-init configuration:

After you update `cloud-config.yml`, you can either

1. **Build the ARM template locally**:
   ```bash
   (cd azure ; ./build.sh)
   ```
   This creates `build/azure/new-vm.arm.json` with the cloud-init configuration embedded.

2. **Push changes on `main` branch and let GitHub Actions build the ARM template**:
   > [![Build Azure ARM Template](https://github.com/ConservationMetrics/gc-deploy/actions/workflows/build-and-deploy.yml/badge.svg)](https://github.com/ConservationMetrics/gc-deploy/actions/workflows/build-and-deploy.yml)
    - It will be hosted at [`https://conservationmetrics.github.io/gc-deploy/azure/new-vm.arm.json`](https://conservationmetrics.github.io/gc-deploy/azure/new-vm.arm.json)
    - You can also use the [ARM template viewer](https://armviz.io/#/?load=https%3A%2F%2Fconservationmetrics.github.io%2Fgc-deploy%2Fazure%2Fnew-vm.arm.json) to view the ARM template


NOTES:
- The `cloud-config.yml` contains ARM template parameter references like `parameters('storageAccountName')` which are invalid YAML but get processed correctly by the ARM template at deployment time. The build script converts the cloud-init configuration into a properly escaped JSON string for embedding in the ARM template
- Always rebuild the template after modifying `cloud-config.yml`
