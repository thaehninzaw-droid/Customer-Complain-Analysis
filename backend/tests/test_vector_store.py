import pytest

from app.rag import vector_store


@pytest.fixture(autouse=True)
def _clean_store():
    vector_store.reset_memory_store()
    yield
    vector_store.reset_memory_store()


def test_search_ranks_exact_match_first():
    vector_store.upsert([
        {"id": 0, "vector": [1, 0, 0], "payload": {"source": "a"}},
        {"id": 1, "vector": [0, 1, 0], "payload": {"source": "b"}},
        {"id": 2, "vector": [0.9, 0.1, 0], "payload": {"source": "c"}},
    ])
    results = vector_store.search([1, 0, 0], top_k=2)
    assert results[0]["payload"]["source"] == "a"
    assert results[0]["score"] > results[1]["score"]


def test_upsert_with_same_id_overwrites():
    vector_store.upsert([{"id": 0, "vector": [1, 0, 0], "payload": {"source": "old"}}])
    vector_store.upsert([{"id": 0, "vector": [1, 0, 0], "payload": {"source": "new"}}])
    results = vector_store.search([1, 0, 0], top_k=5)
    assert len(results) == 1
    assert results[0]["payload"]["source"] == "new"


def test_search_on_empty_store_returns_empty_list():
    assert vector_store.search([1, 0, 0], top_k=3) == []
