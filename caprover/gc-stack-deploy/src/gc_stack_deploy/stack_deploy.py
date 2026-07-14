"""
Deploy multiple apps of the Guardian stack to a VM running CapRover.

Use a configuration file of variable values.

This greatly reduces the clicking and copy/pasting needed to deploy the full
Guardian Connector stack.  The script is able to inject the same variable value
(e.g. database info) into multiple apps that request it.

"""

import argparse
import http.server
import importlib.resources
import io
import logging
import os
import secrets
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from functools import reduce

import bcrypt
import psycopg
from caprover_api import caprover_api
from ruamel.yaml import YAML

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_config(file_path):
    """Load configuration from YAML file."""
    try:
        with open(file_path, "r") as file:
            ryaml = YAML()
            config = ryaml.load(file)
    except FileNotFoundError:
        print(f"Configuration file {file_path} not found.")
        sys.exit(1)
    return config


def set_yaml_value(yaml_str: str | None, key: str | list[str], value: object) -> str:
    """
    Set a value at a (nested) key in a YAML string and return the updated YAML.

    Parameters
    ----------
    yaml_str
        YAML-formatted string (empty or None treated as empty document).
    key
        Dot-delimited string (e.g. "a.b.c") or list of key segments.
    value
        Value to set.

    Returns
    -------
    Re-serialized YAML string.
    """
    raw = yaml_str or ""
    ryaml = YAML()
    ryaml.preserve_quotes = True

    data = ryaml.load(raw) or {}

    keys = key.split(".") if isinstance(key, str) else list(key)
    # Walk to the parent, creating intermediate dicts as needed
    parent = reduce(lambda d, k: d.setdefault(k, {}), keys[:-1], data)
    parent[keys[-1]] = value

    buf = io.StringIO()
    ryaml.dump(data, buf)
    return buf.getvalue()


def _verify_existing_postgres_app(
    cap, pg_app_name, postgres_from_container, postgres_from_vm
):
    """
    If the pg_app_name app exists in CapRover, sanity-check that its configuration
    (host and port) match what was parsed from YAML `from_container`/`from_vm`

    Warn on mismatch. We don't fail (but maybe we should).
    """
    app = cap.get_app(pg_app_name)
    if not app:
        # No `postgres` app in CapRover — assume external Postgres.
        return

    if postgres_from_container.host != "srv-captain--postgres":
        logger.warn(
            f"===== A `{pg_app_name}` app exists in CapRover, but from_container.host is "
            f"{postgres_from_container.host!r} (expected 'srv-captain--postgres'). "
            f"Downstream apps may fail to connect. ====="
        )

    mappings = app.get("ports") or []
    host_ports = [
        int(m["hostPort"])
        for m in mappings
        if int(m.get("containerPort", 0)) == postgres_from_container.port
    ]
    if host_ports and postgres_from_vm.port not in host_ports:
        logger.warn(
            f"===== Deployed `postgres` app maps host port(s) {host_ports} -> "
            f"{postgres_from_container.port}, but from_vm.port="
            f"{postgres_from_vm.port} in YAML. The script's bare-metal "
            f"connection will likely fail. Update from_vm.port to match. ====="
        )


def set_memory_limit(cap, appname, memory_bytes=1610612736):
    app = cap.get_app(appname)
    new_suo = set_yaml_value(
        app["serviceUpdateOverride"],
        "TaskTemplate.Resources.Limits.MemoryBytes",
        memory_bytes,
    )
    cap.update_app(appname, serviceUpdateOverride=new_suo)


def construct_app_variables(config, service_name, init=None):
    variables = {} if init is None else init
    for key, val in config[service_name].items():
        if key == "deploy":
            continue
        variables[f"$$cap_{key}"] = val
    return variables


