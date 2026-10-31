# UniMind - Phase 3 Final Technical Implementation Plan: Text Chunking & Dense Embeddings 🧠

**Revision:** 3.2 (Per-File Transaction Manifest, Authoritative Concurrency & Non-Destructive Recovery)  
**Date:** November 1, 2026  
**Author:** Antigravity AI Engineering Assistant  
**Project:** UniMind – AI-Powered University Knowledge Assistant  
**Milestone:** Phase 3 – Text Chunking, Token Sizing, and Dense Vector Embedding Pipeline  
**Team:** Group G21 (Utkarsh, Suhani, Sanchayeeta)  
**Status:** **FINAL APPROVED ARCHITECTURE (AWAITING IMPLEMENTATION APPROVAL)**

---

## 1. Executive Summary & Locked Decisions

Phase 3 establishes the **Chunking and Dense Embedding Subsystem** for UniMind. It transforms layout-aware documents from Phase 2 into token-bounded semantic passages, computes normalized 384-dimensional dense vectors using `intfloat/multilingual-e5-small`, guarantees exact page-and-block provenance, and persists artifacts using an authoritative SQLite concurrency lock and a **Per-File Transaction Manifest** that guarantees crash-safe recovery without data loss.

### Locked Architectural Decisions
1. **Default Embedding Model**: `intfloat/multilingual-e5-small`
   - **Multilingual Support**: Supports English, Hindi, and Hinglish university inquiries.
   - **Vector Dimension**: 384 dimensions (float32).
   - **Context Window**: 512 max input tokens.
   - **Prefixes**: Prepend `"passage: "` during chunk encoding and `"query: "` during search queries.
   - **Configurability**: Model switching preserved via `settings.EMBEDDING_MODEL_NAME` (fallback: `sentence-transformers/all-MiniLM-L6-v2`).
2. **Pipeline Trigger**: **Explicit Processing Endpoint (`POST /api/v1/documents/{doc_id}/process`)**
   - Preserves existing Phase 2 upload behavior (`POST /upload` returns status `PROCESSED`).
   - Decouples document ingestion from computationally heavy transformer inference.
   - Allows independent retry of failed embedding operations.
3. **Rigorous Scope Constraints**:
   - Zero FAISS index building in this phase (deferred to Phase 4).
   - Zero Gemini LLM API calls in this phase (deferred to Phase 5).
   - Zero frontend components in this phase.
   - Zero real institutional documents or fabricated policies; testing exclusively uses synthetic PDF fixtures.

---

## 2. Authoritative SQLite Concurrency Lock

To prevent two simultaneous processing requests from racing or an outdated worker from overwriting a newer processing attempt across multiple workers or processes:

### 2.1 Short-Transaction CAS Lock Acquisition
The lock is acquired in a **dedicated, short SQLite transaction** *before* model inference begins:

```sql
BEGIN IMMEDIATE;

UPDATE documents
SET status = 'PROCESSING_EMBEDDINGS',
    staged_tx_id = :tx_id,
    updated_at = :now_iso
WHERE doc_id = :doc_id
  AND status IN ('PROCESSED', 'FAILED');

COMMIT;
```

### 2.2 Concurrency Evaluation & State Responses
- **Lock Acquired (`rowcount == 1`)**: The worker records `staged_tx_id = tx_id` and proceeds to in-memory chunking and model inference.
- **Lock Denied (`rowcount == 0`)**: Inspects current document status:
  - If current `status == 'PROCESSING_EMBEDDINGS'`: Return **HTTP 409 Conflict** with payload:
    `{"detail": "Document is currently being processed by another worker. Please retry after completion."}`
  - If current `status == 'INDEXED'`: Return **HTTP 400 Bad Request** (`{"detail": "Document is already indexed. Pass force=true to re-index."}`).
  - If current `status == 'DELETING'`: Return **HTTP 400 Bad Request** (`{"detail": "Document is undergoing deletion."}`).

