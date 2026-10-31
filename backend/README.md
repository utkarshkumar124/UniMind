# UniMind Backend 🚀

This directory contains the FastAPI-based backend service for **UniMind - AI-Powered University Knowledge Assistant**.

## 📁 Directory Structure

```text
backend/
├── app/
│   ├── core/           # Central configuration, settings, security & constants
│   ├── models/         # Pydantic models, request/response schemas
│   ├── routes/         # API endpoints and route definitions
│   ├── services/       # Core business logic and service orchestrators
│   ├── rag/            # Document processing, embeddings, FAISS & grounding (Future phases)
│   ├── utils/          # Utility functions and helper modules
│   ├── __init__.py
│   └── main.py         # FastAPI application entrypoint
└── README.md
```

## 🛠️ Getting Started

### 1. Configure Environment
Ensure `.env` exists in the project root:
```bash
cp .env.example .env
```

### 2. Start the Development Server
Run the FastAPI application using Uvicorn from the project root:
```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```
Or directly using Python:
```bash
python -m backend.app.main
```

### 3. Interactive Documentation
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health) or [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

