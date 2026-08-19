"""
Indexes the SOP knowledge base using BM25 keyword search.

No Gemini API calls needed for indexing — chunks are saved to a JSON
file and searched at query time using pure-Python BM25. Gemini is
still used for generating the final answer, just not for embedding.

This replaced Gemini embeddings + Qdrant after hitting the free tier's
1000/day embedding quota on large document sets. See docs/DECISIONS.md.

Usage:
    python -m app.rag.knowledge_base           # index/re-index
    python -m app.rag.knowledge_base --clear   # wipe index and Qdrant

Reads every .md, .txt, and .pdf file in data/knowledge_base/.
Drop new SOP files there and re-run — no code changes needed.
"""
import argparse
import sys
from pathlib import Path

# Load .env before any app import so GEMINI_API_KEY etc. are available
# when the server starts this as a standalone module.
_this_dir = Path(__file__).resolve().parent
for _cand in [_this_dir.parent.parent / ".env",
              _this_dir.parent.parent.parent / ".env"]:
    if _cand.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=_cand)
        except ImportError:
            pass
        break

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from app.rag import vector_store  # noqa: E402 (used for --clear only)
from app.rag.bm25_store import BM25Index, INDEX_FILE  # noqa: E402

KB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_base"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_documents() -> list:
    """Returns [{"source": filename, "text": full_text}, ...]"""
    docs = []
    if not KB_DIR.exists():
        return docs
    for path in sorted(KB_DIR.iterdir()):
        if path.name.startswith("."):
            continue  # skip hidden files (.bm25_index.json etc.)
        if path.suffix.lower() in (".md", ".txt"):
            docs.append({"source": path.name,
                          "text": path.read_text(encoding="utf-8", errors="replace")})
        elif path.suffix.lower() == ".pdf":
            try:
                docs.append({"source": path.name, "text": _read_pdf(path)})
            except Exception as e:
                print(f"[knowledge_base] Skipping {path.name}: {e}")
    return docs


def chunk_text(text: str,
               chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> list:
    """Paragraph-aware sliding-window chunker."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) <= chunk_size:
                current = para
            else:
                for i in range(0, len(para), chunk_size - overlap):
                    chunks.append(para[i:i + chunk_size])
                current = ""
    if current:
        chunks.append(current)
    return chunks


def build_index() -> int:
    """Chunks all KB documents, builds a BM25 index, saves to disk.
    No API calls. Returns the number of chunks indexed."""
    documents = load_documents()
    if not documents:
        print(f"[knowledge_base] No documents found in {KB_DIR}")
        return 0

    all_chunks = []
    for doc in documents:
        for chunk in chunk_text(doc["text"]):
            all_chunks.append({"text": chunk, "source": doc["source"]})

    print(f"[knowledge_base] {len(documents)} document(s) → {len(all_chunks)} chunks")

    index = BM25Index()
    index.fit(all_chunks)
    index.save(INDEX_FILE)

    from app.rag import bm25_store
    bm25_store.clear_cache()  # force reload on next request

    print(f"[knowledge_base] BM25 index saved → {INDEX_FILE.name}")
    print(f"[knowledge_base] Ready. No API calls needed — Gemini is only")
    print(f"                 used when an admin asks a question.")
    return len(all_chunks)


def clear_index() -> None:
    """Deletes the BM25 index file and the Qdrant collection (if configured)."""
    deleted_any = False
    if INDEX_FILE.exists():
        INDEX_FILE.unlink()
        from app.rag import bm25_store
        bm25_store.clear_cache()
        print(f"[knowledge_base] Deleted BM25 index: {INDEX_FILE.name}")
        deleted_any = True

    if vector_store.is_configured():
        try:
            _delete_qdrant_collection()
            print("[knowledge_base] Deleted Qdrant collection.")
            deleted_any = True
        except Exception as e:
            print(f"[knowledge_base] Could not delete Qdrant collection: {e}")

    if not deleted_any:
        print("[knowledge_base] Nothing to clear.")


def _delete_qdrant_collection() -> None:
    """Drops the Qdrant collection so it can be rebuilt from scratch."""
    import os
    import requests as req
    url = f"{os.getenv('QDRANT_URL')}/collections/{vector_store.COLLECTION_NAME}"
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("QDRANT_API_KEY")
    if api_key:
        headers["api-key"] = api_key
    resp = req.delete(url, headers=headers, timeout=15)
    if resp.status_code not in (200, 404):
        resp.raise_for_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true",
                        help="Clear the existing index and Qdrant collection, then exit")
    args = parser.parse_args()

    if args.clear:
        clear_index()
    else:
        build_index()
