"""
Tests for app/rag/hybrid_retriever.py

Coverage:
  - BM25-only queries (real BM25Index)
  - Embedding-only queries (Gemini + vector_store fully mocked)
  - Hybrid RRF fusion (both arms populated)
  - Graceful degradation when Gemini is down / not configured
  - Edge cases: empty index, empty results, single-arm lists
"""
import math
import pytest

from app.rag.hybrid_retriever import HybridRetriever, RRF_K
from app.rag.bm25_store import BM25Index


# ─────────────────────────────────────────────────── fixtures / helpers ───


def _make_chunk(text: str, source: str = "test_sop.md") -> dict:
    return {"text": text, "source": source}


def _make_result(text: str, score: float = 1.0, source: str = "test_sop.md") -> dict:
    return {"score": score, "payload": {"text": text, "source": source}}


@pytest.fixture()
def small_bm25_index(tmp_path):
    """A real BM25Index with three chunks, saved to tmp_path."""
    chunks = [
        _make_chunk("billing dispute resolution steps for repeat charges", "billing_sop.md"),
        _make_chunk("technical outage escalation procedure for network downtime", "technical_sop.md"),
        _make_chunk("service complaint handling and customer follow-up process", "service_sop.md"),
    ]
    idx = BM25Index()
    idx.fit(chunks)
    index_path = tmp_path / ".bm25_index.json"
    idx.save(index_path)
    return idx, index_path


@pytest.fixture()
def retriever_with_index(small_bm25_index, monkeypatch):
    """HybridRetriever whose BM25 arm uses the small in-memory index."""
    idx, _path = small_bm25_index

    # Patch is_indexed() and get_index() so search_bm25 uses our fixture.
    import app.rag.hybrid_retriever as hr_mod
    monkeypatch.setattr(hr_mod, "is_indexed", lambda: True)
    monkeypatch.setattr(hr_mod, "get_index", lambda: idx)

    # Disable Gemini by default — individual tests re-enable it if needed.
    import app.rag.gemini_client as gc
    monkeypatch.setattr(gc, "GEMINI_API_KEY", None)

    return HybridRetriever()


# ─────────────────────────────────────────────────────── BM25-only tests ───


class TestBM25Search:
    def test_exact_keyword_returns_matching_chunk(self, retriever_with_index):
        results = retriever_with_index.search_bm25("billing dispute", top_k=3)
        assert len(results) >= 1
        texts = [r["payload"]["text"] for r in results]
        assert any("billing" in t for t in texts)

    def test_best_bm25_hit_is_ranked_first(self, retriever_with_index):
        results = retriever_with_index.search_bm25("outage escalation", top_k=3)
        assert results[0]["payload"]["text"].startswith("technical outage")

    def test_top_k_respected(self, retriever_with_index):
        results = retriever_with_index.search_bm25("complaint", top_k=2)
        assert len(results) <= 2

    def test_no_match_query_returns_empty(self, retriever_with_index):
        # "zzznomatch" appears in none of the three chunks
        results = retriever_with_index.search_bm25("zzznomatch", top_k=5)
        assert results == []

    def test_empty_query_returns_empty(self, retriever_with_index):
        results = retriever_with_index.search_bm25("", top_k=5)
        assert results == []

    def test_index_not_built_returns_empty(self, monkeypatch):
        """search_bm25 returns [] without raising when there's no index."""
        import app.rag.hybrid_retriever as hr_mod
        monkeypatch.setattr(hr_mod, "is_indexed", lambda: False)
        r = HybridRetriever()
        assert r.search_bm25("billing", top_k=5) == []


# ─────────────────────────────────────────────── Embedding-only tests (mocked) ───


