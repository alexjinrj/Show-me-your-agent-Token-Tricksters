from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src"


def imported_roots(package: str) -> set[str]:
    roots: set[str] = set()
    for path in (SOURCE_ROOT / package).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def test_core_does_not_depend_on_outer_layers() -> None:
    forbidden = {"load_data", "enterprise_state", "tools", "agent_runtime", "interfaces"}
    assert imported_roots("core").isdisjoint(forbidden)


def test_agent_runtime_reaches_business_capabilities_through_tools() -> None:
    forbidden = {"core", "load_data", "enterprise_state", "interfaces"}
    assert imported_roots("agent_runtime").isdisjoint(forbidden)
