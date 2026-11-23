"""Architectural boundary test enforcing strict domain layer isolation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "src" / "econ_tracker" / "domain"

FORBIDDEN_IMPORT_PREFIXES = (
    "sqlalchemy",
    "fastapi",
    "starlette",
    "httpx",
    "pydantic",
    "alembic",
    "uvicorn",
    "typer",
    "econ_tracker.storage",
    "econ_tracker.sources",
    "econ_tracker.services",
    "econ_tracker.api",
)


@pytest.mark.unit
def test_domain_layer_has_zero_external_or_outer_layer_imports() -> None:
    """Verify domain/ imports strictly stdlib and econ_tracker.domain only."""
    py_files = sorted(DOMAIN_DIR.glob("*.py"))
    assert py_files, "Expected domain source files to exist"

    violations: list[str] = []
    for file_path in py_files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                        violations.append(f"{file_path.name}: import {alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith(FORBIDDEN_IMPORT_PREFIXES)
            ):
                violations.append(f"{file_path.name}: from {node.module} import ...")

    assert not violations, "Domain layer boundary violated:\n" + "\n".join(violations)
