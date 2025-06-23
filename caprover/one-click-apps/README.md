This folder contains custom one-click apps for CapRover.


## Best Practices for CapRover deployment

### Use "Service Update Override" to change how the Docker Image behaves

There are times you need to change some of the configuration inside the upstream Docker image.
I am not talking about installed packages or the image's filesystem. I refer to instructions
set on the Dockerfile, such as [`CMD`](https://docs.docker.com/reference/dockerfile/#cmd) or
[`HEALTHCHECK`](https://docs.docker.com/reference/dockerfile/#healthcheck) that change
how the Docker system interacts with those files.

We recommend to use "Service Update Override" to change configurations without modifying the Docker image.
CapRover does not provide first-class support for these things but [it does provide Service Update Override
as an escape hatch.](https://caprover.com/docs/service-update-override.html)
You may use it to configure anything supported in the Docker API's [`ServiceUpdate` object](https://docs.docker.com/engine/api/v1.40/#operation/ServiceUpdate)

A common use case is when the same Docker image is used for a webapp and for a background worker
service: running different processes from the same code. Very often the upstream image
is configured to run the webapp by default, so in order to set up the worker, we may need to:

* override the image's default `CMD` (command), to run the worker.
* disable a `HEALTHCHECK` that is configured to ping the webserver, which is not running in the worker process.

In this case, both CapRover apps (Docker services) would deploy the same Docker image using
**Method 6: Deploy via ImageName**, and after deployment, set the **Service Update Override** in CapRover
under "App Configs":

```yaml
TaskTemplate:
  ContainerSpec:
    Command:
      - /app/docker/docker-bootstrap.sh
      - worker
    HealthCheck:
      Test: ["NONE"]  # disable the application health check, since this is a worker.
```

We recommend this approach because:
- Service Update Override persists when a new image is deployed (via "Deploy via ImageName").
  (This cannot be said for alternatives like using `dockerfileLines` to build a derivative image with overridden configuration)
- Service Update Override tends to be the most self-documenting solution for viewers of the CapRover web portal.

#### Alternative: `dockerfileLines`

A limitation of Service Update Override is that one-click-apps support only a small fraction
of what's allowed. In the example above, the one-click app can override `Command`, but not the `HealthCheck`:

```yaml
  $$cap_appname-worker:
    command: ["/app/docker/docker-bootstrap.sh", "beat"]  # works in a one-click app
    healthcheck:  # FIXME: This doesn't do anything for caprover
      disable: true
```

Therefore a one-click app definition might have to instead deploy from a https://caprover.com/docs/captain-definition-file.html whose "dockerfileLines" is basically just changing the CMD:

```yaml
  $$cap_appname-worker:
    dockerfileLines:
    - FROM $$cap_app_docker_image
    - HEALTHCHECK NONE  # otherwise Docker keeps restarting this container when it doesn't respond on port 8088
```

...and perhaps recommend in its `instructions.end` to switch this to Service Update Override after installation.
