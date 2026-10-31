# UniMind - Phase 2 Technical Implementation Plan: Document Ingestion Engine 📄

**Date:** November 1, 2026  
**Author:** Antigravity AI Engineering Assistant  
**Project:** UniMind – AI-Powered University Knowledge Assistant  
**Milestone:** Phase 2 – Document Ingestion Engine  
**Team:** Group G21 (Utkarsh, Suhani, Sanchayeeta)  
**Status:** **PLANNING DRAFT (AWAITING APPROVAL)**

---

## 1. Executive Summary

Phase 2 establishes the **Document Ingestion Engine** for UniMind. This subsystem is responsible for securely receiving institutional documents, verifying file integrity, extracting layout-aware text via PyMuPDF, preserving granular page-level metadata for downstream RAG citation provenance, performing text normalization, and persisting raw and processed artifacts.

In accordance with project constraints:
- **No real LPU policies or fabricated institutional documents** will be introduced; only **synthetic test fixtures** will be utilized for verification.
- **No RAG indexing or LLM embeddings** will be executed in this milestone; this phase focuses solely on robust document ingestion, parsing, cleaning, and storage.

---

## 2. Target File Modifications & Creations

```text
UniMind/
├── requirements.txt                      [MODIFY] Add python-multipart>=0.0.9
│
├── backend/app/
│   ├── core/
│   │   └── config.py                     [MODIFY] Add upload size limit, allowed mime types, storage dirs
│   ├── models/
│   │   └── schemas.py                    [MODIFY] Add DocumentUploadResponse, PageMetadata, DocumentMetadata
│   ├── routes/
│   │   ├── api.py                        [MODIFY] Mount documents.router under /api/v1
│   │   └── documents.py                  [CREATE] POST /documents/upload, GET /documents/{id}, GET /documents
│   ├── services/
│   │   ├── __init__.py                   [MODIFY] Export DocumentService
│   │   └── document_service.py           [CREATE] Coordinate validation, parsing, cleaning, and storage
│   ├── rag/
│   │   ├── __init__.py                   [MODIFY] Export parser and cleaner utilities
│   │   ├── parser.py                     [CREATE] PyMuPDF extraction, layout analysis, scanned PDF detection
│   │   └── cleaner.py                    [CREATE] Text normalization, hyphenation fix, whitespace sanitation
│   └── utils/
│       ├── __init__.py                   [MODIFY] Export validator & logger
│       └── file_validator.py             [CREATE] Magic byte check, extension check, filename sanitization
│
└── tests/
    ├── fixtures/                         [CREATE] Synthetic test PDF generators
    ├── test_file_validator.py            [CREATE] Unit tests for magic bytes, size limits, and sanitization
    ├── test_pdf_parser.py                [CREATE] Unit tests for PyMuPDF extraction and cleaning
    └── test_documents_api.py             [CREATE] Integration tests for FastAPI document upload & retrieval endpoints
```

---

## 3. Detailed Component Architecture

### 3.1 Security & File Validation Layer (`backend/app/utils/file_validator.py`)
To prevent arbitrary file upload vulnerabilities, path traversals, and corrupted files:
1. **Magic Number Verification:** Verify that the first 5 bytes match `b"%PDF-"`. Rejects spoofed files (e.g. `.exe` renamed to `.pdf`).
2. **MIME Type Validation:** Ensure `content_type` matches `application/pdf`.
3. **File Size Enforcement:** Enforce configurable maximum upload size (e.g. `MAX_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024` / 25 MB). Reject oversized payloads with HTTP 413.
4. **Filename Sanitization:** Strip directory paths, null bytes, and dangerous characters. Generate a deterministic UUIDv4 for storage: `{doc_id}_{secure_name}.pdf`.
5. **Deduplication Checksum:** Compute SHA-256 hash of incoming bytes to identify duplicate uploads.

### 3.2 PyMuPDF Extraction & Layout Analysis (`backend/app/rag/parser.py`)
Uses `fitz` (`PyMuPDF`) for high-performance in-memory parsing:
1. **Encrypted PDF Detection:** Check `doc.is_encrypted`. If encrypted/password-protected, raise HTTP 422 with a clear explanatory error.
2. **Page-by-Page Extraction:** Iterate through pages using `page.get_text("blocks")` to preserve reading order and structural layout.
3. **Metadata Extraction:** Extract document title, author, creation date, and total page count from document properties.
4. **Scanned PDF & Image Detection:**
   - Detect pages where extractable text length is below threshold (`< 50` characters) while embedded image count is `> 0`.
   - Set `is_scanned = True` and flag document with warning `scanned_content_detected`.
5. **Empty Document Detection:** Detect pages with 0 characters or pure whitespace. Set `is_empty = True`.

### 3.3 Text Normalization & Cleaning (`backend/app/rag/cleaner.py`)
Text retrieved from PDFs often contains artifacts that degrade vector embedding quality. The cleaner module applies:
1. **Unicode Normalization:** Apply `unicodedata.normalize("NFKC", text)` to standardize symbols and ligature characters (e.g., `ﬁ`, `ﬂ`).
2. **Hyphenation Restoration:** Detect and merge words split across line breaks (e.g., `insti-\ntutional` $\rightarrow$ `institutional`).
3. **Whitespace Sanitation:** Collapse multi-spaces and replace excessive consecutive newlines (`\n{3,}` $\rightarrow$ `\n\n`) while preserving paragraph boundaries.
4. **Control Character Elimination:** Strip non-printable ASCII control characters (preserving standard whitespace `\t`, `\n`).

