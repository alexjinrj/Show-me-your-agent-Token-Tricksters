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


def test_domain_does_not_depend_on_outer_layers() -> None:
    forbidden = {"infra", "tools", "runtime", "api", "skill"}
    assert imported_roots("domain").isdisjoint(forbidden)


def test_legacy_flat_packages_are_gone() -> None:
    # The pre-refactor top-level packages must not come back as compat shims.
    for name in ("core", "load_data", "enterprise_state", "agent_runtime", "interfaces"):
        assert not (SOURCE_ROOT / name).exists(), name
