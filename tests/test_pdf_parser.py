"""Unit tests for PyMuPDF parser and text cleaner."""

import unittest
from backend.app.rag.cleaner import clean_text, extract_snippet
from backend.app.rag.parser import parse_pdf_document, PDFParsingError
from tests.synthetic_pdf_generator import (
    create_valid_multipage_pdf,
    create_empty_pdf,
    create_scanned_image_pdf,
    create_encrypted_pdf,
    create_malformed_pdf,
)


class TestPDFParserAndCleaner(unittest.TestCase):
    """Test suite for PDF extraction, layout parsing, and cleaning logic."""

    def test_clean_text_normalizations(self):
        """Test NFKC unicode normalization, whitespace collapsing, and hyphenation repair."""
        raw = "The  academic   regu-\nlation stipulates that \x00attendance is required.\n\n\n\nSection 2."
        cleaned = clean_text(raw)

        # Hyphenation restored
        self.assertIn("regulation", cleaned)
        self.assertNotIn("regu-", cleaned)

        # Null bytes removed
        self.assertNotIn("\x00", cleaned)

        # Excess newlines collapsed
        self.assertNotIn("\n\n\n", cleaned)
        self.assertIn("\n\nSection 2.", cleaned)

    def test_extract_snippet(self):
        """Test snippet extraction with max_chars limit."""
        long_text = "A" * 300
        snippet = extract_snippet(long_text, max_chars=100)
        self.assertTrue(snippet.endswith("..."))
        self.assertLessEqual(len(snippet), 103)

    def test_parse_valid_multipage_pdf(self):
        """Test parsing a valid 3-page synthetic PDF with metadata and structural blocks."""
        pdf_bytes = create_valid_multipage_pdf()
        result = parse_pdf_document(pdf_bytes, filename="campus_guide.pdf")

        self.assertEqual(result["filename"], "campus_guide.pdf")
        self.assertEqual(result["total_pages"], 3)
        self.assertGreater(result["total_characters"], 100)
        self.assertGreater(result["total_words"], 20)
        self.assertFalse(result["is_empty"])
        self.assertFalse(result["has_scanned_pages"])
        self.assertFalse(result["needs_ocr_review"])

        # Check metadata
        self.assertEqual(result["doc_metadata"]["title"], "Synthetic University Guidelines 2026")

        # Check pages structure
        pages = result["pages"]
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertIn("Academic Regulations", pages[0]["text"])
        self.assertGreater(len(pages[0]["blocks"]), 0)

    def test_parse_empty_pdf(self):
        """Test that empty synthetic PDF is detected without crashing."""
        pdf_bytes = create_empty_pdf()
        result = parse_pdf_document(pdf_bytes, filename="empty_guide.pdf")

        self.assertEqual(result["total_pages"], 2)
        self.assertEqual(result["total_characters"], 0)
        self.assertEqual(result["total_words"], 0)
        self.assertTrue(result["is_empty"])

    def test_parse_scanned_image_pdf_flags_ocr_review(self):
        """Test that synthetic scanned/image PDF triggers needs_ocr_review flag."""
        pdf_bytes = create_scanned_image_pdf()
        result = parse_pdf_document(pdf_bytes, filename="scanned_notice.pdf")

        self.assertEqual(result["total_pages"], 1)
        self.assertTrue(result["has_scanned_pages"])
        self.assertTrue(result["needs_ocr_review"])
        self.assertTrue(result["pages"][0]["is_scanned"])
        self.assertTrue(result["pages"][0]["needs_ocr_review"])
        self.assertGreater(result["pages"][0]["image_count"], 0)

    def test_parse_encrypted_pdf_rejection(self):
        """Test that encrypted/password-protected PDFs raise PDFParsingError."""
        pdf_bytes = create_encrypted_pdf(password="secret")

        with self.assertRaises(PDFParsingError) as ctx:
            parse_pdf_document(pdf_bytes, filename="locked.pdf")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("password-protected or encrypted", ctx.exception.detail)

    def test_parse_malformed_pdf_rejection(self):
        """Test that malformed/corrupted PDFs raise PDFParsingError."""
        pdf_bytes = create_malformed_pdf()

        with self.assertRaises(PDFParsingError) as ctx:
            parse_pdf_document(pdf_bytes, filename="corrupt.pdf")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Corrupted or malformed", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()

