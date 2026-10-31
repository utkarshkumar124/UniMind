# UniMind 🎓

### AI-Powered University Knowledge Assistant

**Your University. Your Knowledge. One Intelligence.**

UniMind is an AI-powered university knowledge assistant designed to help students access academic and institutional information through natural language conversations.

Built using **Retrieval-Augmented Generation (RAG)**, UniMind aims to provide accurate, context-aware and document-grounded answers using a dedicated knowledge base.

Instead of relying entirely on an LLM's pretrained knowledge, UniMind retrieves relevant information from its knowledge base before generating responses.

## 🎯 Project Objectives

- Provide students with an intelligent university information assistant.
- Answer questions using relevant institutional documents.
- Reduce unsupported and fabricated AI responses.
- Provide document-based references and citations.
- Identify questions that cannot be answered using available information.
- Create a scalable knowledge platform that can support multiple university departments.

## ⚙️ Proposed Technology Stack

| Component | Technology |
|---|---|
| Frontend | React |
| UI Styling | Tailwind CSS |
| Backend | Python, FastAPI |
| Document Processing | PyMuPDF |
| Embedding Model | Sentence Transformers |
| Vector Database | FAISS |
| Large Language Model | Gemini API |
| Metadata Storage | SQLite |
| Version Control | Git & GitHub |
| Development Environment | Antigravity |

*Technology choices are provisional and subject to evaluation.*

## 🧠 System Architecture

```text
User Query
    |
    v
Query Processing
    |
    v
Embedding Generation
    |
    v
Vector Similarity Search
    |
    v
Relevant Context Retrieval
    |
    v
Evidence Validation
    |
    v
LLM Answer Generation
    |
    v
Grounded Answer + Sources
    |
    v
User
```

If sufficient supporting information is unavailable, UniMind will abstain instead of inventing an answer.

## ✨ Planned Features

- Natural-language question answering
- PDF and document ingestion
- Semantic search
- Context-aware answer generation
- Source document citations
- Unknown-answer detection
- Chat interface and conversation history
- Multi-category knowledge organization
- Scalable document management

## 📂 Project Structure

```text
UniMind/
│
├── frontend/
│
├── backend/
│   └── app/
│       ├── routes/
│       ├── services/
│       ├── rag/
│       ├── models/
│       └── utils/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── evaluation/
│
├── vector_store/
│
├── documentation/
│
├── scripts/
│
├── tests/
│
├── .env.example
├── .gitignore
└── README.md
```

## 👥 Project Team

**Group G21**

| Member | Role |
|---|---|
| Utkarsh (15) | AI & RAG Lead |
| Suhani (7) | Frontend Development |
| Sanchayeeta (32) | Backend & Knowledge Base |

## 🚀 Development Roadmap

1. Project initialization and architecture
2. Knowledge base preparation
3. Document processing and ingestion
4. Text chunking and embedding generation
5. Vector database implementation
6. Semantic retrieval engine
7. LLM integration
8. Grounding and hallucination control
9. Backend API development
10. Frontend development
11. Evaluation and optimization
12. Deployment and documentation

## 📊 Evaluation Strategy

The system will be evaluated using:

- Recall@K
- Mean Reciprocal Rank (MRR)
- Answer accuracy
- Answer groundedness
- Abstention precision and recall
- Response latency (P50/P95)

Actual benchmark results will be published after testing.

## 🔐 Security and Data Integrity

- API keys will be stored in environment variables.
- Private student information will not be included in the public knowledge base.
- Institutional documents will require appropriate authorization.
- Document sources and versions will be tracked.
- Answers will be restricted to supporting evidence.

## 📌 Current Development Status

**Status: Initial Planning & Architecture**

UniMind is currently in its initial development stage. The application, knowledge base and evaluation pipeline are yet to be implemented.

## 📄 License

This project is intended to be released under the MIT License. Third-party documents and datasets remain subject to their respective licenses and permissions.

---

**UniMind – Your University. Your Knowledge. One Intelligence.**
