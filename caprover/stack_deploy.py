"""
Deploy multiple apps of the Guardian stack to a VM running CapRover.

Use a configuration file of variable values.

This greatly reduces the clicking and copy/pasting needed to deploy the full
Guardian Connector stack.  The script is able to inject the same variable value
(e.g. database info) into multiple apps that request it.

"""

import argparse
import logging
import sys

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


def deploy_stack(config, gc_repository, dry_run):
    """Deploy application stack based on the configuration file."""

    # Initialize CapRover API with URL and password from config
    cap = caprover_api.CaproverAPI(
        dashboard_url=config.get("caproverUrl"), password=config.get("caproverPassword")
    )

    # Deploy PostgreSQL if specified in config
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
                app_variables=postgres_variables,
                automated=True,
            )
        postgres_host = "srv-captain--postgres"
        postgres_port = "5432"
        postgres_ssl = "false"
    else:
        # Using an external PostgreSQL instance
        logger.info("Using external PostgreSQL configuration.")
        postgres_host = config["postgres"]["host"]
        postgres_port = config["postgres"]["port"]
        postgres_ssl = "true"

    # Deploy Windmill if specified in config
    one_click_app_name = "windmill-only"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        windmill_db_user = config[one_click_app_name].pop("db_user")
        windmill_db_pass = config[one_click_app_name].pop("db_pass")
        variables = {
            "$$cap_database_url": f"postgres://{windmill_db_user}:{windmill_db_pass}@{postgres_host}:{postgres_port}/windmill"
        }

        variables = construct_app_variables(config, one_click_app_name, variables)
        logger.info(f"Deploying {one_click_app_name.capitalize()} one-click app")

        input("Before continuing, enable UUID-OSSP extension on the Azure database...")

        # As superadmin, create a user windmill_admin and create a windmill database
        with psycopg.connect(
            f"host={postgres_host} port={postgres_port} user={config['postgres']['user']} password={config['postgres']['pass']} dbname=postgres",
            autocommit=True,
        ) as conn:
            logger.info("Connected to database as superadmin")
            if not dry_run:
                with conn.cursor() as cur:
                    # Execute a command: this creates a new table
                    cur.execute("CREATE DATABASE windmill;")
                    cur.execute(
                        f"CREATE USER {windmill_db_user} PASSWORD '{windmill_db_pass}';"
                    )
                    cur.execute(
                        f"GRANT ALL PRIVILEGES ON DATABASE windmill TO {windmill_db_user};"
                    )
                    # Azure only:
                    cur.execute(f"GRANT azure_pg_admin TO {windmill_db_user};")
                    cur.execute(f"ALTER USER {windmill_db_user} CREATEROLE;")

        if not dry_run:
            # As windmill_login
            with psycopg.connect(
                f"host={postgres_host} port={postgres_port} user={windmill_db_user} password={windmill_db_pass} dbname=windmill"
            ) as conn:
                logger.info(f"Connected to database as {windmill_db_user}")
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
                    cur.execute(f"GRANT windmill_admin TO {windmill_db_user};")
                    cur.execute(f"GRANT windmill_user TO {windmill_db_user};")
        if not dry_run:
            cap.deploy_one_click_app(
                one_click_app_name,
                app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=gc_repository,
            )
            cap.enable_ssl(app_name)
            cap.update_app(app_name, force_ssl=True, support_websocket=True)

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
        variables = {
            "$$cap_postgres_host": postgres_host,
            "$$cap_postgres_port": postgres_port,
            "$$cap_postgres_userpassword": f"{config['postgres']['user']}:{config['postgres']['pass']}",
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
            cap.enable_ssl(app_name)
            cap.update_app(
                app_name, force_ssl=True, redirectDomain=f"{app_name}.{cap.root_domain}"
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

            if redirect_from_domain := config[one_click_app_name].get(
                "redirect_from_domain"
            ):
                try:
                    cap.add_domain(app_name, redirect_from_domain)
                    cap.enable_ssl(app_name, redirect_from_domain)
                except Exception as e:
                    logger.error(f"Verification failed: {e}")

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
            cap.enable_ssl(app_name)
            cap.update_app(app_name, force_ssl=True)

        if redirect_to_root:
            logger.info(
                f"Will serve {app_name} at the root domain: [{cap.root_domain}]"
            )
            if not dry_run:
                cap.add_domain(app_name, cap.root_domain)
                cap.enable_ssl(app_name, cap.root_domain)
                cap.update_app(app_name, redirectDomain=cap.root_domain)

    # Deploy GC Explorer if specified in config
    one_click_app_name = "gc-explorer"
    if config.get(one_click_app_name, {}).get("deploy", False):
        app_name = config[one_click_app_name].get("app_name", one_click_app_name)
        variables = {
            "$$cap_postgres_host": postgres_host,
            "$$cap_postgres_port": postgres_port,
            "$$cap_postgres_ssl": postgres_ssl,
            "$$cap_postgres_user": config["postgres"]["user"],
            "$$cap_postgres_pass": config["postgres"]["pass"],
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
            cap.enable_ssl(app_name)
            cap.update_app(
                app_name, force_ssl=True, redirectDomain=f"{app_name}.{cap.root_domain}"
            )

            if redirect_from_domain := config[one_click_app_name].get(
                "redirect_from_domain"
            ):
                try:
                    cap.add_domain(app_name, redirect_from_domain)
                    cap.enable_ssl(app_name, redirect_from_domain)
                except Exception as e:
                    logger.error(f"Verification failed: {e}")

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
            cap.enable_ssl(app_name)
            cap.update_app(
                app_name,
                force_ssl=True,
                support_websocket=True,
                redirectDomain=f"{app_name}.{cap.root_domain}",
            )

            if redirect_from_domain := config[one_click_app_name].get(
                "redirect_from_domain"
            ):
                try:
                    cap.add_domain(app_name, redirect_from_domain)
                    cap.enable_ssl(app_name, redirect_from_domain)
                except Exception as e:
                    logger.error(f"Verification failed: {e}")

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
            cap.enable_ssl(app_name)
            cap.update_app(
                app_name, force_ssl=True, redirectDomain=f"{app_name}.{cap.root_domain}"
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

            if redirect_from_domain := config[one_click_app_name].get(
                "redirect_from_domain"
            ):
                try:
                    cap.add_domain(app_name, redirect_from_domain)
                    cap.enable_ssl(app_name, redirect_from_domain)
                except Exception as e:
                    logger.error(f"Verification failed: {e}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
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

    # Load configuration
    config = load_config(args.config_file)

    # Deploy application stack
    deploy_stack(config, args.repo, args.dry_run)


if __name__ == "__main__":
    main()
