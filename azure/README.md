# Deploy CapRover in Azure

## 🚀 Quick Deployment (10 minutes)

### I. Launch a VM with Warehouse Storage

1. [Click here to deploy a new VM on Azure](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FConservationMetrics%2Fgc-deploy%2Frefs%2Fheads%2Fmain%2Fbuild%2Fazure%2Fnew-vm.arm.json)
2. Fill in required parameters:
   - **Resource Group:** Recommend creating new, so the only thing in the resource group is this Guardian Deployment deployment. See also ["Prerequisites"](#prerequisites) above for discussion about permission requirements.
   - **Region:** Where will this stack be hosted? e.g. for data about Brazil, choose "`Brazil South`" to adhere to [Brazilian Data Protection Laws](https://www.gov.br/esporte/pt-br/acesso-a-informacao/lgpd). The Instance (VM) "Region" will be same as the Resource group's region.
   - **Create Storage Account / Storage Account Name:** See ["Configuring Azure Files"](#configuring-azure-files-optional) below.
3. Click "Review + Create". Wait for deployment (about 2 minutes).

### II. Set up DNS

1. Get your VM's IP address from the Azure Portal
2. In your domain provider's control panel, add an A record. Assuming you have a domain like `guardianconnector.net`, add a A record to your VM's public IP:

    TYPE: A record
    HOST: *.mycommunity (.guardianconnector.net)
    POINTS TO: (IP Address of your VM)
    TTL: 3600

3. Confirm: check if IP address resolves to the IP you set in your DNS.

    nslookup random123.mycommunity.guardianconnector.net

(Note that `random123` is needed because you set a wildcard entry in your DNS by setting `*.mycommunity` as your host, not `mycommunity`)


### III. Set up CapRover

You must configure CapRover via SSH and its Caprover CLI. For security reasons configuring through the web interface is disabled.

1. SSH into your new VM:
   ```bash
   ssh -i ~/.ssh/your-secret-key YOUR_USERNAME@YOUR_VM_IP
   ```
2. Run the CapRover setup:
   ```bash
   caprover serversetup
   ```
   - When asked for "IP address of server": type `127.0.0.1`.
   - For "Root domain": enter your full domain (example: `mycommunity.guardianconnector.net`)

### IV. Install the Guardian Connector software stack

Install the app stack by following [`caprover/README.md`](https://github.com/ConservationMetrics/gc-forge/blob/main/caprover/README.md).


## 📖 More information

This folder can launch infrastructure to host a Guardian Connector stack in a VM in Azure.

The build process creates an Azure Resource Manager (ARM) template that provisions
a VM with Docker and configures Azure Files storage mounting.

The final built ARM can be deployed via Azure Portal or CLI.

### Prerequisites

Your Azure user must have **Contributor** role on an existing Resource Group to deploy the stack,
or **Contributor** role on the Subscription to create a new Resource Group for the stack.

### Configuring Azure Files (Optional)

Many communities keep their data lake files on Azure Files. This is optional.

1. **To use Azure Files:**
   - Create the Storage Account and Files share beforehand
   - The `cloud-config.yml` already contains the mount script with ARM parameter placeholders
   - You'll provide the storage account details as parameters during deployment

2. **To not use Azure Files:**
   - Delete the entire `write_files:` section from `cloud-config.yml`
   - When deploying, set `createStorageAccount` to `false`

## 🛠️ Building the Template

The ARM template needs to be built before deployment to inject the cloud-init configuration:

1. **Update `cloud-config.yml`** with your specific configuration (see above for Azure Files setup)
2. **Build the template**:
   ```bash
   (cd azure-vm ; ./build.sh)
   ```
   This creates `docs/build/azure/new-vm.arm.json` with the cloud-init configuration embedded.

NOTES:
- The `cloud-config.yml` contains ARM template parameter references like `parameters('storageAccountName')` which are invalid YAML but get processed correctly by the ARM template at deployment time. The build script converts the cloud-init configuration into a properly escaped JSON string for embedding in the ARM template
- Always rebuild the template after modifying `cloud-config.yml`