class TestEmbeddingSearch:
    def test_returns_empty_when_gemini_not_configured(self, monkeypatch):
        import app.rag.gemini_client as gc
        monkeypatch.setattr(gc, "GEMINI_API_KEY", None)
        r = HybridRetriever()
        assert r.search_embeddings("billing dispute") == []

    def test_returns_results_when_gemini_available(self, monkeypatch):
        """Mock embed_text to return a fake vector; mock vector_store.search."""
        import app.rag.gemini_client as gc
        import app.rag.hybrid_retriever as hr_mod

        monkeypatch.setattr(gc, "GEMINI_API_KEY", "fake-key-for-testing")
        monkeypatch.setattr(gc, "embed_text", lambda text, task_type=None: [0.1, 0.2, 0.3])

        fake_store_results = [
            {"score": 0.95, "payload": {"text": "billing resolution steps", "source": "billing_sop.md"}},
            {"score": 0.80, "payload": {"text": "repeat charges handling", "source": "billing_sop.md"}},
        ]
        monkeypatch.setattr(hr_mod._vector_store, "search",
                            lambda vector, top_k: fake_store_results[:top_k])

        r = HybridRetriever()
        results = r.search_embeddings("billing dispute", top_k=2)
        assert len(results) == 2
        assert results[0]["score"] == 0.95
        assert results[0]["payload"]["text"] == "billing resolution steps"

    def test_gemini_error_returns_empty_not_raises(self, monkeypatch):
        import app.rag.gemini_client as gc
        from app.rag.gemini_client import GeminiError

        monkeypatch.setattr(gc, "GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(gc, "embed_text",
                            lambda text, task_type=None: (_ for _ in ()).throw(
                                GeminiError("Read timed out")))

        r = HybridRetriever()
        # Must not raise; must return empty list
        results = r.search_embeddings("billing dispute")
        assert results == []

    def test_vector_store_error_returns_empty_not_raises(self, monkeypatch):
        import app.rag.gemini_client as gc
        import app.rag.hybrid_retriever as hr_mod

        monkeypatch.setattr(gc, "GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(gc, "embed_text", lambda text, task_type=None: [0.1, 0.2])
        monkeypatch.setattr(hr_mod._vector_store, "search",
                            lambda vector, top_k: (_ for _ in ()).throw(
                                Exception("Qdrant unreachable")))

        r = HybridRetriever()
        results = r.search_embeddings("billing dispute")
        assert results == []


# ───────────────────────────────────────────────────────── RRF fusion tests ───


class TestFuseResults:
    def _r(self, text: str, score: float = 1.0) -> dict:
        return _make_result(text, score)

    def test_empty_inputs_return_empty(self):
        r = HybridRetriever()
        assert r.fuse_results([], []) == []

    def test_only_bm25_returns_rrf_scored_list(self):
        r = HybridRetriever()
        bm25 = [self._r("chunk A"), self._r("chunk B"), self._r("chunk C")]
        result = r.fuse_results(bm25, [])
        # Order must be preserved; scores should be decreasing.
        texts = [x["payload"]["text"] for x in result]
        assert texts == ["chunk A", "chunk B", "chunk C"]
        assert result[0]["score"] > result[1]["score"] > result[2]["score"]

    def test_only_embeddings_returns_rrf_scored_list(self):
        r = HybridRetriever()
        emb = [self._r("chunk X"), self._r("chunk Y")]
        result = r.fuse_results([], emb)
        assert [x["payload"]["text"] for x in result] == ["chunk X", "chunk Y"]

    def test_chunk_in_both_lists_scores_higher_than_single_list(self):
        """A chunk that ranks well in both lists should outscore a chunk
        that only appears in one list."""
        r = HybridRetriever()
        shared_text = "billing dispute"
        only_bm25_text = "technical outage"
        only_emb_text = "service complaint"

        bm25 = [self._r(shared_text), self._r(only_bm25_text)]
        emb = [self._r(shared_text), self._r(only_emb_text)]

        fused = r.fuse_results(bm25, emb)
        scores = {item["payload"]["text"]: item["score"] for item in fused}

        # The shared chunk should beat both single-list chunks.
        assert scores[shared_text] > scores[only_bm25_text]
        assert scores[shared_text] > scores[only_emb_text]

    def test_rrf_score_formula(self):
        """Verify the RRF score matches the formula: 1/(k+rank) for both lists."""
        r = HybridRetriever()
        k = RRF_K
        # Single chunk ranked #1 in both lists.
        bm25 = [self._r("chunk A")]
        emb = [self._r("chunk A")]
        fused = r.fuse_results(bm25, emb)
        expected = round(1.0 / (k + 1) + 1.0 / (k + 1), 6)
        assert math.isclose(fused[0]["score"], expected, rel_tol=1e-5)

    def test_deduplication_by_text(self):
        """The same chunk text must appear only once in the output."""
        r = HybridRetriever()
        bm25 = [self._r("billing dispute"), self._r("technical outage")]
        emb = [self._r("billing dispute"), self._r("service complaint")]
        fused = r.fuse_results(bm25, emb)
        texts = [x["payload"]["text"] for x in fused]
        assert len(texts) == len(set(texts))

    def test_top_k_applied_in_search(self, retriever_with_index):
        """The orchestrating search() method respects top_k."""
        results = retriever_with_index.search("billing", top_k=1)
        assert len(results) <= 1


# ────────────────────────────────────────────── Graceful degradation tests ───


class TestGracefulDegradation:
    def test_bm25_only_when_no_gemini_key(self, retriever_with_index):
        """When Gemini isn't configured, search() should still return
        BM25 results rather than crashing or returning []."""
        results = retriever_with_index.search("billing dispute", top_k=3)
        # BM25 arm has 3 chunks, at least one should match
        assert len(results) >= 1
        assert all("payload" in r for r in results)

    def test_no_crash_when_gemini_times_out(self, retriever_with_index, monkeypatch):
        """Simulates Gemini timing out on the embedding call."""
        import app.rag.gemini_client as gc
        from app.rag.gemini_client import GeminiError

        monkeypatch.setattr(gc, "GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(gc, "embed_text",
                            lambda text, task_type=None: (_ for _ in ()).throw(
                                GeminiError("Read timed out (read timeout=20)")))

        results = retriever_with_index.search("billing dispute", top_k=3)
        # Should still return BM25 results, not raise.
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_no_crash_when_both_retrievers_return_empty(self, monkeypatch):
        """When BM25 has no index and embeddings are disabled, search()
        returns [] without raising."""
        import app.rag.hybrid_retriever as hr_mod
        import app.rag.gemini_client as gc
        monkeypatch.setattr(hr_mod, "is_indexed", lambda: False)
        monkeypatch.setattr(gc, "GEMINI_API_KEY", None)

        r = HybridRetriever()
        assert r.search("anything", top_k=5) == []

    def test_hybrid_fusion_used_when_both_arms_available(self, retriever_with_index,
                                                          monkeypatch):
        """When Gemini is configured and returns results, the fused list
        should contain chunks from both arms (deduped)."""
        import app.rag.gemini_client as gc
        import app.rag.hybrid_retriever as hr_mod

        # Gemini returns a result that BM25 would NOT find (different vocabulary)
        monkeypatch.setattr(gc, "GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(gc, "embed_text", lambda text, task_type=None: [0.1])
        semantic_chunk = {"text": "paraphrase: a customer is being repeatedly billed",
                          "source": "billing_sop.md"}
        monkeypatch.setattr(hr_mod._vector_store, "search",
                            lambda vector, top_k: [
                                {"score": 0.9, "payload": semantic_chunk}
                            ])

        results = retriever_with_index.search("billing", top_k=5)
        texts = [r["payload"]["text"] for r in results]
        # BM25 hit must be present
        assert any("billing" in t for t in texts)
        # Semantic hit from embedding must also be present
        assert any("paraphrase" in t for t in texts)
