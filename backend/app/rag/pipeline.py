"""
RAG pipeline: Hybrid retrieval (BM25 + optional Gemini embeddings) →
LLM generateContent → answer.

Generation backend (in priority order):
  1. Groq (GROQ_API_KEY set) — fast, geo-accessible, generous free tier.
  2. Gemini (GEMINI_API_KEY set, no GROQ_API_KEY) — fallback for envs
     where Groq is unavailable but Gemini is reachable.
  3. Neither configured → raises an error that chatbot.py catches and
     converts to a graceful template fallback.

Retrieval is always BM25 (pure Python, zero API keys needed), with
optional Gemini query embeddings fused via RRF when available.
The generation backend choice does NOT affect retrieval.

See docs/DECISIONS.md Decision 33 for the Groq migration rationale.
"""
from . import gemini_client
from . import groq_client
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


def _is_configured() -> bool:
    """True when at least one generation backend is available."""
    return groq_client.is_configured() or gemini_client.is_configured()


def _generate(prompt: str) -> str:
    """Call whichever LLM backend is configured, Groq first.
    Raises GroqError / GeminiError on failure — callers catch both."""
    if groq_client.is_configured():
        return groq_client.generate_text(prompt, system_instruction=SYSTEM_INSTRUCTION)
    if gemini_client.is_configured():
        return gemini_client.generate_text(prompt, system_instruction=SYSTEM_INSTRUCTION)
    raise groq_client.GroqError(
        "No LLM configured. Set GROQ_API_KEY (recommended) or GEMINI_API_KEY in .env."
    )


def answer(question: str, extra_context: str = None, top_k: int = 5) -> dict:
    """Returns {"answer": str, "sources": [str, ...], "used_rag": bool,
                "used_bm25": bool, "used_embeddings": bool}.

    Raises GroqError/GeminiError if no LLM is configured or the call fails.
    API surface is backward-compatible: callers reading only "answer",
    "sources", and "used_rag" work unchanged.
    """
    if not _is_configured():
        raise groq_client.GroqError(
            "No LLM configured. Set GROQ_API_KEY (recommended) or GEMINI_API_KEY in .env."
        )

    # ── Hybrid retrieval (BM25 always; Gemini embeddings if available) ───
    if not is_indexed():
        context_block   = (
            "No knowledge base indexed yet. "
            "Run `python -m app.rag.knowledge_base` from the backend/ folder."
        )
        sources         = []
        used_rag        = False
        used_bm25       = False
        used_embeddings = False
    else:
        retriever = get_retriever()
        bm25_hits = retriever.search_bm25(question, top_k=top_k)
        emb_hits  = retriever.search_embeddings(question, top_k=top_k)
        hits      = retriever.fuse_results(bm25_hits, emb_hits)[:top_k]

        used_bm25       = bool(bm25_hits)
        used_embeddings = bool(emb_hits)

        if hits:
            context_block = "\n\n---\n\n".join(
                f"[Source: {h['payload'].get('source', 'unknown')}]\n"
                f"{h['payload'].get('text', '')}"
                for h in hits
            )
            sources  = sorted({h["payload"].get("source", "unknown") for h in hits})
            used_rag = True
        else:
            context_block = (
                "No relevant SOP entries found for this query. "
                "Answer based on general telecom support best practices."
            )
            sources  = []
            used_rag = False

    # ── LLM generation ────────────────────────────────────────────────────
    prompt_parts = [f"SOP CONTEXT:\n{context_block}"]
    if extra_context:
        prompt_parts.append(f"COMPLAINT CONTEXT:\n{extra_context}")
    prompt_parts.append(f"ADMIN QUESTION:\n{question}")
    prompt = "\n\n".join(prompt_parts)

    text = _generate(prompt)
    return {
        "answer":          text,
        "sources":         sources,
        "used_rag":        used_rag,
        "used_bm25":       used_bm25,
        "used_embeddings": used_embeddings,
    }
