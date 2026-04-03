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

# Cloud Notebook Runtime – MVP

> Execute code on a cloud notebook (Kaggle) directly from your local VSCode,
> with an adapter-based architecture for swapping providers in the future.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Local Machine                                                       │
│                                                                      │
│  ┌──────────────┐   HTTP/REST    ┌────────────────────────────────┐ │
│  │  VSCode /    │ ─────────────► │  FastAPI Control Plane         │ │
│  │  CLI Client  │                │  (backend/api.py)              │ │
│  │              │ ◄───────────── │                                │ │
│  │  client/     │   WebSocket    │  ┌──────────────────────────┐  │ │
│  │  cli_client  │   /ws/{id}     │  │  RuntimeAdapter (ABC)    │  │ │
│  └──────────────┘                │  │  runtime/adapter.py      │  │ │
│                                  │  └────────────┬─────────────┘  │ │
│                                  │               │ implements      │ │
│                                  │  ┌────────────▼─────────────┐  │ │
│                                  │  │  KaggleRuntimeAdapter    │  │ │
│                                  │  │  runtime/kaggle_adapter  │  │ │
│                                  │  └────────────┬─────────────┘  │ │
│                                  │               │                 │ │
│                                  │  ┌────────────▼─────────────┐  │ │
│                                  │  │  ExecutionStore           │  │ │
│                                  │  │  (in-memory, MVP)        │  │ │
│                                  │  └──────────────────────────┘  │ │
│                                  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                          │
                                          │  (TODO: real Kaggle API)
                                          ▼
                               ┌─────────────────────┐
                               │  Kaggle Notebook     │
                               │  Runtime  (Cloud)    │
                               └─────────────────────┘
```

### Key components

| Path | Purpose |
|---|---|
| `runtime/adapter.py` | `RuntimeAdapter` abstract base class + data models |
| `runtime/kaggle_adapter.py` | Kaggle stub – simulates full lifecycle |
| `runtime/store.py` | Thread-safe in-memory execution store |
| `backend/api.py` | FastAPI control-plane (all HTTP + WS endpoints) |
| `backend/auth.py` | Bearer-token middleware |
| `backend/models.py` | Pydantic request/response schemas |
| `client/cli_client.py` | End-to-end demo CLI client |
| `tests/` | Pytest suite for adapter + API |

## Setup (Runtime MVP)

### 1. Install dependencies

```bash
pip install -r requirements-runtime.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env – set KAGGLE_USERNAME and KAGGLE_KEY when ready for real integration
```

### 3. Start the backend

```bash
python -m backend.api
# → Uvicorn listening on http://0.0.0.0:8000
# → Interactive docs at http://localhost:8000/docs
```

### 4. Run the demo CLI client

```bash
# In a second terminal:
python client/cli_client.py
```

Expected output:

```
============================================================
Cloud Notebook Runtime – CLI Demo Client
============================================================

[1/5] Health check …
      {'status': 'healthy', 'provider': 'kaggle', 'version': '1.0.0'}

[2/5] Creating session …
      session_id = kaggle-session-a1b2c3d4

[3/5] Submitting code …
      execution_id = exec-<uuid>
      initial status = queued

[4/5] Listening for live updates via WebSocket …
      [WS] status=queued
      [WS] status=running
      [WS] status=completed

[5/5] Final status poll …
      status  = completed
      output  =
        Hello from the cloud notebook runtime!
        Python version: 3.x.x
        Sum 1..100 = 5050

============================================================
Demo complete!
============================================================
```

### 5. Run tests

```bash
python -m pytest tests/ -v
```

## API Reference

All non-public endpoints require `Authorization: Bearer <API_TOKEN>` when
`API_TOKEN` is set in the environment.

### `GET /health`
Returns liveness status. No auth required.

```bash
curl http://localhost:8000/health
# {"status":"healthy","provider":"kaggle","version":"1.0.0"}
```

### `POST /session/create`
Create a new provider session.

```bash
curl -X POST http://localhost:8000/session/create \
     -H "Content-Type: application/json" \
     -d '{}'
# {"session_id":"kaggle-session-xxxx","provider":"kaggle","created_at":"..."}
```

### `POST /execute`
Submit Python code for async execution.

```bash
curl -X POST http://localhost:8000/execute \
     -H "Content-Type: application/json" \
     -d '{"session_id":"<session_id>","code":"print(\"hello\")"}'
# {"execution_id":"exec-xxxx","session_id":"...","status":"queued"}
```

### `GET /status/{execution_id}`
Poll the current state of an execution.

```bash
curl http://localhost:8000/status/exec-xxxx
# {"execution_id":"exec-xxxx","status":"completed","output":"hello\n",...}
```

### `POST /cancel/{execution_id}`
Cancel a queued or running execution.

```bash
curl -X POST http://localhost:8000/cancel/exec-xxxx
# {"execution_id":"exec-xxxx","status":"cancelled"}
```

### `WS /ws/{client_id}`
WebSocket endpoint for live status streaming.

```python
import websockets, asyncio, json

async def listen():
    async with websockets.connect("ws://localhost:8000/ws/my-client") as ws:
        async for msg in ws:
            print(json.loads(msg))

asyncio.run(listen())
```

## Adding a New Provider

To add a new runtime provider (e.g. Google Colab, SageMaker):

1. Create `runtime/<provider>_adapter.py` and subclass `RuntimeAdapter`:

```python
from runtime.adapter import RuntimeAdapter, SessionInfo, ExecutionResult

class ColabRuntimeAdapter(RuntimeAdapter):
    @property
    def provider_name(self) -> str:
        return "colab"

    async def create_session(self, metadata=None) -> SessionInfo: ...
    async def execute(self, session_id, code, execution_id, metadata=None) -> ExecutionResult: ...
    async def get_status(self, execution_id) -> ExecutionResult: ...
    async def cancel(self, execution_id) -> ExecutionResult: ...
```

2. Register it in `backend/api.py`'s `_PROVIDERS` dict:

```python
_PROVIDERS = {
    "kaggle": lambda: KaggleRuntimeAdapter(_store),
    "colab":  lambda: ColabRuntimeAdapter(_store),   # ← add this
}
```

3. Set `RUNTIME_PROVIDER=colab` in your `.env`.

## Known Limitations (MVP)

| Limitation | Notes |
|---|---|
| Kaggle not fully integrated | The `KaggleRuntimeAdapter` is a **stub** that simulates execution locally. Real Kaggle API calls are marked with `# TODO` comments. |
| Kaggle cold-start latency | Real Kaggle kernels take 30–120 s to start; no SLA or interactive mode. |
| In-memory state | Restarting the server resets all sessions and executions. Replace `ExecutionStore` with Redis/DB for persistence. |
| No kernel cancellation via Kaggle API | Kaggle's public API does not expose a stop-kernel endpoint. |
| Local code execution (stub) | The stub runs submitted code in the API server process – **unsafe for untrusted input**. Replace with real Kaggle execution for production. |
| Single-process only | The in-memory store is not shared across worker processes. |
