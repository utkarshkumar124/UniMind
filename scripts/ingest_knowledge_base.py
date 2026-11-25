"""Render the UniMind LPU knowledge base markdown files into structured PDFs,
ingest and embed them via DocumentService + EmbeddingService, and commit a unified
FAISS IndexIDMap2 generation bundle into vector_store/.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import faiss
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import settings
from backend.app.rag.vector_store import vector_store_service
from backend.app.services.document_service import document_service
from backend.app.services.embedding_service import embedding_service

KB_DIR = ROOT_DIR / "knowledge_base"
OUT_PDF_DIR = ROOT_DIR / "data" / "kb_pdfs"


def register_fonts() -> Tuple[str, str]:
    """Register Unicode-capable Arial fonts on Windows so symbols like INR render cleanly."""
    win_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    regular_ttf = win_fonts / "arial.ttf"
    bold_ttf = win_fonts / "arialbd.ttf"
    if regular_ttf.exists() and bold_ttf.exists():
        pdfmetrics.registerFont(TTFont("UniSans", str(regular_ttf)))
        pdfmetrics.registerFont(TTFont("UniSans-Bold", str(bold_ttf)))
        return "UniSans", "UniSans-Bold"
    return "Helvetica", "Helvetica-Bold"


HANDBOOK_BUNDLES: List[Dict[str, Any]] = [
    {
        "filename": "lpu_university_overview_and_contacts.pdf",
        "title": "Lovely Professional University (LPU) — Overview, Schools & Official Contacts",
        "department": "Administration",
        "category": "Overview",
        "files": [
            "index.md",
            "university/overview.md",
            "university/departments_and_schools.md",
            "university/campus_facilities.md",
            "university/contacts.md",
        ],
    },
    {
        "filename": "lpu_academics_and_calendar_2026_27.pdf",
        "title": "LPU Academic System, 2026-2027 Calendar, Curriculum & Registration",
        "department": "Academic Affairs",
        "category": "Curriculum",
        "files": [
            "academics/academic_calendar.md",
            "academics/academic_system.md",
            "academics/course_registration.md",
            "academics/curriculum.md",
            "academics/academic_progression.md",
        ],
    },
    {
        "filename": "lpu_attendance_policy.pdf",
        "title": "LPU Attendance Policy, Calculation, Duty Leave & Detention Rules",
        "department": "Academic Affairs",
        "category": "Policy",
        "files": [
            "academics/attendance_policy.md",
            "faq/academics_faq.md",
        ],
    },
    {
        "filename": "lpu_examinations_and_grading.pdf",
        "title": "LPU Examinations, CA/MTT/ETE Evaluation, Grading, CGPA & Reappear Rules",
        "department": "Examinations",
        "category": "Regulation",
        "files": [
            "examinations/evaluation_system.md",
            "examinations/grading_and_cgpa.md",
            "examinations/examination_rules.md",
            "examinations/reappear_and_backlog.md",
            "examinations/results_and_appeals.md",
        ],
    },
    {
        "filename": "lpu_hostel_and_mess_handbook_2026_27.pdf",
        "title": "LPU Hostel, Residential Fees (2026-2027), Gadgets, Leave & Mess Guide",
        "department": "Residential Services",
        "category": "Hostel",
        "files": [
            "student_services/hostel.md",
            "student_services/mess.md",
            "faq/hostel_faq.md",
        ],
    },
    {
        "filename": "lpu_campus_services_medical_library_transport.pdf",
        "title": "LPU Campus Services — Medical (Uni Health Centre), Library, Transport, Sports & Welfare",
        "department": "Student Services",
        "category": "Services",
        "files": [
            "student_services/medical_services.md",
            "student_services/library.md",
            "student_services/transport.md",
            "student_services/sports_and_gym.md",
            "student_services/student_welfare.md",
        ],
    },
    {
        "filename": "lpu_fees_scholarships_and_refunds_2026_27.pdf",
        "title": "LPU Tuition & Exam Fees (2026), Scholarships, Payments, Loans & Refund Policy",
        "department": "Finance & Accounts",
        "category": "Finance",
        "files": [
            "finance/fee_structure.md",
            "finance/scholarships.md",
            "finance/payments.md",
            "finance/refund_policy.md",
        ],
    },
    {
        "filename": "lpu_placements_and_career_services.pdf",
        "title": "LPU Placements, Internships & Centre for Professional Enhancement (CPE)",
        "department": "Career Services",
        "category": "Placements",
        "files": [
            "careers/placements.md",
            "careers/internships.md",
            "careers/career_services.md",
        ],
    },
    {
        "filename": "lpu_student_portals_and_digital_services.pdf",
        "title": "LPU Digital Services — UMS, MyClass, LPU Live, LPU Touch & Portal Directory",
        "department": "IT & Digital Services",
        "category": "Portals",
        "files": [
            "portals/digital_services.md",
            "portals/portal_directory.md",
        ],
    },
    {
        "filename": "lpu_policies_discipline_anti_ragging_grievance.pdf",
        "title": "LPU Student Conduct, Disciplinary Rules, Anti-Ragging, ICC, Grievances & Campus Life",
        "department": "Student Welfare",
        "category": "Policy",
        "files": [
            "policies/student_policies.md",
            "policies/grievance_redressal.md",
            "policies/anti_ragging.md",
            "policies/disciplinary_rules.md",
            "campus_life/rules_and_conduct.md",
            "campus_life/clubs_and_societies.md",
            "campus_life/events.md",
        ],
    },
    {
        "filename": "lpu_comprehensive_student_faqs.pdf",
        "title": "Lovely Professional University (LPU) — Comprehensive Verified Student FAQs",
        "department": "Student Welfare",
        "category": "FAQ",
        "files": [
            "faq/general_faq.md",
            "faq/examination_faq.md",
            "faq/finance_faq.md",
        ],
    },
]


def clean_inline_md(text: str, use_ascii_fallback: bool) -> str:
    """Convert inline markdown formatting to safe ReportLab XML-escaped text."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Clean LaTeX inline markers into readable plain text
    text = text.replace("$$", "").replace("$", "")
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1) / (\2)", text)
    text = text.replace(r"\sum", "Sum").replace(r"\times", "x").replace(r"\div", "/")
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    if use_ascii_fallback:
        text = text.replace("₹", "Rs. ").replace("—", "-").replace("–", "-").replace("→", "->").replace("≥", ">=")
    return text


