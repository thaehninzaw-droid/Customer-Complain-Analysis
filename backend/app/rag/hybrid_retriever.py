"""
Hybrid retrieval: BM25 (always available) + optional Gemini query
embeddings fused via Reciprocal Rank Fusion (RRF).

Why hybrid?
  BM25 is fast, local, and strong for exact-match SOP keywords
  ("billing", "outage", "repeat charge"). Gemini embedding queries
  add semantic coverage so paraphrases ("how do I deal with a customer
  who keeps getting charged") also surface the right SOP chunks even
  when they share no tokens with the query. Fusing the two ranked
  lists with RRF is dead simple and consistently beats either alone.

Design constraints (see docs/DECISIONS.md Decision 30):
  - BM25 index is always built at index time (no quota risk).
  - Embeddings are NEVER computed for document chunks at index time —
    only for the incoming query at query time. One embedding call per
    user question, not 2315 (the full chunk count).
  - If Gemini is unavailable, the system falls back to BM25-only
    without any error surfacing to the caller.
  - Zero external API keys required for the system to work.

Reciprocal Rank Fusion (RRF):
  score_rrf(doc, k=60) = Σ  1 / (k + rank_in_list_i)
  k=60 is the standard default (Cormack et al. 2009). A document
  appearing at rank 1 in both lists scores ≈ 2/61 ≈ 0.033, much
  higher than a doc at rank 5 in only one list (1/65 ≈ 0.015).
  BM25 exact-match hits dominate naturally because BM25 already
  puts exact-match documents at the top of its ranked list; RRF
  amplifies that advantage further.

Usage (via pipeline.py — this class isn't called directly):
    retriever = HybridRetriever()
    results = retriever.search("how to handle repeat billing")
    # → [{"score": float, "payload": {"text": str, "source": str}}, ...]
"""
from __future__ import annotations

import logging
from typing import Optional

from .bm25_store import BM25Index, get_index, is_indexed
from . import gemini_client
from . import vector_store as _vector_store

logger = logging.getLogger(__name__)

# RRF smoothing constant (standard default from Cormack et al. 2009).
RRF_K: int = 60


