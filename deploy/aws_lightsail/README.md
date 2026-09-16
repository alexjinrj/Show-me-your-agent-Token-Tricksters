# AWS Lightsail deploy module

Deploy the app (FastAPI API + static SPA, built as one Docker image) to an
**AWS Lightsail Container Service** with a single command. You do not need to
know anything about Lightsail — build your frontend into `frontend/`, then run
the deploy.

This module lives at the repository root (`deploy/aws_lightsail/`), deliberately
outside `src/`: it is DevOps automation, not part of the packaged business
library. Run all commands below from the repository root.

## What it does

1. Builds the Docker image from the repository `Dockerfile`.
2. Ensures a Lightsail container service exists (creates it if missing).
3. Pushes the image to that service.
4. Creates a deployment that exposes the container on a public HTTPS endpoint
   with a `/healthz` health check.
5. Waits until it is `RUNNING` and prints the public URL.

The public URL looks like
`https://<service>.<guid>.<region>.cs.amazonlightsail.com` and serves both the
SPA and the `/api/*` endpoints.

## Prerequisites (one-time, on the machine that runs the deploy)

- **Docker** — to build the image.
- **AWS CLI v2** — configured with credentials for the target account.
- **lightsailctl** plugin — required to push images to Lightsail.
  See the [install guide](https://lightsail.aws.amazon.com/ls/docs/en_us/articles/amazon-lightsail-install-software).
- Python dependencies installed: `uv sync`.

> The competition AWS account is a **separate profile** from any personal one.
> Make sure your shell is authenticated against the correct account/region
> before deploying (e.g. `export AWS_PROFILE=<competition-profile>`), then pass
> `--region` or set `LIGHTSAIL_REGION` to match.

## Usage

From the repository root:

```bash
# Build + push + deploy, then print the URL.
uv run python -m deploy.aws_lightsail deploy

# Check current state.
uv run python -m deploy.aws_lightsail status

# Delete the service (destructive; needs --yes).
uv run python -m deploy.aws_lightsail teardown --yes
```

Or from Python:

```python
from deploy.aws_lightsail import deploy

result = deploy()
print(result.url)
```

## Configuration

Every option has a flag and a `LIGHTSAIL_*` environment variable. Flags win over
env vars, which win over defaults.

| Setting        | Flag              | Env var                       | Default                     |
| -------------- | ----------------- | ----------------------------- | --------------------------- |
| Service name   | `--service-name`  | `LIGHTSAIL_SERVICE_NAME`      | `sme-business-coordinator`  |
| Region         | `--region`        | `LIGHTSAIL_REGION`            | `ap-southeast-1`            |
| Power (size)   | `--power`         | `LIGHTSAIL_POWER`             | `micro`                     |
| Scale (nodes)  | `--scale`         | `LIGHTSAIL_SCALE`             | `1`                         |
| Image tag      | `--image-tag`     | `LIGHTSAIL_IMAGE_TAG`         | `<service>:latest`          |
| Container port | —                 | `LIGHTSAIL_CONTAINER_PORT`    | `8000`                      |
| Health path    | —                 | `LIGHTSAIL_HEALTH_CHECK_PATH` | `/healthz`                  |

Example:

```bash
uv run python -m deploy.aws_lightsail deploy \
  --service-name my-demo --region us-east-1 --power nano
```

## Notes

- The deploy is **idempotent for the service**: re-running `deploy` on an
  existing service just ships a new deployment version.
- Only `teardown --yes` deletes cloud resources; nothing is deleted implicitly.
- Lightsail public endpoints are **HTTPS only** (the load balancer terminates
  TLS and talks HTTP to the container).
