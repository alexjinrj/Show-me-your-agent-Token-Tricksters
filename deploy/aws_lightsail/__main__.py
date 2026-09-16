"""Enable ``python -m deploy.aws_lightsail``."""

from __future__ import annotations

from deploy.aws_lightsail.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
