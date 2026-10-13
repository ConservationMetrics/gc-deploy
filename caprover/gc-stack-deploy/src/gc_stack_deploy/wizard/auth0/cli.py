"""Shell out to the official Auth0 CLI (`auth0`) from Python

This includes  it, signing-in a tenant admin, & running commands.

1. Installing / uninstalling the CLI:
  `install_cli()` downloads a pinned release of the CLI into a new temporary directory (no
   sudo needed), and checks its SHA. The CLI runs with HOME set to
   that directory.
   remove_cli() deletes the temporary directory.

2. `CliLogin` runs `auth0 login`, which prints a URL and a short code.
   The caller displays them; the admin opens the URL, signs in, and approves.

3. `run_cli()` and `run_json()` run any other `auth0` command as that admin.

Security
--------
The CLI's own token is never read. The CLI stores it in the OS keyring if there is one (which
`remove_cli()` does not clear), else in the temporary directory.
Either way, `auth0 logout` removes it.

Why shell out to the CLI?
-------------------------
The wizard needs an M2M application authorized for the Management API scopes.

- Creating it by hand requires too much clicking in the Auth0 web portal
- The Python SDK can't bootstrap this itself, because of the chicken-and-egg problem where
  it would need a token that already has the scopes it's trying to grant.
- The CLI is able to do it programmatically **because CLI signs in as tenant admin.**
  Thus it can create apps and grant scopes.

"""

import hashlib
import io
import json
import os
import platform
import queue
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass

CLI = "auth0"
COMMAND_TIMEOUT_SECONDS = 60

CLI_VERSION = "1.36.0"
CLI_DOWNLOAD_URL = (
    "https://github.com/auth0/auth0-cli/releases/download/"
    "v{version}/auth0-cli_{version}_{platform}.tar.gz"
)
# From https://github.com/auth0/auth0-cli/releases/tag/v1.36.0
CLI_ARCHIVE_SHA256 = {
    "Linux_x86_64": "5f95695b07ddca90a6cb87392fa0d94c0b945b0f3653f51aa58997c436ba139c",
    "Linux_arm64": "f798e960fc27a0b730444a582ff21e200af7731cee5a654c7f645b4955fc4a19",
    # Max reports "Darwin"
    "Darwin_x86_64": "29fb72b983028c050eed98d58151b46b9595569ee889e8b87929ae564df4ea17",
    "Darwin_arm64": "77849d6fe8e94bf1c38120a597c6a162c196da5011900e658068395a2b9a666c",
}

_cli_dir: str | None = None  # set by install_cli(), cleared by remove_cli()


class Auth0CliError(Exception):
    """An `auth0` CLI step failed; the message is suitable to show the user."""


@dataclass
class DeviceCode:
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None


def validate_tenant_domain(domain: str) -> None:
    """Raise ValueError unless `domain` looks like a canonical Auth0 tenant domain.

    The CLI's browser login only works for "<tenant>.<region>.auth0.com" tenants (not custom
    domains, and not Private Cloud).
    """
    if (
        not domain
        or any(c in domain for c in "/:@ ")
        or not domain.endswith(".auth0.com")
    ):
        raise ValueError(
            "Enter the tenant's Auth0 domain, e.g. your-tenant.us.auth0.com "
        )


def install_cli(
    *, urlopen=urllib.request.urlopen, system: str = "", machine: str = ""
) -> None:
    """Download the Auth0 CLI into a new temporary directory, stored in memory at `_cli_dir`

    Call `remove_cli()` to delete it.

    Does nothing if it is already installed.
    """
    global _cli_dir
    if _cli_dir is not None:
        return
    system = system or platform.system()
    machine = machine or platform.machine()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}
    platform_name = f"{system}_{arch.get(machine.lower(), machine)}"
    expected_sha256 = CLI_ARCHIVE_SHA256.get(platform_name)
    if expected_sha256 is None:
        raise Auth0CliError(
            f"There is no Auth0 CLI download for this machine ({platform_name})."
        )
    url = CLI_DOWNLOAD_URL.format(version=CLI_VERSION, platform=platform_name)
    try:
        with urlopen(url, timeout=COMMAND_TIMEOUT_SECONDS) as response:
            archive = response.read()
    except OSError as exc:
        raise Auth0CliError(
            f"Could not download the Auth0 CLI from {url}: {exc}"
        ) from exc
    if hashlib.sha256(archive).hexdigest() != expected_sha256:
        raise Auth0CliError(f"The Auth0 CLI downloaded from {url} failed its checksum.")
    cli_dir = tempfile.mkdtemp(
        prefix="gc-stack-deploy-auth0-"
    )  # readable only by this user
    cli_path = os.path.join(cli_dir, CLI)
    try:
        with (
            tarfile.open(fileobj=io.BytesIO(archive)) as tar,
            tar.extractfile(CLI) as src,
            open(cli_path, "wb") as dst,
        ):
            shutil.copyfileobj(src, dst)
        os.chmod(cli_path, 0o700)
    except (tarfile.TarError, KeyError, OSError) as exc:
        shutil.rmtree(cli_dir, ignore_errors=True)
        raise Auth0CliError(f"Could not unpack the Auth0 CLI: {exc}") from exc
    _cli_dir = cli_dir


