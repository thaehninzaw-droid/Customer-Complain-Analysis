"""
Loads the SOP / playbook knowledge base (SRS 3.2: "The AI chatbot
indexes reference PDFs containing standard operating procedures (SOPs)
or solution guides"), chunks it, embeds each chunk via Gemini, and
upserts into the vector store (Qdrant or the in-memory fallback - see
vector_store.py).

Reads every .md/.txt and .pdf file in data/knowledge_base/ - drop a
real SOP PDF in that folder and it gets picked up automatically next
time you run the indexer, no code changes needed. PDF text extraction
uses pypdf (already in requirements.txt via the pdf skill's tooling).

Run the indexer with:
    python -m app.rag.knowledge_base
(requires GEMINI_API_KEY set in backend/.env - see docs/RAG_CHATBOT.md
and docs/GETTING_STARTED.md Step 11)
"""
import sys
from pathlib import Path

# Load .env BEFORE importing gemini_client/vector_store, which read
# GEMINI_API_KEY and QDRANT_URL at import time via os.getenv().
# Without this, running `python -m app.rag.knowledge_base` directly
# from the command line finds no API key even if backend/.env is
# properly configured - the dotenv loader in app/db.py only fires when
# the FastAPI server starts, not when standalone scripts are run.
# See docs/DECISIONS.md #26.
_this_dir = Path(__file__).resolve().parent
for _candidate in [
    _this_dir.parent.parent / ".env",        # backend/.env (most likely)
    _this_dir.parent.parent.parent / ".env",  # repo-root/.env (fallback)
]:
    if _candidate.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=_candidate)
        except ImportError:
            pass
        break

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from app.rag import gemini_client, vector_store  # noqa: E402

KB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_base"

CHUNK_SIZE = 800   # characters
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
        if path.suffix.lower() in (".md", ".txt"):
            docs.append({"source": path.name, "text": path.read_text(encoding="utf-8")})
        elif path.suffix.lower() == ".pdf":
            try:
                docs.append({"source": path.name, "text": _read_pdf(path)})
            except Exception as e:
                print(f"[knowledge_base] Skipping {path.name} - couldn't extract text: {e}")
    return docs


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """Simple fixed-size sliding-window chunker. Splits on paragraph
    boundaries where possible so chunks don't cut mid-sentence as
    often; good enough for a knowledge base of a few short SOP docs -
    swap for a smarter splitter if the KB grows a lot."""
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
                # A single paragraph longer than chunk_size - hard-split it.
                for i in range(0, len(para), chunk_size - overlap):
                    chunks.append(para[i:i + chunk_size])
                current = ""
    if current:
        chunks.append(current)
    return chunks


def build_index() -> int:
    """Loads every KB document, chunks it, embeds each chunk, and
    upserts into the configured vector store. Returns the number of
    chunks indexed. Requires GEMINI_API_KEY - raises GeminiError if
    not configured (see app/rag/gemini_client.py)."""
    documents = load_documents()
    all_chunks = []  # list of (source, chunk_text)
    for doc in documents:
        for chunk in chunk_text(doc["text"]):
            all_chunks.append((doc["source"], chunk))

    if not all_chunks:
        print(f"[knowledge_base] No documents found in {KB_DIR}")
        return 0

    texts = [c[1] for c in all_chunks]
    vectors = gemini_client.embed_texts(texts, task_type="RETRIEVAL_DOCUMENT")

    vector_store.ensure_collection(vector_size=len(vectors[0]))
    points = [
        {
            "id": i,
            "vector": vectors[i],
            "payload": {"text": texts[i], "source": all_chunks[i][0]},
        }
        for i in range(len(all_chunks))
    ]
    vector_store.upsert(points)
    print(f"[knowledge_base] Indexed {len(points)} chunks from {len(documents)} documents "
          f"({'Qdrant' if vector_store.is_configured() else 'in-memory fallback'}).")
    return len(points)


if __name__ == "__main__":
    build_index()
