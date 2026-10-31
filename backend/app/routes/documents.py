"""API routes for Document Ingestion, Retrieval, and Management."""

from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from backend.app.models.schemas import (
    DocumentUploadResponse,
    DocumentListItem,
    DocumentDetailResponse,
    DocumentDeleteResponse,
)
from backend.app.utils.file_validator import read_and_validate_upload
from backend.app.services.document_service import document_service

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and Ingest PDF Document",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF document binary"),
    department: str = Form("General", description="University department name"),
    category: str = Form("Policy", description="Document category (e.g. Policy, Timetable, Syllabus)"),
) -> DocumentUploadResponse:
    """Upload, validate, parse, and ingest a PDF document.

    Performs:
    - Bounded memory read and size checks (max 25 MB).
    - PDF magic byte and MIME type validation.
    - Filename sanitization.
    - PyMuPDF text and structural block extraction.
    - Scanned PDF detection (flags needs_ocr_review).
    - Atomic storage of raw PDF and processed JSON.
    - Duplicate detection via SHA-256 hash.
    """
    file_bytes, file_hash, sanitized_filename = await read_and_validate_upload(file)

    result = document_service.ingest_document(
        file_bytes=file_bytes,
        filename=sanitized_filename,
        file_hash=file_hash,
        department=department,
        category=category,
    )

    return DocumentUploadResponse(**result)


@router.get(
    "",
    response_model=List[DocumentListItem],
    summary="List Ingested Documents",
)
async def list_documents(
    department: Optional[str] = None,
    limit: int = 100,
) -> List[DocumentListItem]:
    """List all ingested documents in the catalog, optionally filtered by department."""
    docs = document_service.list_documents(department=department, limit=limit)
    return [DocumentListItem(**d) for d in docs]


@router.get(
    "/{doc_id}",
    response_model=DocumentDetailResponse,
    summary="Get Document Details and Extracted Content",
)
async def get_document(doc_id: str) -> DocumentDetailResponse:
    """Retrieve full document record including extracted page content and layout blocks."""
    doc = document_service.get_document_details(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )
    return DocumentDetailResponse(**doc)


@router.delete(
    "/{doc_id}",
    response_model=DocumentDeleteResponse,
    summary="Delete Document",
)
async def delete_document(doc_id: str) -> DocumentDeleteResponse:
    """Delete a document, its raw PDF file, processed JSON structure, and catalog entry."""
    success = document_service.delete_document(doc_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )
    return DocumentDeleteResponse(
        doc_id=doc_id,
        deleted=True,
        message="Document, raw file, processed data, and registry record deleted successfully.",
    )

