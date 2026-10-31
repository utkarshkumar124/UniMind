"""Generate Phase 1 Technical Audit Report PDF."""

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
            self.drawString(40, 755, "UniMind - Phase 1 Technical Audit Report")
            self.setStrokeColor(colors.HexColor("#e5e7eb"))
            self.setLineWidth(0.5)
            self.line(40, 748, 572, 748)
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(572, 25, page_str)
        self.drawString(40, 25, "UniMind Technical Audit | Group G21 - Phase 1 Quality Gate")
        self.setStrokeColor(colors.HexColor("#e5e7eb"))
        self.setLineWidth(0.5)
        self.line(40, 35, 572, 35)
        self.restoreState()


def build_audit_pdf(output_path: str):
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
    title_s = ParagraphStyle("T", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#1e3a8a"))
    sub_s = ParagraphStyle("Sub", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=colors.HexColor("#2563eb"))
    meta_s = ParagraphStyle("M", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=colors.HexColor("#4b5563"))
    h1_s = ParagraphStyle("H1", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=colors.HexColor("#1e3a8a"), spaceBefore=8, spaceAfter=4)
    body_s = ParagraphStyle("B", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#1f2937"))
    code_s = ParagraphStyle("C", parent=styles["Normal"], fontName="Courier", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#111827"))
    th_s = ParagraphStyle("TH", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white)
    tc_s = ParagraphStyle("TC", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#1f2937"))

    story = []
    story.append(Paragraph("UniMind 🔍 - Phase 1 Technical Audit Report", title_s))
    story.append(Spacer(1, 2))
    story.append(Paragraph("Architecture, Code Quality, Test Coverage & Security Inspection", sub_s))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Scope:</b> Phase 1 Scaffold & Environment &nbsp;|&nbsp; <b>Audit Date:</b> November 1, 2026", meta_s))
    story.append(Paragraph("<b>Overall Audit Verdict:</b> <font color='#10b981'><b>PASS (READY FOR PHASE 2)</b></font>", meta_s))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=8))

    story.append(Paragraph("1. Inspection Summary & Verification Checklist", h1_s))
    chk_data = [
        [Paragraph("Audit Item", th_s), Paragraph("Target Artifact", th_s), Paragraph("Findings & Verdict", th_s), Paragraph("Status", th_s)],
        [Paragraph("Dependencies & Versions", tc_s), Paragraph("requirements.txt", tc_s), Paragraph("Valid versions; no excess packages. PyMuPDF, FAISS, Sentence-Transformers, Gemini present.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("Configuration & Security", tc_s), Paragraph(".env.example", tc_s), Paragraph("Zero API keys exposed; full 12-factor settings defined for ports, CORS, and paths.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("Application Skeleton", tc_s), Paragraph("backend/app/main.py", tc_s), Paragraph("FastAPI factory, modern lifespan, CORS, and versioned routing correctly configured.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("Settings Architecture", tc_s), Paragraph("backend/app/core/config.py", tc_s), Paragraph("Pydantic BaseSettings with JSON/CSV parser for origins and default fallbacks.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("Router Structure", tc_s), Paragraph("backend/app/routes/api.py", tc_s), Paragraph("Cleanly modular; isolates v1 endpoints under /api/v1 prefix.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("Architectural Integrity", tc_s), Paragraph("documentation/ARCHITECTURE.md", tc_s), Paragraph("Fully aligned with code; documents hallucination control and RAG roadmap.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("Test Coverage & Rigor", tc_s), Paragraph("tests/test_health.py", tc_s), Paragraph("100% of Phase 1 endpoints covered (/, /health, /api/v1/health). All 3 pass.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("Secrets / Leaks Check", tc_s), Paragraph("Entire Repository", tc_s), Paragraph("Regex scan confirmed 0 exposed API keys, credentials, or private tokens.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("Scope Boundaries", tc_s), Paragraph("RAG / LLM / UI", tc_s), Paragraph("No premature RAG logic, Gemini client initialization, or React frontend created.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
        [Paragraph("GitHub Integrity", tc_s), Paragraph("Git status / diff", tc_s), Paragraph("Original README.md, LICENSE, and .gitignore remain 100% intact.", tc_s), Paragraph("<font color='#10b981'><b>PASS</b></font>", tc_s)],
    ]
    t_chk = Table(chk_data, colWidths=[110, 110, 240, 72])
    t_chk.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1e3a8a")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0,0), (-1,-1), 2.5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2.5),
    ]))
    story.append(t_chk)
    story.append(Spacer(1, 8))

    story.append(Paragraph("2. Identified Issues & Severity Analysis", h1_s))
    iss_data = [
        [Paragraph("ID", th_s), Paragraph("Component", th_s), Paragraph("Observation / Potential Risk", th_s), Paragraph("Severity", th_s), Paragraph("Recommendation", th_s)],
        [Paragraph("ISS-01", tc_s), Paragraph("requirements.txt", tc_s), Paragraph("<code>python-multipart</code> is omitted. Required by FastAPI when handling multipart form uploads (e.g. PDF document uploads in Phase 2).", tc_s), Paragraph("<font color='#eab308'><b>LOW</b></font><br/>(Phase 2)", tc_s), Paragraph("Add <code>python-multipart>=0.0.9</code> before implementing PDF upload endpoint.", tc_s)],
        [Paragraph("ISS-02", tc_s), Paragraph("config.py / main.py", tc_s), Paragraph("<code>ALLOWED_ORIGINS</code> validator falls back to <code>['*']</code> on invalid formats. When <code>allow_credentials=True</code>, browsers reject wildcard origin.", tc_s), Paragraph("<font color='#eab308'><b>LOW</b></font><br/>(Security)", tc_s), Paragraph("Fallback to explicit defaults <code>['http://localhost:3000']</code> instead of wildcard <code>['*']</code>.", tc_s)],
        [Paragraph("ISS-03", tc_s), Paragraph("config.py", tc_s), Paragraph("<code>GEMINI_API_KEY</code> is typed as plain <code>str</code> rather than <code>SecretStr</code>. Potential accidental leakage in debug logs or repr().", tc_s), Paragraph("<font color='#6b7280'><b>INFO</b></font><br/>(Best Practice)", tc_s), Paragraph("Upgrade to <code>pydantic.SecretStr</code> in Phase 3 when LLM authentication is wired.", tc_s)],
        [Paragraph("ISS-04", tc_s), Paragraph("main.py vs health.py", tc_s), Paragraph("Duplicate health response logic: <code>/health</code> defined in <code>main.py</code> and <code>/api/v1/health</code> defined in <code>health.py</code>.", tc_s), Paragraph("<font color='#6b7280'><b>INFO</b></font><br/>(Code Quality)", tc_s), Paragraph("Refactor <code>main.py</code> to reuse <code>health_check()</code> or mount root health router directly.", tc_s)],
    ]
    t_iss = Table(iss_data, colWidths=[38, 75, 175, 64, 180])
    t_iss.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1e3a8a")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0,0), (-1,-1), 2.5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2.5),
    ]))
    story.append(t_iss)
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. Test Suite Re-Execution Results", h1_s))
    t_box = [
        [Paragraph("""<b>Test Command:</b> <code>python -m unittest discover -s tests -v</code><br/>
<b>Test Execution Summary:</b><br/>
&bull; <code>test_api_v1_health_check (test_health.TestHealthEndpoints)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_root_endpoint (test_health.TestHealthEndpoints)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_root_health_check (test_health.TestHealthEndpoints)</code> ... <font color='#10b981'><b>ok</b></font><br/>
<b>Status:</b> 3 Passed, 0 Failed, 0 Errors in 0.014s &nbsp;|&nbsp; <b>Conclusion:</b> 100% Endpoint Health Verified.""", code_s)]
    ]
    t3 = Table(t_box, colWidths=[532])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f3f4f6")),
        ("BOX", (0,0), (-1,-1), 1, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(t3)

    doc.build(story, canvasmaker=NumberedCanvas)
    print("Audit PDF generated successfully.")


if __name__ == "__main__":
    out = os.path.abspath(r"documentation\reports\Phase_1_Technical_Audit_Report.pdf")
    build_audit_pdf(out)

