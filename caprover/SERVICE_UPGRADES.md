# Service Upgrades

This document describes how to upgrade components in the Guardian Connector stack.

There are two distinct upgrade paths, depending on what you are changing:

1. **CapRover upgrades** – upgrading the CapRover server itself  
2. **Service upgrades** – upgrading one or more deployed application images

Service upgrades can be performed in two alternative ways, depending on scale and workflow:

- **Option A:** Manual image upgrades via the CapRover UI  
- **Option B:** Batch upgrades to a service across many Guardian Connectorinstances using the `caprover-batch-deploy` tool

Use the sections below to jump directly to the relevant procedure.

## Upgrading CapRover

The CapRover UI indicates when there is a new version of CapRover available. You will see a "🎁 🎁 Update Available 🎁 🎁!" message at the top of the dashboard. Clicking on it will take to you to a `/maintenance` page, where you can click on the "Install Update" button to install the latest update.

However, as noted on that page:

> CapRover allows in-place updates to be installed. However, always read the change logs before updating your CapRover. There might be breaking changes that you need to be aware of. The update usually takes around 60 seconds and your CapRover may become unresponsive until the update process is finished. Your apps will stay functional and responsive during this time, except for a very short period of 10 seconds or less.

CapRover updates can take a few minutes, and you might see service downtime or nginx errors during and shortly after the update.


## Manual image upgrades via CapRover UI

Most apps allow you to simply update the underlying image from the CapRover webapp using [**Method 6: Deploy via ImageName**](https://caprover.com/docs/one-click-apps.html#simple-image-update). You can confirm this applies to you in CapRover under **Deployment > Version History**. If the latest "Image Name" is the official image, you can use Method 6 and paste the new official image.

But if the latest "Image Name" is something like `img-captain-...` then you may need to use one of the other methods. See the app's documentation.

If an app comprises multiple services (for example, Superset and Windmill) you will need to Deploy the new image on each one.

## Using the `caprover-batch-deploy` tool

CMI has developed a tool that can batch upgrade Guardian Connector services to multiple CapRover instances via the HTTP API. The script authenticates with CapRover API using passwords read from a KeePass database.

We keep this tool in a private repository as it is built to work with our own KeePass database and credential storage patterns, but it is available on request. Please reach out to us if you would like to use it.

## Upgrade patterns

For CMI's own deployments, we aim to keep the Guardian Connector stack up to date with the latest versions of the underlying services. We aim to upgrade the stack once a month, on the last Tuesday of the month.