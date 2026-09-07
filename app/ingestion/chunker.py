import hashlib
from typing import List, Dict, Any
from app.database.models import ChunkRecord
from app.config import CHUNK_TARGET_WORDS

def chunk_pdf_pages(
    pages: List[Dict[str, Any]],
    document_id: int,
    target_words: int = CHUNK_TARGET_WORDS
) -> List[ChunkRecord]:
    """
    Chunks extracted PDF pages semantically, respecting page boundaries and paragraphs.
    Every chunk records document_id, chunk_index, page_start, page_end, and text.
    """
    chunks: List[ChunkRecord] = []
    current_words: List[str] = []
    current_text_blocks: List[str] = []
    page_start = None
    page_end = None
    chunk_index = 0

    for p in pages:
        p_num = p["page_number"]
        p_text = p["text"]
        if not p_text.strip():
            continue

        paragraphs = [para.strip() for para in p_text.split("\n\n") if para.strip()]
        if not paragraphs:
            paragraphs = [p_text.strip()]

        for para in paragraphs:
            para_words = para.split()
            if not para_words:
                continue

            if page_start is None:
                page_start = p_num
            page_end = p_num

            current_text_blocks.append(para)
            current_words.extend(para_words)

            # Check if chunk reached target size
            if len(current_words) >= target_words:
                chunk_text = "\n\n".join(current_text_blocks)
                chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                chunks.append(
                    ChunkRecord(
                        document_id=document_id,
                        chunk_index=chunk_index,
                        page_start=page_start,
                        page_end=page_end,
                        text=chunk_text,
                        chunk_hash=chunk_hash
                    )
                )
                chunk_index += 1
                current_words = []
                current_text_blocks = []
                page_start = None
                page_end = None

    # Flush remaining text
    if current_text_blocks:
        chunk_text = "\n\n".join(current_text_blocks)
        chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
        chunks.append(
            ChunkRecord(
                document_id=document_id,
                chunk_index=chunk_index,
                page_start=page_start or 1,
                page_end=page_end or page_start or 1,
                text=chunk_text,
                chunk_hash=chunk_hash
            )
        )

    return chunks