def remove_cli() -> None:
    """Delete the directory `install_cli()` made, containing the CLI and its login. Safe to repeat."""
    global _cli_dir
    if _cli_dir is not None:
        shutil.rmtree(_cli_dir, ignore_errors=True)
        _cli_dir = None


def _cli() -> str:
    if _cli_dir is None:
        raise Auth0CliError("The Auth0 CLI is not installed (see install_cli).")
    return os.path.join(_cli_dir, CLI)


def _env() -> dict[str, str]:
    # Sets the env to Agent mode: JSON output, no prompts, no colors.
    return {
        **os.environ,
        "HOME": _cli_dir or "",
        "AUTH0_AGENT_MODE": "true",
        "NO_COLOR": "1",
    }


def run_cli(args: list[str], *, run=subprocess.run) -> str:
    """Run an `auth0` command and return its stdout.

    Output is never included in error messages: it may contain a client secret.
    """
    try:
        result = run(
            [_cli(), *args],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            env=_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Auth0CliError(f"`{CLI} {args[0]}` could not run: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise Auth0CliError(
            f"`{CLI} {' '.join(args[:2])}` failed: {detail[-1] if detail else result.returncode}"
        )
    return result.stdout


def run_json(args: list[str], *, run=subprocess.run) -> dict:
    """Run an `auth0` command and return its JSON output as a dict."""
    stdout = run_cli(args, run=run)
    if not stdout.strip():
        return {}
    try:
        body = json.loads(stdout)
    except ValueError as exc:
        raise Auth0CliError(f"`{CLI} {args[0]}` printed unexpected output.") from exc
    return body if isinstance(body, dict) else {}


def _json_objects(lines: Iterator[str]) -> Iterator[dict]:
    """Yield each line of CLI output that is a JSON object (in agent mode, one per line)."""
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj


class CliLogin:
    """A running `auth0 login`, which prints a device code and waits for approval."""

    def __init__(self, domain: str, *, popen=subprocess.Popen):
        self.domain = domain
        self._proc = popen(
            [_cli(), "login", "--domain", domain, "--no-input"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_env(),
        )
        self._objects: queue.Queue = queue.Queue()
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def _read_stdout(self) -> None:
        try:
            for obj in _json_objects(iter(self._proc.stdout)):
                self._objects.put(obj)
        finally:
            self._objects.put(None)  # EOF

    def _next_object(
        self, cancelled: Callable[[], bool], timeout: float
    ) -> dict | None:
        deadline = time.monotonic() + timeout
        while True:
            if cancelled():
                self.cancel()
                raise Auth0CliError("Login cancelled.")
            try:
                return self._objects.get(timeout=0.2)
            except queue.Empty:
                if time.monotonic() >= deadline:
                    self.cancel()
                    raise Auth0CliError("Timed out waiting for the Auth0 CLI.")

    def _fail(self, what: str) -> Auth0CliError:
        stderr = ""
        try:
            self._proc.wait(timeout=5)
            stderr = (self._proc.stderr.read() or "").strip()
        except Exception:
            pass
        detail = stderr.splitlines()[-1] if stderr else "no details"
        return Auth0CliError(f"{what}: {detail}")

    def wait_for_device_code(
        self, cancelled: Callable[[], bool] = lambda: False, timeout: float = 30
    ) -> DeviceCode:
        """Block until the CLI prints the URL and code for the admin to open."""
        while True:
            obj = self._next_object(cancelled, timeout)
            if obj is None:
                raise self._fail("Auth0 CLI login did not start")
            if "user_code" in obj and "verification_uri" in obj:
                return DeviceCode(
                    user_code=obj["user_code"],
                    verification_uri=obj["verification_uri"],
                    verification_uri_complete=obj.get("verification_uri_complete"),
                )

    def wait_for_approval(
        self, cancelled: Callable[[], bool] = lambda: False, timeout: float = 15 * 60
    ) -> None:
        """Block until the admin approves, or raise if they don't."""
        while True:
            obj = self._next_object(cancelled, timeout)
            if obj is None:
                raise self._fail("Auth0 login was not completed")
            if obj.get("logged_in") is True:
                self._proc.wait(timeout=10)
                return

    def cancel(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
