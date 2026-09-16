"""Configuration for AWS Lightsail deployments.

All values have sensible defaults and can be overridden with environment
variables (prefixed ``LIGHTSAIL_``) or explicit keyword arguments. This keeps
the common case a single command while still allowing power users to tune the
service name, region, and capacity.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# Powers offered by Lightsail container services, cheapest first.
VALID_POWERS: tuple[str, ...] = ("nano", "micro", "small", "medium", "large", "xlarge")

# Lightsail service-name rules: 1-63 chars, alphanumeric + hyphens, no leading
# or trailing hyphen.
_SERVICE_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

DEFAULT_SERVICE_NAME = "sme-business-coordinator"
DEFAULT_REGION = "ap-southeast-1"  # Singapore; matches the SGD demo dataset.
DEFAULT_POWER = "micro"
DEFAULT_SCALE = 1
DEFAULT_CONTAINER_PORT = 8000
DEFAULT_HEALTH_CHECK_PATH = "/healthz"
DEFAULT_CONTAINER_NAME = "app"


def _repo_root() -> Path:
    # config.py lives at src/deploy/aws_lightsail/config.py -> repo root is 3 up.
    return Path(__file__).resolve().parents[3]


def _env(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class LightsailConfig:
    """Everything needed to build, push, and deploy the image to Lightsail.

    Attributes:
        service_name: Lightsail container service name (also part of the URL).
        region: AWS region hosting the service.
        power: Node size (nano..xlarge). Drives price and resources.
        scale: Number of nodes.
        container_port: Port the app listens on inside the container.
        health_check_path: HTTP path the load balancer probes for health.
        container_name: Logical container name within the deployment.
        image_tag: Local Docker tag built before pushing.
        repo_root: Repository root that holds the Dockerfile.
        dockerfile: Path to the Dockerfile, relative to repo_root or absolute.
        environment: Extra environment variables injected into the container.
    """

    service_name: str = DEFAULT_SERVICE_NAME
    region: str = DEFAULT_REGION
    power: str = DEFAULT_POWER
    scale: int = DEFAULT_SCALE
    container_port: int = DEFAULT_CONTAINER_PORT
    health_check_path: str = DEFAULT_HEALTH_CHECK_PATH
    container_name: str = DEFAULT_CONTAINER_NAME
    image_tag: str = f"{DEFAULT_SERVICE_NAME}:latest"
    repo_root: Path = field(default_factory=_repo_root)
    dockerfile: Path = Path("Dockerfile")
    environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _SERVICE_NAME_RE.match(self.service_name):
            raise ValueError(
                "service_name must be 1-63 chars, lowercase alphanumeric or hyphens, "
                f"and not start/end with a hyphen: {self.service_name!r}"
            )
        if self.power not in VALID_POWERS:
            raise ValueError(f"power must be one of {VALID_POWERS}, got {self.power!r}")
        if self.scale < 1:
            raise ValueError(f"scale must be >= 1, got {self.scale}")
        if not (1 <= self.container_port <= 65535):
            raise ValueError(f"container_port out of range: {self.container_port}")
        if not self.health_check_path.startswith("/"):
            raise ValueError(f"health_check_path must start with '/': {self.health_check_path!r}")

    @property
    def dockerfile_path(self) -> Path:
        path = self.dockerfile
        return path if path.is_absolute() else self.repo_root / path

    @classmethod
    def from_env(cls, **overrides: object) -> LightsailConfig:
        """Build config from ``LIGHTSAIL_*`` env vars, then apply overrides.

        Explicit keyword ``overrides`` (e.g. from CLI flags) win over env vars,
        which win over the built-in defaults.
        """
        service_name = _env("LIGHTSAIL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
        env_values: dict[str, object] = {
            "service_name": service_name,
            "region": _env("LIGHTSAIL_REGION", DEFAULT_REGION),
            "power": _env("LIGHTSAIL_POWER", DEFAULT_POWER),
            "scale": _env_int("LIGHTSAIL_SCALE", DEFAULT_SCALE),
            "container_port": _env_int("LIGHTSAIL_CONTAINER_PORT", DEFAULT_CONTAINER_PORT),
            "health_check_path": _env("LIGHTSAIL_HEALTH_CHECK_PATH", DEFAULT_HEALTH_CHECK_PATH),
            "image_tag": _env("LIGHTSAIL_IMAGE_TAG", f"{service_name}:latest"),
        }
        # Drop overrides set to None so callers can pass argparse defaults freely.
        clean_overrides = {k: v for k, v in overrides.items() if v is not None}
        env_values.update(clean_overrides)
        return cls(**env_values)  # type: ignore[arg-type]
