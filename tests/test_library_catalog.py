"""Tests for jarvis.library.catalog and librarian_base — TDD Wave 4.3."""
from __future__ import annotations
import pytest


# ---------------------------------------------------------------------------
# LibraryCatalog Tests
# ---------------------------------------------------------------------------

def _make_catalog(tmp_path):
    from jarvis.library.catalog import LibraryCatalog
    return LibraryCatalog(db_path=str(tmp_path / "catalog.db"))


# 1. test_add_entry_returns_id
def test_add_entry_returns_id(tmp_path):
    catalog = _make_catalog(tmp_path)
    entry_id = catalog.add_entry(
        domain="grocery", title="Milk prices", source_type="web"
    )
    assert isinstance(entry_id, str)
    assert len(entry_id) == 36  # UUID format


# 2. test_search_by_title
def test_search_by_title(tmp_path):
    catalog = _make_catalog(tmp_path)
    catalog.add_entry(domain="grocery", title="Milk prices", source_type="web")
    results = catalog.search("Milk")
    assert len(results) == 1
    assert results[0]["title"] == "Milk prices"


# 3. test_search_by_summary
def test_search_by_summary(tmp_path):
    catalog = _make_catalog(tmp_path)
    catalog.add_entry(
        domain="grocery", title="Fruit report", source_type="web",
        summary="apples cost $2 per pound"
    )
    results = catalog.search("apples")
    assert len(results) == 1
    assert results[0]["title"] == "Fruit report"


# 4. test_search_domain_filter
def test_search_domain_filter(tmp_path):
    catalog = _make_catalog(tmp_path)
    catalog.add_entry(domain="grocery", title="Banana prices", source_type="web")
    catalog.add_entry(domain="finance", title="Banana stocks", source_type="web")
    results = catalog.search("Banana", domain="grocery")
    assert len(results) == 1
    assert results[0]["domain"] == "grocery"


# 5. test_get_by_domain
def test_get_by_domain(tmp_path):
    catalog = _make_catalog(tmp_path)
    for i in range(3):
        catalog.add_entry(domain="grocery", title=f"Grocery item {i}", source_type="web")
    catalog.add_entry(domain="finance", title="Finance item", source_type="web")

    results = catalog.get_by_domain("grocery")
    assert len(results) == 3
    assert all(r["domain"] == "grocery" for r in results)


# 6. test_queue_research_returns_id
def test_queue_research_returns_id(tmp_path):
    catalog = _make_catalog(tmp_path)
    rid = catalog.queue_research(domain="grocery", topic="seasonal produce prices")
    assert isinstance(rid, str)
    assert len(rid) == 36


# 7. test_get_queue_returns_queued
def test_get_queue_returns_queued(tmp_path):
    catalog = _make_catalog(tmp_path)
    catalog.queue_research(domain="grocery", topic="topic A")
    catalog.queue_research(domain="grocery", topic="topic B")
    results = catalog.get_queue()
    assert len(results) == 2


# 8. test_get_queue_priority_order
def test_get_queue_priority_order(tmp_path):
    catalog = _make_catalog(tmp_path)
    catalog.queue_research(domain="grocery", topic="normal topic", priority="normal")
    catalog.queue_research(domain="grocery", topic="urgent topic", priority="urgent")
    results = catalog.get_queue()
    assert results[0]["priority"] == "urgent"


# 9. test_complete_research
def test_complete_research(tmp_path):
    catalog = _make_catalog(tmp_path)
    rid = catalog.queue_research(domain="grocery", topic="test topic")
    catalog.complete_research(rid, result_summary="Found 5 items")

    completed = catalog.get_queue(status="completed")
    assert len(completed) == 1
    assert completed[0]["result_summary"] == "Found 5 items"
    assert completed[0]["status"] == "completed"


# 10. test_get_queue_domain_filter
def test_get_queue_domain_filter(tmp_path):
    catalog = _make_catalog(tmp_path)
    catalog.queue_research(domain="grocery", topic="grocery topic")
    catalog.queue_research(domain="finance", topic="finance topic")

    results = catalog.get_queue(domain="grocery")
    assert len(results) == 1
    assert results[0]["domain"] == "grocery"


# ---------------------------------------------------------------------------
# BaseResearchLibrarian Tests
# ---------------------------------------------------------------------------

def _make_librarian(tmp_path):
    """Create a concrete librarian subclass for testing."""
    from jarvis.library.catalog import LibraryCatalog
    from jarvis.library.librarian_base import BaseResearchLibrarian

    class TestLibrarian(BaseResearchLibrarian):
        domain = "grocery"

        def __init__(self, catalog_path, lake):
            super().__init__()
            self._catalog = LibraryCatalog(db_path=catalog_path)
            self._lake = lake

        def survey(self):
            return [
                {"title": "Item A", "source_type": "web", "summary": "About item A",
                 "quality_score": 0.8, "tags": "food"},
                {"title": "Item B", "source_type": "web", "summary": "About item B",
                 "quality_score": 0.7, "tags": "price"},
            ]

        def evaluate(self, findings):
            return findings  # accept all

    class FakeLake:
        def __init__(self):
            self.stored = []
        def store_fact(self, **kwargs):
            self.stored.append(kwargs)
            return "fake-id"

    lake = FakeLake()
    lib = TestLibrarian(str(tmp_path / "catalog.db"), lake)
    return lib, lake


# 11. test_run_cycle_calls_all_methods
def test_run_cycle_calls_all_methods(tmp_path):
    librarian, lake = _make_librarian(tmp_path)
    report = librarian.run_cycle()
    assert report["domain"] == "grocery"
    assert report["surveyed"] == 2
    assert report["cataloged"] == 2
    assert "error" not in report


# 12. test_run_cycle_error_in_survey
def test_run_cycle_error_in_survey(tmp_path):
    from jarvis.library.catalog import LibraryCatalog
    from jarvis.library.librarian_base import BaseResearchLibrarian

    class BrokenLibrarian(BaseResearchLibrarian):
        domain = "grocery"

        def __init__(self, catalog_path):
            super().__init__()
            self._catalog = LibraryCatalog(db_path=catalog_path)
            self._lake = None

        def survey(self):
            raise RuntimeError("No sources available")

        def evaluate(self, findings):
            return findings

    lib = BrokenLibrarian(str(tmp_path / "catalog.db"))
    report = lib.run_cycle()
    assert "error" in report
    assert "No sources available" in report["error"]


# 13. test_run_cycle_catalogs_and_stores_facts
def test_run_cycle_catalogs_and_stores_facts(tmp_path):
    librarian, lake = _make_librarian(tmp_path)
    report = librarian.run_cycle()
    assert report["cataloged"] == 2
    assert len(lake.stored) == 2
    # Verify store_fact was called with correct domain
    assert all(call["domain"] == "grocery" for call in lake.stored)
