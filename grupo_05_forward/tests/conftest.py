"""Shared pytest fixtures for ForwardEngine tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow `pytest grupo_05_forward/tests` from the repo root or package folder.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from grupo_05_forward.io import load_knowledge_base, load_working_memory

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def knowledge_base():
    return load_knowledge_base(FIXTURES / "conocimiento_minimo.json")


@pytest.fixture
def working_memory():
    return load_working_memory(FIXTURES / "memoria_minima.json")
