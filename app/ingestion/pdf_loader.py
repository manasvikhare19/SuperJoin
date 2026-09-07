import hashlib
from pathlib import Path
from typing import Dict, Any, List, Union
import pymupdf
from app.ingestion.cleaner import clean_extracted_text

def compute_sha256(file_input: Union[str, Path, bytes]) -> str:
    hasher = hashlib.sha256()
    if isinstance(file_input, (str, Path)):
        with open(file_input, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
    elif isinstance(file_input, bytes):
        hasher.update(file_input)
    else:
        raise ValueError("Unsupported input type for SHA256 computation")
    return hasher.hexdigest()

def extract_pdf_pages(file_input: Union[str, Path, bytes]) -> Dict[str, Any]:
    """
    Extracts text page by page from a PDF using PyMuPDF.
    Returns:
        {
            "file_hash": str,
            "total_pages": int,
            "pages": [
                {
                    "page_number": int (1-indexed),
                    "text": str,
                    "char_count": int
                }, ...
            ]
        }
    """
    file_hash = compute_sha256(file_input)

    if isinstance(file_input, bytes):
        doc = pymupdf.open(stream=file_input, filetype="pdf")
    else:
        doc = pymupdf.open(str(file_input))

    total_pages = len(doc)
    pages: List[Dict[str, Any]] = []

    for idx in range(total_pages):
        page = doc[idx]
        raw_text = page.get_text()
        cleaned = clean_extracted_text(raw_text)
        pages.append({
            "page_number": idx + 1,
            "text": cleaned,
            "char_count": len(cleaned)
        })

    doc.close()

    return {
        "file_hash": file_hash,
        "total_pages": total_pages,
        "pages": pages
    }
