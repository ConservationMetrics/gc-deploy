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
from contextlib import nullcontext

from caprover_api import caprover_api
from ruamel.yaml import YAML

from .APPS_REGISTRY import APPS_REGISTRY, PostgresApp
from .base import DeploymentContext, PostgresConnectionConfig

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


def build_deployment_context(config, gc_repository, dry_run):
    # Initialize CapRover API with URL and password from config
    cap = caprover_api.CaproverAPI(
        dashboard_url=config["caproverUrl"], password=config["caproverPassword"]
    )
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

    webapps_use_ssl = config.get("webappsUseSsl", True)
    return DeploymentContext(
        cap,
        postgres_from_container,
        postgres_from_vm,
        gc_repository,
        webapps_use_ssl,
        dry_run,
    )


def deploy_stack(config, gc_repository, dry_run):
    """Deploy application stack based on the configuration file."""
    ctx = build_deployment_context(config, gc_repository, dry_run)

    # Apps in the registry that have a config block, in registry order
    apps_with_config = [
        cls for cls in APPS_REGISTRY if cls.one_click_app_name in config
    ]
    # Further filter to those where deployed:true, and instantiate an instance with the config and DeploymentContext
    apps_to_deploy = [
        cls
        for cls in apps_with_config
        if config[cls.one_click_app_name].get("deploy", False)
    ]

    # Edge case: not deploying postgres, but we want to check it because so much
    # downstream depends on it.
    if PostgresApp in apps_with_config and PostgresApp not in apps_to_deploy:
        logger.info("Using already-deployed or external PostgreSQL configuration.")
        pg_app_name = config[PostgresApp.one_click_app_name].get(
            "app_name", PostgresApp.one_click_app_name
        )
        if not dry_run:
            _verify_existing_postgres_app(
                ctx.caprover,
                pg_app_name,
                ctx.postgres_from_container,
                ctx.postgres_from_vm,
            )

    # Install apps!
    for cls in apps_to_deploy:
        app = cls(config[cls.one_click_app_name], ctx)
        app.install()


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
