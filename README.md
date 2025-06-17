# Deploy the Guardian Connector stack in Cloud or locally

## Components of the Guardian Connector Stack

### 🖥️ Compute

A computer server to run the software.

- a virtual machine in the cloud of your choice.

### 📂 Storage for your Data Warehouse

Store, organize, and selectively share all your data. The warehouse consists of:

- a filesystem for media (pictures, maps, videos)
- a SQL Database for tabular data & surveys

### 📦 App stack

Deploy software easily with [CapRover](https://caprover.com/).

- **Windmill**: Sync from outside data providers, schedule your data workflows, and run other scripts.
- **Superset**: Visualize and explore structured/tabular data with interactive dashboards.
- **Filebrowser**: Easily view and create share links for your media (pictures, videos...).
- **GuardianConnector Explorer**: Unified view of tabular, media, and maps.
- **CoMapeo Archive Server**: A CoMapeo archive server that synchronizes with CoMapeo devices.
- ...plus you can install any other web-based software you want.

## High-level steps to spawn a new stack

1. Deploy a VM.
    - [`azure/README.md`](azure/README.md) describes setting this up on Azure.
    - [`digitalocean-vm/README.md`](digitalocean-vm/README.md) describes setting up a VM with CapRover included on DigitalOcean.
    - With the right amount of knowledge, you can follow the above guides and/or CapRover's own [Getting Started](https://caprover.com/docs/get-started.html) guide to figure out how to deploy a VM on your hosting platform of choice.

2. Create your data warehouse: file storage & a SQL database.
    - The Azure deployment can automatically create an Azure Storage Account and Files share for you, or you can use an existing one. If you are storing files on the VM directly, you can skip Azure Files entirely.
2. If you plan on using auth0, set up an **auth0 tenant** with a user authorization workflow and client applications to help secure access to the apps you will deploy. See [`auth0/README.md`](auth0/README.md)

3. Install the app stack by following [`caprover/README.md`](https://github.com/ConservationMetrics/gc-forge/blob/main/caprover/README.md).
4. Set up data pipelines & other scripts to run in Windmill.
    - See [**ConservationMetrics/gc-scripts-hub**](https://github.com/ConservationMetrics/gc-scripts-hub/)