class HybridRetriever:
    """Combines BM25 keyword search with optional Gemini embedding
    queries fused via Reciprocal Rank Fusion.

    Public API:
        search_bm25(query, top_k) → list[dict]
        search_embeddings(query, top_k) → list[dict]   # may return []
        fuse_results(bm25_results, emb_results, k) → list[dict]
        search(query, top_k) → list[dict]               # orchestrates all
    """

    # ------------------------------------------------------------------ BM25

    def search_bm25(self, query: str, top_k: int = 5) -> list[dict]:
        """Pure BM25 keyword retrieval against the local JSON index.

        Returns up to top_k results as:
            [{"score": float, "payload": {"text": str, "source": str}}, ...]

        Returns [] if the index hasn't been built yet (not an error —
        the caller handles this gracefully).
        """
        if not is_indexed():
            logger.debug("[hybrid] BM25 index not built yet — skipping BM25")
            return []
        index: Optional[BM25Index] = get_index()
        if index is None:
            return []
        return index.search(query, top_k=top_k)

    # --------------------------------------------------------------- Embeddings

    def search_embeddings(self, query: str, top_k: int = 5) -> list[dict]:
        """Embed the query with Gemini, then search Qdrant (or the
        in-memory cosine-similarity fallback if QDRANT_URL isn't set).

        Returns [] — never raises — when:
          - GEMINI_API_KEY is not configured
          - The Gemini embedding call times out / returns an error
          - The vector store is empty (nothing indexed there yet)
          - QDRANT_URL is not set and the in-memory store is empty

        Result format matches BM25 for easy fusion:
            [{"score": float, "payload": {"text": str, "source": str}}, ...]
        """
        if not gemini_client.is_configured():
            logger.debug("[hybrid] GEMINI_API_KEY not set — skipping embeddings")
            return []

        try:
            vector = gemini_client.embed_text(query, task_type="RETRIEVAL_QUERY")
        except gemini_client.GeminiError as exc:
            logger.warning("[hybrid] Gemini embedding unavailable: %s — "
                           "falling back to keyword search only", exc)
            return []
        except Exception as exc:  # pragma: no cover  (network, parse errors)
            logger.warning("[hybrid] Unexpected embedding error: %s", exc)
            return []

        try:
            raw = _vector_store.search(vector, top_k=top_k)
        except Exception as exc:
            logger.warning("[hybrid] Vector store search failed: %s", exc)
            return []

        # Normalise scores so they're always floats (Qdrant cosine is
        # already in [-1, 1]; the in-memory fallback is also cosine).
        return [
            {"score": float(r.get("score", 0.0)), "payload": r.get("payload", {})}
            for r in raw
        ]

    # ------------------------------------------------------------------- RRF

    def fuse_results(
        self,
        bm25_results: list[dict],
        embedding_results: list[dict],
        k: int = RRF_K,
    ) -> list[dict]:
        """Reciprocal Rank Fusion over two ranked lists.

        Each result dict must have a "payload" key with at least a "text"
        field.  The text is used as the document identity key for dedup.

        Returns a new ranked list (highest RRF score first) covering
        all unique chunks from both inputs, with a synthetic "score"
        equal to the RRF value (useful for debugging / logging).

        Edge cases:
          - Either list empty → returns the other list unchanged (with
            scores rewritten to their RRF value from rank alone).
          - Both lists empty → returns [].
        """
        if not bm25_results and not embedding_results:
            return []
        if not embedding_results:
            # Still apply RRF normalisation for consistent score field.
            return self._rrf_single(bm25_results, k)
        if not bm25_results:
            return self._rrf_single(embedding_results, k)

        # Build text→payload map (BM25 wins on tie for payload content).
        payload_by_text: dict[str, dict] = {}
        for r in embedding_results:
            txt = r["payload"].get("text", "")
            payload_by_text[txt] = r["payload"]
        for r in bm25_results:
            txt = r["payload"].get("text", "")
            payload_by_text[txt] = r["payload"]  # BM25 overwrites

        # Accumulate RRF scores keyed by chunk text.
        rrf_scores: dict[str, float] = {}

        for rank, result in enumerate(bm25_results, start=1):
            key = result["payload"].get("text", "")
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)

        for rank, result in enumerate(embedding_results, start=1):
            key = result["payload"].get("text", "")
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)

        sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        return [
            {"score": round(score, 6), "payload": payload_by_text[text]}
            for text, score in sorted_items
            if text in payload_by_text
        ]

    @staticmethod
    def _rrf_single(results: list[dict], k: int) -> list[dict]:
        """Apply RRF scoring to a single ranked list (for consistent
        score field format even in the non-hybrid case)."""
        return [
            {
                "score": round(1.0 / (k + rank), 6),
                "payload": r["payload"],
            }
            for rank, r in enumerate(results, start=1)
        ]

    # ----------------------------------------------------------------- orchestrate

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Run hybrid retrieval and return fused top_k results.

        Flow:
          1. BM25 search (always; never raises).
          2. Gemini query embedding + vector store search (optional;
             silently skipped on any error).
          3. RRF fusion.
          4. Return top_k fused results.

        Fallback priority:
          - Gemini unavailable → BM25-only results (no error).
          - BM25 index missing → embedding-only results (no error).
          - Both missing → [] (pipeline.py will tell the admin).

        The returned format matches BM25Index.search() so pipeline.py
        needs no changes:
            [{"score": float, "payload": {"text": str, "source": str}}, ...]
        """
        bm25 = self.search_bm25(query, top_k=top_k)
        emb = self.search_embeddings(query, top_k=top_k)

        fused = self.fuse_results(bm25, emb)

        # Log which retrievers contributed (visible in server logs).
        used = []
        if bm25:
            used.append(f"bm25({len(bm25)})")
        if emb:
            used.append(f"embeddings({len(emb)})")
        if used:
            logger.debug("[hybrid] %s → %d fused results for: %.80s",
                         "+".join(used), len(fused), query)
        else:
            logger.debug("[hybrid] no results from any retriever for: %.80s", query)

        return fused[:top_k]


# Module-level singleton (thread-safe because construction is idempotent).
_retriever: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    """Return the shared HybridRetriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
