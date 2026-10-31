"""Synthetic PDF test fixture generators.

Uses synthetic data only. No real institutional documents or proprietary policies.
"""

import io
from typing import Dict
from PIL import Image

try:
    import pymupdf as fitz
except ImportError:
    import fitz


def create_valid_multipage_pdf() -> bytes:
    """Generate a valid synthetic 3-page university campus information guide."""
    doc = fitz.open()

    # Page 1: Academic Policies
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text(
        (50, 70),
        "Synthetic University - Academic Regulations\n\n"
        "1. Attendance Guidelines\n"
        "Students are expected to maintain at least 75% attendance in all scheduled courses.\n"
        "Absences must be officially communicated to the respective department head within 48 hours.\n\n"
        "2. Examination Rules\n"
        "Students must present their institutional identity card at the entry gate of the examination hall.",
        fontsize=11,
    )

    # Page 2: Campus Facilities
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text(
        (50, 70),
        "Synthetic University - Campus Facilities Guide\n\n"
        "1. Central Library\n"
        "The central library operates from 08:00 AM to 10:00 PM on weekdays.\n"
        "A collection of digital journals and reference materials is accessible online.\n\n"
        "2. Sports Complex\n"
        "The indoor sports arena is available to all registered students during regular term sessions.",
        fontsize=11,
    )

    # Page 3: Transportation Schedule
    page3 = doc.new_page(width=595, height=842)
    page3.insert_text(
        (50, 70),
        "Synthetic University - Campus Transportation\n\n"
        "Shuttle Route A: Departs central pavilion every 30 minutes from 07:30 AM.\n"
        "Shuttle Route B: Connects the residential dormitories to the science complex.\n"
        "Bicycle parking stands are situated adjacent to all primary lecture halls.",
        fontsize=11,
    )

    doc.set_metadata({
        "title": "Synthetic University Guidelines 2026",
        "author": "Antigravity Engineering Mock",
        "subject": "Campus Policies Mock",
    })

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_empty_pdf() -> bytes:
    """Generate a synthetic 2-page PDF with blank pages (no text)."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.new_page(width=595, height=842)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_scanned_image_pdf() -> bytes:
    """Generate a synthetic 1-page PDF containing an embedded image and < 50 characters of text.

    Triggers the scanned PDF detection heuristic (needs_ocr_review).
    """
    img = Image.new("RGB", (120, 120), color=(50, 100, 150))
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Less than 50 chars of text
    page.insert_text((50, 50), "Notice Scan", fontsize=10)
    page.insert_image(fitz.Rect(50, 100, 250, 300), stream=img_bytes)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_encrypted_pdf(password: str = "secure_pass_123") -> bytes:
    """Generate a password-protected/encrypted synthetic PDF."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 70), "Confidential Synthetic Document", fontsize=12)
    pdf_bytes = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw=password,
        owner_pw=password,
    )
    doc.close()
    return pdf_bytes


def create_malformed_pdf() -> bytes:
    """Generate corrupted bytes starting with %PDF- header but broken body."""
    return b"%PDF-1.4\nCorrupted content without xref table or valid dictionary objects..."


def create_fake_signature_pdf() -> bytes:
    """Generate a file with non-PDF header bytes."""
    return b"NOT_A_VALID_PDF_HEADER_JUST_RANDOM_TEXT_DATA"

