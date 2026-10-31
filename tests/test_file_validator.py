"""Unit tests for file validator and security functions."""

import unittest
import io
from fastapi import UploadFile
from backend.app.utils.file_validator import (
    sanitize_filename,
    read_and_validate_upload,
    FileValidationError,
    PDF_MAGIC_BYTES,
)
from tests.synthetic_pdf_generator import create_valid_multipage_pdf, create_fake_signature_pdf


class TestFileValidator(unittest.IsolatedAsyncioTestCase):
    """Test suite for filename sanitization, bounded reading, and file validation."""

    def test_sanitize_filename_traversal_and_bad_chars(self):
        """Test stripping of directory traversal characters and special symbols."""
        # Path traversal sequences - extracts safe basename
        self.assertEqual(sanitize_filename("../../etc/passwd.pdf"), "passwd.pdf")
        self.assertEqual(sanitize_filename("..\\..\\windows\\system32.pdf"), "system32.pdf")

        # Dangerous characters and whitespace
        dirty_name = "Campus  Policy *?<>:;\"|!#$.pdf"
        clean_name = sanitize_filename(dirty_name)
        self.assertNotIn("*", clean_name)
        self.assertNotIn("?", clean_name)
        self.assertNotIn("<", clean_name)
        self.assertTrue(clean_name.endswith(".pdf"))

        # Empty filename fallback
        self.assertEqual(sanitize_filename(""), "unnamed_document.pdf")
        self.assertEqual(sanitize_filename(None), "unnamed_document.pdf")

    async def test_read_and_validate_upload_success(self):
        """Test reading and validating a legitimate PDF file."""
        pdf_bytes = create_valid_multipage_pdf()
        file_obj = io.BytesIO(pdf_bytes)
        upload = UploadFile(filename="academic_handbook.pdf", file=file_obj, headers={"content-type": "application/pdf"})

        data, sha256_hash, sanitized_name = await read_and_validate_upload(upload)
        self.assertEqual(data, pdf_bytes)
        self.assertEqual(sanitized_name, "academic_handbook.pdf")
        self.assertIsInstance(sha256_hash, str)
        self.assertEqual(len(sha256_hash), 64)  # 64-char hex SHA-256

    async def test_rejection_of_invalid_extension(self):
        """Test that non-PDF extensions are rejected."""
        pdf_bytes = create_valid_multipage_pdf()
        file_obj = io.BytesIO(pdf_bytes)
        upload = UploadFile(filename="script.exe", file=file_obj, headers={"content-type": "application/pdf"})

        with self.assertRaises(FileValidationError) as ctx:
            await read_and_validate_upload(upload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Unsupported file extension", ctx.exception.detail)

    async def test_rejection_of_invalid_magic_bytes(self):
        """Test that files lacking the %PDF- magic signature are rejected."""
        fake_bytes = create_fake_signature_pdf()
        file_obj = io.BytesIO(fake_bytes)
        upload = UploadFile(filename="spoofed.pdf", file=file_obj, headers={"content-type": "application/pdf"})

        with self.assertRaises(FileValidationError) as ctx:
            await read_and_validate_upload(upload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("File header signature check failed", ctx.exception.detail)

    async def test_rejection_of_empty_file(self):
        """Test that 0-byte uploads are rejected."""
        file_obj = io.BytesIO(b"")
        upload = UploadFile(filename="empty.pdf", file=file_obj, headers={"content-type": "application/pdf"})

        with self.assertRaises(FileValidationError) as ctx:
            await read_and_validate_upload(upload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Uploaded file is empty", ctx.exception.detail)

    async def test_rejection_of_oversized_file(self):
        """Test bounded memory reading rejects files exceeding size limit."""
        pdf_bytes = create_valid_multipage_pdf()
        file_obj = io.BytesIO(pdf_bytes)
        upload = UploadFile(filename="large.pdf", file=file_obj, headers={"content-type": "application/pdf"})

        with self.assertRaises(FileValidationError) as ctx:
            await read_and_validate_upload(upload, max_size_bytes=200)
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("File size exceeds maximum allowed limit", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
