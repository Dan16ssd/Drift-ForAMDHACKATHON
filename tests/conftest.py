from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from drift.llm import MockChatClient
from drift.sensor.scorer import sense

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def mock_client() -> MockChatClient:
    return MockChatClient()


def load_records(name: str) -> list[dict]:
    path = FIXTURES / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sensed_window(records: list[dict], client: MockChatClient) -> list[dict]:
    """Turn raw fixture records into ledger-shaped rows (id, ts, features)."""
    rows = []
    for i, rec in enumerate(records):
        rows.append(
            {
                "id": i + 1,
                "ts": datetime.fromisoformat(rec["ts"]),
                "features": sense(client, rec),
            }
        )
    return rows