### 2.3 Strict Outdated Worker Rejection
Every subsequent database update verifying processing progress, chunk insertion, or final status completion enforces:
```sql
WHERE doc_id = :doc_id AND staged_tx_id = :tx_id
```
If a worker was stalled or delayed and another retry took over, `staged_tx_id` will no longer match. The outdated worker's database write will fail with `rowcount == 0` and abort immediately without overwriting the newer attempt.
*(Note: `asyncio.Lock` is strictly an optional in-process optimization; SQLite remains the single authoritative lock across all processes and cluster workers).*

---

## 3. Per-File Transaction Manifest Protocol

To achieve true persistence consistency and handle crashes between individual file rotations, every processing run creates a **Per-File Transaction Manifest** persisted at:
`data/processed/{doc_id}_tx_{tx_id}.manifest.json`

### 3.1 Manifest Schema
```json
{
  "tx_id": "9b1deb4d3b7d4bad9bdd2b0d7b3dcb6d",
  "doc_id": "85731e3a-f24a-4acb-aacb-487cd0aacb61",
  "created_at": "2026-11-01T02:15:00Z",
  "stage": "STAGING",
  "db_committed": false,
  "pre_existing_files": {
    "embeddings_npy_existed": true,
    "chunks_json_existed": true
  },
  "staged_files": {
    "embeddings_npy": {
      "path": "data/processed/{doc_id}_embeddings.npy.staged_{tx_id}",
      "sha256": "a3b4c5...",
      "written": true
    },
    "chunks_json": {
      "path": "data/processed/{doc_id}_chunks.json.staged_{tx_id}",
      "sha256": "d6e7f8...",
      "written": true
    }
  },
  "backup_files": {
    "embeddings_npy_backup": "data/processed/{doc_id}_embeddings.npy.backup_{tx_id}",
    "chunks_json_backup": "data/processed/{doc_id}_chunks.json.backup_{tx_id}"
  },
  "active_files": {
    "embeddings_npy": {
      "path": "data/processed/{doc_id}_embeddings.npy",
      "rotated": false
    },
    "chunks_json": {
      "path": "data/processed/{doc_id}_chunks.json",
      "rotated": false
    }
  }
}
```

### 3.2 Transaction Protocol Sequence
1. **Manifest Creation**: Record `tx_id`, `doc_id`, and check which active files physically exist before processing begins.
2. **Staging**:
   - Write `embeddings.npy.staged_{tx_id}` with `allow_pickle=False` and compute SHA-256.
   - Write `chunks.json.staged_{tx_id}` and compute SHA-256.
   - Update manifest `stage = 'STAGED'`.
3. **Pre-Commit Safe Backup & Rotation**:
   - Update manifest `stage = 'ROTATING'`.
   - **For Embeddings Matrix**:
     - If `pre_existing_files.embeddings_npy_existed == true`: Rename active to `.backup_{tx_id}`.
     - Rename `.staged_{tx_id}` to active `{doc_id}_embeddings.npy`.
     - Update manifest `active_files.embeddings_npy.rotated = true`.
   - **For Chunks JSON**:
     - If `pre_existing_files.chunks_json_existed == true`: Rename active to `.backup_{tx_id}`.
     - Rename `.staged_{tx_id}` to active `{doc_id}_chunks.json`.
     - Update manifest `active_files.chunks_json.rotated = true`.
   - Update manifest `stage = 'ROTATED'`.
4. **SQLite Transaction**:
   - `PRAGMA foreign_keys = ON;`
   - `BEGIN IMMEDIATE;`
   - Verify `staged_tx_id == tx_id`.
   - `DELETE FROM chunks WHERE doc_id = ?;`
   - Batch `INSERT INTO chunks (...) VALUES (...);`
   - `UPDATE documents SET status = 'INDEXED', total_chunks = N, staged_tx_id = NULL, active_tx_id = :tx_id WHERE doc_id = :doc_id AND staged_tx_id = :tx_id;`
   - `COMMIT;`
5. **Finalization**:
   - Update manifest `db_committed = true` and `stage = 'FINALIZING'`.
   - Unlink `.backup_{tx_id}` files if they existed.
   - Unlink manifest file.

---

## 4. Crash-Recovery Scenario Matrix

