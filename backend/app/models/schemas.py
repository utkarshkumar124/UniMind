"""Pydantic schemas and data transfer models for UniMind API."""

from typing import List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema for API health status check response."""

    status: str = Field(default="healthy", description="Current service health state")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Deployment environment")


class RootResponse(BaseModel):
    """Schema for root endpoint response."""

    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Application version")
    status: str = Field(default="online", description="Service status")
    docs_url: str = Field(..., description="Interactive API documentation URL")
    health_url: str = Field(..., description="Service health endpoint URL")
    api_v1_url: str = Field(..., description="API v1 root route")


class StructuralBlock(BaseModel):
    """Extracted structural text block with coordinates."""

    block_number: int = Field(..., description="Block index within page")
    bbox: List[float] = Field(..., description="Bounding box coordinates [x0, y0, x1, y1]")
    text: str = Field(..., description="Cleaned block text")


class PageInfo(BaseModel):
    """Page-level extraction details and quality flags."""

    page_number: int = Field(..., description="1-indexed page number")
    text: Optional[str] = Field(default=None, description="Cleaned extracted page text")
    snippet: str = Field(default="", description="Short preview snippet")
    char_count: int = Field(default=0, description="Character count on page")
    word_count: int = Field(default=0, description="Word count on page")
    is_empty: bool = Field(default=False, description="Whether the page contains zero text")
    is_scanned: bool = Field(default=False, description="Whether the page contains images without extractable text")
    needs_ocr_review: bool = Field(default=False, description="Flag for scanned/image content needing OCR review")
    image_count: int = Field(default=0, description="Number of embedded raster images on page")
    blocks: Optional[List[StructuralBlock]] = Field(default=None, description="Structural text blocks")


class DocumentUploadResponse(BaseModel):
    """Response returned upon successful document upload and parsing."""

    doc_id: str = Field(..., description="Unique document UUID")
    filename: str = Field(..., description="Sanitized original document filename")
    file_hash_sha256: str = Field(..., description="SHA-256 hash of document binary")
    file_size_bytes: int = Field(..., description="Document size in bytes")
    total_pages: int = Field(..., description="Total pages in document")
    department: str = Field(default="General", description="Associated university department")
    category: str = Field(default="Policy", description="Document category")
    status: str = Field(..., description="Processing status: PROCESSING, PROCESSED, FAILED")
    has_scanned_pages: bool = Field(default=False, description="Whether any page is scanned/image-based")
    needs_ocr_review: bool = Field(default=False, description="Flag indicating OCR review is recommended")
    is_empty: bool = Field(default=False, description="Whether the entire document contains zero text")
    total_words: int = Field(default=0, description="Total word count in document")
    total_characters: int = Field(default=0, description="Total character count in document")
    is_duplicate: bool = Field(default=False, description="Whether this upload was identified as a duplicate")
    uploaded_at: str = Field(..., description="ISO 8601 upload timestamp")
    pages: List[PageInfo] = Field(default_factory=list, description="Extracted pages and metadata")


class DocumentListItem(BaseModel):
    """Summary item in document catalog list."""

    doc_id: str = Field(..., description="Unique document UUID")
    filename: str = Field(..., description="Sanitized document filename")
    file_hash_sha256: str = Field(..., description="SHA-256 hash of document binary")
    file_size_bytes: int = Field(..., description="Document size in bytes")
    total_pages: int = Field(..., description="Total pages")
    department: str = Field(..., description="Associated university department")
    category: str = Field(..., description="Document category")
    status: str = Field(..., description="Document processing status")
    has_scanned_pages: bool = Field(default=False, description="Scanned pages flag")
    needs_ocr_review: bool = Field(default=False, description="OCR review flag")
    is_empty: bool = Field(default=False, description="Empty document flag")
    total_words: int = Field(default=0, description="Total word count")
    total_characters: int = Field(default=0, description="Total character count")
    total_chunks: int = Field(default=0, description="Total indexed chunks")
    uploaded_at: str = Field(..., description="ISO 8601 upload timestamp")
    updated_at: Optional[str] = Field(default=None, description="ISO 8601 last update timestamp")


class DocumentDetailResponse(DocumentListItem):
    """Full document record including extracted page content."""

    pages: List[PageInfo] = Field(default_factory=list, description="Extracted pages")


class BlockReference(BaseModel):
    """Reference to a specific structural block within a document page."""

    page_number: int = Field(..., description="1-indexed page number containing block")
    block_index: int = Field(..., description="Block index within page")
    bbox: List[float] = Field(..., description="Bounding box coordinates [x0, y0, x1, y1]")


class DocumentChunk(BaseModel):
    """Granular semantic text chunk with exact provenance and vector offset."""

    chunk_id: str = Field(..., description="Deterministic unique identifier {doc_id}#p{page}#c{idx}")
    doc_id: str = Field(..., description="Parent document UUID")
    filename: str = Field(..., description="Source document filename")
    department: str = Field(..., description="University department")
    category: str = Field(..., description="Document category")
    page_start: int = Field(..., description="1-indexed starting page number")
    page_end: int = Field(..., description="1-indexed ending page number")
    chunk_index: int = Field(..., description="0-indexed position within document")
    blocks: List[BlockReference] = Field(default_factory=list, description="Structural blocks spanned by this chunk")
    text: str = Field(..., description="Normalized chunk text")
    token_count: int = Field(..., description="Token count using model tokenizer")
    char_count: int = Field(..., description="Character count")
    file_hash_sha256: str = Field(..., description="SHA-256 hash of original document binary")
    embedding_offset: int = Field(..., description="Row index in dense vector embeddings matrix")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class DocumentProcessResponse(BaseModel):
    """Response returned upon successful document chunking and embedding generation."""

    doc_id: str = Field(..., description="Processed document UUID")
    status: str = Field(..., description="Processing status (e.g. INDEXED)")
    total_chunks: int = Field(..., description="Total semantic chunks generated and indexed")
    model_name: str = Field(..., description="Embedding model used")
    vector_dimension: int = Field(..., description="Dimension of generated embedding vectors")
    embedding_file: str = Field(..., description="Filename of stored dense vectors (.npy)")
    chunks_file: str = Field(..., description="Filename of stored chunk catalog (.json)")
    processing_time_seconds: float = Field(..., description="Execution time in seconds")
    processed_at: str = Field(..., description="ISO 8601 completion timestamp")


class DocumentDeleteResponse(BaseModel):
    """Response returned upon document deletion."""

    doc_id: str = Field(..., description="UUID of deleted document")
    deleted: bool = Field(default=True, description="Deletion confirmation")
    message: str = Field(..., description="Status message")
