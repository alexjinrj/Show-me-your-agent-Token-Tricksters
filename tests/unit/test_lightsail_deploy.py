from __future__ import annotations

import shutil

import pytest

from deploy.aws_lightsail import LightsailConfig
from deploy.aws_lightsail.config import VALID_POWERS
from deploy.aws_lightsail.deploy import _IMAGE_REF_RE, DeploymentError, preflight


def test_default_config_is_valid() -> None:
    config = LightsailConfig()
    assert config.service_name == "sme-business-coordinator"
    assert config.power in VALID_POWERS
    assert config.scale >= 1
    assert config.container_port == 8000
    assert config.health_check_path == "/healthz"
    assert config.image_tag == "sme-business-coordinator:latest"


@pytest.mark.parametrize(
    "bad_name",
    ["-leading", "trailing-", "UPPER", "has space", "", "x" * 64, "under_score"],
)
def test_invalid_service_names_rejected(bad_name: str) -> None:
    with pytest.raises(ValueError):
        LightsailConfig(service_name=bad_name)


def test_invalid_power_rejected() -> None:
    with pytest.raises(ValueError):
        LightsailConfig(power="gigantic")


def test_invalid_scale_rejected() -> None:
    with pytest.raises(ValueError):
        LightsailConfig(scale=0)


def test_from_env_reads_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGHTSAIL_SERVICE_NAME", "env-service")
    monkeypatch.setenv("LIGHTSAIL_REGION", "us-east-1")
    monkeypatch.setenv("LIGHTSAIL_POWER", "nano")
    monkeypatch.setenv("LIGHTSAIL_SCALE", "3")

    config = LightsailConfig.from_env()
    assert config.service_name == "env-service"
    assert config.region == "us-east-1"
    assert config.power == "nano"
    assert config.scale == 3
    # Image tag defaults off the (env-provided) service name.
    assert config.image_tag == "env-service:latest"

    # Explicit overrides beat env vars; None overrides are ignored.
    overridden = LightsailConfig.from_env(region="ap-southeast-1", power=None)
    assert overridden.region == "ap-southeast-1"
    assert overridden.power == "nano"


def test_dockerfile_path_resolves_relative_to_repo_root() -> None:
    config = LightsailConfig()
    assert config.dockerfile_path == config.repo_root / "Dockerfile"


@pytest.mark.parametrize(
    "line,expected",
    [
        (
            'Refer to this image as ":sme-business-coordinator.app.1" in deployments.',
            ":sme-business-coordinator.app.1",
        ),
        (
            'Refer to this image as ":my-demo.app.42" in deployments.',
            ":my-demo.app.42",
        ),
    ],
)
def test_image_ref_parsing(line: str, expected: str) -> None:
    match = _IMAGE_REF_RE.search(line)
    assert match is not None
    assert match.group(1) == expected


def test_preflight_missing_dockerfile(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force all binaries to appear present, but point at a repo with no Dockerfile.
    monkeypatch.setattr(shutil, "which", lambda _b: "/usr/bin/stub")
    config = LightsailConfig(repo_root=tmp_path)
    with pytest.raises(DeploymentError, match="Dockerfile not found"):
        preflight(config)


def test_preflight_missing_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _b: None)
    with pytest.raises(DeploymentError, match="Missing required tool"):
        preflight(LightsailConfig())
