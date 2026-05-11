# Set up CapRover locally for development

To set up CapRover locally, see this guide: https://caprover.com/docs/run-locally.html

If the local installation incantation in the guide doesn't work for you, or if you prefer to handle local development setup in an isolated virtual environment, you can take the approach suggested in [this video tutorial](https://www.youtube.com/watch?v=J_6H11DrzXY) of spinning up a Docker inside of Docker (`dind`) image:

1. Set up the `dind` image:

    ```bash
    docker run --privileged -d -p 80:80 -p 443:443 -p 3000:3000 --name caprover-docker docker:dind
    ```

2. Open an interactive shell session inside the `caprover-docker` container:

    ```bash
    docker exec -it caprover-docker /bin/sh
    ```

3. Create the `/captain/data` directory:

    ```bash
    mkdir -p /captain/data/
    ```

4. Now, you can run the installation command for local installation from the guide:

    ```bash
    echo  "{\"skipVerifyingDomains\":\"true\"}" >  /captain/data/config-override.json
    docker run -e ACCEPTED_TERMS=true \
    -e MAIN_NODE_IP_ADDRESS=127.0.0.1 \
    -p 80:80 -p 443:443 -p 3000:3000 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /captain:/captain caprover/caprover
    ```

5. If you want to check on the initialization status, you can run
   ```bash
   docker ps
   ```

   Find the container id, and then run

   ```bash
   docker logs -f <container_id>
   ```

   If successfully initiatized, you should see a log message:
   ```
   **** Captain is initialized and ready to serve you! ****
   ```

6. Now, you can access CapRover at http://captain.captain.localhost:3000/ (or a different port if you opted for one in step 4). The password for the initial setup is `captain42`.
