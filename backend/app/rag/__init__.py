"""
RAG (Retrieval-Augmented Generation) pipeline for the Admin AI Chatbot
module (SRS 3.2): Gemini for embeddings + generation, Qdrant for
vector storage, a small markdown/PDF knowledge base of SOPs.

  gemini_client.py   - REST wrapper around the Gemini API
  vector_store.py     - Qdrant REST wrapper + in-memory fallback
  knowledge_base.py   - loads/chunks/indexes the SOP documents
  pipeline.py          - ties the above together into ask(question)

See docs/RAG_CHATBOT.md for the architecture and setup instructions,
and DECISIONS.md for why this stack (Gemini + Qdrant) was chosen.
"""
