"""Retrieval-Augmented Generation (RAG) module and document processing engine."""

from backend.app.rag.cleaner import clean_text, extract_snippet
from backend.app.rag.parser import parse_pdf_document, PDFParsingError
from backend.app.rag.chunker import DocumentChunker, calculate_effective_token_budget
from backend.app.rag.embedder import DenseEmbedder, get_default_embedder, MockEmbeddingModel

__all__ = [
    "clean_text",
    "extract_snippet",
    "parse_pdf_document",
    "PDFParsingError",
    "DocumentChunker",
    "calculate_effective_token_budget",
    "DenseEmbedder",
    "get_default_embedder",
    "MockEmbeddingModel",
]
