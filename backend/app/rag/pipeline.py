"""
RAG pipeline: Hybrid retrieval (BM25 + optional Gemini embeddings) →
Gemini generateContent → answer.

Retrieval is handled by app/rag/hybrid_retriever.py (HybridRetriever).
  - BM25: always available, pure Python, no API calls.
  - Gemini embeddings: optional, query-only (never indexes the corpus),
    fused with BM25 via Reciprocal Rank Fusion (RRF).
  - Graceful degradation: if Gemini embeddings are unavailable for any
    reason (missing key, timeout, rate limit), BM25-only results are
    used silently.

Gemini generateContent is still required for the final answer.
Raises gemini_client.GeminiError on generation failures — callers
(app/chatbot.py) catch this and fall back to the template response.

See docs/DECISIONS.md Decision 30 and docs/RAG_CHATBOT.md.
"""
from . import gemini_client
from .bm25_store import is_indexed
from .hybrid_retriever import get_retriever

SYSTEM_INSTRUCTION = (
    "You are an internal assistant for customer-support admins at a telecom "
    "complaints desk (product: Loopline). Answer using the SOP context "
    "provided below as your primary source — if the context doesn't cover "
    "the question, say so plainly rather than guessing. Keep answers short "
    "and actionable: tell the admin what to do next, referencing specific "
    "SOP steps or policies where relevant. You're talking to a trained "
    "support agent, not the customer — be direct and skip pleasantries."
)


def answer(question: str, extra_context: str = None, top_k: int = 5) -> dict:
    """Returns {"answer": str, "sources": [str, ...], "used_rag": bool,
                "used_bm25": bool, "used_embeddings": bool}.
    Raises GeminiError if Gemini isn't configured or the generation call fails.

    The API surface is backward-compatible: callers that only read
    "answer", "sources", and "used_rag" continue to work unchanged.
    The two new boolean fields are informational extras for the UI.
    """
    if not gemini_client.is_configured():
        raise gemini_client.GeminiError("GEMINI_API_KEY not configured.")

    # ── Hybrid retrieval (BM25 always; embeddings if available) ──────────
    if not is_indexed():
        context_block = (
            "No knowledge base indexed yet. "
            "Run `python -m app.rag.knowledge_base` from the backend/ folder."
        )
        sources = []
        used_rag = False
        used_bm25 = False
        used_embeddings = False
    else:
        retriever = get_retriever()

        # Run both arms so we can report which ones contributed.
        bm25_hits = retriever.search_bm25(question, top_k=top_k)
        emb_hits = retriever.search_embeddings(question, top_k=top_k)
        hits = retriever.fuse_results(bm25_hits, emb_hits)[:top_k]

        used_bm25 = bool(bm25_hits)
        used_embeddings = bool(emb_hits)

        if hits:
            context_block = "\n\n---\n\n".join(
                f"[Source: {h['payload'].get('source', 'unknown')}]\n"
                f"{h['payload'].get('text', '')}"
                for h in hits
            )
            sources = sorted({h["payload"].get("source", "unknown") for h in hits})
            used_rag = True
        else:
            context_block = (
                "No relevant SOP entries found for this query. "
                "Answer based on general telecom support best practices."
            )
            sources = []
            used_rag = False

    # ── Gemini generateContent ────────────────────────────────────────────
    prompt_parts = [f"SOP CONTEXT:\n{context_block}"]
    if extra_context:
        prompt_parts.append(f"COMPLAINT CONTEXT:\n{extra_context}")
    prompt_parts.append(f"ADMIN QUESTION:\n{question}")
    prompt = "\n\n".join(prompt_parts)

    text = gemini_client.generate_text(prompt, system_instruction=SYSTEM_INSTRUCTION)
    return {
        "answer": text,
        "sources": sources,
        "used_rag": used_rag,
        "used_bm25": used_bm25,
        "used_embeddings": used_embeddings,
    }
