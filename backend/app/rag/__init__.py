"""
RAG (Retrieval-Augmented Generation) pipeline for the Admin AI Chatbot
module (SRS 3.2).

Retrieval: hybrid BM25 + optional Gemini query embeddings (RRF fusion).
Generation: Gemini generateContent.

  bm25_store.py        - pure-Python Okapi BM25 index (JSON persistence)
  hybrid_retriever.py  - HybridRetriever: BM25 + embeddings + RRF fusion
  gemini_client.py     - REST wrapper for Gemini generate + embed endpoints
  vector_store.py      - Qdrant REST wrapper + in-memory cosine fallback
                         (used by hybrid_retriever for embedding path)
  knowledge_base.py    - loads/chunks/indexes SOP docs into BM25 index
  pipeline.py          - ties retrieval + generation into answer(question)

See docs/RAG_CHATBOT.md for the full architecture and setup instructions.
See docs/DECISIONS.md Decision 30 for the BM25 pivot and hybrid design.
"""
