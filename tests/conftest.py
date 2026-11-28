"""Shared fixtures. Case 04's warehouse is built once per session into a temp dir."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASE_04_SRC = ROOT / "case-studies" / "04-ai-analyst-reliability" / "src"
if str(CASE_04_SRC) not in sys.path:
    sys.path.insert(0, str(CASE_04_SRC))


@pytest.fixture(scope="session")
def analyst_db(tmp_path_factory) -> Path:
    from analyst_eval.warehouse import build

    return build(tmp_path_factory.mktemp("case04") / "analyst.db")