| Interruption / Crash Point | State in SQLite (`documents`) | Manifest & Filesystem State | Exact Deterministic Recovery Action | Resulting System State |
|---|---|---|---|---|
| **Crash Point 1**:<br/>During in-memory chunking or model inference | `status = 'PROCESSING_EMBEDDINGS'`<br/>`staged_tx_id = '{tx_id}'` | Manifest in `STAGING`. No `.staged_*` files yet. Prior active files intact. | Manifest indicates no rotation occurred. Reset SQLite `status = 'PROCESSED'`. Unlink manifest. | Safe. Document ready for retry. Prior valid files intact. |
| **Crash Point 2**:<br/>During or after writing `.staged_{tx_id}` files | `status = 'PROCESSING_EMBEDDINGS'`<br/>`staged_tx_id = '{tx_id}'` | Manifest in `STAGED`. `.staged_{tx_id}` files exist. Active files untouched. | Unlink unreferenced `.staged_{tx_id}` files. Reset SQLite `status = 'PROCESSED'`. Unlink manifest. | Safe. Staged files pruned. Prior valid files intact. |
| **Crash Point 3**:<br/>During file rotation: crash between the two file replacements | `status = 'PROCESSING_EMBEDDINGS'`<br/>`staged_tx_id = '{tx_id}'` | Manifest in `ROTATING`: `embeddings_npy.rotated = true`, but `chunks_json.rotated = false`. `.backup_{tx_id}` exists for embeddings. | **Per-File Rollback using Manifest**: Consults `active_files` flags. Replaces active `embeddings.npy` with its `.backup_{tx_id}`. Unlinks remaining `.staged_{tx_id}`. Reset `status = 'PROCESSED'`. | Safe. Asymmetric rotation cleanly reverted. Previous valid state preserved. |
| **Crash Point 4**:<br/>After both file rotations, before SQLite commit | `status = 'PROCESSING_EMBEDDINGS'`<br/>`staged_tx_id = '{tx_id}'` | Manifest in `ROTATED`: `db_committed = false`. Both active files are new, both `.backup_{tx_id}` files exist. | **Full Rollback using Manifest**: Restore each pre-existing active file from its corresponding `.backup_{tx_id}`. Delete uncommitted new files. Reset `status = 'PROCESSED'`. | Safe. Files restored to pre-transaction state matching uncommitted database. |
| **Crash Point 5**:<br/>During SQLite commit failure / rollback | SQLite rolled back to `PROCESSING_EMBEDDINGS`. | Manifest `db_committed = false`. Both `.backup_{tx_id}` files exist. | **Rollback Execution**: Restores active files from backups. Unlinks failed files. Reset SQLite `status = 'FAILED'` with error details. | Safe. Database and filesystem remain 100% consistent. |
| **Crash Point 6**:<br/>After SQLite commit, before backup deletion | `status = 'INDEXED'`<br/>`active_tx_id = '{tx_id}'`<br/>`staged_tx_id = NULL` | Manifest `db_committed = true`. New active files in place. Residual `.backup_{tx_id}` files exist. | **Checksum Verification & Finalize**: Verify active files match manifest SHA-256. Unlink residual `.backup_{tx_id}` files. Unlink manifest. | Safe. Confirmed valid transaction preserved; stale backup garbage cleaned. |
| **Crash Point 7**:<br/>Recovery cannot establish consistent state (e.g. backup missing/corrupted during rollback) | Inconsistent or corrupted state detected during recovery. | Files present but checksum mismatch or missing backup file. | **Non-Destructive Quarantine**: Do NOT delete files. Rename files to `.quarantine_{tx_id}`. Mark SQLite `status = 'MANUAL_RECOVERY_REQUIRED'`. Log urgent admin alert. | Safe. Potentially valid data is preserved for inspection; no silent data destruction. |
| **Crash Point 8**:<br/>Server crash during document deletion | `status = 'DELETING'` | Some files unlinked, some remaining. SQLite row present. | Retries unlinking residual files. Deletes SQLite row. | Safe. Cascading deletion completes cleanly. Zero orphan files. |

---

## 5. State-Driven Startup Recovery Ordering & Quarantine Safety

The startup recovery scanner (`startup_recovery_scan`) runs on backend boot **before** any incoming HTTP traffic is accepted:

