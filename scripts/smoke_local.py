"""Check a fresh local database and every UI module without LLM credentials."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="business-coordinator-smoke-") as temporary:
        env = dict(os.environ)
        # This check never connects to a configured model or touches the developer database.
        for name in tuple(env):
            if name.startswith("BC_"):
                env.pop(name)
        env["BC_DB_PATH"] = str(Path(temporary) / "fresh.db")
        log_path = Path(temporary) / "server.log"
        with log_path.open("w+") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "interfaces.api.main:app",
                    "--app-dir",
                    "src",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:

                def read(path: str) -> bytes:
                    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
                        assert response.status == 200, path
                        return response.read()

                def data(path: str) -> dict:
                    return json.loads(read(path))

                deadline = time.monotonic() + 60
                while True:
                    try:
                        read("/healthz")
                        break
                    except (URLError, TimeoutError):
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            raise RuntimeError(f"Server failed to start:\n{log.read()}") from None
                        time.sleep(0.2)
                html = read("/").decode()
                assert 'data-page="crm"' in html and 'data-page="operations"' in html
                read("/app.js")
                read("/styles.css")
                snapshot = data("/api/snapshot")["manifest"]
                for module in ("overview", "sales", "inventory", "accounting", "operations"):
                    result = data(f"/api/v1/modules/{module}")
                    assert result["snapshot_reference"] == snapshot["snapshot_id"], module
                    print(f"PASS {module}")
                crm = data("/api/v1/crm/summary")
                assert crm["dataset_reference"] == snapshot["snapshot_id"]
                cases = data("/api/v1/crm/complaints")["data"]
                assert cases, "Seeded demo must expose order-service cases"
                data(f"/api/v1/crm/complaints/{cases[0]['id']}")
                assert data("/api/assistant/status")["enabled"] is False
                assert data("/api/snapshot")["manifest"]["content_hash"] == snapshot["content_hash"]
                print(
                    "PASS CRM investigation, shared snapshot, disabled AI, unchanged Actual State"
                )
                print("Fresh startup passed. Temporary database and server will be removed.")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