def render_bundle_pdf(bundle: Dict[str, Any], out_path: Path, font_reg: str, font_bold: str) -> bytes:
    """Render a group of markdown documents into a clean, text-extractable PDF."""
    use_ascii = font_reg == "Helvetica"
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=15,
        leading=19,
        spaceAfter=8,
    )
    h1_style = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=13,
        leading=17,
        spaceBefore=10,
        spaceAfter=4,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=11,
        leading=15,
        spaceBefore=8,
        spaceAfter=3,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=font_reg,
        fontSize=9.5,
        leading=13.5,
        spaceAfter=4,
    )

    story: List[Any] = []
    skip_sources_block = False

    meta_prefixes = (
        "Title:",
        "Category:",
        "Last verified:",
        "Applicable academic year/session:",
        "Source reliability:",
        "Status:",
    )

    for rel_path in bundle["files"]:
        md_path = KB_DIR / rel_path
        lines = md_path.read_text(encoding="utf-8").splitlines()
        skip_sources_block = False
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(meta_prefixes):
                continue
            if line.lower().startswith("## sources") or line.lower().startswith("# sources"):
                skip_sources_block = True
                continue
            if skip_sources_block:
                if line.startswith("#") and not line.lower().startswith("## sources"):
                    skip_sources_block = False
                else:
                    continue
            if line in ("## Direct Answer", "## Overview"):
                continue
            # Skip pure markdown separator rows like |---|---|
            if re.fullmatch(r"\|[\s:\-|]+\|", line):
                continue
            # Convert markdown table rows into readable lines ending with a period
            if line.startswith("|") and line.endswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                line = " — ".join(cells) + "."
            # Prevent URLs or portal domains from causing fake sentence splits on '.' inside extractive QA
            line = re.sub(r"`?https?://[^\s\)\"`]+`?", "official LPU portal", line)
            line = line.replace("ums.lpu.in", "UMS portal").replace("myclass.lpu.in", "MyClass portal").replace("lpulive.lpu.in", "LPU Live portal").replace("admission.lpu.in", "LPUAdmit portal").replace("lpu.in", "LPU official website")
            if line.startswith("# "):
                heading_txt = line[2:].strip()
                if not heading_txt.endswith((":", ".", "?")):
                    heading_txt += ":"
                story.append(Paragraph(clean_inline_md(heading_txt, use_ascii), h1_style))
            elif line.startswith("## ") or line.startswith("### "):
                heading_txt = line.lstrip("#").strip()
                if not heading_txt.endswith((":", ".", "?")):
                    heading_txt += ":"
                story.append(Paragraph(clean_inline_md(heading_txt, use_ascii), h2_style))
            else:
                if line.startswith("> "):
                    line = line[2:].strip()
                elif line.startswith("- "):
                    line = "• " + line[2:].strip()
                if not line.endswith((".", "!", "?", ":")):
                    line += "."
                story.append(Paragraph(clean_inline_md(line, use_ascii), body_style))
        story.append(Spacer(1, 4 * mm))

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    doc.build(story)
    return out_path.read_bytes()


