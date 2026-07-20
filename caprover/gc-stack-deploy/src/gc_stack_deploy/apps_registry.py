import io
import logging
import secrets
import subprocess
import time
import urllib.request
from dataclasses import replace
from functools import reduce

import bcrypt
import psycopg
from ruamel.yaml import YAML

from .base import AppSpec

logger = logging.getLogger(__name__)


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


def set_memory_limit(cap, appname, memory_bytes=1610612736):
    app = cap.get_app(appname)
    new_suo = set_yaml_value(
        app["serviceUpdateOverride"],
        "TaskTemplate.Resources.Limits.MemoryBytes",
        memory_bytes,
    )
    cap.update_app(appname, serviceUpdateOverride=new_suo)


def construct_app_variables(app_cfg, init=None):
    variables = {} if init is None else init
    for key, val in app_cfg.items():
        if key == "deploy":
            continue
        variables[f"$$cap_{key}"] = val
    return variables


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


class PostgresApp(AppSpec):
    one_click_app_name = "postgres"

    def _install(self) -> None:
        cap = self.ctx.caprover
        pg_app_name = self.app_name

        postgres_variables = {
            "$$cap_pg_user": self.app_cfg["user"],
            "$$cap_pg_pass": self.app_cfg["pass"],
            "$$cap_pg_database": self.app_cfg.get("database", "postgres"),
            "$$cap_postgres_version": self.app_cfg.get("version", "16"),
        }
        self.logger.info("Deploying PostgreSQL")
        if not self.ctx.dry_run:
            cap.deploy_one_click_app(
                one_click_app_name=self.one_click_app_name,
                app_name=pg_app_name,
                app_variables=postgres_variables,
                automated=True,
            )
            cap.update_app(
                pg_app_name,
                port_mapping=[
                    f"{self.ctx.postgres_from_vm.port}:{self.ctx.postgres_from_container.port}"
                ],
            )


class WindmillApp(AppSpec):
    one_click_app_name = "windmill-only"
    depends_on = (PostgresApp.one_click_app_name,)
    databases = ("warehouse", "windmill")

    @property
    def windmill_db_user_and_password(self):
        windmill_db_user = self.app_cfg.pop(  # FIXME: config should be immutable
            "azure_db_user", self.ctx.postgres_from_container.user
        )
        windmill_db_pass = self.app_cfg.pop(
            "azure_db_pass", self.ctx.postgres_from_container.password
        )
        return windmill_db_user, windmill_db_pass

    def _install(self) -> None:
        is_using_azure_db = "azure_db_user" in self.app_cfg
        if is_using_azure_db:
            input(
                "Before continuing, enable UUID-OSSP extension on the Azure database..."
            )

        windmill_db_user, windmill_db_pass = self.windmill_db_user_and_password
        variables = {
            "$$cap_database_url": f"postgres://{windmill_db_user}:{windmill_db_pass}@{self.ctx.postgres_from_container.host}:{self.ctx.postgres_from_container.port}/windmill"
        }
        variables = construct_app_variables(self.app_cfg, variables)

        dry_run = self.ctx.dry_run
        self.logger.info("Settuing up database for Windmill")
        if not dry_run:
            # As superadmin, create a windmill database
            with (
                psycopg.connect(
                    self.ctx.postgres_from_vm.connstr("postgres"), autocommit=True
                ) as conn,
                conn.cursor() as cur,
            ):
                logger.info("Connected to database as superadmin")
                if is_using_azure_db:
                    cur.execute(
                        f"CREATE USER {windmill_db_user} PASSWORD '{windmill_db_pass}';"
                    )
                    cur.execute(
                        f"GRANT ALL PRIVILEGES ON DATABASE windmill TO {windmill_db_user};"
                    )
                    # Azure only:
                    cur.execute(
                        psycopg.sql.SQL("GRANT azure_pg_admin TO {};").format(
                            psycopg.sql.Identifier(windmill_db_user)
                        )
                    )
                    cur.execute(
                        psycopg.sql.SQL("ALTER USER {} CREATEROLE;").format(
                            psycopg.sql.Identifier(windmill_db_user)
                        )
                    )

        # As windmill_login
        postgres_azure_user = replace(
            self.ctx.postgres_from_vm, user=windmill_db_user, password=windmill_db_pass
        )
        if is_using_azure_db and not dry_run:
            with psycopg.connect(postgres_azure_user.connstr("windmill")) as conn:
                self.logger.info(f"Connected to database as {postgres_azure_user.user}")
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
                    cur.execute(
                        psycopg.sql.SQL("GRANT windmill_admin TO {};").format(
                            psycopg.sql.Identifier(postgres_azure_user.user)
                        )
                    )
                    cur.execute(
                        psycopg.sql.SQL("GRANT windmill_user TO {};").format(
                            psycopg.sql.Identifier(postgres_azure_user.user)
                        )
                    )

        # Hacky workaround: pre-pull large Windmill image to avoid CapRover timeout
        _pre_pull_windmill_image(variables, self.ctx.gc_repository)
        self.logger.info("Deploying Windmill one-click-app")
        if not dry_run:
            cap = self.ctx.caprover
            cap.deploy_one_click_app(
                self.one_click_app_name,
                self.app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=self.ctx.gc_repository,
            )
            cap.update_app(self.app_name, support_websocket=True)
            if self.ctx.webapps_use_ssl:
                cap.enable_ssl(self.app_name)
                cap.update_app(self.app_name, force_ssl=True)

            for svcname in (
                self.app_name,
                f"{self.app_name}-worker",
                f"{self.app_name}-worker-native",
            ):
                set_memory_limit(cap, svcname)


