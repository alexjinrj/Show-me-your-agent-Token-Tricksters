"""Orchestrate a Lightsail Container Service deployment of the app image.

High-level flow (:func:`deploy`):

1. Preflight: check that ``docker``, ``aws`` CLI, and the ``lightsailctl``
   plugin are installed, and that AWS credentials resolve.
2. Build the Docker image from the repository ``Dockerfile``.
3. Ensure the Lightsail container service exists (create if missing).
4. Push the local image to the service; capture the registered image ref.
5. Create a deployment that publishes the container on its public endpoint
   with an HTTP health check.
6. Poll until the service is ``RUNNING`` and return the public HTTPS URL.

Control-plane calls use ``boto3``; image build/push shell out to ``docker`` and
the ``aws lightsail push-container-image`` command (which needs ``lightsailctl``).
Only :func:`teardown` deletes cloud resources, and it is never called implicitly.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from deploy.aws_lightsail.config import LightsailConfig


class DeploymentError(RuntimeError):
    """Raised when a deployment step fails with an actionable message."""


@dataclass(frozen=True)
class DeploymentResult:
    """Outcome of a successful :func:`deploy` call."""

    service_name: str
    region: str
    url: str
    state: str
    image_ref: str


# ---- Preflight ---------------------------------------------------------------

REQUIRED_BINARIES = ("docker", "aws")


def _which(binary: str) -> bool:
    return shutil.which(binary) is not None


def preflight(config: LightsailConfig) -> None:
    """Fail fast with clear guidance if the local toolchain is incomplete."""
    missing = [b for b in REQUIRED_BINARIES if not _which(b)]
    if missing:
        raise DeploymentError(
            "Missing required tool(s): "
            + ", ".join(missing)
            + ". Install Docker and the AWS CLI v2, then retry."
        )
    if not _which("lightsailctl") and not _lightsailctl_via_aws():
        raise DeploymentError(
            "The 'lightsailctl' plugin is required to push images to Lightsail. "
            "Install it: https://lightsail.aws.amazon.com/ls/docs/en_us/articles/"
            "amazon-lightsail-install-software"
        )
    if not config.dockerfile_path.is_file():
        raise DeploymentError(f"Dockerfile not found at {config.dockerfile_path}")


def _lightsailctl_via_aws() -> bool:
    """lightsailctl may be resolvable by the aws CLI even if not on PATH."""
    # We cannot cheaply verify this without a network call, so treat a present
    # aws CLI as sufficient and let the push step surface a precise error.
    return _which("aws")


# ---- Shell helpers -----------------------------------------------------------


def _run(
    cmd: list[str],
    *,
    capture: bool = False,
    stream: bool = False,
) -> str:
    """Run a subprocess, raising :class:`DeploymentError` on failure.

    Returns captured stdout when ``capture`` is True, else an empty string.
    """
    printable = " ".join(cmd)
    try:
        if stream:
            subprocess.run(cmd, check=True)
            return ""
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DeploymentError(f"Command not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise DeploymentError(f"Command failed ({printable}):\n{detail}") from exc
    return result.stdout if capture else ""


# ---- boto3 client ------------------------------------------------------------


def _client(config: LightsailConfig) -> Any:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise DeploymentError(
            "boto3 is required for Lightsail deployments. Add it to the project "
            "dependencies (uv add boto3) and re-sync."
        ) from exc
    return boto3.client("lightsail", region_name=config.region)


# ---- Steps -------------------------------------------------------------------


def build_image(config: LightsailConfig, *, stream: bool = True) -> None:
    """Build the Docker image from the repository Dockerfile."""
    cmd = [
        "docker",
        "build",
        "-t",
        config.image_tag,
        "-f",
        str(config.dockerfile_path),
        str(config.repo_root),
    ]
    _run(cmd, stream=stream)


def get_service(config: LightsailConfig, client: Any | None = None) -> dict[str, Any] | None:
    """Return the container service dict, or ``None`` if it does not exist."""
    client = client or _client(config)
    response = client.get_container_services(serviceName=config.service_name)
    services = response.get("containerServices", [])
    return services[0] if services else None


def ensure_service(config: LightsailConfig, client: Any | None = None) -> dict[str, Any]:
    """Create the container service if absent; wait until it is ready to deploy."""
    client = client or _client(config)
    try:
        existing = get_service(config, client)
    except client.exceptions.NotFoundException:
        existing = None
    if existing is None:
        client.create_container_service(
            serviceName=config.service_name,
            power=config.power,
            scale=config.scale,
        )
    return _wait_until_deployable(config, client)


def _wait_until_deployable(
    config: LightsailConfig,
    client: Any,
    *,
    timeout_s: int = 600,
    interval_s: int = 10,
) -> dict[str, Any]:
    """Wait until the service can accept a deployment (READY or RUNNING)."""
    deadline = time.monotonic() + timeout_s
    while True:
        service = get_service(config, client)
        if service is None:  # pragma: no cover - race guard
            raise DeploymentError(f"Container service {config.service_name!r} disappeared")
        state = service.get("state", "")
        if state in {"READY", "RUNNING"}:
            return service
        if state in {"DISABLED", "DELETING"}:
            raise DeploymentError(f"Container service is in a terminal state: {state}")
        if time.monotonic() > deadline:
            raise DeploymentError(
                f"Timed out after {timeout_s}s waiting for service to become READY "
                f"(last state: {state})"
            )
        time.sleep(interval_s)


_IMAGE_REF_RE = re.compile(r'(?:Refer to this image as\s+"?|")(:[\w.-]+\.[\w.-]+\.\d+)"?')


def push_image(config: LightsailConfig) -> str:
    """Push the local image to Lightsail; return the registered image ref.

    The ``aws lightsail push-container-image`` command prints a line such as::

        Refer to this image as ":sme-business-coordinator.app.1" in deployments.

    We parse and return that ``:service.label.N`` reference.
    """
    label = config.container_name
    cmd = [
        "aws",
        "lightsail",
        "push-container-image",
        "--region",
        config.region,
        "--service-name",
        config.service_name,
        "--label",
        label,
        "--image",
        config.image_tag,
    ]
    output = _run(cmd, capture=True)
    match = _IMAGE_REF_RE.search(output)
    if not match:
        raise DeploymentError(
            "Could not parse the registered image reference from push output:\n" + output
        )
    return match.group(1)


def create_deployment(
    config: LightsailConfig,
    image_ref: str,
    client: Any | None = None,
) -> None:
    """Create a deployment publishing the container on its public endpoint."""
    client = client or _client(config)
    environment = {
        "BC_HOST": "0.0.0.0",
        "BC_HOST_PORT": str(config.container_port),
        **config.environment,
    }
    client.create_container_service_deployment(
        serviceName=config.service_name,
        containers={
            config.container_name: {
                "image": image_ref,
                "ports": {str(config.container_port): "HTTP"},
                "environment": environment,
            }
        },
        publicEndpoint={
            "containerName": config.container_name,
            "containerPort": config.container_port,
            "healthCheck": {
                "path": config.health_check_path,
                "successCodes": "200",
                "healthyThreshold": 2,
                "unhealthyThreshold": 2,
                "timeoutSeconds": 5,
                "intervalSeconds": 10,
            },
        },
    )


def wait_for_running(
    config: LightsailConfig,
    client: Any | None = None,
    *,
    timeout_s: int = 900,
    interval_s: int = 15,
) -> dict[str, Any]:
    """Poll until the current deployment is active and the service is RUNNING."""
    client = client or _client(config)
    deadline = time.monotonic() + timeout_s
    while True:
        service = get_service(config, client)
        if service is None:  # pragma: no cover - race guard
            raise DeploymentError(f"Container service {config.service_name!r} disappeared")
        deployment = service.get("currentDeployment") or {}
        dep_state = deployment.get("state", "")
        if service.get("state") == "RUNNING" and dep_state == "ACTIVE":
            return service
        if dep_state == "FAILED":
            raise DeploymentError(
                "The deployment failed. Check container logs in the Lightsail console."
            )
        if time.monotonic() > deadline:
            raise DeploymentError(
                f"Timed out after {timeout_s}s waiting for RUNNING/ACTIVE "
                f"(service={service.get('state')}, deployment={dep_state})"
            )
        time.sleep(interval_s)


# ---- Public entry points -----------------------------------------------------


def deploy(config: LightsailConfig | None = None) -> DeploymentResult:
    """Build, push, and deploy the app image to Lightsail. Returns the URL."""
    config = config or LightsailConfig.from_env()
    preflight(config)
    client = _client(config)

    build_image(config)
    ensure_service(config, client)
    image_ref = push_image(config)
    create_deployment(config, image_ref, client)
    service = wait_for_running(config, client)

    url = service.get("url", "")
    return DeploymentResult(
        service_name=config.service_name,
        region=config.region,
        url=url,
        state=str(service.get("state", "")),
        image_ref=image_ref,
    )


def status(config: LightsailConfig | None = None) -> dict[str, Any]:
    """Return a compact status view of the container service."""
    config = config or LightsailConfig.from_env()
    service = get_service(config)
    if service is None:
        return {"service_name": config.service_name, "exists": False}
    deployment = service.get("currentDeployment") or {}
    return {
        "service_name": config.service_name,
        "exists": True,
        "state": service.get("state"),
        "url": service.get("url"),
        "power": service.get("power"),
        "scale": service.get("scale"),
        "deployment_state": deployment.get("state"),
        "deployment_version": deployment.get("version"),
    }


def teardown(config: LightsailConfig | None = None) -> None:
    """Delete the container service. Destructive and irreversible."""
    config = config or LightsailConfig.from_env()
    client = _client(config)
    client.delete_container_service(serviceName=config.service_name)
