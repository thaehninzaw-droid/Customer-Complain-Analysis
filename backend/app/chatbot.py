"""
RAG chatbot recommendations - two entry points, two audiences:

  get_recommendation(complaint_text, category) -> str
      Used by /chatbot/recommend, the simple category-in/advice-out
      call the customer-facing homepage widget uses (and that the
      admin dashboard can also call for a quick per-ticket suggestion).
      Tries the real RAG pipeline first (Gemini + Qdrant, see
      app/rag/pipeline.py); falls back to the template dict below if
      GEMINI_API_KEY isn't set, no knowledge base has been indexed
      yet, or the call fails for any reason. Same "never let an AI
      integration break the request" rule as app/classify.py and
      app/priority.py.

  ask_admin_chatbot(question, ticket_context=None) -> dict
      Used by /admin/chatbot/ask, the Admin AI Chatbot module (SRS
      3.2): free-form Q&A grounded in the indexed SOP documents
      (data/knowledge_base/). Returns which SOP sources were used.
      Falls back to a plain "AI chatbot isn't configured yet" message
      (not a fake answer) if RAG isn't available - see
      docs/RAG_CHATBOT.md for setup.

See DECISIONS.md for why Gemini + Qdrant was chosen, and
docs/RAG_CHATBOT.md for the full architecture write-up.
"""
from .categories import CATEGORIES
from .rag import gemini_client
from .rag.pipeline import answer as rag_answer

RECOMMENDATIONS = {
    "Billing": "Recommended action: verify the charge against the account's billing history, and adjust or refund if it was an error.",
    "Financial": "Recommended action: review the fee or refund request against policy, and process or explain the outcome to the customer.",
    "Technical": "Recommended action: check for a known outage in the customer's area; if none, run a remote diagnostic or schedule a technician.",
    "Service": "Recommended action: escalate to a supervisor and follow up with the customer within 24 hours.",
    "Others": "Recommended action: route to a general support queue for manual review.",
}

# Guardrail: every category must have a recommendation, and vice versa -
# catches the list drifting out of sync with categories.py.
assert set(RECOMMENDATIONS) == set(CATEGORIES), "RECOMMENDATIONS keys must exactly match categories.py"


def get_recommendation(complaint_text: str, category: str) -> str:
    """Returns a recommended action for a complaint. Tries the real
    RAG pipeline first; falls back to the static template below."""
    if gemini_client.is_configured():
        try:
            question = f"A customer filed this {category} complaint: \"{complaint_text}\". What should the support agent do?"
            result = rag_answer(question, top_k=2)
            return result["answer"]
        except Exception:
            # Missing/unreachable knowledge base, network error, bad
            # API key, rate limit, etc. - fall through to the
            # always-available template rather than erroring the
            # request.
            pass
    return RECOMMENDATIONS.get(category, RECOMMENDATIONS["Others"])


def ask_admin_chatbot(question: str, ticket_context: str = None) -> dict:
    """Powers POST /admin/chatbot/ask. Returns
    {"answer": str, "sources": [str,...], "used_rag": bool}."""
    if gemini_client.is_configured():
        try:
            result = rag_answer(question, extra_context=ticket_context, top_k=4)
            return {"answer": result["answer"], "sources": result["sources"], "used_rag": True}
        except Exception as e:
            return {
                "answer": (
                    "The AI chatbot hit an error talking to Gemini/Qdrant "
                    f"({e}). Falling back: try rephrasing, or check "
                    "docs/RAG_CHATBOT.md for setup/troubleshooting."
                ),
                "sources": [],
                "used_rag": False,
            }
    return {
        "answer": (
            "The AI chatbot isn't configured yet - set GEMINI_API_KEY "
            "(and optionally QDRANT_URL) in your .env, then run "
            "`python -m app.rag.knowledge_base` to index the SOP docs. "
            "See docs/RAG_CHATBOT.md."
        ),
        "sources": [],
        "used_rag": False,
    }

