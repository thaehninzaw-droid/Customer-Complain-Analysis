"""
Orchestrates the RAG pipeline: embed the question -> search the
vector store for relevant SOP chunks -> build a grounded prompt ->
ask Gemini -> return an answer plus which SOP sources were used.

This is what app/chatbot.py calls internally for the Admin AI Chatbot
(SRS 3.2). It raises GeminiError on any failure (missing API key,
network error) - callers are expected to catch that and fall back to
the template response, same "never let an AI integration break the
request" rule used everywhere else in this codebase (see
app/classify.py, app/priority.py).
"""
from . import gemini_client, vector_store

SYSTEM_INSTRUCTION = (
    "You are an internal assistant for customer-support admins at a telecom "
    "complaints desk (product: Loopline). Answer using the SOP context "
    "provided below as your primary source - if the context doesn't cover "
    "the question, say so plainly rather than guessing. Keep answers short "
    "and actionable: tell the admin what to do next, referencing specific "
    "SOP steps or policies where relevant. You're talking to a trained "
    "support agent, not the customer - be direct and skip pleasantries."
)


def answer(question: str, extra_context: str = None, top_k: int = 4) -> dict:
    """Returns {"answer": str, "sources": [str, ...]}. Raises
    gemini_client.GeminiError if Gemini isn't configured or the call
    fails - see app/chatbot.py for the fallback path."""
    if not gemini_client.is_configured():
        raise gemini_client.GeminiError("GEMINI_API_KEY not configured.")

    query_vector = gemini_client.embed_text(question, task_type="RETRIEVAL_QUERY")
    hits = vector_store.search(query_vector, top_k=top_k)

    if not hits:
        context_block = (
            "(No indexed SOP documents yet - run "
            "`python -m app.rag.knowledge_base` to build the index.)"
        )
        sources = []
    else:
        context_block = "\n\n---\n\n".join(
            f"[Source: {h['payload'].get('source', 'unknown')}]\n{h['payload'].get('text', '')}"
            for h in hits
        )
        sources = sorted({h["payload"].get("source", "unknown") for h in hits})

    prompt_parts = [f"SOP CONTEXT:\n{context_block}"]
    if extra_context:
        prompt_parts.append(f"COMPLAINT CONTEXT:\n{extra_context}")
    prompt_parts.append(f"ADMIN QUESTION:\n{question}")
    prompt = "\n\n".join(prompt_parts)

    text = gemini_client.generate_text(prompt, system_instruction=SYSTEM_INSTRUCTION)
    return {"answer": text, "sources": sources}
