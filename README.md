# Deploy the Guardian Connector stack in Cloud or locally

## An overview: Components of the Guardian Connector Stack

### 🖥️ Compute

A computer server running your applications.
- A virtual machine in the cloud of your choice, or self-host in the office.

### 📂 Storage for your Data Warehouse

Store, organize, and selectively share all your data:

- **File storage** for media (pictures, maps, videos)
- **SQL database** for surveys and other tabular data.

### 🔐 Access Control

Secure login system to control who can access your applications.

### 📦 App stack

- **Windmill**: Sync from outside data providers, schedule your data workflows, and run other scripts.
- **Superset**: Visualize and explore structured/tabular data with interactive dashboards.
- **Filebrowser**: Easily view and create share links for your media (pictures, videos...).
- **GuardianConnector Explorer**: Unified view of tabular, media, and maps.
- **CoMapeo Archive Server**: A CoMapeo archive server that synchronizes with CoMapeo devices.
- ...plus install any other web applications you need using [CapRover](https://caprover.com/).

## Deployment Guide

High-level steps to spawn a new stack

1. 🖥️ Choose your cloud provider and deploy a VM running CapRover.
    - **[Azure Setup Guide](azure/README.md)**
    - **[DigitalOcean Setup Guide](digitalocean-vm/README.md)**
    - or [DIY on-premises or on another hosting provider](caprover/INSTALL_CAPROVER_ON_NEW_VM.md)

2. 📂 Create your data warehouse: file storage & a SQL database.
    - The Azure deployment can automatically create an Azure Storage Account and Files share for you, or you can use an existing one. If you are storing files on the VM directly, you can skip Azure Files entirely.
3. 🔐 If you plan on using auth0, set up an **auth0 tenant** with a user authorization workflow and client applications to help secure access to the apps you will deploy. See [`auth0/README.md`](auth0/README.md)

4. 📦 Install the app stack by following [`caprover/README.md`](caprover/README.md).
5. Set up data pipelines & other scripts to run in Windmill.
    - See [**ConservationMetrics/gc-scripts-hub**](https://github.com/ConservationMetrics/gc-scripts-hub/)