### 3.4 Storage & Metadata Persistence (`backend/app/services/document_service.py`)
1. **Raw Storage:** Persist raw PDF in `data/raw/{doc_id}.pdf`.
2. **Processed Storage:** Persist parsed and cleaned JSON structure in `data/processed/{doc_id}.json`.
3. **Registry Index:** Update centralized `data/processed/registry.json` (or SQLite database) with catalog metadata for instant listing and querying.

---

## 4. API Request & Response Schemas

### 4.1 Ingestion Request Payload
Endpoint: `POST /api/v1/documents/upload`  
Content-Type: `multipart/form-data`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file` | `UploadFile` | Yes | The PDF binary document. |
| `department` | `str` (Form) | No | University department (default: `"General"`). |
| `category` | `str` (Form) | No | Document category (e.g., `"Academic Policy"`, `"Timetable"`). |

### 4.2 Ingestion Response Schema (`DocumentUploadResponse`)
```json
{
  "doc_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "filename": "synthetic_campus_guide.pdf",
  "file_hash_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "file_size_bytes": 1048576,
  "total_pages": 4,
  "department": "Academics",
  "category": "Policy",
  "status": "PROCESSED",
  "has_scanned_pages": false,
  "total_words": 1420,
  "total_characters": 9350,
  "uploaded_at": "2026-11-01T01:30:00Z",
  "pages": [
    {
      "page_number": 1,
      "char_count": 2400,
      "word_count": 360,
      "is_empty": false,
      "is_scanned": false,
      "snippet": "Synthetic University Academic Regulations 2026..."
    }
  ]
}
```

### 4.3 Document Detail Schema (`DocumentDetailResponse`)
Endpoint: `GET /api/v1/documents/{doc_id}`
Returns complete document record including all page-level cleaned texts, character offsets, and structural blocks ready for Phase 3 chunking.

---

## 5. End-to-End Ingestion Workflow

```text
Client Upload (POST /api/v1/documents/upload)
                 │
                 ▼
       [1. Security Validation]
       ├── Check file size <= MAX_UPLOAD_SIZE_BYTES
       ├── Validate extension is '.pdf'
       └── Validate magic bytes == b'%PDF-'
                 │ (Pass)
                 ▼
       [2. Checksum & Dedup]
       ├── Compute SHA-256 hash
       └── Verify if document already registered
                 │
                 ▼
       [3. PyMuPDF Processing]
       ├── Check doc.is_encrypted
       ├── Extract document-level metadata
       └── Iterate pages (extract text blocks & images)
                 │
                 ▼
       [4. Content Quality Analysis]
       ├── Check for empty pages (text len == 0)
       └── Check for scanned pages (images > 0 and text < 50 chars)
                 │
                 ▼
       [5. Text Normalization]
       ├── NFKC Unicode normalization
       ├── Reconstruct hyphenated words
       └── Clean excess whitespace
                 │
                 ▼
       [6. Persistence]
       ├── Save raw PDF to data/raw/{doc_id}.pdf
       ├── Save extracted JSON to data/processed/{doc_id}.json
       └── Update catalog registry data/processed/registry.json
                 │
                 ▼
       Client Response (HTTP 201 Created)
```

---

## 6. Testing Strategy (Using Synthetic Documents Only)

To strictly prevent inclusion of real university policies or fabricated proprietary information, automated tests will dynamically generate synthetic test PDFs using ReportLab/PyMuPDF:

1. **`test_standard_synthetic_pdf`**: Multi-page PDF containing known synthetic text, headings, and tables. Asserts exact page counts, extracted words, and metadata preservation.
2. **`test_empty_pdf`**: A PDF containing blank pages. Verifies that `is_empty = True` is flagged and appropriate status warnings are returned.
3. **`test_scanned_image_synthetic_pdf`**: A PDF generated with an embedded image and zero text. Verifies `is_scanned = True` detection.
4. **`test_magic_byte_spoofing`**: A text or executable file renamed with a `.pdf` extension. Asserts HTTP 400 rejection on magic byte mismatch.
5. **`test_oversized_file_rejection`**: Upload exceeding size threshold. Asserts HTTP 413 rejection.
6. **`test_corrupted_pdf_rejection`**: Corrupted byte stream. Asserts HTTP 422 rejection.
7. **`test_deduplication`**: Uploading the identical synthetic file twice returns the existing document record or flags duplicate without duplicate disk waste.

---

## 7. Step-by-Step Implementation Order

| Step | Action | Files Touched |
|---|---|---|
| **Step 2.1** | Add `python-multipart>=0.0.9` to `requirements.txt` and install dependency. | `requirements.txt` |
| **Step 2.2** | Implement validation utility (`file_validator.py`) & upload config settings. | `backend/app/utils/file_validator.py`, `backend/app/core/config.py` |
| **Step 2.3** | Implement text cleaning utility (`cleaner.py`). | `backend/app/rag/cleaner.py` |
| **Step 2.4** | Implement PyMuPDF extractor (`parser.py`). | `backend/app/rag/parser.py` |
| **Step 2.5** | Implement document service & persistence logic (`document_service.py`). | `backend/app/services/document_service.py` |
| **Step 2.6** | Implement Pydantic request/response schemas. | `backend/app/models/schemas.py` |
| **Step 2.7** | Implement FastAPI document routes and mount in API router. | `backend/app/routes/documents.py`, `backend/app/routes/api.py` |
| **Step 2.8** | Author synthetic test fixtures & complete test suites. | `tests/test_file_validator.py`, `tests/test_pdf_parser.py`, `tests/test_documents_api.py` |
| **Step 2.9** | Execute end-to-end verification and generate Milestone Output PDF and Markdown reports. | `documentation/reports/` |

---

*Plan formulated per project constraints. No code modified. Awaiting user approval to commence Step 2.1.*

