<div align="center">

# 🤖 BA-Bot — AI Business Analyst Agent

**Automate your requirements discovery. Talk to an AI. Export a polished FDR document.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-8.x-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)

</div>

---

## 📌 What is BA-Bot?

BA-Bot is a full-stack AI-powered tool built for **Business Analysts, Product Managers, and Project Leads** at L&T PES.

Instead of spending hours in manual requirement-gathering workshops, you simply **have a conversation** with an AI agent. It asks the right questions, listens to your answers, and builds a structured requirements document — automatically.

> 💡 **The core idea:** Replace hours of manual elicitation sessions with a smart conversational AI that extracts, structures, and exports your requirements in minutes.

---

## ✨ Features

### 🗂️ Multi-Project Dashboard
Manage multiple active projects from a single interface. Each card shows real-time completion progress, department, and sponsor info. Delete or resume any project in one click.

### 💬 AI Interview Workspace
A chat interface powered by a **Forjinn AI flow** (LLM backend). The agent asks structured questions to capture:
- Project name, department, sponsor, business unit & timeline
- Project overview and key stakeholders
- Business problem statement and goals
- Desired outcomes and constraints
- Functional requirements with priority + confidence scores

AI responses are **streamed token-by-token** in real time using Server-Sent Events (SSE), giving an instant, fluid feel.

### 🧠 Auto Field Extraction
As the interview progresses, the backend **automatically parses AI responses** using regex pattern matching to fill in structured project data fields — no copy-pasting required.

### 📋 Requirements Review Panel
Review all captured data in a clean structured layout before finalising. See per-section completion status with live progress indicators across 6 tracked dimensions:

| Dimension | Tracked Field |
|---|---|
| Overview | Project description |
| Discovery | Business problem |
| Business | Business goals |
| Functional | Functional requirements list |
| NFR | Constraints & non-functional requirements |
| Approval | Missing fields count |

### 📄 One-Click Document Export
Generate a **polished, presentation-ready Final Discovery Requirements (FDR)** document with a single click:
- **DOCX** — MS Word format with proper heading levels, bullet styles, and numbered lists
- **PDF** — ReportLab-rendered with custom typography, spacing, and layout

The AI compiles the full document from the conversation history before rendering.

### 📊 Analytics Dashboard
Automatically tracks total projects, completion rate, pending work, and a **"Hours Saved" metric** calculated per completed project.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                     Browser (React)                  │
│   Dashboard ─► New Project ─► Interview ─► Review   │
│                      ▲              │                │
│               SSE streaming    User input            │
└──────────────────────┼──────────────┼───────────────┘
                       │              ▼
┌──────────────────────────────────────────────────────┐
│                 FastAPI Backend (Python)              │
│                                                      │
│  POST /api/predict ──► Forjinn AI Flow (LLM)        │
│  GET  /api/projects ──► SQLite (SQLAlchemy ORM)     │
│  POST /api/project  ──► Persist project JSON        │
│  GET  /api/project/{id}/export ──► PDF/DOCX gen     │
└──────────────────────────────────────────────────────┘
                       │
             ┌─────────┴──────────┐
             │   ba_bot.db        │
             │   (SQLite)         │
             └────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | React 19 + TypeScript | SPA with strong type safety |
| **Build Tool** | Vite 8 | Instant HMR, lightning-fast builds |
| **Styling** | Vanilla CSS | Fully custom design system |
| **Math Rendering** | KaTeX | In-chat equation rendering |
| **Backend** | FastAPI 0.115 | Async REST API + SSE streaming |
| **ORM** | SQLAlchemy 2.0 | Database abstraction |
| **Database** | SQLite | Zero-config persistent storage |
| **PDF Export** | ReportLab | Custom styled PDF generation |
| **DOCX Export** | python-docx | Word document generation |
| **AI Gateway** | Forjinn Flow | LLM prediction with session memory |

---

## 📂 Project Structure

```
ba-agent/
├── backend/
│   ├── app.py              # FastAPI app — all routes and export logic
│   ├── database.py         # SQLAlchemy engine + session setup
│   ├── models.py           # Project DB model (id, data as JSON blob)
│   └── requirements.txt    # Python dependencies
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx         # Entire SPA: routing, state, views, SSE client
│   │   ├── App.css         # Design system: tokens, layout, animations
│   │   └── main.tsx        # React DOM mount
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
└── ba_bot.db               # Auto-generated SQLite database
```

---

## 🚀 Getting Started

### Prerequisites
- **Node.js** v18+
- **Python** 3.10+
- **pip**

---

### 1 — Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the API server
python app.py
```

| Endpoint | Description |
|---|---|
| `http://127.0.0.1:8000/api/health` | Health check |
| `http://127.0.0.1:8000/docs` | Interactive Swagger UI |

---

### 2 — Frontend

```bash
cd frontend

npm install
npm run dev
```

Open **`http://localhost:5173`** in your browser.

---

## 🔌 API Reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/health` | Server health check |
| `GET` | `/api/projects` | List all saved projects |
| `GET` | `/api/project/{id}` | Fetch a single project |
| `POST` | `/api/project` | Create a new project |
| `PUT` | `/api/project/{id}` | Update an existing project |
| `DELETE` | `/api/project/{id}` | Delete a project |
| `POST` | `/api/predict` | Stream AI response via SSE |
| `GET` | `/api/project/{id}/export?format=pdf\|docx` | Export FDR document |

---

## 🗃️ Data Model

Each project is stored as a **JSON blob** in SQLite, structured as follows:

```json
{
  "id": 1,
  "sessionId": "session-uuid",
  "pdfGenerated": false,
  "messages": [{ "role": "ai|user", "text": "..." }],
  "project": {
    "name": "...",
    "department": "...",
    "sponsor": "...",
    "business_unit": "...",
    "expected_completion": "..."
  },
  "overview": {
    "description": "...",
    "stakeholders": ["..."]
  },
  "discovery": {
    "business_problem": "...",
    "business_goals": "...",
    "desired_outcomes": "...",
    "constraints": "..."
  },
  "functional_requirements": [
    { "title": "...", "priority": "High", "confidence": 0.95 }
  ],
  "missing_fields": [],
  "next_question": "..."
}
```

---

## 🔧 Development

```bash
# Frontend — dev server with HMR
cd frontend && npm run dev

# Frontend — production build
cd frontend && npm run build

# Frontend — lint check
cd frontend && npm run lint

# Backend — run with auto-reload
cd backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

---

## 🏢 Built For

**L&T PES (Larsen & Toubro — Precision Engineering & Systems)**
Built as an internal productivity tool to accelerate requirements engineering workflows.

---

<div align="center">
  <sub>Built with ❤️ using FastAPI · React · SQLite · Forjinn AI</sub>
</div>
