# Set up CapRover in Azure

## 🚀 Quick Deployment (10 minutes)

### I. Launch a VM with Warehouse Storage

1. Click to deploy a new VM on Azure:
    > [<img src="https://aka.ms/deploytoazurebutton"/>](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fconservationmetrics.github.io%2Fgc-deploy%2Fazure%2Fnew-vm.arm.json)
2. Fill in required parameters:
    - **Resource Group:** Recommend creating new, so the only thing in the resource group is this Guardian Deployment deployment. See also ["Prerequisites"](#prerequisites) below for discussion about permission requirements.
    - **Region:** Where will this stack be hosted? e.g. for data about Brazil, choose "`Brazil South`" to adhere to [Brazilian Data Protection Laws](https://www.gov.br/esporte/pt-br/acesso-a-informacao/lgpd). The Instance (VM) "Region" will be same as the Resource group's region.
    - **Create Storage Account / Storage Account Name:** See ["Configuring Azure Files"](#configuring-azure-files-optional) below.
    - **Select SSH Public Key Source:** Select "Generate new key pair" to generate a new SSH key pair, or select "Use existing key pair stored in Azure" (which is what CMI does to avoid having to manage SSH keys in multiple places).
3. Click "Review + Create". Wait for deployment (about 2 minutes).

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

You must configure CapRover using the CapRover CLI _from the server itself._
For security reasons, initial configuration from another machine is disabled, both via web interface or the CLI on a remote box _(due to Azure NSG blocking port 3000)_.

1. SSH into your new VM:
    ```bash
    ssh -i ~/.ssh/your-secret-key YOUR_USERNAME@captain.mycommunity.guardianconnector.net
    ```
    (or use the IP address if your domain is not yet pointing to the VM)

2. Run the CapRover setup:
    ```bash
    caprover serversetup
    ```
    - Answer "y" to the question "have you already started CapRover container on your server?"
    - When asked for "IP address of server": type `127.0.0.1`.
    - For "Root domain": enter your full domain (example: `mycommunity.guardianconnector.net`)
    - For "Caprover machine name", enter your alias for the VM (example: `mycommunity`)

    Note that it may take the server a few minutes to install CapRover. If, when running this command, you get an error that `caprover: command not found`, wait a few minutes and try again.

### IV. Install the Guardian Connector software stack

- Install the app stack by following [`../caprover/INSTALL_GC_STACK.md`](../caprover/INSTALL_GC_STACK.md).
- Set up auth0 by following [`../auth0/README.md`](../auth0/README.md).
- Set up a Mapbox account to provide the API key for the apps.

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
     - Storage Account Name: {alias}
     - Storage Account Folder: {alias}-files
   - **Note:** check the standard quota for the file share, and adjust as needed. (CMI typically sets 1024 GB, or 1 TB)

2. **To not use Azure Files:**
   - Delete the entire `write_files:` section from `cloud-config.yml`
   - When deploying, set `createStorageAccount` to `false`

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
