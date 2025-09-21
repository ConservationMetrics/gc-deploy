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
import logging
import os
import shutil
import socketserver
import sys
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace

import psycopg
import yaml
from caprover_api import caprover_api

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_config(file_path):
    """Load configuration from YAML file."""
    try:
        with open(file_path, "r") as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Configuration file {file_path} not found.")
        sys.exit(1)
    return config


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
        Base delay in seconds between retries (exponential backoff).
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
                time.sleep(delay_seconds * (2 ** (attempt - 1)))
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
        s = f"host={self.host} port={self.port} user={self.user} password={self.password}"
        if dbname:
            s += f" dbname={dbname}"
        return s


def deploy_stack(config, gc_repository, dry_run):
    """Deploy application stack based on the configuration file."""

    # Initialize CapRover API with URL and password from config
    cap = caprover_api.CaproverAPI(
        dashboard_url=config["caproverUrl"], password=config["caproverPassword"]
    )
    webapps_ssl = config.get("webappsUseSsl", True)

    # Deploy PostgreSQL if specified in config
    if config["postgres"].get("deploy", False):
        # Deploy internal PostgreSQL instance on CapRover
        app_name = "postgres"
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
                app_variables=postgres_variables,
                automated=True,
            )

        # this is the connection to be used by inter-container networking
        postgres_from_container = PostgresConnectionConfig(
            "srv-captain--postgres",
            config["postgres"]["user"],
            config["postgres"]["pass"],
            ssl=False,
        )
        # this is the connection to be used from this script (which runs on the host)
        postgres_from_vm = None

        # For Docker deployments, expose the postgres server at this custom port on the VM
        postgres_vm_port = int(config["postgres"]["exposePort"])
        cap.update_app(
            app_name,
            port_mapping=[f"{postgres_vm_port}:{postgres_from_container.port}"],
        )

        # this is the connection to be used from this script (which runs on the host)
        postgres_from_vm = PostgresConnectionConfig(
            cap.root_domain,
            config["postgres"]["user"],
            config["postgres"]["pass"],
            ssl=False,
            port=postgres_vm_port,
        )

    else:
        # Using an external PostgreSQL instance
        logger.info("Using external PostgreSQL configuration.")
        postgres_from_container = postgres_from_vm = PostgresConnectionConfig(
            config["postgres"]["host"],
            config["postgres"]["user"],
            config["postgres"]["pass"],
            ssl=True,
            port=config["postgres"]["port"],
        )

    with (
        postgres_patient_connect(
            postgres_from_vm.connstr("postgres"), autocommit=True
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("CREATE DATABASE warehouse;")

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

        # As superadmin, create a windmill database
        with psycopg.connect(
            postgres_from_vm.connstr("postgres"), autocommit=True
        ) as conn:
            logger.info("Connected to database as superadmin")
            if not dry_run:
                with conn.cursor() as cur:
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

        if is_using_azure_db and not dry_run:
            # As windmill_login
            postgres_azure_user = replace(
                postgres_from_vm, user=windmill_db_user, password=windmill_db_pass
            )
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

    # Deploy Superset if specified in config
    one_click_app_name = "superset-only"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
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
                new_suo = (
                    worker_app["serviceUpdateOverride"]
                    + '\n    HealthCheck:\n      Test: ["NONE"]'
                )
                cap.update_app(appname, serviceUpdateOverride=new_suo)

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

    # Deploy Filebrowser if specified in config
    one_click_app_name = "filebrowser"
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
                environment_variables={"FB_ROOT": "/srv/datalake"},
            )


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
