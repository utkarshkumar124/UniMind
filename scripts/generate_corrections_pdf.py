"""Script to generate the Phase 1 Corrections & Refinements PDF Report."""

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
            self.drawString(40, 755, "UniMind - Phase 1 Technical Corrections Report")
            self.setStrokeColor(colors.HexColor("#e5e7eb"))
            self.setLineWidth(0.5)
            self.line(40, 748, 572, 748)
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(572, 25, page_str)
        self.drawString(40, 25, "UniMind Quality Assurance | Group G21 - Corrections Complete")
        self.setStrokeColor(colors.HexColor("#e5e7eb"))
        self.setLineWidth(0.5)
        self.line(40, 35, 572, 35)
        self.restoreState()


def build_corrections_pdf(output_path: str):
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
    story.append(Paragraph("UniMind 🛠️ - Phase 1 Corrections & Hardening Report", title_s))
    story.append(Spacer(1, 2))
    story.append(Paragraph("Implementation of Approved Audit Refinements & Test Expansion", sub_s))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Scope:</b> Phase 1 Audit Corrections &nbsp;|&nbsp; <b>Execution Date:</b> November 1, 2026", meta_s))
    story.append(Paragraph("<b>Status:</b> <font color='#10b981'><b>ALL CORRECTIONS IMPLEMENTED & VERIFIED (9/9 TESTS PASSED)</b></font>", meta_s))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=8))

    story.append(Paragraph("1. Implemented Corrections Summary", h1_s))
    corr_data = [
        [Paragraph("Correction Item", th_s), Paragraph("Target File", th_s), Paragraph("Changes Applied", th_s), Paragraph("Status", th_s)],
        [
            Paragraph("<b>1. CORS Wildcard & Credentials Fix</b>", tc_s),
            Paragraph("<code>backend/app/core/config.py</code><br/><code>backend/app/main.py</code>", tc_s),
            Paragraph("Replaced wildcard fallback with explicit localhost origins (<code>http://localhost:3000</code>, <code>http://127.0.0.1:3000</code>). Added dynamic <code>cors_allow_credentials</code> property to disallow credentials whenever wildcard origin is present.", tc_s),
            Paragraph("<font color='#10b981'><b>VERIFIED</b></font>", tc_s)
        ],
        [
            Paragraph("<b>2. SecretStr API Key Masking</b>", tc_s),
            Paragraph("<code>backend/app/core/config.py</code>", tc_s),
            Paragraph("Converted <code>GEMINI_API_KEY</code> from plain <code>str</code> to <code>pydantic.SecretStr</code>. Masked in all string/repr logs. Added <code>get_gemini_api_key()</code> for safe explicit access.", tc_s),
            Paragraph("<font color='#10b981'><b>VERIFIED</b></font>", tc_s)
        ],
        [
            Paragraph("<b>3. Health Logic De-duplication</b>", tc_s),
            Paragraph("<code>backend/app/main.py</code>", tc_s),
            Paragraph("Eliminated duplicated dictionary creation in <code>root_health_check()</code>; now reuses <code>await health_check()</code> from <code>backend/app/routes/health.py</code>. Both <code>/health</code> and <code>/api/v1/health</code> URLs and responses preserved.", tc_s),
            Paragraph("<font color='#10b981'><b>VERIFIED</b></font>", tc_s)
        ],
        [
            Paragraph("<b>4. Dependency Discipline</b>", tc_s),
            Paragraph("<code>requirements.txt</code>", tc_s),
            Paragraph("Kept <code>requirements.txt</code> untouched. <code>python-multipart</code> deferred to Phase 2 document upload implementation as instructed.", tc_s),
            Paragraph("<font color='#10b981'><b>VERIFIED</b></font>", tc_s)
        ],
    ]
    t_corr = Table(corr_data, colWidths=[120, 110, 230, 72])
    t_corr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_corr)
    story.append(Spacer(1, 8))

    story.append(Paragraph("2. Expanded Test Suite Coverage & Results", h1_s))
    story.append(Paragraph("A dedicated test module <code>tests/test_config.py</code> was added alongside updated assertions in <code>tests/test_health.py</code>, scaling total test coverage to 9 automated unit tests:", body_s))
    story.append(Spacer(1, 4))

    t_box = [
        [Paragraph("""<b>Test Execution Command:</b> <code>python -m unittest discover -s tests -v</code><br/>
<b>Test Suite Results:</b><br/>
&bull; <code>test_default_cors_origins (test_config.TestConfigSettings)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_cors_fallback_on_invalid_or_empty_input (test_config.TestConfigSettings)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_cors_wildcard_disables_credentials (test_config.TestConfigSettings)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_cors_custom_origins_enable_credentials (test_config.TestConfigSettings)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_gemini_api_key_secret_masking (test_config.TestConfigSettings)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_root_endpoint (test_health.TestHealthEndpoints)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_root_health_check (test_health.TestHealthEndpoints)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_api_v1_health_check (test_health.TestHealthEndpoints)</code> ... <font color='#10b981'><b>ok</b></font><br/>
&bull; <code>test_health_endpoints_consistency (test_health.TestHealthEndpoints)</code> ... <font color='#10b981'><b>ok</b></font><br/>
<b>Summary:</b> 9 Ran, 0 Failed, 0 Errors in 0.019s &nbsp;|&nbsp; <b>Status:</b> 100% Passing""", code_s)]
    ]
    t3 = Table(t_box, colWidths=[532])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t3)
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. Constraint Verification & Status", h1_s))
    story.append(Paragraph("&bull; <b>No RAG / LLM functionality implemented:</b> Reserved in package structure.<br/>"
                           "&bull; <b>Frontend intact:</b> No frontend alterations or npm additions.<br/>"
                           "&bull; <b>GitHub repository intact:</b> <code>README.md</code>, <code>LICENSE</code>, <code>.gitignore</code> untouched.<br/>"
                           "&bull; <b>Phase 2 gate:</b> Execution halted awaiting explicit user approval.", body_s))

    doc.build(story, canvasmaker=NumberedCanvas)
    print("Corrections PDF generated successfully.")


if __name__ == "__main__":
    out = os.path.abspath(r"documentation\reports\Phase_1_Corrections_Report.pdf")
    build_corrections_pdf(out)
