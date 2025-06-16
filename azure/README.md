# Launch a VM in Azure

This folder can launch infrastructure to host a Guardian Connector stack in a VM in Azure.

The build process creates an Azure Resource Manager (ARM) template that provisions
a VM with Docker and configures Azure Files storage mounting.

The final built ARM can be deployed via Azure Portal or CLI.

## Instructions

### Configuring Azure Files (Optional)

Many communities keep their data lake files on Azure Files. This is optional.

1. **To use Azure Files:**
   - Create the Storage Account and Files share beforehand
   - The `cloud-config.yml` already contains the mount script with ARM parameter placeholders
   - You'll provide the storage account details as parameters during deployment

2. **To not use Azure Files:**
   - Delete the entire `write_files:` section from `cloud-config.yml`

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
