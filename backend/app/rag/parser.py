"""PyMuPDF document parser, layout extractor, and scanned PDF detection."""

from typing import Dict, Any, List
from fastapi import status
from backend.app.rag.cleaner import clean_text, extract_snippet
from backend.app.utils.file_validator import FileValidationError

try:
    import pymupdf as fitz
except ImportError:
    import fitz


class PDFParsingError(FileValidationError):
    """Exception raised when PDF parsing fails."""

    def __init__(self, detail: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT):
        super().__init__(detail=detail, status_code=status_code)


def parse_pdf_document(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Parse a PDF byte stream using PyMuPDF and extract page-level text, blocks, and metadata.

    Args:
        file_bytes: Raw binary bytes of the PDF.
        filename: Sanitized original filename.

    Returns:
        Structured dictionary containing document metadata, page objects, and quality flags.

    Raises:
        PDFParsingError: If PDF is malformed, corrupt, or encrypted.
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise PDFParsingError(f"Corrupted or malformed PDF document: {str(e)}")

    try:
        # Check for encryption / password-protection
        if doc.is_encrypted:
            raise PDFParsingError(
                "PDF document is password-protected or encrypted. Unencrypted documents are required.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        total_pages = doc.page_count
        if total_pages == 0:
            raise PDFParsingError(
                "PDF contains 0 pages.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        pages_data: List[Dict[str, Any]] = []
        total_chars = 0
        total_words = 0
        has_scanned_pages = False
        needs_ocr_review = False
        empty_page_count = 0

        # Extract document-level metadata safely
        meta = doc.metadata or {}
        doc_metadata = {
            "title": (meta.get("title") or "").strip(),
            "author": (meta.get("author") or "").strip(),
            "subject": (meta.get("subject") or "").strip(),
            "creator": (meta.get("creator") or "").strip(),
            "producer": (meta.get("producer") or "").strip(),
            "creation_date": meta.get("creationDate") or "",
            "modification_date": meta.get("modDate") or "",
        }

        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_num = page_idx + 1  # 1-indexed

            # Extract structural text blocks: (x0, y0, x1, y1, text, block_no, block_type)
            # block_type 0 = text, 1 = image
            raw_blocks = page.get_text("blocks")
            images = page.get_images()

            structural_blocks: List[Dict[str, Any]] = []
            page_text_pieces: List[str] = []

            for block in raw_blocks:
                # Text blocks have block[6] == 0
                if len(block) >= 7 and block[6] == 0:
                    raw_block_text = block[4]
                    cleaned_block_text = clean_text(raw_block_text)
                    if cleaned_block_text:
                        structural_blocks.append({
                            "block_number": block[5],
                            "bbox": [round(coord, 2) for coord in block[:4]],
                            "text": cleaned_block_text,
                        })
                        page_text_pieces.append(cleaned_block_text)

            combined_page_text = "\n\n".join(page_text_pieces).strip()
            cleaned_page_text = clean_text(combined_page_text)

            char_count = len(cleaned_page_text)
            word_count = len(cleaned_page_text.split()) if cleaned_page_text else 0

            # Empty Page Check
            is_empty = (char_count == 0)
            if is_empty:
                empty_page_count += 1

            # Scanned Content Check (Text < 50 chars but embedded images present)
            # Flagged as needs_ocr_review (No OCR is claimed or implemented in this phase)
            is_scanned = (char_count < 50 and len(images) > 0)
            page_needs_ocr = is_scanned

            if is_scanned:
                has_scanned_pages = True
                needs_ocr_review = True

            pages_data.append({
                "page_number": page_num,
                "text": cleaned_page_text,
                "snippet": extract_snippet(cleaned_page_text, max_chars=180),
                "char_count": char_count,
                "word_count": word_count,
                "is_empty": is_empty,
                "is_scanned": is_scanned,
                "needs_ocr_review": page_needs_ocr,
                "image_count": len(images),
                "blocks": structural_blocks,
            })

            total_chars += char_count
            total_words += word_count

        all_empty = (empty_page_count == total_pages)

        return {
            "filename": filename,
            "total_pages": total_pages,
            "total_characters": total_chars,
            "total_words": total_words,
            "is_empty": all_empty,
            "has_scanned_pages": has_scanned_pages,
            "needs_ocr_review": needs_ocr_review,
            "doc_metadata": doc_metadata,
            "pages": pages_data,
        }
    finally:
        doc.close()