1. **Ordering Rule**: Transaction recovery logic runs **first** to evaluate transaction states before any files are pruned. Files are never deleted solely based on an arbitrary timer.
2. **Transaction Classification**:
   - Query all documents from SQLite: `SELECT doc_id, status, active_tx_id, staged_tx_id FROM documents;`
   - Scan `data/processed/` directory for all manifest files (`*.manifest.json`) and associated artifacts:
     - **Committed Transactions (`db_committed == true`)**:
       - Verify active files match manifest `staged_files` checksums.
       - If verified, unlink residual `.backup_*` files and remove manifest.
     - **Incomplete Transactions (`db_committed == false`)**:
       - Execute exact per-file rollback using manifest `active_files.rotated` flags.
       - Restore backed-up files.
       - Reset SQLite status to `PROCESSED`.
     - **In-Flight Deletions (`status == 'DELETING'`)**:
       - Unlink all residual document files and finalize SQLite row deletion.
3. **Non-Destructive Quarantine Protocol**:
   - If recovery cannot establish a verified safe rollback (e.g., checksum mismatch or missing backup):
     - The recovery scanner **never deletes the data**.
     - Files are moved to `data/processed/{doc_id}.quarantine_{tx_id}/`.
     - Document status is set to `'MANUAL_RECOVERY_REQUIRED'`.
     - An alert is logged detailing the exact manifest discrepancy.

---

## 6. Exact Dynamic Tokenizer Accounting & Block Provenance

### 6.1 Dynamic Budget Formulation
The token budget is calculated dynamically at runtime via the active model's tokenizer without hardcoding prefix counts:
```python
def calculate_effective_token_budget(tokenizer, prefix: str = "passage: ") -> int:
    model_max_len = tokenizer.model_max_length  # 512 for E5
    special_tokens_count = len(tokenizer.build_inputs_with_special_tokens([]))  # 2 for <s>/</s>
    prefix_tokens_count = len(tokenizer.encode(prefix, add_special_tokens=False))
    return model_max_len - special_tokens_count - prefix_tokens_count
```
- **Validation**: `CHUNK_SIZE_TOKENS` (default: 380 tokens) is validated on startup against `calculate_effective_token_budget`.
- **Pre-Inference Assertion**:
  `full_input = prefix + chunk.text`  
  `assert len(tokenizer.encode(full_input, add_special_tokens=True)) <= model_max_len`  
  Silent truncation is strictly prohibited.

### 6.2 Composite Block Provenance
To avoid ambiguity from PyMuPDF block numbers restarting on each page, structural block references are stored as composite objects:
```json
"blocks": [
  {
    "page_number": 2,
    "block_index": 3,
    "bbox": [54.0, 120.0, 540.0, 180.0]
  }
]
```

### 6.3 Short-Chunk Preservation
Chunks are **never** discarded based on having fewer than 30 tokens. Critical institutional facts (office hours, fees, deadlines, room numbers) are preserved. Chunks are discarded only if they contain **zero alphanumeric characters**.

---

## 7. Deployment Compatibility & Model Caching (Local & Render)

1. **Configurable Cache Path**:
   `MODEL_CACHE_DIR`: Configured in `Settings` as `settings.MODEL_CACHE_DIR or os.getenv("HF_HOME", "data/models")`. In local development, weights persist permanently in `data/models/` or standard Hugging Face cache.
2. **Render Deployment Strategy**:
   - *Option A (Persistent Disk)*: Attach a Render Persistent Disk mounted at `/var/data` and configure `HF_HOME=/var/data/huggingface`. Cache survives all redeployments and restarts.
   - *Option B (Ephemeral with Graceful Cold-Start)*: If running on free/ephemeral tier without a disk, set `HF_HUB_DOWNLOAD_TIMEOUT = 120`s. Lazy initialization inside `POST /documents/{doc_id}/process` ensures that document uploads (`POST /upload`) and health checks (`GET /health`) are **never blocked or slowed down** by model downloading. If a timeout occurs, returns HTTP 503.

---

## 8. HTTP Error Handling Contract

