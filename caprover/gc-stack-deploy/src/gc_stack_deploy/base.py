"""Core data classes for gc-stack-deploy

AppSpec: Superclass for a deployable app (Postgres, Windmill, Redis, ...).
    Subclasses MUST override _install() and declare depends_on.
    In rare cases, subclasses MAY want to override _uninstall() and/or check_installed()

DeploymentContext: shared, immutable-ish state (CapRover client, resolved
    postgres connection configs, dry_run flag) passed into every call instead
    of being closed over.

TODO: Unit test these in isolation.  Assert install / uninstall calls on CapRover API.
"""

import abc
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum

import psycopg


class AppStatus(str, Enum):
    NOT_INSTALLED = "not installed"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    UNINSTALLING = "uninstalling"


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


@dataclass
class DeploymentContext:
    """Container of state that's global-ish and immutable-ish over the entire script execution.

    It gets passed to every app that needs to be installed / uninstalled
    """

    caprover: "caprover_api.CaproverAPI"
    postgres_from_container: PostgresConnectionConfig
    postgres_from_vm: PostgresConnectionConfig
    gc_repository: str
    webapps_use_ssl: bool
    dry_run: bool


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


def _psql_create_database_if_not_exists(cursor, dbname):
    try:
        q = psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(dbname))
        cursor.execute(q)
    except psycopg.errors.DuplicateDatabase:
        pass


class AppSpec(abc.ABC):
    """Base class for a single deployable app in the CapRover stack.

    Each concrete subclass declares a `one_click_app_name` (the CapRover one-click app
    it wraps), zero or more `databases` it needs to exist before install, and implements
    `_install()` with its app-specific calls.

    Database provisioning (via `databases`) is idempotent and independent
    of whether this app's own Postgres server was deployed by this run
    or already existed: `install()` always ensures the databases are
    present before delegating to `_install()`.

    `depends_on` is only declarative at this point: nothing currently
    reads it to enforce install ordering.
    """

    one_click_app_name: str
    depends_on: tuple[str] = ()
    databases: tuple[str] = ()

    def __init__(self, app_config, ctx: DeploymentContext):
        """Bind this app to a deployment context."""
        self.app_cfg = app_config
        self.ctx = ctx
        self.logger = logging.getLogger(
            f"gc-stack-deploy.apps.{self.one_click_app_name}"
        )

    @property
    def app_name(self) -> str:
        return self.app_cfg.get("app_name", self.one_click_app_name)

    def check_installed(self) -> AppStatus:
        """Query CapRover for this app's current status."""
        return (
            AppStatus.INSTALLED
            if self.ctx.caprover.get_app(self.app_name)
            else AppStatus.NOT_INSTALLED
        )

    def install(self) -> None:
        self.logger.info(f"Beginning install of {self.app_name}")
        if self.databases and not self.ctx.dry_run:
            with (
                postgres_patient_connect(
                    self.ctx.postgres_from_vm.connstr(), autocommit=True
                ) as conn,
                conn.cursor() as cur,
            ):
                for dbname in self.databases:
                    _psql_create_database_if_not_exists(cur, dbname)

        self._install()  # subclass-specific logic

        self.logger.info(f"Finished install of {self.app_name}")

    @abc.abstractmethod
    def _install(self) -> None:
        """App-specific install steps. Called by install() after
        this app's `databases` have been created. Do not call directly."""
        raise NotImplementedError()

    def uninstall(self) -> None:
        self.logger.info(f"Beginning uninstall of {self.app_name}")
        self._uninstall()
        self.logger.info(f"Finished uninstall of {self.app_name}")

    def _uninstall(self) -> None:
        """Uninstall the app from caprover.

        It removes ALL apps matching the app_name prefix.  That will handle examples like

            mywebapp
            mywebapp-worker

        This implementation DOES delete docker volume mounts (since those are managed by CapRover),
        but does NOT undo any database setup (e.g. CREATE DATABASE ...) done as part of install().

        Override for different behavior.
        """
        self.ctx.caprover.delete_app_matching_pattern(
            rf"^{self.app_name}", automated=True
        )
