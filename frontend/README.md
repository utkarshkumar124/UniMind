# UniMind Frontend 🎨

The student-facing user interface for UniMind — AI Academic Assistant for Lovely Professional University.

## 🚀 Quick Start

### 1. Install Dependencies
```bash
npm install
```

### 2. Development Server
```bash
npm run dev
```
Starts the Vite dev server on `http://localhost:5173`.  
API requests to `/api/*` are automatically reverse-proxied to the FastAPI backend running on `http://localhost:8000`.

### 3. Production Build
```bash
npm run build
```
Executes TypeScript type-checking (`tsc --noEmit`) and compiles optimized static assets into `dist/`.

---

## 🛠️ Technology Stack
- **Framework:** React 18 with Vite
- **Styling:** Tailwind CSS v4 (`@tailwindcss/vite`)
- **Icons:** Lucide React
- **Markdown Rendering:** React Markdown with custom cited-source buttons
- **Routing:** React Router DOM v6
- **Language:** TypeScript 5.5

---

## 🔌 Backend Integration Architecture

The frontend integrates seamlessly with the UniMind backend:
- **Vite Proxy (`vite.config.ts`):** Directs `/api` traffic to `http://localhost:8000`.
- **Knowledge Base (`src/features/KnowledgeBase.tsx`):**
  - Fetches ingested documents directly from `GET /api/v1/documents`.
  - Supports file uploads via multipart `POST /api/v1/documents/upload`.
  - Automatically triggers document chunking and vector embedding via `POST /api/v1/documents/{id}/process`.
  - Seamless fallback to demonstration documents when the backend is offline.
- **Chat Interface (`src/features/Chat.tsx`):**
  - Conversational question-answering with token streaming simulation.
  - Interactive clickable citation tags linking to source passages and document previews.
- **Settings (`src/features/Settings.tsx`):**
  - Displays dynamic live backend connection status via `GET /api/v1/health`.
