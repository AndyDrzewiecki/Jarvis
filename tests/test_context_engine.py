"""Tests for jarvis.context_engine — TDD Wave 4.2."""
from __future__ import annotations
import os
import pytest


def _make_engine(tmp_path):
    from jarvis.context_engine import ContextEngine
    return ContextEngine(library_root=str(tmp_path / "library"))


# ---------------------------------------------------------------------------
# 1. test_rebuild_creates_file
# ---------------------------------------------------------------------------

def test_rebuild_creates_file(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "query", lambda **kwargs: [])
    monkeypatch.setattr(am, "log_decision", lambda **kwargs: "x")

    # Mock KnowledgeLake
    class FakeLake:
        def query_facts(self, domain=None, limit=30):
            return []
        def recent_by_domain(self, limit_per_domain=2):
            return {}

    import jarvis.knowledge_lake as kl
    monkeypatch.setattr(kl, "KnowledgeLake", FakeLake)

    # Mock HouseholdState
    class FakeState:
        def current(self):
            return {"primary": "normal", "modifiers": []}
    import jarvis.household_state as hs
    monkeypatch.setattr(hs, "HouseholdState", FakeState)

    engine = _make_engine(tmp_path)
    engine.rebuild("grocery")

    path = tmp_path / "library" / "grocery" / "context_engine.md"
    assert path.exists()


# ---------------------------------------------------------------------------
# 2. test_rebuild_includes_guidelines
# ---------------------------------------------------------------------------

def test_rebuild_includes_guidelines(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "query", lambda **kwargs: [])
    monkeypatch.setattr(am, "log_decision", lambda **kwargs: "x")

    class FakeLake:
        def query_facts(self, domain=None, limit=30):
            return []
        def recent_by_domain(self, limit_per_domain=2):
            return {}

    import jarvis.knowledge_lake as kl
    monkeypatch.setattr(kl, "KnowledgeLake", FakeLake)

    class FakeState:
        def current(self):
            return {"primary": "normal", "modifiers": []}
    import jarvis.household_state as hs
    monkeypatch.setattr(hs, "HouseholdState", FakeState)

    # Seed guidelines
    lib = tmp_path / "library" / "grocery"
    lib.mkdir(parents=True)
    (lib / "guidelines.md").write_text("# Grocery Specialist Guidelines v1\n\nBuy fresh produce.")

    engine = _make_engine(tmp_path)
    result = engine.rebuild("grocery")

    assert "Operating Guidelines" in result
    assert "Buy fresh produce." in result


# ---------------------------------------------------------------------------
# 3. test_rebuild_includes_knowledge
# ---------------------------------------------------------------------------

def test_rebuild_includes_knowledge(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "query", lambda **kwargs: [])
    monkeypatch.setattr(am, "log_decision", lambda **kwargs: "x")

    class FakeLake:
        def query_facts(self, domain=None, limit=30):
            return [{"summary": "Apples cost $2/lb", "content": "Apples cost $2/lb"}]
        def recent_by_domain(self, limit_per_domain=2):
            return {}

    import jarvis.knowledge_lake as kl
    monkeypatch.setattr(kl, "KnowledgeLake", FakeLake)

    class FakeState:
        def current(self):
            return {"primary": "normal", "modifiers": []}
    import jarvis.household_state as hs
    monkeypatch.setattr(hs, "HouseholdState", FakeState)

    engine = _make_engine(tmp_path)
    result = engine.rebuild("grocery")

    assert "Domain Knowledge" in result
    assert "Apples cost $2/lb" in result


# ---------------------------------------------------------------------------
# 4. test_rebuild_includes_household_state
# ---------------------------------------------------------------------------

def test_rebuild_includes_household_state(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "query", lambda **kwargs: [])
    monkeypatch.setattr(am, "log_decision", lambda **kwargs: "x")

    class FakeLake:
        def query_facts(self, domain=None, limit=30):
            return []
        def recent_by_domain(self, limit_per_domain=2):
            return {}

    import jarvis.knowledge_lake as kl
    monkeypatch.setattr(kl, "KnowledgeLake", FakeLake)

    class FakeState:
        def current(self):
            return {"primary": "budget_sensitive", "modifiers": ["tight_budget"]}
    import jarvis.household_state as hs
    monkeypatch.setattr(hs, "HouseholdState", FakeState)

    engine = _make_engine(tmp_path)
    result = engine.rebuild("grocery")

    assert "Household State" in result
    assert "budget_sensitive" in result


