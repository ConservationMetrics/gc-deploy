# Launch a VM in Azure

## 🚀 Quick Deployment (5 minutes)

1. [Click here to deploy a new VM on Azure](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FConservationMetrics%2Fgc-deploy%2Frefs%2Fheads%2Fmain%2Fbuild%2Fazure%2Fnew-vm.arm.json)
2. Fill in required fields:
   - Resource Group: Create new (e.g. `guardian-«community»`)
   - Storage account:
      - `createStorageAccount: true` to create a new storage account
      - `createStorageAccount: false` and give a `Storage Account Name` & `Folder` to use an existing Azure storage account.
      - `createStorageAccount: false` and skip `Storage Account Name` & `Folder` to store files directly on the VM.
   - Admin Password: Strong password for VM login
3. Click "Review + Create"
4. After deployment: SSH to your VM and install CapRover

## Prerequisites

Your Azure user must have **Contributor** role on an existing Resource Group to deploy the stack,
or **Contributor** role on the Subscription to create a new Resource Group for the stack.

## Instructions

This folder can launch infrastructure to host a Guardian Connector stack in a VM in Azure.

The build process creates an Azure Resource Manager (ARM) template that provisions
a VM with Docker and configures Azure Files storage mounting.

The final built ARM can be deployed via Azure Portal or CLI.

### Configuring Azure Files (Optional)

Many communities keep their data lake files on Azure Files. This is optional.

1. **To use Azure Files:**
   - Create the Storage Account and Files share beforehand
   - The `cloud-config.yml` already contains the mount script with ARM parameter placeholders
   - You'll provide the storage account details as parameters during deployment

2. **To not use Azure Files:**
   - Delete the entire `write_files:` section from `cloud-config.yml`
   - When deploying, set `createStorageAccount` to `false`

NOTEs:
- The `cloud-config.yml` contains ARM template parameter references like `parameters('storageAccountName')` which are invalid YAML but get processed correctly by the ARM template at deployment time. The build script converts the cloud-init configuration into a properly escaped JSON string for embedding in the ARM template
- Always rebuild the template after modifying `cloud-config.yml`

### Building the ARM Template

The ARM template needs to be built before deployment to inject the cloud-init configuration:

1. **Update `cloud-config.yml`** with your specific configuration (see above for Azure Files setup)
2. **Build the template**:
   ```bash
   (cd azure-vm ; ./build.sh)
   ```
   This creates `docs/build/azure/new-vm.arm.json` with the cloud-init configuration embedded.

### Launching using Azure Portal

1. Go to **Azure Portal** > **Deploy a custom template** ([link](https://portal.azure.com/#create/Microsoft.Template))
2. Select **Build your own template in the editor**
3. Upload the built `docs/build/azure/new-vm.arm.json` file
4. Complete the **parameters**
   - **Resource Group:** Recommend creating new, so the only thing in the resource group is this Guardian Deployment deployment. See also ["Prerequisites"](#prerequisites) above for discussion about permission requirements.
   - **Region:** Where will this stack be hosted? e.g. for data about Brazil, choose "`Brazil South`" to adhere to [Brazilian Data Protection Laws](https://www.gov.br/esporte/pt-br/acesso-a-informacao/lgpd). The Instance (VM) "Region" will be same as the Resource group's region.
   - **Create Storage Account / Storage Account Name:** See ["Configuring Azure Files"](#configuring-azure-files-optional) above.
5. Review and click **Review + Create**

### Launching using CLI

1. Run the deployment command:
   ```bash
   az deployment group create \
     --resource-group <resource_group_name> \
     --template-file docs/build/azure/new-vm.arm.json \
     --parameters storageAccountName=<your_storage_account> \
                  storageAccountFolder=<your_share_name> \
                  storageAccessKey=<your_access_key>
   ```
2. Confirm deployment in Azure Portal under **Deployments**
