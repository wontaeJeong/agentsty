from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentsty.infrastructure.config.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

for path in (ROOT, SRC):
    as_str = str(path)
    if as_str not in sys.path:
        sys.path.insert(0, as_str)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
