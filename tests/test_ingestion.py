import pytest
from pathlib import Path
from app.ingestion.cleaner import clean_extracted_text
from app.ingestion.pdf_loader import compute_sha256, extract_pdf_pages
from app.ingestion.chunker import chunk_pdf_pages

def test_clean_extracted_text_preserves_financials():
    raw = "Rev enue from opera- \n tions stood at  \u20b98,765 crore   (YoY: 12.7%)."
    cleaned = clean_extracted_text(raw)
    assert "₹8,765 crore" in cleaned or "8,765 crore" in cleaned
    assert "operations" in cleaned
    assert "12.7%" in cleaned

def test_compute_sha256():
    sample_bytes = b"SuperJoin Fact Knowledge Layer Test Bytes"
    hash1 = compute_sha256(sample_bytes)
    hash2 = compute_sha256(sample_bytes)
    assert hash1 == hash2
    assert len(hash1) == 64

def test_pdf_extraction_starter_dataset():
    pdf_path = Path("starter-datasets/delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf")
    if not pdf_path.exists():
        pytest.skip("Starter dataset file not found at expected path")

    res = extract_pdf_pages(pdf_path)
    assert res["total_pages"] == 27
    assert len(res["pages"]) == 27
    assert res["pages"][0]["page_number"] == 1
    assert len(res["file_hash"]) == 64

    # Test chunking
    chunks = chunk_pdf_pages(res["pages"], document_id=1, target_words=200)
    assert len(chunks) > 0
    assert chunks[0].page_start >= 1
    assert chunks[0].page_end >= chunks[0].page_start
    assert len(chunks[0].chunk_hash) == 64
