"""Command-line interface for Lightsail deployments.

Subcommands:

- ``deploy``   -- build, push, and deploy the image; prints the public URL.
- ``status``   -- show the current service/deployment state.
- ``teardown`` -- delete the container service (requires ``--yes``).

Every option also has a ``LIGHTSAIL_*`` environment variable equivalent; flags
win over env vars, which win over defaults.
"""

from __future__ import annotations

import argparse
import json
import sys

from deploy.aws_lightsail.config import VALID_POWERS, LightsailConfig
from deploy.aws_lightsail.deploy import (
    DeploymentError,
    deploy,
    status,
    teardown,
)


def _add_common_config_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--service-name", default=None, help="Lightsail container service name.")
    parser.add_argument("--region", default=None, help="AWS region (e.g. ap-southeast-1).")
    parser.add_argument("--power", default=None, choices=VALID_POWERS, help="Node size.")
    parser.add_argument("--scale", type=int, default=None, help="Number of nodes.")
    parser.add_argument("--image-tag", default=None, help="Local Docker image tag to build/push.")


def _config_from_args(args: argparse.Namespace) -> LightsailConfig:
    return LightsailConfig.from_env(
        service_name=getattr(args, "service_name", None),
        region=getattr(args, "region", None),
        power=getattr(args, "power", None),
        scale=getattr(args, "scale", None),
        image_tag=getattr(args, "image_tag", None),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m deploy.aws_lightsail",
        description="Deploy the SME Business Coordinator to AWS Lightsail.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    deploy_p = sub.add_parser("deploy", help="Build, push, and deploy the image.")
    _add_common_config_flags(deploy_p)

    status_p = sub.add_parser("status", help="Show container service status.")
    _add_common_config_flags(status_p)

    teardown_p = sub.add_parser("teardown", help="Delete the container service (destructive).")
    _add_common_config_flags(teardown_p)
    teardown_p.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion without an interactive prompt.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = _config_from_args(args)
    except ValueError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "deploy":
            print(f"Deploying '{config.service_name}' to {config.region} ...")
            result = deploy(config)
            print("\nDeployment complete.")
            print(f"  Service : {result.service_name}")
            print(f"  State   : {result.state}")
            print(f"  Image   : {result.image_ref}")
            print(f"  URL     : {result.url}")
            return 0

        if args.command == "status":
            print(json.dumps(status(config), indent=2))
            return 0

        if args.command == "teardown":
            if not args.yes:
                print(
                    f"Refusing to delete '{config.service_name}' without --yes.",
                    file=sys.stderr,
                )
                return 2
            teardown(config)
            print(f"Deleted container service '{config.service_name}'.")
            return 0
    except DeploymentError as exc:
        print(f"\nDeployment error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")  # pragma: no cover
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