class RedisApp(AppSpec):
    one_click_app_name = "redis"

    def _install(self) -> None:
        variables = construct_app_variables(self.app_cfg)

        self.logger.info("Deploying Redis")
        if not self.ctx.dry_run:
            self.ctx.caprover.deploy_one_click_app(
                self.one_click_app_name,
                self.app_name,
                app_variables=variables,
                automated=True,
            )
            set_memory_limit(self.ctx.caprover, self.app_name)


class SupersetApp(AppSpec):
    one_click_app_name = "superset-only"
    depends_on = (
        PostgresApp.one_click_app_name,
        RedisApp.one_click_app_name,
    )
    databases = ("warehouse",)

    def _install(self) -> None:
        postgres_from_container = self.ctx.postgres_from_container
        cap = self.ctx.caprover

        if not self.ctx.dry_run:
            with (
                psycopg.connect(
                    self.ctx.postgres_from_vm.connstr(), autocommit=True
                ) as conn,
                conn.cursor() as cur,
            ):
                cur.execute("CREATE DATABASE superset_metastore;")

        variables = {
            "$$cap_postgres_host": postgres_from_container.host,
            "$$cap_postgres_port": postgres_from_container.port,
            "$$cap_postgres_userpassword": f"{postgres_from_container.user}:{postgres_from_container.password}",
        }
        variables = construct_app_variables(self.app_cfg, variables)
        self.logger.info(f"Deploying {self.one_click_app_name} one-click app")
        if not self.ctx.dry_run:
            cap.deploy_one_click_app(
                self.one_click_app_name,
                self.app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=self.ctx.gc_repository,
            )
            if self.ctx.webapps_use_ssl:
                cap.enable_ssl(self.app_name)
                cap.update_app(self.app_name, force_ssl=True)

            # disable the healthcheck in Service Update Override, which will be maintained
            # in future deploys. This is OPTIONAL here because the one-click app already
            # does this in a custom dockerfileLines, but recommended to ease upgrades.
            for appname in (
                f"{self.app_name}-init-and-beat",
                f"{self.app_name}-worker",
            ):
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

            set_memory_limit(cap, self.app_name)  # The web service (not worker)


class GCLandingPageApp(AppSpec):
    one_click_app_name = "gc-landing-page"
    depends_on = (PostgresApp.one_click_app_name,)
    databases = ("warehouse", "guardianconnector")

    def _install(self) -> None:
        postgres_from_container = self.ctx.postgres_from_container
        cap = self.ctx.caprover

        redirect_to_root = self.app_cfg.get("redirect_to_root", True)
        variables = {
            "$$cap_postgres_host": postgres_from_container.host,
            "$$cap_postgres_port": postgres_from_container.port,
            "$$cap_postgres_ssl": postgres_from_container.ssl,
            "$$cap_postgres_user": postgres_from_container.user,
            "$$cap_postgres_pass": postgres_from_container.password,
        }
        variables = construct_app_variables(self.app_cfg, variables)
        self.logger.info(f"Deploying {self.one_click_app_name} one-click app")
        if not self.ctx.dry_run:
            cap.deploy_one_click_app(
                self.one_click_app_name,
                self.app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=self.ctx.gc_repository,
            )
            if self.ctx.webapps_use_ssl:
                cap.enable_ssl(self.app_name)
                cap.update_app(self.app_name, force_ssl=True)
            set_memory_limit(cap, self.app_name)

        if redirect_to_root:
            self.logger.info(
                f"Will serve {self.app_name} at the root domain: [{cap.root_domain}]"
            )
            if not self.ctx.dry_run:
                cap.add_domain(self.app_name, cap.root_domain)
                if self.ctx.webapps_use_ssl:
                    cap.enable_ssl(self.app_name, cap.root_domain)
                cap.update_app(self.app_name, redirectDomain=cap.root_domain)


