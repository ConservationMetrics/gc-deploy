# Troubleshooting a deployment on CapRover

This doc lists common failure cases and what to do.

## Rebooting the VM

> [!TIP]
> Rebooting the VM is very often the most expedient way to fix opaque or seemingly transient problems
> with Docker Swarm or with CapRover.

As long as the VM is not running additional stuff that is not part of the Guardian Connector stack, then
it's safe to restart a VM.
- There will not be data loss.
- Docker and CapRover should start automatically after reboot.

```
$ sudo shutdown --reboot now
```

Note that I have _not_ had great luck trying to "only" restart the Docker service (`systemctl restart docker`) without rebooting.


## Missing Volume Mount on VM

- Check log files after VM boot, to confirm the mount script is executed as expected:
    * `/var/log/cloud-init.log` — logs the general cloud-init process.
    * `/var/log/cloud-init-output.log` — captures the output from the mount-drive.sh script itself.
- Run `/var/lib/cloud/scripts/per-boot/mount-datalake.sh` manually if needed.


## CapRover is running but one specific app is not running.

List services.
```
$ sudo docker service list
ID             NAME                 MODE         REPLICAS   IMAGE
s4qs8pkyx1eh   captain-captain      replicated   1/1        caprover/caprover:1.13.1
qwmynacoiol5   captain-nginx        replicated   1/1        nginx:1.24
da7k7crhdlsb   srv-captain--files   replicated   0/1        filebrowser/filebrowser:v2     # <--- 0/1
```

If the missing service shows 0 replicas, then Docker Swarm is trying to start it but cannot.
Use the service name from `list` output to show recent attempts to start the container:

```
$ sudo docker service ps srv-captain--files --no-trunc
NAME                   IMAGE            DESIRED STATE   CURRENT STATE           ERROR
srv-captain--files.1   filebrowser:v2   Shutdown        Failed 8 minutes ago    "ERROR MSG HERE"
```

If the error message looks familiar and you think the app is just misconfigured, then
fix the error by modifying necessary "App Configs" in the CapRover web portal for this app.
(One common source of error that prevents some apps from starting is that the volume mount to Azure Files
was not created upon VM bootup.  See [**Missing volume mount on VM**](#missing-volume-mount-on-vm).)

On the other hand, if the error message is totally opaque to you and/or seemingly unrelated to this
specific app, maybe there's a lower-level problem with Docker. Sometimes when this happens, the most expedient
thing to try is to shutdown and restart the VM: See [**Rebooting the VM**](#rebooting-the-vm).

Once fixed you will see:

```
$ sudo docker service ps srv-captain--files --no-trunc
NAME                   IMAGE            DESIRED STATE   CURRENT STATE           ERROR
srv-captain--files.1   filebrowser:v2   Running         Running 8 minutes ago   -

$ sudo docker service list
ID             NAME                 MODE         REPLICAS   IMAGE
s4qs8pkyx1eh   captain-captain      replicated   1/1        caprover/caprover:1.13.1
qwmynacoiol5   captain-nginx        replicated   1/1        nginx:1.24
da7k7crhdlsb   srv-captain--files   replicated   1/1        filebrowser/filebrowser:v2     # <--- 1/1
```

## CapRover has crashed and you need to access app config

All of the app definitions, including environmental variables, are stored in a file on disk:

```
$ sudo cat /captain/data/config-captain.json
```

This could be useful if you need to set up CapRover, and all one-click apps, anew.
For example, if one of the apps (like Apache Superset) was set up with a secret key used to encrypt sensitive information in the database, and you need to retrieve this key to set up the app again (see [**Lost Superset `SECRET KEY`**](#lost-superset-secret_key))

## Windmill worker apps are not starting

It has been observed that the Windmill worker apps don't start if the DB connection string does not have `?sslmode=require` appended, if connecting to a database that requires SSL. This is not added to the DB connection string by default.

## Superset metastore database not created after installation

It may be necessary to manually create the `superset_metastore` database by running the following as a PostgreSQL admin user:

```sql
CREATE DATABASE superset_metastore;
```

## Lost Superset `SECRET_KEY`

Apache Superset requires a `SECRET_KEY` for securing sessions and other cryptographic functions such as encrypting sensitive information in the database.

Our [Superset one-click app](one-click-apps/v4/apps/superset-only.yml) defaults to using a new `SECRET_KEY` on each deploy. If you re-deploy Superset against an existing database with a different `SECRET_KEY`, you will see an error on the front end: "An error occurred while fetching databases: Invalid decryption key,' and in the logs the same ValueError will be raised.

If you need to retrieve a lost `SECRET_KEY` from a previous CapRover deployment (e.g. if CapRover has fatally crashed and you need to re-set up CapRover and Superset), one option is to find it in `config-captain.json` as described in [CapRover has crashed and you need to access app config](#caprover-has-crashed-and-you-need-to-access-app-config).

Barring that, know that very few tables in the Superset metastore use this SECRET_KEY, the
most critical one being `dbs` (to encrypt its columns "password" and "encrypted_extra").
And `dbs` stores the Database Connections, which presumably you are able to create from scratch
via the Superset webapp > Settings > "Database Connections" -- this time with the correct (new) SECRET_KEY.
If charts and dashboards rely on an old Database Connection that was encrypted with a different SECRET_KEY,
you could then modify that old entry in the `dbs` table by overwriting its "password" and "encrypted_extra"
with the values of the new entry you just created.
