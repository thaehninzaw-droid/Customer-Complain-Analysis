"""
Tests for app/rag/knowledge_base.py.

Decision 34 (banking pivot): expected SOP file set updated from telecom
(Billing, Financial, Technical, Service, Other) to the 5 banking SOPs
(Accounts, Cards, Collections, Loans, Other Banking).
"""
from app.rag.knowledge_base import chunk_text, load_documents


def test_load_documents_finds_all_banking_sop_files():
    docs = load_documents()
    sources = {d["source"] for d in docs}
    expected = {
        "Accounts Complaints.md",
        "Cards Complaints.md",
        "Collections Complaints.md",
        "Loans Complaints.md",
        "Other Banking Complaints.md",
    }
    assert sources == expected, (
        f"SOP file mismatch.\nExpected: {sorted(expected)}\nGot:      {sorted(sources)}"
    )


def test_load_documents_returns_non_empty_text():
    docs = load_documents()
    for doc in docs:
        assert doc["text"].strip(), f"SOP file '{doc['source']}' is empty"
        assert len(doc["text"]) > 200, f"SOP file '{doc['source']}' is suspiciously short"


def test_chunk_text_respects_chunk_size():
    text = "\n\n".join([f"Paragraph {i}. " + ("word " * 30) for i in range(10)])
    chunks = chunk_text(text, chunk_size=400, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 450 for c in chunks)


def test_chunk_text_handles_short_text():
    assert chunk_text("Just one short paragraph.") == ["Just one short paragraph."]


def test_chunk_text_handles_empty_text():
    assert chunk_text("") == []


def test_bm25_index_covers_banking_keywords():
    """After reindexing, the BM25 store must return relevant chunks
    for core banking complaint terms.

    Loads directly from the canonical index file path (derived from
    __file__) so that test_bm25_store.py's monkeypatch redirections
    of bm.INDEX_FILE do not affect this test regardless of order."""
    from pathlib import Path
    from app.rag.bm25_store import BM25Index

    # Always compute the real path from __file__ — never from the
    # module-level INDEX_FILE which monkeypatch may have redirected.
    real_index = (
        Path(__file__).resolve().parent.parent  # backend/
        / "data" / "knowledge_base" / ".bm25_index.json"
    )

    if not real_index.exists():
        from app.rag.knowledge_base import build_index
        build_index()

    assert real_index.exists(), "BM25 index file missing after build_index()"

    index = BM25Index.load(real_index)
    assert len(index.chunks) > 0, "BM25 index is empty — SOPs may not have been indexed"

    for query in ["unauthorized credit card charge", "mortgage loan modification", "debt collection harassment"]:
        results = index.search(query, top_k=3)
        assert len(results) > 0, f"No BM25 results for query: {query!r}"
        assert results[0]["score"] > 0, f"Top result has zero score for: {query!r}"
