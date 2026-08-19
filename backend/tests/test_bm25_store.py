"""
Unit tests for app/rag/bm25_store.py

Exercises BM25Index construction, search ranking, persistence,
and the module-level cache helpers.  No external API calls.
"""
import json
import pytest

from app.rag.bm25_store import BM25Index, get_index, clear_cache, is_indexed, INDEX_FILE


# ─────────────────────────────────────── helpers ───

def _chunks(*texts, source="sop.md"):
    return [{"text": t, "source": source} for t in texts]


# ─────────────────────────────────────── BM25Index unit tests ───

class TestBM25IndexBasics:
    def test_fit_sets_chunk_count(self):
        idx = BM25Index()
        idx.fit(_chunks("billing dispute", "technical outage", "service complaint"))
        assert len(idx) == 3

    def test_search_returns_list(self):
        idx = BM25Index()
        idx.fit(_chunks("billing dispute resolution", "outage escalation"))
        results = idx.search("billing", top_k=2)
        assert isinstance(results, list)

    def test_exact_match_ranks_first(self):
        idx = BM25Index()
        idx.fit(_chunks(
            "billing dispute resolution for overcharged accounts",
            "technical outage procedure for network downtime",
            "service complaint handling for unhappy customers",
        ))
        results = idx.search("billing overcharged", top_k=3)
        assert results[0]["payload"]["text"].startswith("billing dispute")

    def test_scores_are_positive_and_descending(self):
        idx = BM25Index()
        idx.fit(_chunks("billing dispute", "billing complaint", "outage escalation"))
        results = idx.search("billing", top_k=3)
        scores = [r["score"] for r in results]
        assert all(s > 0 for s in scores)
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_results(self):
        idx = BM25Index()
        idx.fit(_chunks("a billing issue", "billing error", "billing dispute",
                        "technical billing", "billing refund"))
        assert len(idx.search("billing", top_k=3)) == 3
        assert len(idx.search("billing", top_k=1)) == 1

    def test_unknown_query_term_returns_empty(self):
        idx = BM25Index()
        idx.fit(_chunks("billing dispute", "outage"))
        results = idx.search("zzznomatch", top_k=5)
        assert results == []

    def test_empty_query_returns_empty(self):
        idx = BM25Index()
        idx.fit(_chunks("billing dispute"))
        assert idx.search("", top_k=5) == []

    def test_empty_index_returns_empty(self):
        idx = BM25Index()
        idx.fit([])
        assert idx.search("billing", top_k=5) == []

    def test_result_format(self):
        idx = BM25Index()
        idx.fit(_chunks("billing dispute resolution"))
        result = idx.search("billing", top_k=1)[0]
        assert "score" in result
        assert "payload" in result
        assert "text" in result["payload"]
        assert "source" in result["payload"]


class TestBM25IDF:
    def test_rare_term_scores_higher_than_common(self):
        """A term appearing in only 1 of N documents should have higher
        IDF than one that appears in all N documents."""
        idx = BM25Index()
        # "billing" appears in all three; "outage" appears in only one.
        idx.fit(_chunks(
            "billing outage network failure",
            "billing dispute refund",
            "billing complaint resolution",
        ))
        idf_billing = idx._idf.get("billing", 0)
        idf_outage = idx._idf.get("outage", 0)
        assert idf_outage > idf_billing

    def test_k1_b_defaults(self):
        idx = BM25Index()
        assert idx.k1 == 1.5
        assert idx.b == 0.75


class TestBM25Persistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        chunks = _chunks(
            "billing dispute resolution",
            "technical outage escalation",
            "service follow-up process",
        )
        idx = BM25Index()
        idx.fit(chunks)

        path = tmp_path / "test_index.json"
        idx.save(path)
        assert path.exists()

        loaded = BM25Index.load(path)
        assert len(loaded) == 3
        assert loaded._avgdl == pytest.approx(idx._avgdl, rel=1e-6)

        # Search results should be identical after roundtrip.
        r1 = idx.search("billing", top_k=2)
        r2 = loaded.search("billing", top_k=2)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a["payload"]["text"] == b["payload"]["text"]
            assert a["score"] == pytest.approx(b["score"], rel=1e-5)

    def test_save_creates_parent_dir(self, tmp_path):
        idx = BM25Index()
        idx.fit(_chunks("billing"))
        deep_path = tmp_path / "nested" / "dir" / "index.json"
        idx.save(deep_path)
        assert deep_path.exists()

    def test_saved_json_is_valid(self, tmp_path):
        idx = BM25Index()
        idx.fit(_chunks("billing dispute"))
        path = tmp_path / "idx.json"
        idx.save(path)
        data = json.loads(path.read_text())
        for key in ("k1", "b", "chunks", "tokenized", "doc_freqs", "idf", "avgdl"):
            assert key in data


class TestModuleCache:
    def test_clear_cache_forces_reload(self, monkeypatch):
        """clear_cache() should set _instance to None so the next
        get_index() call reloads from disk."""
        import app.rag.bm25_store as bm
        monkeypatch.setattr(bm, "_instance", object())  # simulate a loaded index
        clear_cache()
        assert bm._instance is None

    def test_is_indexed_false_when_file_missing(self, monkeypatch, tmp_path):
        """is_indexed() returns False when INDEX_FILE doesn't exist."""
        import app.rag.bm25_store as bm
        fake_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(bm, "INDEX_FILE", fake_path)
        assert not bm.is_indexed()

    def test_is_indexed_true_when_file_exists(self, monkeypatch, tmp_path):
        import app.rag.bm25_store as bm
        path = tmp_path / "index.json"
        idx = BM25Index()
        idx.fit(_chunks("billing"))
        idx.save(path)
        monkeypatch.setattr(bm, "INDEX_FILE", path)
        assert bm.is_indexed()

    def test_get_index_returns_none_when_missing(self, monkeypatch, tmp_path):
        import app.rag.bm25_store as bm
        fake_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(bm, "INDEX_FILE", fake_path)
        bm._instance = None
        assert bm.get_index() is None

    def test_get_index_caches_after_first_load(self, monkeypatch, tmp_path):
        import app.rag.bm25_store as bm
        idx = BM25Index()
        idx.fit(_chunks("billing dispute"))
        path = tmp_path / "idx.json"
        idx.save(path)
        monkeypatch.setattr(bm, "INDEX_FILE", path)
        bm._instance = None

        first = bm.get_index()
        second = bm.get_index()
        assert first is second  # same object (cache hit)