def main() -> None:
    OUT_PDF_DIR.mkdir(parents=True, exist_ok=True)
    font_reg, font_bold = register_fonts()
    print(f"Using PDF fonts: regular={font_reg}, bold={font_bold}")

    ingested_docs: List[Dict[str, Any]] = []
    for bundle in HANDBOOK_BUNDLES:
        pdf_path = OUT_PDF_DIR / bundle["filename"]
        pdf_bytes = render_bundle_pdf(bundle, pdf_path, font_reg, font_bold)
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        doc_record = document_service.ingest_document(
            file_bytes=pdf_bytes,
            filename=bundle["filename"],
            file_hash=file_hash,
            department=bundle["department"],
            category=bundle["category"],
        )
        doc_id = doc_record["doc_id"]
        is_dup = doc_record.get("is_duplicate", False)
        print(f"Ingested {bundle['filename']} -> doc_id={doc_id} (duplicate={is_dup})")

        existing_chunks_path = Path(settings.DATA_PROCESSED_DIR) / f"{doc_id}_chunks.json"
        existing_emb_path = Path(settings.DATA_PROCESSED_DIR) / f"{doc_id}_embeddings.npy"
        if doc_record.get("status") == "INDEXED" and existing_chunks_path.exists() and existing_emb_path.exists():
            print(f"  Already indexed: {doc_id}")
        else:
            res = embedding_service.process_document(doc_id=doc_id, force=True)
            print(f"  Embedded {res.total_chunks} chunks in {res.processing_time_seconds:.2f} s")
        ingested_docs.append(doc_record)

    # Build combined FAISS IndexIDMap2 generation across all INDEXED documents
    flat_index = faiss.IndexFlatIP(settings.EMBEDDING_DIMENSION)
    index = faiss.IndexIDMap2(flat_index)

    int_to_chunk_id: Dict[int, str] = {}
    chunk_id_to_int: Dict[str, int] = {}
    doc_id_to_chunk_ids: Dict[str, List[str]] = {}
    chunk_metadata: Dict[str, Dict[str, Any]] = {}
    next_id = 1

    all_vectors: List[np.ndarray] = []
    all_ids: List[int] = []

    for doc_rec in ingested_docs:
        doc_id = doc_rec["doc_id"]
        chunks_path = Path(settings.DATA_PROCESSED_DIR) / f"{doc_id}_chunks.json"
        emb_path = Path(settings.DATA_PROCESSED_DIR) / f"{doc_id}_embeddings.npy"
        chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
        embs = np.load(emb_path).astype(np.float32)

        if len(chunks_data) != embs.shape[0]:
            raise RuntimeError(f"Chunk/embedding count mismatch for {doc_id}: {len(chunks_data)} vs {embs.shape[0]}")

        doc_chunk_ids: List[str] = []
        for idx, chunk in enumerate(chunks_data):
            chunk_id = chunk["chunk_id"]
            faiss_id = next_id
            next_id += 1

            int_to_chunk_id[faiss_id] = chunk_id
            chunk_id_to_int[chunk_id] = faiss_id
            doc_chunk_ids.append(chunk_id)
            chunk_metadata[chunk_id] = {
                "text": chunk["text"],
                "doc_id": doc_id,
                "filename": chunk.get("filename", doc_rec["filename"]),
                "department": chunk.get("department", doc_rec["department"]),
                "category": chunk.get("category", doc_rec["category"]),
                "page_start": int(chunk.get("page_start", 1)),
                "page_end": int(chunk.get("page_end", chunk.get("page_start", 1))),
            }
            all_vectors.append(embs[idx])
            all_ids.append(faiss_id)

        doc_id_to_chunk_ids[doc_id] = doc_chunk_ids

    matrix = np.vstack(all_vectors).astype(np.float32)
    id_array = np.array(all_ids, dtype=np.int64)
    index.add_with_ids(matrix, id_array)

    meta_payload = {
        "int_to_chunk_id": int_to_chunk_id,
        "chunk_id_to_int": chunk_id_to_int,
        "doc_id_to_chunk_ids": doc_id_to_chunk_ids,
        "chunk_metadata": chunk_metadata,
        "next_id": next_id,
    }
    parent_gen = vector_store_service.active_generation_id
    snapshot = vector_store_service.commit_generation_bundle(
        index=index,
        metadata=meta_payload,
        parent_generation_id=parent_gen,
    )
    print(
        f"\nCOMMITTED generation={snapshot.generation_id} | "
        f"docs={snapshot.total_documents} | chunks={snapshot.total_chunks} | vectors={snapshot.total_vectors}"
    )


if __name__ == "__main__":
    main()
