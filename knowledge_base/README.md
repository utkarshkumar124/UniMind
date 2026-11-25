Title: UniMind Knowledge Base Architecture & Maintenance Guide
Category: Documentation
Last verified: 2026-11-25
Applicable academic year/session: 2026–2027
Source reliability: Project Documentation
Status: Verified

# UniMind University Knowledge Base

## Purpose
This directory stores the curated, source-attributed knowledge base for **Lovely Professional University (LPU)** used by **UniMind**, a document-grounded university FAQ & academic assistant.

## Verification Standard
Every claim across these Markdown files obeys strict source attribution:
- **Status: Verified** — Directly observed on official `lpu.in` web pages, `webapi.lpu.in` institutional endpoints, or `ums.lpu.in` / UGC statutory disclosures on `2026-11-25`.
- **Status: Partially verified** — General institutional structure is official, while specific operational sub-thresholds (e.g., exact UMS cutoff windows or internal handbook numbers not published openly without student login) are explicitly flagged for confirmation via UMS E-Notice / LMS / Residential Handbook.
- **Unverified / Unavailable Policy** — Never fabricated; explicitly marked *"Not verified from an official public source"*.

## Ingestion into UniMind RAG
UniMind's FastAPI backend (`backend/app/services/document_service.py`, `embedding_service.py`, and `vector_store.py`) ingests `.pdf` documents, extracts page-level text, splits text into 380-token hierarchical chunks with 40-token overlap, embeds chunks using `intfloat/multilingual-e5-small` (384-d normalized vectors), and builds an immutable FAISS `IndexIDMap2` bundle under `vector_store/generations/`.

To synchronize updates to `knowledge_base/` into UniMind's live FAISS index without modifying backend retrieval logic:
1. Run `python scripts/ingest_knowledge_base.py` from the repository root (`c:\Users\Utkarsh Kumar\Desktop\UniMind`).
2. The script renders structured domain PDFs into `data/kb_pdfs/`, ingests them through `document_service` and `embedding_service`, and commits the unified generation bundle via `vector_store_service.commit_generation_bundle(...)`.
3. Restart the FastAPI server so `vector_store_service.startup_recovery()` activates the updated bundle in memory.