# ---------------------------------------------------------------------------
# 5. test_rebuild_includes_decision_patterns
# ---------------------------------------------------------------------------

def test_rebuild_includes_decision_patterns(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "query", lambda **kwargs: [
        {"id": "d1", "decision": "chose chicken", "outcome": "success"},
        {"id": "d2", "decision": "skipped milk", "outcome": "failure"},
    ])
    monkeypatch.setattr(am, "log_decision", lambda **kwargs: "x")

    class FakeLake:
        def query_facts(self, domain=None, limit=30):
            return []
        def recent_by_domain(self, limit_per_domain=2):
            return {}

    import jarvis.knowledge_lake as kl
    monkeypatch.setattr(kl, "KnowledgeLake", FakeLake)

    class FakeState:
        def current(self):
            return {"primary": "normal", "modifiers": []}
    import jarvis.household_state as hs
    monkeypatch.setattr(hs, "HouseholdState", FakeState)

    engine = _make_engine(tmp_path)
    result = engine.rebuild("grocery")

    assert "Decision Patterns" in result
    assert "chose chicken" in result


# ---------------------------------------------------------------------------
# 6. test_inject_appends_context
# ---------------------------------------------------------------------------

def test_inject_appends_context(tmp_path):
    lib = tmp_path / "library" / "grocery"
    lib.mkdir(parents=True)
    (lib / "context_engine.md").write_text("Some domain context here.")

    engine = _make_engine(tmp_path)
    result = engine.inject("grocery", "Base prompt text.")

    assert "Base prompt text." in result
    assert "DOMAIN CONTEXT" in result
    assert "Some domain context here." in result


# ---------------------------------------------------------------------------
# 7. test_inject_returns_base_when_no_context
# ---------------------------------------------------------------------------

def test_inject_returns_base_when_no_context(tmp_path):
    engine = _make_engine(tmp_path)
    result = engine.inject("grocery", "Base prompt text.")
    assert result == "Base prompt text."


# ---------------------------------------------------------------------------
# 8. test_inject_truncates_at_budget
# ---------------------------------------------------------------------------

def test_inject_truncates_at_budget(tmp_path):
    lib = tmp_path / "library" / "grocery"
    lib.mkdir(parents=True)
    long_context = "X" * 50000
    (lib / "context_engine.md").write_text(long_context)

    engine = _make_engine(tmp_path)
    result = engine.inject("grocery", "Base prompt.", token_budget=100)

    assert "...context truncated..." in result
    # 100 tokens * 4 chars = 400 chars budget
    # Result should not contain 50000 X's
    assert result.count("X") <= 400 + 50  # allow small buffer


# ---------------------------------------------------------------------------
# 9. test_patch_replaces_section
# ---------------------------------------------------------------------------

def test_patch_replaces_section(tmp_path):
    lib = tmp_path / "library" / "grocery"
    lib.mkdir(parents=True)
    (lib / "context_engine.md").write_text(
        "## Foo\nold content\n\n## Bar\nother section"
    )

    engine = _make_engine(tmp_path)
    engine.patch("grocery", "Foo", "new content")

    content = (lib / "context_engine.md").read_text()
    assert "new content" in content
    assert "old content" not in content
    assert "## Bar" in content


# ---------------------------------------------------------------------------
# 10. test_patch_adds_new_section
# ---------------------------------------------------------------------------

def test_patch_adds_new_section(tmp_path):
    lib = tmp_path / "library" / "grocery"
    lib.mkdir(parents=True)
    (lib / "context_engine.md").write_text("## Existing\nsome stuff")

    engine = _make_engine(tmp_path)
    engine.patch("grocery", "NewSection", "brand new content")

    content = (lib / "context_engine.md").read_text()
    assert "## NewSection" in content
    assert "brand new content" in content
    assert "## Existing" in content
