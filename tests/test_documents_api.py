"""Integration tests for Document Ingestion and Management API endpoints."""

import io
import unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from tests.synthetic_pdf_generator import (
    create_valid_multipage_pdf,
    create_scanned_image_pdf,
    create_encrypted_pdf,
    create_fake_signature_pdf,
)


class TestDocumentsAPI(unittest.TestCase):
    """Integration test suite verifying /api/v1/documents endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_upload_valid_document_success(self):
        """Test uploading a legitimate synthetic PDF returns 201 with extracted pages and metadata."""
        pdf_bytes = create_valid_multipage_pdf()
        files = {"file": ("campus_facilities.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"department": "StudentAffairs", "category": "Handbook"}

        response = self.client.post("/api/v1/documents/upload", files=files, data=data)
        self.assertEqual(response.status_code, 201)
        res_data = response.json()

        self.assertIn("doc_id", res_data)
        self.assertEqual(res_data["filename"], "campus_facilities.pdf")
        self.assertEqual(res_data["total_pages"], 3)
        self.assertEqual(res_data["department"], "StudentAffairs")
        self.assertEqual(res_data["status"], "PROCESSED")
        self.assertFalse(res_data["is_duplicate"])
        self.assertFalse(res_data["has_scanned_pages"])
        self.assertFalse(res_data["needs_ocr_review"])
        self.assertGreater(len(res_data["pages"]), 0)

        # Verify no filesystem paths are exposed
        self.assertNotIn("raw_file_path", res_data)
        self.assertNotIn("processed_file_path", res_data)

        # Test duplicate upload
        files_dup = {"file": ("campus_facilities_dup.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        response_dup = self.client.post("/api/v1/documents/upload", files=files_dup, data=data)
        self.assertIn(response_dup.status_code, [200, 201])
        res_dup = response_dup.json()
        self.assertTrue(res_dup["is_duplicate"])
        self.assertEqual(res_dup["doc_id"], res_data["doc_id"])

        # Clean up
        doc_id = res_data["doc_id"]
        del_resp = self.client.delete(f"/api/v1/documents/{doc_id}")
        self.assertEqual(del_resp.status_code, 200)

    def test_upload_scanned_image_pdf_flags_needs_ocr_review(self):
        """Test uploading a scanned image PDF sets needs_ocr_review = True."""
        pdf_bytes = create_scanned_image_pdf()
        files = {"file": ("scanned_notice.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"department": "Hostel", "category": "Notice"}

        response = self.client.post("/api/v1/documents/upload", files=files, data=data)
        self.assertEqual(response.status_code, 201)
        res_data = response.json()

        self.assertTrue(res_data["has_scanned_pages"])
        self.assertTrue(res_data["needs_ocr_review"])

        # Clean up
        self.client.delete(f"/api/v1/documents/{res_data['doc_id']}")

    def test_upload_rejection_fake_signature(self):
        """Test uploading non-PDF bytes returns HTTP 400."""
        fake_bytes = create_fake_signature_pdf()
        files = {"file": ("fake_document.pdf", io.BytesIO(fake_bytes), "application/pdf")}

        response = self.client.post("/api/v1/documents/upload", files=files)
        self.assertEqual(response.status_code, 400)
        self.assertIn("File header signature check failed", response.json()["detail"])

    def test_upload_rejection_encrypted_pdf(self):
        """Test uploading password-protected PDF returns HTTP 422."""
        pdf_bytes = create_encrypted_pdf(password="secret")
        files = {"file": ("locked_handbook.pdf", io.BytesIO(pdf_bytes), "application/pdf")}

        response = self.client.post("/api/v1/documents/upload", files=files)
        self.assertEqual(response.status_code, 422)
        self.assertIn("password-protected or encrypted", response.json()["detail"])

    def test_list_and_get_document_details(self):
        """Test listing documents and fetching individual document details."""
        pdf_bytes = create_valid_multipage_pdf()
        files = {"file": ("test_list_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"department": "Registrar", "category": "Notice"}

        upload_resp = self.client.post("/api/v1/documents/upload", files=files, data=data)
        self.assertEqual(upload_resp.status_code, 201)
        doc_id = upload_resp.json()["doc_id"]

        # 1. Test listing
        list_resp = self.client.get("/api/v1/documents")
        self.assertEqual(list_resp.status_code, 200)
        items = list_resp.json()
        self.assertIsInstance(items, list)
        matching = [item for item in items if item["doc_id"] == doc_id]
        self.assertEqual(len(matching), 1)

        # Verify no filesystem paths in list item
        self.assertNotIn("raw_file_path", matching[0])
        self.assertNotIn("processed_file_path", matching[0])

        # 2. Test get details
        get_resp = self.client.get(f"/api/v1/documents/{doc_id}")
        self.assertEqual(get_resp.status_code, 200)
        detail = get_resp.json()
        self.assertEqual(detail["doc_id"], doc_id)
        self.assertIn("pages", detail)
        self.assertEqual(len(detail["pages"]), 3)

        # 3. Test get non-existent returns 404
        non_existent_resp = self.client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
        self.assertEqual(non_existent_resp.status_code, 404)

        # 4. Clean up via DELETE
        del_resp = self.client.delete(f"/api/v1/documents/{doc_id}")
        self.assertEqual(del_resp.status_code, 200)

        # 5. Verify 404 after deletion
        get_again_resp = self.client.get(f"/api/v1/documents/{doc_id}")
        self.assertEqual(get_again_resp.status_code, 404)

        # 6. Second delete returns 404
        del_again_resp = self.client.delete(f"/api/v1/documents/{doc_id}")
        self.assertEqual(del_again_resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()