@contextmanager
def postgres_patient_connect(*args, retries=10, delay_seconds=2, **kwargs):
    """
    Context manager that retries initial PostgreSQL connection (e.g. waits for server to be ready)

    After successful connect, it does not retry or reconnect for subsequent errors
    during the context block.

    Parameters
    ----------
    *args :
        Positional arguments passed directly to psycopg.connect.
    retries : int, optional
        Maximum number of connection attempts (default 10).
    delay_seconds : int, optional
        Base delay in seconds between retries.
    **kwargs :
        Keyword arguments passed directly to psycopg.connect.

    Yields
    ------
    psycopg.Connection
        A live PostgreSQL connection object.

    Raises
    ------
    psycopg.OperationalError
        If connection cannot be established after the given retries.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with psycopg.connect(*args, **kwargs) as conn:
                yield conn
                return
        except psycopg.OperationalError as e:
            last_exc = e
            if attempt < retries:
                time.sleep(delay_seconds)
            else:
                raise last_exc


@dataclass
class PostgresConnectionConfig:
    """Connection info for a PostgreSQL server in a Docker container."""

    host: str
    user: str
    password: str
    ssl: bool
    port: int = 5432

    def connstr(self, dbname=None):
        sslmode = "require" if self.ssl else "disable"
        s = (
            f"host={self.host} port={self.port} user={self.user} "
            f"password={self.password} sslmode={sslmode}"
        )
        if dbname:
            s += f" dbname={dbname}"
        return s


def _windmill_default_docker_image(gc_repository: str) -> str:
    """Fetch the default Windmill docker image tag from the one-click app definition."""
    # Mimic download one-click-app from remote repository from CaproverAPI's _download_one_click_app_defn
    url = gc_repository + "windmill-only"
    with urllib.request.urlopen(url) as resp:
        raw = resp.read().decode()
    doc = YAML().load(raw)
    # Mimic CaproverAPI's _resolve_app_variables to find variable defaults
    for var in doc.get("caproverOneClickApp", {}).get("variables", []):
        if var.get("id") == "$$cap_app_docker_image":
            default = var.get("defaultValue")
            if default is not None:
                return str(default)
    raise ValueError(
        "$$cap_app_docker_image defaultValue not found in windmill-only one-click app"
    )


def _pre_pull_windmill_image(variables: dict, gc_repository: str) -> None:
    # The Windmill image is large enough to cause CapRover's deploy call to time out
    # before Docker finishes pulling it. Pre-pulling here ensures it is cached.
    image = variables.get("$$cap_app_docker_image") or _windmill_default_docker_image(
        gc_repository
    )
    logger.info(f"Pre-pulling Windmill image {image!r} to avoid CapRover timeout ...")
    subprocess.run(["docker", "pull", image], check=True)
    logger.info("Windmill image pre-pull complete.")


def deploy_stack(config, gc_repository, dry_run):
    """Deploy application stack based on the configuration file."""

    # Initialize CapRover API with URL and password from config
    cap = caprover_api.CaproverAPI(
        dashboard_url=config["caproverUrl"], password=config["caproverPassword"]
    )
    webapps_ssl = config.get("webappsUseSsl", True)

    # Resolve the two Postgres connection configs.
    if config["postgres"].get("deploy", False):
        # We control the deploy: the one-click Postgres has no SSL configured,
        # so any `ssl` field in YAML is ignored to avoid foot-guns.
        container_ssl = vm_ssl = False
    else:
        container_ssl = bool(config["postgres"]["from_container"]["ssl"])
        vm_ssl = bool(config["postgres"]["from_vm"]["ssl"])

    # this is the connection to be used by inter-container networking:
    # i.e. how other CapRover apps reach Postgres. Used in connection strings.
    postgres_from_container = PostgresConnectionConfig(
        host=config["postgres"]["from_container"]["host"],
        port=int(config["postgres"]["from_container"]["port"]),
        user=config["postgres"]["user"],
        password=config["postgres"]["pass"],
        ssl=container_ssl,
    )
    # this is the connection to be used from this script (which runs on the host).
    # Used for one-time setup of databases, users, etc.
    postgres_from_vm = PostgresConnectionConfig(
        host=config["postgres"]["from_vm"]["host"],
        port=int(config["postgres"]["from_vm"]["port"]),
        user=config["postgres"]["user"],
        password=config["postgres"]["pass"],
        ssl=vm_ssl,
    )

    pg_app_name = config["postgres"].get("app_name", "postgres")
    if config["postgres"].get("deploy", False):
        # Deploy internal PostgreSQL instance on CapRover
        postgres_variables = {
            "$$cap_pg_user": config["postgres"]["user"],
            "$$cap_pg_pass": config["postgres"]["pass"],
            "$$cap_pg_database": config["postgres"].get("database", "postgres"),
            "$$cap_postgres_version": config["postgres"].get("version", "16"),
        }
        logger.info("Deploying PostgreSQL")
        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name="postgres",
                app_name=pg_app_name,
                app_variables=postgres_variables,
                automated=True,
            )
            # from_vm.port sets the host-side port mapping
            cap.update_app(
                pg_app_name,
                port_mapping=[
                    f"{postgres_from_vm.port}:{postgres_from_container.port}"
                ],
            )
    else:
        logger.info("Using already-deployed or external PostgreSQL configuration.")
        if not dry_run:
            _verify_existing_postgres_app(
                cap, pg_app_name, postgres_from_container, postgres_from_vm
            )

    if not dry_run:
        with (
            postgres_patient_connect(
                postgres_from_vm.connstr("postgres"), autocommit=True
            ) as conn,
            conn.cursor() as cur,
        ):
            try:
                cur.execute("CREATE DATABASE warehouse;")
            except psycopg.errors.DuplicateDatabase:
                pass

    # Deploy Windmill if specified in config
    one_click_app_name = "windmill-only"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        windmill_db_user = config[one_click_app_name].pop(
            "azure_db_user", postgres_from_container.user
        )
        windmill_db_pass = config[one_click_app_name].pop(
            "azure_db_pass", postgres_from_container.password
        )
        is_using_azure_db = "azure_db_user" in config[one_click_app_name]
        if is_using_azure_db:
            input(
                "Before continuing, enable UUID-OSSP extension on the Azure database..."
            )

        variables = {
            "$$cap_database_url": f"postgres://{windmill_db_user}:{windmill_db_pass}@{postgres_from_container.host}:{postgres_from_container.port}/windmill"
        }

        variables = construct_app_variables(config, one_click_app_name, variables)

        logger.info(f"Deploying {one_click_app_name.capitalize()} one-click app")

        # Hacky workaround: pre-pull large Windmill image to avoid CapRover timeout
        _pre_pull_windmill_image(variables, gc_repository)

        if not dry_run:
            # As superadmin, create a windmill database
            with (
                psycopg.connect(
                    postgres_from_vm.connstr("postgres"), autocommit=True
                ) as conn,
                conn.cursor() as cur,
            ):
                logger.info("Connected to database as superadmin")
                # Execute a command: this creates a new table
                cur.execute("CREATE DATABASE windmill;")
                if is_using_azure_db:
                    cur.execute(
                        f"CREATE USER {windmill_db_user} PASSWORD '{windmill_db_pass}';"
                    )
                    cur.execute(
                        f"GRANT ALL PRIVILEGES ON DATABASE windmill TO {windmill_db_user};"
                    )
                    # Azure only:
                    cur.execute(f"GRANT azure_pg_admin TO {windmill_db_user};")
                    cur.execute(f"ALTER USER {windmill_db_user} CREATEROLE;")

        # As windmill_login
        postgres_azure_user = replace(
            postgres_from_vm, user=windmill_db_user, password=windmill_db_pass
        )
        if is_using_azure_db and not dry_run:
            with psycopg.connect(postgres_azure_user.connstr("windmill")) as conn:
                logger.info(f"Connected to database as {postgres_azure_user.user}")
                with conn.cursor() as cur:
                    # The following comes from https://raw.githubusercontent.com/windmill-labs/windmill/main/init-db-as-superuser.sql
                    cur.execute("CREATE ROLE windmill_user;")
                    cur.execute("""GRANT ALL
                                ON ALL TABLES IN SCHEMA public
                                TO windmill_user;""")
                    cur.execute("""GRANT ALL PRIVILEGES
                                ON ALL SEQUENCES IN SCHEMA public
                                TO windmill_user;""")
                    cur.execute("""ALTER DEFAULT PRIVILEGES
                                IN SCHEMA public
                                GRANT ALL ON TABLES TO windmill_user;""")
                    cur.execute("""ALTER DEFAULT PRIVILEGES
                                IN SCHEMA public
                                GRANT ALL ON SEQUENCES TO windmill_user;""")
                    cur.execute("CREATE ROLE windmill_admin;")  # -WITH BYPASSRLS;
                    cur.execute("GRANT windmill_user TO windmill_admin;")

                    # Going rogue again.
                    cur.execute(f"GRANT windmill_admin TO {postgres_azure_user.user};")
                    cur.execute(f"GRANT windmill_user TO {postgres_azure_user.user};")

        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name,
                app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=gc_repository,
            )
            cap.update_app(app_name, support_websocket=True)
            if webapps_ssl:
                cap.enable_ssl(app_name)
                cap.update_app(app_name, force_ssl=True)

            for svcname in (
                app_name,
                f"{app_name}-worker",
                f"{app_name}-worker-native",
            ):
                set_memory_limit(cap, svcname)

    # Deploy Redis if specified in config
    one_click_app_name = "redis"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        variables = construct_app_variables(config, one_click_app_name)
        logger.info("Deploying Redis")
        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name,
                app_name,
                app_variables=variables,
                automated=True,
            )
            set_memory_limit(cap, app_name)

    # Deploy Superset if specified in config
    one_click_app_name = "superset-only"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        if not dry_run:
            with (
                psycopg.connect(postgres_from_vm.connstr(), autocommit=True) as conn,
                conn.cursor() as cur,
            ):
                cur.execute("CREATE DATABASE superset_metastore;")

        variables = {
            "$$cap_postgres_host": postgres_from_container.host,
            "$$cap_postgres_port": postgres_from_container.port,
            "$$cap_postgres_userpassword": f"{postgres_from_container.user}:{postgres_from_container.password}",
        }
        variables = construct_app_variables(config, one_click_app_name, variables)
        logger.info(f"Deploying {one_click_app_name.capitalize()} one-click app")
        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name,
                app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=gc_repository,
            )
            if webapps_ssl:
                cap.enable_ssl(app_name)
            cap.update_app(
                app_name,
                force_ssl=webapps_ssl,
                redirectDomain=f"{app_name}.{cap.root_domain}",
            )

            # disable the healthcheck in Service Update Override, which will be maintained
            # in future deploys. This is OPTIONAL here because the one-click app already
            # does this in a custom dockerfileLines, but recommended to ease upgrades.
            for appname in (f"{app_name}-init-and-beat", f"{app_name}-worker"):
                worker_app = cap.get_app(appname)
                new_suo = set_yaml_value(
                    worker_app["serviceUpdateOverride"],
                    "TaskTemplate.HealthCheck.Test",
                    ["NONE"],
                )
                # Also set memory limit to workers
                new_suo = set_yaml_value(
                    new_suo, "TaskTemplate.Resources.Limits.MemoryBytes", 1610612736
                )
                cap.update_app(appname, serviceUpdateOverride=new_suo)

            set_memory_limit(cap, app_name)  # The web service (not worker)

    # Deploy GC Landing Page if specified in config
    # Note: as GC Landing Page is intended to be the default landing page, we don't need to add a redirect domain, and instead, we set the redirectDomain to the root domain. (e.g. so that the landing page will load when a user accesses "your-captain-root.net")
    one_click_app_name = "gc-landing-page"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        redirect_to_root = config[one_click_app_name].get("redirect_to_root", True)
        variables = construct_app_variables(config, one_click_app_name)
        logger.info(f"Deploying {one_click_app_name.capitalize()} one-click app")
        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name,
                app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=gc_repository,
            )
            if webapps_ssl:
                cap.enable_ssl(app_name)
                cap.update_app(app_name, force_ssl=True)
            set_memory_limit(cap, app_name)

        if redirect_to_root:
            logger.info(
                f"Will serve {app_name} at the root domain: [{cap.root_domain}]"
            )
            if not dry_run:
                cap.add_domain(app_name, cap.root_domain)
                if webapps_ssl:
                    cap.enable_ssl(app_name, cap.root_domain)
                cap.update_app(app_name, redirectDomain=cap.root_domain)

    # Deploy GC Explorer if specified in config
    one_click_app_name = "gc-explorer"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        if not dry_run:
            with (
                psycopg.connect(postgres_from_vm.connstr(), autocommit=True) as conn,
                conn.cursor() as cur,
            ):
                cur.execute("CREATE DATABASE guardianconnector;")

        variables = {
            "$$cap_postgres_host": postgres_from_container.host,
            "$$cap_postgres_port": postgres_from_container.port,
            "$$cap_postgres_ssl": postgres_from_container.ssl,
            "$$cap_postgres_user": postgres_from_container.user,
            "$$cap_postgres_pass": postgres_from_container.password,
            "$$cap_postgres_database": config[one_click_app_name]["postgres_database"],
        }
        variables = construct_app_variables(config, one_click_app_name, variables)
        logger.info(f"Deploying {one_click_app_name.capitalize()} one-click app")
        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name,
                app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=gc_repository,
            )
            if webapps_ssl:
                cap.enable_ssl(app_name)
            cap.update_app(
                app_name,
                force_ssl=webapps_ssl,
                redirectDomain=f"{app_name}.{cap.root_domain}",
            )
            set_memory_limit(cap, app_name)

    # Deploy CoMapeo Cloud if specified in config
    one_click_app_name = "comapeo-cloud"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        variables = {}
        variables = construct_app_variables(config, one_click_app_name, variables)
        logger.info(f"Deploying {one_click_app_name.capitalize()} one-click app")
        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name,
                app_name,
                app_variables=variables,
                one_click_repository=gc_repository,
                automated=True,
            )
            if webapps_ssl:
                cap.enable_ssl(app_name)
            cap.update_app(
                app_name,
                force_ssl=webapps_ssl,
                support_websocket=True,
                redirectDomain=f"{app_name}.{cap.root_domain}",
            )
            set_memory_limit(cap, app_name)

    # Deploy Filebrowser if specified in config
    one_click_app_name = "filebrowser"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        variables = {}
        variables = construct_app_variables(config, one_click_app_name, variables)
        logger.info(f"Deploying {one_click_app_name.capitalize()} one-click app")

        admin_password = config["filebrowser"].get("admin_password")
        generated = admin_password is None
        if generated:
            admin_password = secrets.token_urlsafe(16)
        hashed_password = bcrypt.hashpw(
            admin_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        if generated:
            print("\n" + "=" * 50)
            print(f"FILEBROWSER ADMIN PASSWORD: {admin_password}")
            print("Save this now -- it will not be shown again.")
            print("=" * 50 + "\n")
        else:
            logger.info("Filebrowser admin password set from config (username: admin)")

        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name,
                app_name,
                app_variables=variables,
                automated=True,
            )
            if webapps_ssl:
                cap.enable_ssl(app_name)
            cap.update_app(
                app_name,
                force_ssl=webapps_ssl,
                redirectDomain=f"{app_name}.{cap.root_domain}",
            )

            cap.update_app(
                app_name,
                persistent_directories=[
                    f"{app_name}-database:/database",
                    f"{app_name}-config:/config",
                    "/mnt/persistent-storage:/srv",  # The files to be served up live here
                ],
                # NOTE: You will get warning pages in the filebrowser app before the `datalake` subdir is created in storage:
                # https://github.com/ConservationMetrics/gc-deploy/pull/12#discussion_r2243697895
                environment_variables={
                    "FB_ROOT": "/srv/datalake",
                    "FB_PASSWORD": hashed_password,
                },
            )
            set_memory_limit(cap, app_name)
            logger.info("Waiting for Filebrowser to initialize its database...")
            time.sleep(20)  # TODO: confirm has started. Now we're just guessing.
            # CaproverAPI doesn't support deletion of an env var, so we just set it to empty
            cap.update_app(app_name, environment_variables={"FB_PASSWORD": ""})


def is_local_path(path):
    """Check if a path is a local file system path."""
    return not (path.startswith("http://") or path.startswith("https://"))


class LocalRepoServer:
    """A context manager for serving a local repository over HTTP."""

    def __init__(self, directory, port=0):
        self.directory = directory
        self.port = port
        self.httpd = None
        self.server_thread = None

    def __enter__(self):
        handler = http.server.SimpleHTTPRequestHandler
        # Use a lambda to bind the directory to the handler
        handler_class = lambda *args, **kwargs: handler(
            *args, directory=self.directory, **kwargs
        )
        self.httpd = socketserver.TCPServer(("", self.port), handler_class)
        self.port = self.httpd.server_address[1]
        logger.info(f"Starting local server for repo at http://127.0.0.1:{self.port}")

        self.server_thread = threading.Thread(target=self.httpd.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        return f"http://127.0.0.1:{self.port}/"

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.httpd:
            logger.info("Shutting down local repo server...")
            self.httpd.shutdown()
            self.httpd.server_close()


def copy_example(dest):
    """
    Copy example config shipped with the package to a local destination

    Parameters
    ----------
    dest : Path
        Destination file to write
    """
    examples = importlib.resources.files("gc_stack_deploy.example_configs")
    for path in examples.iterdir():
        if path.is_file() and path.name == "stack.example.yaml":
            shutil.copy(path, dest)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )

    # OPTIONAL "init" or "deploy" subcommand
    parser.add_argument(
        "command",
        nargs="?",
        choices=["init", "deploy"],
        default="deploy",
        help="Optional subcommand",
    )

    parser.add_argument(
        "-c",
        "--config-file",
        required=True,
        help="Path to configuration YAML file (copy stack.example.yaml)",
    )
    parser.add_argument(
        "--repo",
        default="https://conservationmetrics.github.io/gc-deploy/one-click-apps/v4/apps/",
        help="GC one-click repository app path (default: https://conservationmetrics.github.io/gc-deploy/one-click-apps/v4/apps/)",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable or disable dry-run (default: disabled)",
    )
    args = parser.parse_args()

    if args.command == "init":
        print("init -> " + args.config_file)
        copy_example(args.config_file)
        return

    # Load configuration
    config = load_config(args.config_file)
    repo_path = args.repo

    # Allow to resolve local one-click-app repos via HTTP (useful for testing).
    # CapRoverAPI only supports http://, https:// URLs.
    context_manager = None
    if is_local_path(repo_path):
        # It's a local path, serve it via HTTP
        repo_dir = repo_path.replace("file://", "")
        if not os.path.isdir(repo_dir):
            logger.error(
                f"Local repository path does not exist or is not a directory: {repo_dir}"
            )
            sys.exit(1)
        context_manager = LocalRepoServer(repo_dir)
    else:
        context_manager = nullcontext(repo_path)

    # Deploy application stack
    with context_manager as repo_url:
        deploy_stack(config, repo_url, args.dry_run)


if __name__ == "__main__":
    main()
