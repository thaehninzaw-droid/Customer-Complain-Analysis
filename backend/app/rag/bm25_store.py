"""
BM25 keyword-search index for the RAG knowledge base.

Replaces Gemini embeddings + Qdrant vector search entirely.
No API calls, no rate limits, instant indexing. The index is saved
as a JSON file and loaded on startup. Retrieval quality is very good
for SOP-style documents where exact keywords matter (e.g. "billing",
"payment", "outage") — which is exactly what this knowledge base is.

BM25 (Okapi BM25) is the industry standard for keyword retrieval
and what ElasticSearch/Solr use internally. The math:
    score(q, d) = Σ IDF(t) × tf(t,d) × (k1+1) / (tf(t,d) + k1×(1-b+b×|d|/avgdl))
where k1 controls term-frequency saturation and b controls length
normalisation. Default values (k1=1.5, b=0.75) work well in practice.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path
from threading import Lock

INDEX_FILE = (
    Path(__file__).resolve().parent.parent.parent  # backend/
    / "data" / "knowledge_base" / ".bm25_index.json"
)

_instance = None
_lock = Lock()


def _tokenize(text: str) -> list:
    """Lowercase alphanumeric tokenizer - fast and sufficient for SOP docs."""
    return re.findall(r'\b[a-z0-9]+\b', text.lower())


class BM25Index:
    """Serialisable BM25 index over a list of text chunks."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.chunks: list = []    # [{"text": str, "source": str}, ...]
        self._tokenized: list = []
        self._doc_freqs: dict = {}
        self._idf: dict = {}
        self._avgdl: float = 0.0

    # ---------------------------------------------------------------- build --
    def fit(self, chunks: list) -> None:
        """Build the index from a list of chunk dicts (must have 'text' key)."""
        self.chunks = chunks
        self._tokenized = [_tokenize(c["text"]) for c in chunks]
        N = len(chunks)
        total_len = sum(len(t) for t in self._tokenized)
        self._avgdl = total_len / max(N, 1)

        # Document frequency: how many docs contain each term
        self._doc_freqs = {}
        for tokens in self._tokenized:
            for term in set(tokens):
                self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1

        # IDF (log-smoothed so rare terms score highest)
        self._idf = {
            term: math.log((N - df + 0.5) / (df + 0.5) + 1)
            for term, df in self._doc_freqs.items()
        }

    # --------------------------------------------------------------- search --
    def search(self, query: str, top_k: int = 5) -> list:
        """Return up to top_k chunks ordered by BM25 score, highest first.
        Each result is {"score": float, "payload": {"text": str, "source": str}}."""
        if not self.chunks:
            return []
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        scores = []
        for i, tokens in enumerate(self._tokenized):
            tf = Counter(tokens)
            dl = len(tokens)
            score = 0.0
            for term in query_terms:
                if term not in self._idf:
                    continue
                tf_val = tf.get(term, 0)
                num = tf_val * (self.k1 + 1)
                den = tf_val + self.k1 * (1 - self.b + self.b * dl / max(self._avgdl, 1))
                score += self._idf[term] * num / max(den, 1e-9)
            if score > 0:
                scores.append((score, i))

        scores.sort(reverse=True)
        return [
            {"score": round(s, 4), "payload": self.chunks[idx]}
            for s, idx in scores[:top_k]
        ]

    # --------------------------------------------------------- persistence --
    def save(self, path: Path = INDEX_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "k1": self.k1, "b": self.b,
            "chunks": self.chunks,
            "tokenized": self._tokenized,
            "doc_freqs": self._doc_freqs,
            "idf": self._idf,
            "avgdl": self._avgdl,
        }), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = INDEX_FILE) -> "BM25Index":
        data = json.loads(path.read_text(encoding="utf-8"))
        idx = cls(k1=data["k1"], b=data["b"])
        idx.chunks = data["chunks"]
        idx._tokenized = data["tokenized"]
        idx._doc_freqs = data["doc_freqs"]
        idx._idf = data["idf"]
        idx._avgdl = data["avgdl"]
        return idx

    def __len__(self) -> int:
        return len(self.chunks)


# ------------------------------------------------------------------ module API

def is_indexed() -> bool:
    return INDEX_FILE.exists()


def get_index() -> BM25Index | None:
    """Returns the cached BM25 index, loading it on first call.
    Returns None if the index file doesn't exist yet."""
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        if not INDEX_FILE.exists():
            return None
        try:
            _instance = BM25Index.load(INDEX_FILE)
            return _instance
        except Exception as e:
            print(f"[bm25] Could not load index: {e}")
            return None


def clear_cache() -> None:
    """Force the next call to get_index() to reload from disk."""
    global _instance
    _instance = None
