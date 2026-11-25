Title: Autonomous Research Log — LPU Knowledge Base
Category: Sources & Provenance
Last verified: 2026-11-25
Applicable academic year/session: 2026–2027
Source reliability: Process & Verification Audit Log
Status: Verified

# Autonomous Research & Verification Log

## Execution Date: 2026-11-25

### Phase 1: Codebase & RAG Discovery
- Inspected `backend/app/core/config.py`, `backend/app/services/document_service.py`, `backend/app/services/embedding_service.py`, `backend/app/rag/chunker.py`, `backend/app/rag/vector_store.py`, and `backend/app/rag/retriever.py`.
- Confirmed UniMind ingests `.pdf` documents via `DocumentService` + `EmbeddingService` (`intfloat/multilingual-e5-small`, 384-d embeddings, 380-token hierarchical chunks, 40-token overlap) into `data/processed/` + SQLite + FAISS `IndexIDMap2` bundles under `vector_store/generations/`.
- Confirmed no `knowledge_base/` directory existed prior to this session (`vector_store/current_generation.json` held a 3-chunk test bundle).

### Phase 2: Primary Research & Direct Verification (`lpu.in` + `webapi.lpu.in`)
1. **Link Discovery & HTTP 404 Trap Detection:**
   - Discovered that non-existent `.php` paths on `www.lpu.in` silently return HTTP 200 redirected to `https://www.lpu.in/404.php`. Added explicit `"/404.php" not in final_url` filtering across all automated page fetches so no 404 boilerplate contaminated research data.
2. **Direct Fetching of 31 Official LPU Pages:**
   - Scraped and inspected 31 official `200 OK` pages across Academics, Calendar 2026–27, Holiday List 2026, Libraries, Assessment/Evaluation, Residence, Transport, Healthcare, Security, Shopping/Dining, Banking/Postal, Education Loans, UMS, Scholarships, Placements, CPE Career Enhancement, Student Organizations, Campus Events, Sports, Anti-Ragging, Grievance Redressal, Contacts, Accreditations, Infrastructure, Overview, and Migration.
3. **Official Programme Fee API Inspection (`webapi.lpu.in`):**
   - Inspected `prog-search.js` and queried `https://webapi.lpu.in/webProgrammes/api/ProgramSearch/GetProgramFeeDetail` directly for B.Tech. CSE (`P132`), MBA (`P371-NNAF`), and BBA (`P321`), resolving client-side empty table cells and verifying exact 2026 tuition fees (₹1,60,000 / ₹2,20,000 / ₹80,000 per semester), ₹5,000/semester examination fee, ₹4,000 uniform fee, admission phase dates, and successive semester payment rules.

### Phase 3: Conflicts & Verification Boundaries Resolved
- **B.Tech. CSE Tuition Fee Variation:** Secondary search snippets cited outdated ₹1,20,000–₹1,40,000 figures for non-CSE branches or older cohorts. **Resolved cleanly in favor of Tier-2 Official LPU Fee API (`P132` = ₹1,60,000/sem for Admission 2026 Regular)** while noting cohort/specialization variance.
- **Exam Fee:** Older secondary posts cited ₹4,000–₹4,500. **Verified on official `webapi.lpu.in` API as ₹5,000 per semester** for 2026 Indian intakes (with SAARC international exam fee ₹4,500).
- **CCTV Count Slight Variance:** `security.php` states `7200+ CCTV Cameras` in a card badge and `more than 7400 CCTV cameras` in prose on the same page; both official figures are noted transparently.
- **Login-Gated UMS Internal Ordinances Identified & Not Hallucinated:**
  - Exact numeric Academic Ordinance tables (e.g., per-credit backlog promotion thresholds, UMC category punishment table, exact relative-grading grade boundaries, exact per-paper reappear fee, 2026–27 specific mess fee slab, and block-specific hostel curfew minutes) sit behind authenticated `ums.lpu.in` / `admission.lpu.in` logins and are **explicitly marked as Partially Verified / Not verified from an official public source**, directing students to UMS E-Notices & Ordinances rather than inventing unverified numbers.

### Phase 4 & 5: Ingestion into UniMind RAG Pipeline
- Rendered the curated markdown domains into **11 clean structured PDF handbooks** in `data/kb_pdfs/` via `scripts/ingest_knowledge_base.py`.
- Ingested via `document_service.ingest_document` and embedded with `intfloat/multilingual-e5-small` via `embedding_service.process_document` (`104 chunks`, `104 dense 384-d vectors`).
- Committed immutable FAISS `IndexIDMap2` bundle `gen_20261124_205209_028e10ac` and restarted the FastAPI backend (`embedding_status: READY`).

### Phase 6: Live Retrieval & QA Verification
- Verified `GET /health` (`status: healthy`, `embedding_status: READY`) and `GET /api/v1/documents` (11 `INDEXED` documents matching all LPU departments).
- Executed 10 test queries against `POST /api/v1/query` (`20–38 ms` HTTP response time) covering Attendance, CGPA formula, Reappear dates & filing, Detention/Backlog, Results & Scrutiny, 2026–27 Hostel & Appliances, Fee Payment deadlines, Placements, Course Registration/Minors, and an unverified/out-of-scope check, plus `POST /api/v1/chat` (`24 ms`, 4 cited sources). All relevant queries retrieved their target official LPU handbook chunks.