| HTTP Status Code | Category | Trigger Scenario | API Error Detail Message |
|---|---|---|---|
| **400 Bad Request** | Client / Document State Error | Document has 0 pages, 0 extractable text, or is currently in `DELETING` status. | `"Cannot process document: document is empty or undergoing deletion."` |
| **404 Not Found** | Client Resource Error | Target `doc_id` does not exist in SQLite registry. | `"Document with ID '{doc_id}' not found."` |
| **409 Conflict** | Concurrency State Conflict | Document is already actively undergoing processing by another worker (`status == 'PROCESSING_EMBEDDINGS'`). | `"Document is currently being processed by another worker. Please retry after completion."` |
| **500 Internal Server Error** | Unexpected System Failure | Unhandled I/O failure, disk full, or corrupted intermediate JSON. | `"Internal processing error during chunk generation or persistence."` |
| **503 Service Unavailable** | Infrastructure / Model Failure | Model weights download timeout, Hugging Face Hub unreachable, PyTorch OOM, or model initialization failure. | `"Embedding model service unavailable. Unable to load model weights."` |

---

## 9. Performance & Dual Memory Measurement Protocol

### 9.1 Dual Memory Instrumentation
Every benchmark report records:
- **Python Heap Delta**: Measured via `tracemalloc.get_traced_memory()` (Python-level memory allocation delta in MB).
- **Process Resident Set Size (RSS) Delta**: Measured via `psutil.Process().memory_info().rss` (OS-level physical RAM delta in MB, capturing native C++/PyTorch/BLAS allocations).

### 9.2 Benchmark Test Procedure
1. **Warm-Up**: 10 inference passes on a fixed synthetic passage.
2. **Measurement**: 50 consecutive runs over a fixed test batch of 32 synthetic chunks (~150 tokens each).
3. **Reported Metrics**: Throughput (chunks/sec, tokens/sec), Latencies (P50, P95, mean, std in ms), and Dual Memory Deltas (Heap MB & RSS MB).

---

## 10. Target File Modifications & Creations

```text
UniMind/
├── requirements.txt                      [VERIFY] psutil (installed), sentence-transformers, torch
│
├── backend/app/
│   ├── core/
│   │   └── config.py                     [MODIFY] EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small",
│   │                                              CHUNK_SIZE_TOKENS = 380, CHUNK_OVERLAP_TOKENS = 40,
│   │                                              EMBEDDING_BATCH_SIZE = 32, MODEL_CACHE_DIR
│   ├── models/
│   │   └── schemas.py                    [MODIFY] Add DocumentChunk, BlockReference, DocumentProcessResponse
│   ├── rag/
│   │   ├── __init__.py                   [MODIFY] Export chunker and embedder
│   │   ├── chunker.py                    [CREATE] Dynamic token-budget recursive chunker, short-chunk preservation
│   │   └── embedder.py                   [CREATE] E5/MiniLM embedder, dynamic prefixing, L2 normalizer, validator
│   ├── services/
│   │   ├── __init__.py                   [MODIFY] Export embedding_service
│   │   ├── document_service.py           [MODIFY] SQLite chunks table with CASCADE, startup recovery hook
│   │   └── embedding_service.py          [CREATE] Manifest-driven persistence, CAS concurrency guard, stateful deletion
│   └── routes/
│       └── documents.py                  [MODIFY] Add POST /{doc_id}/process, update DELETE with stateful recovery
│
└── tests/
    ├── test_chunker.py                   [CREATE] Unit tests for dynamic token budget, short chunks, cross-page flow
    ├── test_embedder_unit.py             [CREATE] Fast unit tests using MockEmbeddingModel
    ├── test_embedder_integration.py      [CREATE] Live E5 model inference, L2 norm, tolerance check
    └── test_embedding_service.py         [CREATE] Manifest-driven recovery, crash scenarios 1-8, CAS conflict check
```

---

*Phase 3 Planning Document v3.2 finalized. Per-file manifest protocol, authoritative SQLite concurrency lock, non-destructive quarantine, and complete crash-recovery matrix documented. No code has been modified or written. Awaiting explicit user approval to proceed with implementation.*
