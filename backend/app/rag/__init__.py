"""Retrieval-Augmented Generation (RAG) module and document processing engine."""

from backend.app.rag.cleaner import clean_text, extract_snippet
from backend.app.rag.parser import parse_pdf_document, PDFParsingError

__all__ = [
    "clean_text",
    "extract_snippet",
    "parse_pdf_document",
    "PDFParsingError",
]
