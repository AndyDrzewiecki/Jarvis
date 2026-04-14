from __future__ import annotations
import pytest
from unittest.mock import patch


@pytest.fixture
def miner(tmp_path):
    from jarvis.preference_learning import PreferenceMiner
    return PreferenceMiner(db_path=str(tmp_path / "prefs.db"))


def test_record_signal_creates_record(miner, tmp_path):
    """record_signal() writes one row to the DB."""
    import sqlite3
    miner.record_signal(
        domain="grocery",
        signal_type="explicit",
        content="user prefers organic milk",
        context="chat",
    )
    conn = sqlite3.connect(str(tmp_path / "prefs.db"))
    count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    assert count == 1


def test_mine_empty_returns_zero(miner):
    """No signals → mine() returns 0."""
    with patch("jarvis.core._ask_ollama", return_value="NONE"):
        result = miner.mine()
    assert result == 0


def test_mine_extracts_rules(miner):
    """3 signals seeded, mock LLM returns a RULE → mine() returns 1."""
    for i in range(3):
        miner.record_signal(
            domain="grocery",
            signal_type="implicit",
            content=f"user chose organic option {i}",
            context="chat",
        )

    with patch("jarvis.core._ask_ollama", return_value="RULE: prefer organic | 0.8 | always"):
        result = miner.mine(domain="grocery")

    assert result >= 1


def test_parse_rules_valid(miner):
    """Valid RULE line parses into list with rule/confidence/conditions."""
    rules = miner._parse_rules("RULE: prefer tea | 0.7 | morning")
    assert len(rules) == 1
    assert rules[0]["rule"] == "prefer tea"
    assert abs(rules[0]["confidence"] - 0.7) < 0.001
    assert rules[0]["conditions"] == "morning"


def test_parse_rules_none(miner):
    """NONE response yields empty list."""
    rules = miner._parse_rules("NONE")
    assert rules == []


def test_upsert_new_preference(miner, tmp_path):
    """No existing preference → new row inserted."""
    import sqlite3
    miner._upsert_preference(
        domain="grocery",
        rule="prefer organic",
        confidence=0.8,
        conditions="always",
    )
    conn = sqlite3.connect(str(tmp_path / "prefs.db"))
    count = conn.execute("SELECT COUNT(*) FROM preferences").fetchone()[0]
    conn.close()
    assert count == 1


def test_upsert_reinforce_existing(miner, tmp_path):
    """Same rule upserted twice → evidence_count incremented."""
    import sqlite3
    miner._upsert_preference("grocery", "prefer organic", 0.8, "always")
    miner._upsert_preference("grocery", "prefer organic", 0.85, "always")
    conn = sqlite3.connect(str(tmp_path / "prefs.db"))
    row = conn.execute("SELECT evidence_count FROM preferences").fetchone()
    conn.close()
    assert row[0] >= 2


def test_get_preferences_filter(miner):
    """2 rules in 'grocery', 1 in 'finance' → get_preferences('grocery') returns 2."""
    miner._upsert_preference("grocery", "prefer organic", 0.8, "always")
    miner._upsert_preference("grocery", "prefer store brand", 0.7, "budget")
    miner._upsert_preference("finance", "save 10%", 0.9, "monthly")
    results = miner.get_preferences(domain="grocery")
    assert len(results) == 2


def test_get_preferences_min_confidence(miner):
    """Rules with conf 0.3 and 0.8 → get_preferences(min_confidence=0.5) returns 1."""
    miner._upsert_preference("grocery", "prefer cheap", 0.3, "always")
    miner._upsert_preference("grocery", "prefer organic", 0.8, "always")
    results = miner.get_preferences(min_confidence=0.5)
    assert len(results) == 1
    assert results[0]["confidence"] >= 0.5
