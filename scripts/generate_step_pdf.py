"""Script to generate a professional PDF report for Step 1: Project Scaffolding."""

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
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Custom canvas that adds page numbers and running footer."""

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
        # Header (pages after page 1)
        if self._pageNumber > 1:
            self.drawString(40, 755, "UniMind - Step 1: Scaffold Project Structure & Environment")
            self.setStrokeColor(colors.HexColor("#e5e7eb"))
            self.setLineWidth(0.5)
            self.line(40, 748, 572, 748)

        # Footer
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(572, 25, page_str)
        self.drawString(40, 25, "UniMind AI Knowledge Assistant | Group G21 - Milestone Report")
        self.setStrokeColor(colors.HexColor("#e5e7eb"))
        self.setLineWidth(0.5)
        self.line(40, 35, 572, 35)
        self.restoreState()


def build_pdf(output_path: str):
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
    
    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1e3a8a"),
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#2563eb"),
    )

    meta_style = ParagraphStyle(
        "DocMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#4b5563"),
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=10,
        spaceAfter=4,
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1f2937"),
    )

    code_style = ParagraphStyle(
        "Code_Custom",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#111827"),
    )

    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1f2937"),
    )

    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
    )

    story = []

    # Title & Metadata Header Block
    story.append(Paragraph("UniMind 🎓 - Milestone Execution Report", title_style))
    story.append(Spacer(1, 3))
    story.append(Paragraph("Step 1: Scaffold Project Structure & Environment", subtitle_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Project:</b> AI-Powered University Knowledge Assistant &nbsp;|&nbsp; <b>Team:</b> Group G21 (Utkarsh, Suhani, Sanchayeeta)", meta_style))
    story.append(Paragraph("<b>Status:</b> COMPLETED & VERIFIED (3/3 Tests Passed) &nbsp;|&nbsp; <b>Date:</b> November 1, 2026", meta_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=10))

    # Section 1: Objectives & Constraints Adherence
    story.append(Paragraph("1. Deliverables & Constraint Adherence", h1_style))
    
    status_data = [
        [Paragraph("Deliverable / Constraint", table_header_style), Paragraph("Status", table_header_style), Paragraph("Verification Details", table_header_style)],
        [Paragraph("Project Directory Structure", table_cell_style), Paragraph("<font color='#10b981'><b>COMPLETED</b></font>", table_cell_style), Paragraph("Clean modular architecture created (backend, frontend, data, vector_store, scripts, tests, docs).", table_cell_style)],
        [Paragraph("Backend & Frontend Placeholders", table_cell_style), Paragraph("<font color='#10b981'><b>COMPLETED</b></font>", table_cell_style), Paragraph("Created backend/app structure and frontend/README.md placeholder.", table_cell_style)],
        [Paragraph("requirements.txt", table_cell_style), Paragraph("<font color='#10b981'><b>COMPLETED</b></font>", table_cell_style), Paragraph("Pinned core API, data parsing, vector search, LLM, and test tools.", table_cell_style)],
        [Paragraph(".env.example", table_cell_style), Paragraph("<font color='#10b981'><b>COMPLETED</b></font>", table_cell_style), Paragraph("Template created with ports, CORS origins, data paths, and model configs.", table_cell_style)],
        [Paragraph("FastAPI Application Skeleton", table_cell_style), Paragraph("<font color='#10b981'><b>COMPLETED</b></font>", table_cell_style), Paragraph("Modular app with Settings, CORS, root endpoint, /health, /api/v1/health.", table_cell_style)],
        [Paragraph(".gitignore Verification", table_cell_style), Paragraph("<font color='#10b981'><b>PRESERVED</b></font>", table_cell_style), Paragraph("Already present; ignores .env, .venv, cache; left unmodified.", table_cell_style)],
        [Paragraph("Technical Documentation", table_cell_style), Paragraph("<font color='#10b981'><b>COMPLETED</b></font>", table_cell_style), Paragraph("Created ARCHITECTURE.md, SETUP_GUIDE.md, API_SPECIFICATION.md.", table_cell_style)],
        [Paragraph("No RAG / Gemini / React Yet", table_cell_style), Paragraph("<font color='#10b981'><b>STRICTLY ADHERED</b></font>", table_cell_style), Paragraph("No premature logic, fake documents, or unnecessary dependencies.", table_cell_style)],
    ]

    t1 = Table(status_data, colWidths=[150, 95, 287])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t1)
    story.append(Spacer(1, 10))

    # Section 2: Complete Created Files Register
    story.append(Paragraph("2. Created Files Register", h1_style))

    files_data = [
        [Paragraph("File / Directory", table_header_style), Paragraph("Type", table_header_style), Paragraph("Purpose / Description", table_header_style)],
        [Paragraph("<code>.env.example</code>", table_cell_style), Paragraph("Config", table_cell_style), Paragraph("Configuration template for ports, CORS origins, and future model keys.", table_cell_style)],
        [Paragraph("<code>requirements.txt</code>", table_cell_style), Paragraph("Dependencies", table_cell_style), Paragraph("Specifies FastAPI, Uvicorn, Pydantic, PyMuPDF, FAISS, Sentence Transformers, Gemini.", table_cell_style)],
        [Paragraph("<code>backend/app/main.py</code>", table_cell_style), Paragraph("Python Entrypoint", table_cell_style), Paragraph("FastAPI application instance, CORS middleware, lifespan context, and root endpoints.", table_cell_style)],
        [Paragraph("<code>backend/app/core/config.py</code>", table_cell_style), Paragraph("Configuration", table_cell_style), Paragraph("12-factor configuration management loading .env using Pydantic BaseSettings.", table_cell_style)],
        [Paragraph("<code>backend/app/models/schemas.py</code>", table_cell_style), Paragraph("Data Models", table_cell_style), Paragraph("Pydantic DTO models (HealthResponse, RootResponse).", table_cell_style)],
        [Paragraph("<code>backend/app/routes/health.py</code>", table_cell_style), Paragraph("Router", table_cell_style), Paragraph("Health check endpoint handler (GET /health).", table_cell_style)],
        [Paragraph("<code>backend/app/routes/api.py</code>", table_cell_style), Paragraph("Router Aggregator", table_cell_style), Paragraph("API v1 router grouping versioned endpoints under /api/v1 prefix.", table_cell_style)],
        [Paragraph("<code>backend/app/services/__init__.py</code>", table_cell_style), Paragraph("Package", table_cell_style), Paragraph("Placeholder package for future business logic and orchestrations.", table_cell_style)],
        [Paragraph("<code>backend/app/rag/__init__.py</code>", table_cell_style), Paragraph("Package", table_cell_style), Paragraph("Placeholder package for ingestion, chunking, embeddings, and grounding logic.", table_cell_style)],
        [Paragraph("<code>backend/app/utils/__init__.py</code>", table_cell_style), Paragraph("Package", table_cell_style), Paragraph("Placeholder package for common utilities and helpers.", table_cell_style)],
        [Paragraph("<code>backend/README.md</code>", table_cell_style), Paragraph("Documentation", table_cell_style), Paragraph("Backend structure guide, running instructions, and swagger URLs.", table_cell_style)],
        [Paragraph("<code>frontend/README.md</code>", table_cell_style), Paragraph("Documentation", table_cell_style), Paragraph("Frontend architecture placeholder for React + Tailwind student UI.", table_cell_style)],
        [Paragraph("<code>data/raw/.gitkeep</code>", table_cell_style), Paragraph("Marker", table_cell_style), Paragraph("Tracks directory for original university policy PDFs and notices.", table_cell_style)],
        [Paragraph("<code>data/processed/.gitkeep</code>", table_cell_style), Paragraph("Marker", table_cell_style), Paragraph("Tracks directory for normalized and chunked text documents.", table_cell_style)],
        [Paragraph("<code>data/evaluation/.gitkeep</code>", table_cell_style), Paragraph("Marker", table_cell_style), Paragraph("Tracks directory for golden Q&A evaluation datasets.", table_cell_style)],
        [Paragraph("<code>vector_store/.gitkeep</code>", table_cell_style), Paragraph("Marker", table_cell_style), Paragraph("Tracks directory for persisted local FAISS vector index files.", table_cell_style)],
        [Paragraph("<code>scripts/.gitkeep</code>", table_cell_style), Paragraph("Marker", table_cell_style), Paragraph("Tracks directory for indexing and evaluation automation scripts.", table_cell_style)],
        [Paragraph("<code>tests/test_health.py</code>", table_cell_style), Paragraph("Test Suite", table_cell_style), Paragraph("Automated unit tests covering root endpoint and health check endpoints.", table_cell_style)],
        [Paragraph("<code>documentation/ARCHITECTURE.md</code>", table_cell_style), Paragraph("Documentation", table_cell_style), Paragraph("In-depth architecture specification, diagrams, layer roles, and abstention rules.", table_cell_style)],
        [Paragraph("<code>documentation/SETUP_GUIDE.md</code>", table_cell_style), Paragraph("Documentation", table_cell_style), Paragraph("Step-by-step developer setup, virtualenv creation, and test execution instructions.", table_cell_style)],
        [Paragraph("<code>documentation/API_SPECIFICATION.md</code>", table_cell_style), Paragraph("Documentation", table_cell_style), Paragraph("Formal REST endpoint specifications for current and future phases.", table_cell_style)],
    ]

    t2 = Table(files_data, colWidths=[150, 85, 297])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t2)
    story.append(Spacer(1, 10))

    # Section 3: Automated Testing & Verification
    story.append(Paragraph("3. Automated Testing & Verification Results", h1_style))
    story.append(Paragraph("The FastAPI skeleton was verified by running unit tests against the endpoints using the built-in test client:", body_style))
    story.append(Spacer(1, 4))

    test_box_data = [
        [Paragraph("""<b>Command:</b> <code>python -m unittest tests/test_health.py</code><br/>
