"""API routes for Document Ingestion, Retrieval, and Management."""

from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from backend.app.models.schemas import (
    DocumentUploadResponse,
    DocumentListItem,
    DocumentDetailResponse,
    DocumentDeleteResponse,
    DocumentProcessResponse,
)
from backend.app.utils.file_validator import read_and_validate_upload
from backend.app.services.document_service import document_service
from backend.app.services.embedding_service import (
    embedding_service,
    DocumentNotFoundError,
    ConcurrencyConflictError,
    InvalidDocumentStateError,
)

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


@router.post(
    "/{doc_id}/process",
    response_model=DocumentProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Process Document: Chunk Text and Generate Dense Embeddings",
)
async def process_document(
    doc_id: str,
    force: bool = False,
) -> DocumentProcessResponse:
    """Trigger semantic chunking and dense vector embedding generation for an ingested document.

    Performs:
    - Atomic SQLite CAS concurrency locking against duplicate requests.
    - Hierarchical sliding window token chunking with page and block provenance.
    - Dense embedding generation using multilingual-e5-small with 'passage: ' prefix.
    - Per-file transaction manifest staging and backup rotation.
    - Atomic commit to SQLite chunks registry.
    """
    try:
        response = embedding_service.process_document(doc_id=doc_id, force=force)
        return response
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ConcurrencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except InvalidDocumentStateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document embedding processing failed: {str(e)}",
        )


@router.delete(
    "/{doc_id}",
    response_model=DocumentDeleteResponse,
    summary="Delete Document",
)
async def delete_document(doc_id: str) -> DocumentDeleteResponse:
    """Safely delete a document, raw PDF, processed JSON, chunk index, vector embeddings, and catalog entry."""
    success = embedding_service.delete_document_recoverable(doc_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )
    return DocumentDeleteResponse(
        doc_id=doc_id,
        deleted=True,
        message="Document, raw file, processed data, chunks, and embeddings deleted successfully.",
    )

