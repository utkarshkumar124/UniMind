"""File validation, security checks, and sanitization utilities."""

import os
import re
import hashlib
from typing import Tuple
from fastapi import UploadFile, HTTPException, status
from backend.app.core.config import settings

# PDF standard magic bytes signature
PDF_MAGIC_BYTES = b"%PDF-"


class FileValidationError(HTTPException):
    """Custom HTTP exception for file validation failures."""

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal, control character injection, and directory manipulation.

    Args:
        filename: Raw incoming filename string.

    Returns:
        Cleaned, secure filename.
    """
    if not filename:
        return "unnamed_document.pdf"

    # Normalize directory separators and extract basename only
    base_name = filename.replace("\\", "/").split("/")[-1]

    # Strip non-alphanumeric characters except safe punctuation
    sanitized = re.sub(r"[^\w\.\-\_ ]", "", base_name).strip()
    sanitized = re.sub(r"\s+", "_", sanitized)
    sanitized = re.sub(r"\.{2,}", ".", sanitized)

    if not sanitized:
        return "unnamed_document.pdf"

    name_part, ext = os.path.splitext(sanitized)
    if len(name_part) > 80:
        name_part = name_part[:80]

    return f"{name_part}{ext}"


async def read_and_validate_upload(
    upload_file: UploadFile,
    max_size_bytes: int = settings.MAX_UPLOAD_SIZE_BYTES,
) -> Tuple[bytes, str, str]:
    """Read an uploaded file in bounded chunks and validate size, extension, and magic bytes.

    Prevents unbounded memory usage by reading up to (max_size_bytes + 1) in chunks.

    Args:
        upload_file: Incoming FastAPI UploadFile instance.
        max_size_bytes: Maximum allowed byte size (default 25 MB).

    Returns:
        Tuple of (file_bytes, sha256_hash, sanitized_filename).

    Raises:
        FileValidationError: On invalid extension, oversized file, or magic byte mismatch.
    """
    raw_name = upload_file.filename or ""
    _, raw_ext = os.path.splitext(raw_name)

    # 1. Extension check on incoming filename
    if raw_ext.lower() not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise FileValidationError(
            f"Unsupported file extension '{raw_ext}'. Only {settings.ALLOWED_UPLOAD_EXTENSIONS} files are accepted.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    sanitized_name = sanitize_filename(raw_name)

    # 2. MIME type check
    content_type = (upload_file.content_type or "").lower()
    if content_type and content_type not in settings.ALLOWED_UPLOAD_MIME_TYPES:
        raise FileValidationError(
            f"Invalid MIME type '{content_type}'. Expected 'application/pdf'.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Read in bounded chunks to avoid unbounded memory consumption
    chunk_size = 64 * 1024  # 64 KB chunks
    total_bytes_read = 0
    buffer = bytearray()
    hasher = hashlib.sha256()

    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        total_bytes_read += len(chunk)
        if total_bytes_read > max_size_bytes:
            raise FileValidationError(
                f"File size exceeds maximum allowed limit of {max_size_bytes / (1024 * 1024):.1f} MB.",
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        buffer.extend(chunk)
        hasher.update(chunk)

    if total_bytes_read == 0:
        raise FileValidationError("Uploaded file is empty (0 bytes).", status_code=status.HTTP_400_BAD_REQUEST)

    file_bytes = bytes(buffer)

    # 4. PDF Magic Signature Verification
    if not file_bytes.startswith(PDF_MAGIC_BYTES):
        raise FileValidationError(
            "File header signature check failed: not a valid PDF document.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    sha256_hash = hasher.hexdigest()
    return file_bytes, sha256_hash, sanitized_name
