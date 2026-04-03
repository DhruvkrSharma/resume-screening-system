# Resume Screening System

**Author:** Gladiator2005  
**Date:** 2025-11-09  
**Version:** 1.0.0

## Overview

An intelligent resume screening system that uses NLP and machine learning to match candidate resumes with job requirements. Features multi-role support, PDF extraction with OCR fallback, semantic skill matching, and persistent SQLite storage.

## Features

- ✅ **PDF Text Extraction** - PyMuPDF → pdfplumber → OCR fallback
- ✅ **Smart Skill Extraction** - PhraseMatcher + regex + NLP
- ✅ **Semantic Matching** - Sentence transformers for context-aware matching
- ✅ **Multi-Role Support** - Store and screen for multiple job roles
- ✅ **SQLite Database** - Persistent storage with full audit trail
- ✅ **Ranked Results** - Sort by skills matched + similarity score
- ✅ **Google Colab Ready** - Works seamlessly in Colab notebooks

## Installation

### Local Installation

```bash
chmod +x install.sh
./install.sh
```

### Google Colab

```python
!bash install.sh
```

## Quick Start

```python
from screening_engine import ResumeScreener

# Initialize
screener = ResumeScreener()

# Add a role
screener.add_role_from_text(
    "Python Developer",
    "Looking for Python developer with Flask, PostgreSQL, Docker experience"
)

# Screen resumes
results = screener.screen_resumes(
    role_id=1,
    pdf_paths=["resume1.pdf", "resume2.pdf"]
)

# View results
import pandas as pd
print(pd.DataFrame(results))
```

## Project Structure

```
resume-screening/
├── config.py              # Configuration and constants
├── pdf_extractor.py       # PDF text extraction module
├── skill_extractor.py     # Skill extraction using NLP
├── semantic_matcher.py    # Semantic matching with transformers
├── database.py            # SQLite database operations
├── screening_engine.py    # Main screening engine
├── utils.py               # Utility functions
├── main.py                # Main application
├── install.sh             # Installation script
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## License

MIT License - Free to use and modify

## Author

**Gladiator2005**  
GitHub: https://github.com/Gladiator2005

---

**Happy Screening!** 🚀

---

# Production IDE (MVP v0)

A browser-based code execution IDE supporting **Python, C, and C++**.

## Features

- ⚡ **Monaco Editor** – VS Code-quality editor in the browser
- ▶ **Run Code** – Execute Python / C / C++ with stdout/stderr + exit code + timing
- 🐳 **Docker Compose** – One-command local deployment
- 🔒 **Resource limits** – Timeout + output truncation (hardened sandbox planned for v1)
- 🔌 **WebSocket debug stub** – Placeholder for step-debugger (MVP v1)

## Project Structure

```
├── backend/
│   ├── main.py            # FastAPI app (/api/health, /api/execute, /ws/debug stub)
│   ├── requirements.txt   # Python dependencies
│   ├── Dockerfile         # Backend image (python:3.12-slim + gcc/g++)
│   └── tests/
│       └── test_api.py    # pytest test suite
├── frontend/
│   ├── src/
│   │   ├── App.jsx        # Monaco editor + Run button + output panel
│   │   ├── App.css        # Dark-theme styles
│   │   └── main.jsx       # React entrypoint
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js     # Vite + /api proxy for dev
│   └── Dockerfile         # Multi-stage: build + nginx
├── docker-compose.yml
└── nginx.conf             # Reverse proxy: /api → backend, SPA fallback
```

## Quick Start – Docker Compose (recommended)

```bash
docker compose up --build
```

- Frontend: http://localhost
- Health check: http://localhost/api/health

## Local Development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
# or: python main.py
```

API available at http://localhost:8000/api/health

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 – API calls are proxied to the backend via Vite.

## Running Tests

```bash
cd backend
pip install -r requirements.txt pytest httpx
pytest tests/ -v
```

Tests include:
- Health endpoint
- Python execution (hello world, stderr, syntax error)
- C execution (skipped if `gcc` not available)
- C++ execution (skipped if `g++` not available)
- Timeout enforcement
- Input validation (unsupported language, code too long)

## API Reference

### `GET /api/health`
Returns `{"status": "ok", "version": "0.1.0"}`.

### `POST /api/execute`

```json
{
  "code": "print('hello')",
  "language": "python",
  "timeout": 10
}
```

Response:

```json
{
  "stdout": "hello\n",
  "stderr": "",
  "exit_code": 0,
  "execution_time": 0.042,
  "error": null
}
```

Supported languages: `python`, `c`, `cpp`  
Max timeout: 30 s | Max code length: 50 000 chars | Max output: 10 000 chars

### `WS /ws/debug` *(stub)*

Connects, sends an informational message that the step-debugger is not yet
implemented, then closes. Full implementation is planned for MVP v1.
