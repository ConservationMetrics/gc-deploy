# Recover from Backup

This documentation assumes you've set up DigitalOcean Backups on a VM (which needs to be have been done manually).

You can recover from backup by navigating to the **Backups** tab in the Droplet control panel and clicking ***More** next to the backup you want to recover from. There are two options to choose from:

1. Restore Droplet
2. Create Droplet

## Restore Droplet

This will replace the current Droplet with an older image.

## Create Droplet

This will create a new Droplet from the backup. The menu options are the same as when [Creating a Droplet](README.md#i-create-a-droplet-with-the-caprover-image), only that for **Choose an image**, you can select the backup you want to recover from. This will quickly spin up a new Droplet from the backup.

Please note that only the VM is recovered. After the backup finishes, you will need to manually re-configure Droplet network interface settings such as **firewall rules**, and set up DNS records for the new Droplet.