class GCExplorerApp(AppSpec):
    one_click_app_name = "gc-explorer"
    depends_on = (PostgresApp.one_click_app_name,)
    databases = ("warehouse", "guardianconnector")

    def _install(self) -> None:
        postgres_from_container = self.ctx.postgres_from_container
        cap = self.ctx.caprover

        variables = {
            "$$cap_postgres_host": postgres_from_container.host,
            "$$cap_postgres_port": postgres_from_container.port,
            "$$cap_postgres_ssl": postgres_from_container.ssl,
            "$$cap_postgres_user": postgres_from_container.user,
            "$$cap_postgres_pass": postgres_from_container.password,
            "$$cap_postgres_database": self.app_cfg["postgres_database"],
        }
        variables = construct_app_variables(self.app_cfg, variables)
        self.logger.info(f"Deploying {self.one_click_app_name} one-click app")
        if not self.ctx.dry_run:
            cap.deploy_one_click_app(
                self.one_click_app_name,
                self.app_name,
                app_variables=variables,
                automated=True,
                one_click_repository=self.ctx.gc_repository,
            )
            if self.ctx.webapps_use_ssl:
                cap.enable_ssl(self.app_name)
                cap.update_app(self.app_name, force_ssl=True)
            set_memory_limit(cap, self.app_name)


class ComapeoCloudApp(AppSpec):
    one_click_app_name = "comapeo-cloud"

    def _install(self) -> None:
        variables = {}
        variables = construct_app_variables(self.app_cfg, variables)
        self.logger.info(f"Deploying {self.one_click_app_name} one-click app")
        cap = self.ctx.caprover
        if not self.ctx.dry_run:
            cap.deploy_one_click_app(
                self.one_click_app_name,
                self.app_name,
                app_variables=variables,
                one_click_repository=self.ctx.gc_repository,
                automated=True,
            )
            if self.ctx.webapps_use_ssl:
                cap.enable_ssl(self.app_name)
            cap.update_app(
                self.app_name,
                force_ssl=self.ctx.webapps_use_ssl,
                support_websocket=True,
            )
            set_memory_limit(cap, self.app_name)


class FilebrowserApp(AppSpec):
    one_click_app_name = "filebrowser"

    def _install(self) -> None:

        cap = self.ctx.caprover
        variables = {}
        variables = construct_app_variables(self.app_cfg, variables)
        self.logger.info(f"Deploying {self.one_click_app_name} one-click app")

        admin_password = self.app_cfg.get("admin_password")
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
            self.logger.info(
                "Filebrowser admin password set from config (username: admin)"
            )

        if not self.ctx.dry_run:
            cap.deploy_one_click_app(
                self.one_click_app_name,
                self.app_name,
                app_variables=variables,
                automated=True,
            )
            if self.ctx.webapps_use_ssl:
                cap.enable_ssl(self.app_name)
                cap.update_app(self.app_name, force_ssl=True)

            cap.update_app(
                self.app_name,
                persistent_directories=[
                    f"{self.app_name}-database:/database",
                    f"{self.app_name}-config:/config",
                    "/mnt/persistent-storage:/srv",  # The files to be served up live here
                ],
                # NOTE: You will get warning pages in the filebrowser app before the `datalake` subdir is created in storage:
                # https://github.com/ConservationMetrics/gc-deploy/pull/12#discussion_r2243697895
                environment_variables={
                    "FB_ROOT": "/srv/datalake",
                    "FB_PASSWORD": hashed_password,
                },
            )
            set_memory_limit(cap, self.app_name)
            self.logger.info("Waiting for Filebrowser to initialize its database...")
            time.sleep(20)  # TODO: confirm has started. Now we're just guessing.
            # CaproverAPI doesn't support deletion of an env var, so we just set it to empty
            cap.update_app(self.app_name, environment_variables={"FB_PASSWORD": ""})


APPS_REGISTRY: list[type[AppSpec]] = [
    PostgresApp,
    WindmillApp,
    RedisApp,
    SupersetApp,
    GCLandingPageApp,
    GCExplorerApp,
    ComapeoCloudApp,
    FilebrowserApp,
]
