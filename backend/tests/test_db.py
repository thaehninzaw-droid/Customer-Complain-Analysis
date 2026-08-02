from app.db import _InMemoryCollection


def test_find_one_returns_first_match_or_none():
    col = _InMemoryCollection()
    col.insert_one({"ticket_no": 1, "status": "Pending"})
    col.insert_one({"ticket_no": 2, "status": "Resolved"})

    assert col.find_one({"ticket_no": 2})["status"] == "Resolved"
    assert col.find_one({"ticket_no": 999}) is None


def test_update_one_applies_set_and_is_reflected_in_find():
    col = _InMemoryCollection()
    col.insert_one({"ticket_no": 1, "status": "Pending", "priority": "Low"})

    col.update_one({"ticket_no": 1}, {"$set": {"status": "Resolved"}})

    updated = col.find_one({"ticket_no": 1})
    assert updated["status"] == "Resolved"
    assert updated["priority"] == "Low"  # untouched field stays as-is


def test_update_one_on_missing_doc_returns_none_without_raising():
    col = _InMemoryCollection()
    assert col.update_one({"ticket_no": 999}, {"$set": {"status": "Resolved"}}) is None
