"""Shared deterministic fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

SCENARIO = Path(__file__).parents[1] / "scenarios" / "late-feature-incident.json"


@pytest.fixture
def incident() -> dict[str, object]:
    return cast(dict[str, object], json.loads(SCENARIO.read_text(encoding="utf-8")))