<b>Ran:</b> 3 unit tests in 0.019s<br/>
<b>Result:</b> <font color='#10b981'><b>PASS (OK)</b></font><br/>
&bull; <code>test_root_endpoint</code>: HTTP 200, status='online', service name, documentation URLs validated.<br/>
&bull; <code>test_root_health_check</code>: HTTP 200, status='healthy', environment & version validated.<br/>
&bull; <code>test_api_v1_health_check</code>: HTTP 200, versioned router check (/api/v1/health) validated.""", code_style)]
    ]
    t3 = Table(test_box_data, colWidths=[532])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t3)
    story.append(Spacer(1, 10))

    # Section 4: Git Status & Next Steps
    story.append(Paragraph("4. Git Status & Next Milestone Ready", h1_style))
    story.append(Paragraph("Git status was verified to ensure zero unintended alterations to existing repository files (<code>.gitignore</code>, <code>LICENSE</code>, <code>README.md</code>). All new files remain cleanly staged as untracked additions awaiting user approval.", body_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Next Milestone Available:</b> Step 2 – Document Ingestion, PDF Processing & Chunking Pipeline.", body_style))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF successfully generated at: {output_path}")


if __name__ == "__main__":
    target = os.path.abspath(r"documentation\reports\Step_1_Scaffolding_Report.pdf")
    build_pdf(target)

