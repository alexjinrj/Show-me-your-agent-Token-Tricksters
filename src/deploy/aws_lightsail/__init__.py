"""Deploy the SME Business Coordinator to an AWS Lightsail Container Service.

Typical use by an application developer, after building the frontend::

    from deploy.aws_lightsail import deploy

    result = deploy()          # uses defaults + LIGHTSAIL_* env vars
    print(result.url)          # public HTTPS URL

Or from the command line::

    python -m deploy.aws_lightsail deploy
    python -m deploy.aws_lightsail status
    python -m deploy.aws_lightsail teardown

The deploy uses ``boto3`` for the Lightsail control plane and shells out to
``docker`` and the AWS CLI (``lightsailctl``) to build and push the image.
"""

from __future__ import annotations

from deploy.aws_lightsail.config import LightsailConfig
from deploy.aws_lightsail.deploy import (
    DeploymentError,
    DeploymentResult,
    deploy,
    status,
    teardown,
)

__all__ = [
    "LightsailConfig",
    "DeploymentError",
    "DeploymentResult",
    "deploy",
    "status",
    "teardown",
]
