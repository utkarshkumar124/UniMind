"""Script to generate Phase 2 Planning PDF Report."""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#6b7280"))
        if self._pageNumber > 1:
            self.drawString(40, 755, "UniMind - Phase 2 Planning: Document Ingestion Engine")
            self.setStrokeColor(colors.HexColor("#e5e7eb"))
            self.setLineWidth(0.5)
            self.line(40, 748, 572, 748)
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(572, 25, page_str)
        self.drawString(40, 25, "UniMind AI Knowledge Assistant | Group G21 - Phase 2 Architecture")
        self.setStrokeColor(colors.HexColor("#e5e7eb"))
        self.setLineWidth(0.5)
        self.line(40, 35, 572, 35)
        self.restoreState()


def build_phase2_plan_pdf(output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=45,
        bottomMargin=45,
    )

    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("T", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#1e3a8a"))
    sub_s = ParagraphStyle("Sub", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=colors.HexColor("#2563eb"))
    meta_s = ParagraphStyle("M", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=colors.HexColor("#4b5563"))
    h1_s = ParagraphStyle("H1", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=colors.HexColor("#1e3a8a"), spaceBefore=7, spaceAfter=3)
    body_s = ParagraphStyle("B", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#1f2937"))
    code_s = ParagraphStyle("C", parent=styles["Normal"], fontName="Courier", fontSize=7, leading=9, textColor=colors.HexColor("#111827"))
    th_s = ParagraphStyle("TH", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white)
    tc_s = ParagraphStyle("TC", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#1f2937"))

    story = []
    story.append(Paragraph("UniMind 📄 - Phase 2 Implementation Plan", title_s))
    story.append(Spacer(1, 2))
    story.append(Paragraph("Subsystem: Document Ingestion, PyMuPDF Parsing & Metadata Engine", sub_s))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Author:</b> Antigravity AI Engineering Assistant &nbsp;|&nbsp; <b>Team:</b> Group G21", meta_s))
    story.append(Paragraph("<b>Status:</b> <font color='#2563eb'><b>PROPOSED ARCHITECTURE (AWAITING APPROVAL)</b></font> &nbsp;|&nbsp; <b>Date:</b> November 1, 2026", meta_s))
    story.append(Spacer(1, 5))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=7))

    story.append(Paragraph("1. Core Architectural Modules & Planned Files", h1_s))
    modules_data = [
        [Paragraph("Module / Layer", th_s), Paragraph("Target File", th_s), Paragraph("Operational Responsibility", th_s)],
        [Paragraph("Dependencies", tc_s), Paragraph("<code>requirements.txt</code>", tc_s), Paragraph("Add <code>python-multipart>=0.0.9</code> for FastAPI form-data handling.", tc_s)],
        [Paragraph("File Security", tc_s), Paragraph("<code>backend/app/utils/file_validator.py</code>", tc_s), Paragraph("Magic bytes check (<code>b'%PDF-'</code>), MIME type, size limit, filename sanitization.", tc_s)],
        [Paragraph("Text Cleaning", tc_s), Paragraph("<code>backend/app/rag/cleaner.py</code>", tc_s), Paragraph("Unicode NFKC normalization, hyphenation restoration across line breaks, whitespace cleanup.", tc_s)],
        [Paragraph("PyMuPDF Extractor", tc_s), Paragraph("<code>backend/app/rag/parser.py</code>", tc_s), Paragraph("In-memory extraction, structural text blocks, scanned page / image detection, empty page checks.", tc_s)],
        [Paragraph("Document Service", tc_s), Paragraph("<code>backend/app/services/document_service.py</code>", tc_s), Paragraph("Orchestrates upload workflow, raw storage (<code>data/raw/</code>), processed storage (<code>data/processed/</code>).", tc_s)],
        [Paragraph("Schemas", tc_s), Paragraph("<code>backend/app/models/schemas.py</code>", tc_s), Paragraph("DTOs for upload requests, document metadata, page statistics, and error models.", tc_s)],
        [Paragraph("API Endpoints", tc_s), Paragraph("<code>backend/app/routes/documents.py</code>", tc_s), Paragraph("<code>POST /api/v1/documents/upload</code>, <code>GET /api/v1/documents/{id}</code>, <code>GET /api/v1/documents</code>.", tc_s)],
        [Paragraph("Test Suite", tc_s), Paragraph("<code>tests/test_pdf_parser.py</code><br/><code>tests/test_documents_api.py</code>", tc_s), Paragraph("Automated tests using strictly synthetic generated PDFs (standard, empty, corrupt, scanned).", tc_s)],
    ]
    t_mod = Table(modules_data, colWidths=[90, 160, 282])
    t_mod.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t_mod)
    story.append(Spacer(1, 6))

    story.append(Paragraph("2. Security, Scanned Documents & Edge Cases", h1_s))
    edge_data = [
        [Paragraph("Edge Case / Security Threat", th_s), Paragraph("Defensive Strategy & Implementation", th_s)],
        [Paragraph("<b>File Type Spoofing</b>", tc_s), Paragraph("Validates first 5 bytes against PDF signature <code>%PDF-</code>. File extension alone is never trusted.", tc_s)],
        [Paragraph("<b>Path Traversal / Injection</b>", tc_s), Paragraph("Filename sanitized to alphanumeric characters; stored on disk using deterministic UUID4 keys.", tc_s)],
        [Paragraph("<b>Denial of Service (Oversized)</b>", tc_s), Paragraph("Enforces strict 25 MB file limit. Rejects excess payloads immediately with HTTP 413.", tc_s)],
        [Paragraph("<b>Encrypted / Locked PDFs</b>", tc_s), Paragraph("Checks <code>doc.is_encrypted</code> prior to extraction. Returns HTTP 422 with clear diagnostic message.", tc_s)],
        [Paragraph("<b>Scanned Image PDFs</b>", tc_s), Paragraph("Detects pages where extractable text < 50 chars but image count > 0. Flags document with scanned warning.", tc_s)],
        [Paragraph("<b>Empty Documents</b>", tc_s), Paragraph("Detects 0-length text; marks status as <code>EMPTY</code> to prevent polluting downstream vector indexes.", tc_s)],
    ]
    t_edge = Table(edge_data, colWidths=[150, 382])
    t_edge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t_edge)
    story.append(Spacer(1, 6))

    story.append(Paragraph("3. Synthetic Testing Strategy & Implementation Steps", h1_s))
    story.append(Paragraph("<b>Synthetic Document Protocol:</b> To strictly adhere to university compliance constraints, tests will dynamically synthesize test PDFs (Standard Policy Mock, Blank Document, Corrupted Byte Stream, Image-only Mock). Real institutional documents are completely excluded.", body_s))
    story.append(Spacer(1, 4))

    steps_box = [
        [Paragraph("""<b>Step-by-Step Implementation Sequence:</b><br/>
1. <b>Step 2.1:</b> Add <code>python-multipart>=0.0.9</code> to <code>requirements.txt</code> & verify environment.<br/>
2. <b>Step 2.2:</b> Build <code>file_validator.py</code> (magic bytes, MIME check, filename sanitization).<br/>
3. <b>Step 2.3:</b> Build <code>cleaner.py</code> (NFKC normalization, hyphenation restoration, whitespace cleaning).<br/>
4. <b>Step 2.4:</b> Build <code>parser.py</code> using PyMuPDF (block extraction, page metadata, scanned detection).<br/>
5. <b>Step 2.5:</b> Build <code>document_service.py</code> (persistence to <code>data/raw/</code> and <code>data/processed/</code>).<br/>
6. <b>Step 2.6:</b> Define Pydantic request/response schemas in <code>schemas.py</code>.<br/>
7. <b>Step 2.7:</b> Build <code>documents.py</code> router and mount under <code>/api/v1/documents</code>.<br/>
8. <b>Step 2.8:</b> Author synthetic test suites in <code>tests/</code> and run verification.<br/>
9. <b>Step 2.9:</b> Generate Milestone PDF and Markdown completion reports and await approval.""", code_s)]
    ]
    t_steps = Table(steps_box, colWidths=[532])
    t_steps.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_steps)

    doc.build(story, canvasmaker=NumberedCanvas)
    print("Phase 2 Plan PDF generated successfully.")


if __name__ == "__main__":
    out = os.path.abspath(r"documentation\reports\Phase_2_Planning_Document_Ingestion_Engine.pdf")
    build_phase2_plan_pdf(out)

