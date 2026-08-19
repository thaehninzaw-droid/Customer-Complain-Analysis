from app.rag.knowledge_base import chunk_text, load_documents


def test_load_documents_finds_all_sop_files():
    docs = load_documents()
    sources = {d["source"] for d in docs}
    expected_files = {
        "Billing Complaints.md",
        "Service Complaints.md",
        "Technical Complaints.md",
        "Other Complaints.md",
        "Financial Complaints.md",
    }
    assert sources == expected_files


def test_chunk_text_respects_chunk_size():
    text = "\n\n".join([f"Paragraph {i}. " + ("word " * 30) for i in range(10)])
    chunks = chunk_text(text, chunk_size=400, overlap=50)
    assert len(chunks) > 1
    # allow a little slack over chunk_size for the hard-split path
    assert all(len(c) <= 450 for c in chunks)


def test_chunk_text_handles_short_text():
    assert chunk_text("Just one short paragraph.") == ["Just one short paragraph."]


def test_chunk_text_handles_empty_text():
    assert chunk_text("") == []
