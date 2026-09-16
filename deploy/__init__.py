"""Deployment adapters for the SME Business Coordinator.

Each subpackage targets one hosting provider and exposes a small, self-contained
API so an application developer can deploy the single Docker image (FastAPI API +
static SPA) without learning that provider's control plane.

Currently available:

- :mod:`deploy.aws_lightsail` -- deploy to an AWS Lightsail Container Service.
"""
