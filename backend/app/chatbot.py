"""
RAG chatbot recommendations - two entry points, two audiences:

  get_recommendation(complaint_text, category) -> str
      Used by /chatbot/recommend, the simple category-in/advice-out
      call the customer-facing homepage widget uses (and that the
      admin dashboard can also call for a quick per-ticket suggestion).
      Tries the real RAG pipeline first (BM25 retrieval + Gemini
      generation, see app/rag/pipeline.py); falls back to the template
      dict below if GEMINI_API_KEY isn't set, no knowledge base has
      been indexed yet, or the call fails for any reason. Same "never
      let an AI integration break the request" rule as app/classify.py
      and app/priority.py.

  ask_admin_chatbot(question, ticket_context=None) -> dict
      Used by /admin/chatbot/ask, the Admin AI Chatbot module (SRS
      3.2): free-form Q&A grounded in the indexed SOP documents
      (data/knowledge_base/). Returns which SOP sources were used.
      Falls back to a plain "AI chatbot isn't configured yet" message
      (not a fake answer) if RAG isn't available - see
      docs/RAG_CHATBOT.md for setup.

Retrieval: BM25 keyword search (pure Python, no API, always available)
with optional Gemini embedding queries fused via Reciprocal Rank
Fusion (hybrid mode). Generation: Gemini generateContent only.
See docs/DECISIONS.md Decision 30 and docs/RAG_CHATBOT.md.
"""
from .categories import CATEGORIES
from .rag import gemini_client
from .rag import groq_client
from .rag.pipeline import answer as rag_answer

RECOMMENDATIONS = {
    "Cards": (
        "Recommended action: verify whether the transaction was authorized. "
        "If fraudulent, initiate a chargeback dispute, issue a replacement card, "
        "and apply a provisional credit within 1-5 business days per Regulation Z."
    ),
    "Accounts": (
        "Recommended action: check the account hold or freeze reason. "
        "If an unauthorized ACH or wire is involved, file a dispute and apply a "
        "provisional credit within 10 business days per EFTA. Reset credentials "
        "and issue a new debit card if the account was compromised."
    ),
    "Loans": (
        "Recommended action: pull the full payment history and compare to the loan "
        "agreement. If a servicer error is found, issue a written correction within "
        "7 business days (RESPA). For modification requests, acknowledge within "
        "5 days and decide within 30 days of a complete application (Regulation X)."
    ),
    "Collections & Credit reporting": (
        "Recommended action: verify the account data against internal records. "
        "If inaccurate, submit a Metro 2 correction to the bureau within 30 days "
        "(FCRA 623). If a collector is harassing the customer, issue a cease-contact "
        "letter and log a potential FDCPA violation for Compliance."
    ),
    "Other banking": (
        "Recommended action: identify whether the complaint involves a fee, "
        "account opening/closure, or another service issue. Check Regulation DD "
        "disclosure requirements for fee complaints. Escalate to a supervisor "
        "if the customer requests it, and provide the CFPB complaint portal "
        "address if unresolved after escalation."
    ),
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
    return RECOMMENDATIONS.get(category, RECOMMENDATIONS["Other banking"])


def ask_admin_chatbot(question: str, ticket_context: str = None) -> dict:
    """Powers POST /admin/chatbot/ask. Returns
    {"answer": str, "sources": [str,...], "used_rag": bool}.
    Uses Groq for generation if GROQ_API_KEY is set, Gemini otherwise."""
    if groq_client.is_configured() or gemini_client.is_configured():
        try:
            result = rag_answer(question, extra_context=ticket_context, top_k=4)
            return {"answer": result["answer"], "sources": result["sources"], "used_rag": True}
        except Exception as e:
            return {
                "answer": (
                    f"The AI chatbot hit an error generating a response ({e}). "
                    "BM25 keyword search is still available — try rephrasing "
                    "your question, or check docs/RAG_CHATBOT.md for "
                    "setup/troubleshooting."
                ),
                "sources": [],
                "used_rag": False,
            }
    return {
        "answer": (
            "The AI chatbot isn't configured yet — set GROQ_API_KEY "
            "(recommended) or GEMINI_API_KEY in your .env, then run "
            "`python -m app.rag.knowledge_base` to index the SOP docs. "
            "BM25 keyword search handles retrieval — no extra keys needed. "
            "See docs/RAG_CHATBOT.md."
        ),
        "sources": [],
        "used_rag": False,
    }

