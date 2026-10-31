"""Unit tests for DocumentService: storage, SQLite registry, deduplication, and deletion."""

import os
import shutil
import tempfile
import unittest
import hashlib
from concurrent.futures import ThreadPoolExecutor
from backend.app.services.document_service import DocumentService, atomic_write
from tests.synthetic_pdf_generator import create_valid_multipage_pdf, create_scanned_image_pdf


class TestDocumentService(unittest.TestCase):
    """Test suite for DocumentService storage, SQLite persistence, and lifecycle operations."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="unimind_test_storage_")
        self.raw_dir = os.path.join(self.test_dir, "raw")
        self.processed_dir = os.path.join(self.test_dir, "processed")
        self.db_path = os.path.join(self.test_dir, "test_unimind.db")

        # Instantiate service with isolated temporary paths
        self.service = DocumentService(db_path=self.db_path)
        self.service.raw_dir = self.raw_dir
        self.service.processed_dir = self.processed_dir
        self.service._init_storage()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_write(self):
        """Test atomic file writing creates destination file without leaving .tmp files."""
        dest_file = os.path.join(self.test_dir, "atomic_sample.txt")
        atomic_write(dest_file, "Sample atomic content")

        self.assertTrue(os.path.exists(dest_file))
        with open(dest_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "Sample atomic content")

        # Verify no temporary files remain in directory
        all_files = os.listdir(self.test_dir)
        self.assertEqual(len([f for f in all_files if ".tmp_" in f]), 0)

    def test_ingest_document_lifecycle(self):
        """Test full document ingestion: raw file, processed JSON, and SQLite registry."""
        pdf_bytes = create_valid_multipage_pdf()
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        result = self.service.ingest_document(
            file_bytes=pdf_bytes,
            filename="academic_calendar.pdf",
            file_hash=file_hash,
            department="Academics",
            category="Calendar",
        )

        doc_id = result["doc_id"]
        self.assertIsNotNone(doc_id)
        self.assertEqual(result["status"], "PROCESSED")
        self.assertEqual(result["total_pages"], 3)
        self.assertEqual(result["department"], "Academics")
        self.assertFalse(result["is_duplicate"])

        # Verify no local filesystem paths are exposed in the result
        self.assertNotIn("raw_file_path", result)
        self.assertNotIn("processed_file_path", result)

        # Verify raw file and processed file exist on disk in isolated dirs
        raw_file = os.path.join(self.raw_dir, f"{doc_id}.pdf")
        processed_file = os.path.join(self.processed_dir, f"{doc_id}.json")
        self.assertTrue(os.path.exists(raw_file))
        self.assertTrue(os.path.exists(processed_file))

    def test_duplicate_upload_handling(self):
        """Test uploading identical PDF returns existing record without redundant disk storage."""
        pdf_bytes = create_valid_multipage_pdf()
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # First upload
        first = self.service.ingest_document(
            file_bytes=pdf_bytes,
            filename="handbook_v1.pdf",
            file_hash=file_hash,
            department="Academics",
            category="Policy",
        )
        self.assertFalse(first["is_duplicate"])

        # Second upload with identical hash
        second = self.service.ingest_document(
            file_bytes=pdf_bytes,
            filename="handbook_v2.pdf",
            file_hash=file_hash,
            department="Academics",
            category="Policy",
        )
        self.assertTrue(second["is_duplicate"])
        self.assertEqual(second["doc_id"], first["doc_id"])
        self.assertEqual(second["file_hash_sha256"], first["file_hash_sha256"])

        # Ensure only 1 raw file exists in raw_dir
        raw_files = os.listdir(self.raw_dir)
        self.assertEqual(len(raw_files), 1)

    def test_list_and_filter_documents(self):
        """Test listing documents and filtering by department."""
        pdf_bytes = create_valid_multipage_pdf()
        h1 = hashlib.sha256(pdf_bytes).hexdigest()

        self.service.ingest_document(
            file_bytes=pdf_bytes,
            filename="policy_a.pdf",
            file_hash=h1,
            department="Admissions",
            category="Policy",
        )

        pdf_bytes2 = create_scanned_image_pdf()
        h2 = hashlib.sha256(pdf_bytes2).hexdigest()

        self.service.ingest_document(
            file_bytes=pdf_bytes2,
            filename="notice_b.pdf",
            file_hash=h2,
            department="Hostel",
            category="Notice",
        )

        all_docs = self.service.list_documents()
        self.assertEqual(len(all_docs), 2)

        # Filter by department
        admissions_docs = self.service.list_documents(department="Admissions")
        self.assertEqual(len(admissions_docs), 1)
        self.assertEqual(admissions_docs[0]["department"], "Admissions")

        # Verify no filesystem paths are in listed records
        for d in all_docs:
            self.assertNotIn("raw_file_path", d)
            self.assertNotIn("processed_file_path", d)

    def test_safe_document_deletion(self):
        """Test deleting document cleans up raw PDF, processed JSON, and SQLite record."""
        pdf_bytes = create_valid_multipage_pdf()
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        result = self.service.ingest_document(
            file_bytes=pdf_bytes,
            filename="to_delete.pdf",
            file_hash=file_hash,
            department="Library",
            category="Rules",
        )
        doc_id = result["doc_id"]
        raw_file = os.path.join(self.raw_dir, f"{doc_id}.pdf")
        processed_file = os.path.join(self.processed_dir, f"{doc_id}.json")

        self.assertTrue(os.path.exists(raw_file))
        self.assertTrue(os.path.exists(processed_file))

        # Perform deletion
        deleted = self.service.delete_document(doc_id)
        self.assertTrue(deleted)

        # Files and record should no longer exist
        self.assertFalse(os.path.exists(raw_file))
        self.assertFalse(os.path.exists(processed_file))
        self.assertIsNone(self.service.get_document_by_id(doc_id))

        # Subsequent deletion should return False
        self.assertFalse(self.service.delete_document(doc_id))

    def test_concurrent_upload_integrity(self):
        """Test registry integrity when multiple uploads occur in parallel threads."""
        def upload_synthetic_doc(idx: int):
            # Create unique bytes per thread by tweaking metadata
            doc_bytes = create_valid_multipage_pdf() + f"//thread_{idx}".encode()
            f_hash = hashlib.sha256(doc_bytes).hexdigest()
            return self.service.ingest_document(
                file_bytes=doc_bytes,
                filename=f"concurrent_doc_{idx}.pdf",
                file_hash=f_hash,
                department=f"Dept_{idx}",
                category="General",
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(upload_synthetic_doc, i) for i in range(4)]
            results = [f.result() for f in futures]

        self.assertEqual(len(results), 4)
        doc_ids = {r["doc_id"] for r in results}
        self.assertEqual(len(doc_ids), 4)

        all_docs = self.service.list_documents()
        self.assertEqual(len(all_docs), 4)


if __name__ == "__main__":
    unittest.main()

