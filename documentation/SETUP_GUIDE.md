# UniMind Developer Setup Guide 💻

This guide provides instructions to configure, run, and verify the UniMind project locally.

---

## 1. Prerequisites
- **Python**: Version 3.10 or higher (Python 3.11 recommended).
- **Git**: Installed and configured.
- **Node.js**: (Optional for Phase 1, required for Phase 4 React frontend).

---

## 2. Environment Setup

### 2.1 Clone Repository
```bash
git clone https://github.com/your-username/UniMind.git
cd UniMind
```

### 2.2 Create and Activate a Virtual Environment
- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
- **macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 2.3 Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 3. Configuration

Copy the example environment configuration file:
```bash
# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

Review `.env` and configure any custom parameters. For Phase 1 (skeleton), default values work out of the box without external API keys.

---

## 4. Running the Backend Service

Start the FastAPI application with auto-reloading enabled:
```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```
Or run directly via Python module:
```bash
python -m backend.app.main
```

### 4.1 Verify Service Execution
- **Root Endpoint**: Visit [http://localhost:8000/](http://localhost:8000/)
  - Expected response: `{"service": "...", "status": "online", ...}`
- **Health Endpoint**: Visit [http://localhost:8000/health](http://localhost:8000/health) or [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
  - Expected response: `{"status": "healthy", ...}`
- **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative API Docs (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 5. Running the Test Suite

Run the unit test suite:
```bash
python -m unittest tests/test_health.py
```
Or with pytest (if installed):
```bash
pytest tests/
```

