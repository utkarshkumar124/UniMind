# UniMind API Specification 📡

## Base URL
- **Local Development**: `http://localhost:8000`
- **Versioned API Root**: `/api/v1`

---

## 1. System Endpoints (Implemented)

### 1.1 Root Service Information
Provides high-level service metadata and navigational links to documentation and endpoints.

- **URL**: `/`
- **Method**: `GET`
- **Authentication**: None
- **Response** (`200 OK`):
  ```json
  {
    "service": "UniMind Knowledge Assistant",
    "version": "0.1.0",
    "status": "online",
    "docs_url": "/docs",
    "health_url": "/health",
    "api_v1_url": "/api/v1"
  }
  ```

### 1.2 Health Check (Top-Level & Versioned)
Used by load balancers, orchestrators, and monitoring probes to assess system operational health.

- **URL**: `/health` and `/api/v1/health`
- **Method**: `GET`
- **Authentication**: None
- **Response** (`200 OK`):
  ```json
  {
    "status": "healthy",
    "service": "UniMind Knowledge Assistant",
    "version": "0.1.0",
    "environment": "development"
  }
  ```

---

## 2. Planned Endpoints Roadmap (Future Phases)

The following endpoints will be introduced in subsequent milestones:

### 2.1 Natural Language Query Endpoint (Phase 3)
- **URL**: `/api/v1/query`
- **Method**: `POST`
- **Description**: Submits a natural-language question, performs vector retrieval against institutional documents, and returns a grounded response with source citations or an abstention message.
- **Request Body (Draft)**:
  ```json
  {
    "question": "What is the minimum attendance required to appear for semester examinations?",
    "department": "Academics",
    "top_k": 5
  }
  ```
- **Response Body (Draft)**:
  ```json
  {
    "answer": "According to the Academic Regulations, students must maintain a minimum of 75% attendance in each course to be eligible for end-semester examinations.",
    "abstained": false,
    "confidence_score": 0.94,
    "citations": [
      {
        "document_name": "Academic_Regulations_2025.pdf",
        "page_number": 14,
        "excerpt": "A student must maintain an attendance record of at least 75%..."
      }
    ]
  }
  ```

### 2.2 Document Management & Ingestion Endpoint (Phase 2)
- **URL**: `/api/v1/documents/upload`
- **Method**: `POST`
- **Description**: Uploads university policy PDFs, triggers text extraction, chunking, and embedding generation into the FAISS vector store.

---

## 3. Error Handling Standards

All error responses adhere to standard HTTP status codes and return structured JSON:

```json
{
  "detail": "Description of the error condition."
}
```

Common status codes:
- `400 Bad Request`: Malformed or invalid input.
- `404 Not Found`: Requested document or resource does not exist.
- `422 Unprocessable Entity`: Validation failure on request body schema.
- `500 Internal Server Error`: Unexpected internal processing exception.

