"""Core data classes for gc-stack-deploy

AppSpec: Superclass for a deployable app (Postgres, Windmill, Redis, ...).
    Each implements install(ctx) and declares depends_on.

DeploymentContext: shared, immutable-ish state (CapRover client, resolved
    postgres connection configs, dry_run flag) passed into every call instead
    of being closed over.

TODO: Unit test these in isolation.  Assert install calls on CapRover API.
"""

import abc
import logging
from dataclasses import dataclass


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

    It gets passed to every app that needs to be installed
    """

    caprover: "caprover_api.CaproverAPI"
    postgres_from_container: PostgresConnectionConfig
    postgres_from_vm: PostgresConnectionConfig
    gc_repository: str
    webapps_use_ssl: bool
    dry_run: bool


class AppSpec(abc.ABC):
    one_click_app_name: str
    depends_on: tuple[str] = ()

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

    @abc.abstractmethod
    def install(self) -> None:
        raise NotImplementedError()
