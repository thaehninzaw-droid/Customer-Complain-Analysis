"""
RAG pipeline: BM25 search → Gemini generateContent → answer.

Gemini is used ONLY for generating the final answer, not for embedding.
Retrieval is handled by app/rag/bm25_store.py (pure Python, no API).

Raises gemini_client.GeminiError on Gemini failures — callers catch
this and fall back to the template response (see app/chatbot.py).
"""
from . import gemini_client
from .bm25_store import get_index, is_indexed

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
    """Returns {"answer": str, "sources": [str, ...], "used_rag": bool}.
    Raises GeminiError if Gemini isn't configured or the call fails."""
    if not gemini_client.is_configured():
        raise gemini_client.GeminiError("GEMINI_API_KEY not configured.")

    # ── BM25 retrieval (no API call) ─────────────────────────────────────
    if not is_indexed():
        context_block = (
            "No knowledge base indexed yet. "
            "Run `python -m app.rag.knowledge_base` from the backend/ folder."
        )
        sources = []
        used_rag = False
    else:
        index = get_index()
        hits = index.search(question, top_k=top_k) if index else []

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
    return {"answer": text, "sources": sources, "used_rag": used_rag}
