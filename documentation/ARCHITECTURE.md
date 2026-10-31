# UniMind Technical Architecture 🏛️

## 1. Executive Summary

**UniMind** is a university knowledge assistant designed to deliver accurate, citation-backed answers to student inquiries regarding academic policies, campus procedures, timetables, and facilities.

Built on **Retrieval-Augmented Generation (RAG)** principles, UniMind eliminates hallucinations by constraining LLM generation strictly to retrieved institutional context. If supporting evidence is insufficient or missing, the system detects this condition and explicitly abstains rather than fabricating information.

---

## 2. High-Level System Architecture

```text
+--------------------------------------------------------------+
|                        Client Layer                          |
|  - React SPA (Tailwind CSS)                                  |
|  - Conversational Interface & Source Inspector               |
+------------------------------+-------------------------------+
                               |
                               | HTTP / JSON REST
                               v
+--------------------------------------------------------------+
|                     FastAPI Backend                          |
|  - Router Layer (/api/v1/health, /api/v1/query, etc.)         |
|  - Pydantic Validation & Serialization                       |
|  - Dependency Injection & Configuration Management           |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
|                       RAG Pipeline                           |
|                                                              |
|  [Query Processing] ---> [Dense Embedding (Sentence Trans.)]  |
|                                     |                        |
|                                     v                        |
|                            [FAISS Similarity Search]         |
|                                     |                        |
|                                     v                        |
|                            [Context Retrieval & Rank]        |
|                                     |                        |
|                                     v                        |
|                            [Grounding & Relevance Check]     |
|                                     |                        |
|                 +-------------------+-------------------+    |
|                 |                                       |    |
|         (Score >= Threshold)                 (Score < Threshold)
|                 |                                       |    |
|                 v                                       v    |
|       [Gemini Answer Gen]                       [Abstain]    |
|   (Grounded Answer + Citations)             ("I don't know") |
+--------------------------------------------------------------+
```

---

## 3. Modular Directory Breakdown

| Directory | Layer / Purpose | Key Responsibilities |
|---|---|---|
| `backend/app/core/` | Core Infrastructure | Configuration (`config.py`), security, global singletons. |
| `backend/app/models/` | Data Models | Pydantic DTOs, request payloads, response schemas. |
| `backend/app/routes/` | API Routers | Endpoint handlers, route aggregation (`api.py`), versioning (`/api/v1`). |
| `backend/app/services/` | Business Logic | Orchestrators, document ingestion workflows, chat state. |
| `backend/app/rag/` | RAG Engine | Text splitting, embeddings generation, vector search, prompt templates. |
| `backend/app/utils/` | Utilities | Logging, text sanitization, timing, error handlers. |
| `frontend/` | Presentation | React application, UI state, conversation components. |
| `data/raw/` | Knowledge Base (Source) | Original institutional documents (PDFs, docs, tables). |
| `data/processed/` | Knowledge Base (Staged) | Cleaned, normalized chunks with metadata. |
| `data/evaluation/` | Quality Assurance | Golden Q&A benchmark datasets, evaluation scripts. |
| `vector_store/` | Persistence | Serialized FAISS indices, ID-to-chunk index maps. |
| `documentation/` | Documentation | Architecture, setup, API contracts, benchmark results. |
| `tests/` | Verification | Unit tests, integration tests, contract tests. |

---

## 4. RAG Pipeline Design (Upcoming Phases)

### Phase 2: Ingestion & Embeddings
1. **Document Parsing**: Extract clean text and structural metadata (source name, page number, section header) using `PyMuPDF`.
2. **Chunking Strategy**: Recursive character chunking with overlap (e.g. 500 characters with 100 character overlap) to preserve contextual boundaries.
3. **Dense Embeddings**: Generate vectors using `sentence-transformers/all-MiniLM-L6-v2`.
4. **Vector Indexing**: Build and persist a cosine/L2 FAISS index in `vector_store/`.

### Phase 3: Retrieval, LLM Grounding & Abstention
1. **Similarity Retrieval**: Retrieve top-$k$ nearest document chunks for each query.
2. **Relevance Thresholding**: Compute retrieval confidence. If distance exceeds a predetermined threshold, bypass LLM generation and trigger a structured abstention response.
3. **Constrained Prompting**: Pass retrieved context chunks to Gemini API (`gemini-1.5-flash`) with a strict system prompt forbidding speculation.
4. **Citations & Provenance**: Include source document identifiers, page numbers, and snippet quotes in the response.

---

## 5. Security & Configuration Principles
- **12-Factor App Configuration**: All environment-dependent parameters (ports, keys, directories) are centralized in `Settings` and loaded via `.env`.
- **Zero Secret Ingestion**: `.env` and sensitive API keys are strictly excluded from version control via `.gitignore`.
- **CORS Isolation**: Explicitly restrict origin domains to trusted frontend hosts.

