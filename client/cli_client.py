#!/usr/bin/env python3
"""
CLI demo client for the Cloud Notebook Runtime API.

Usage
-----
  # Start the backend first:
  python -m backend.api

  # Then in another terminal:
  python client/cli_client.py

Environment variables (override defaults):
  API_BASE_URL   http://localhost:8000
  API_TOKEN      (leave empty if auth disabled)

The client will:
  1. Check /health
  2. Create a session
  3. Submit a code execution
  4. Open a WebSocket and print live status updates
  5. Poll /status until completion
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

try:
    import httpx
    import websockets
except ImportError:
    print(
        "Missing dependencies. Install them with:\n"
        "  pip install httpx websockets",
        file=sys.stderr,
    )
    sys.exit(1)

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TOKEN = os.getenv("API_TOKEN", "")
WS_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://")
CLIENT_ID = "cli-demo-client"

DEMO_CODE = """
# Demo: runs on the cloud runtime
import sys
print("Hello from the cloud notebook runtime!")
print(f"Python version: {sys.version}")
result = sum(range(1, 101))
print(f"Sum 1..100 = {result}")
"""


def _headers() -> dict:
    if API_TOKEN:
        return {"Authorization": f"Bearer {API_TOKEN}"}
    return {}


async def main() -> None:
    print("=" * 60)
    print("Cloud Notebook Runtime – CLI Demo Client")
    print("=" * 60)

    async with httpx.AsyncClient(base_url=BASE_URL, headers=_headers(), timeout=10.0) as http:

        # 1. Health check ------------------------------------------------
        print("\n[1/5] Health check …")
        resp = await http.get("/health")
        resp.raise_for_status()
        print(f"      {resp.json()}")

        # 2. Create session ----------------------------------------------
        print("\n[2/5] Creating session …")
        resp = await http.post("/session/create", json={})
        resp.raise_for_status()
        session = resp.json()
        session_id = session["session_id"]
        print(f"      session_id = {session_id}")

        # 3. Submit execution --------------------------------------------
        print("\n[3/5] Submitting code …")
        resp = await http.post(
            "/execute",
            json={"session_id": session_id, "code": DEMO_CODE},
        )
        resp.raise_for_status()
        execution = resp.json()
        execution_id = execution["execution_id"]
        print(f"      execution_id = {execution_id}")
        print(f"      initial status = {execution['status']}")

        # 4. WebSocket live updates --------------------------------------
        print("\n[4/5] Listening for live updates via WebSocket …")
        ws_uri = f"{WS_URL}/ws/{CLIENT_ID}"
        if API_TOKEN:
            ws_uri += f"?token={API_TOKEN}"

        received_terminal = asyncio.Event()

        async def _listen() -> None:
            terminal_states = {"completed", "failed", "cancelled"}
            try:
                async with websockets.connect(ws_uri) as ws:
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
                        except asyncio.TimeoutError:
                            print("      (WebSocket timeout – moving on)")
                            break
                        msg = json.loads(raw)
                        if msg.get("event") == "status_update" and msg.get("execution_id") == execution_id:
                            status = msg.get("status", "?")
                            print(f"      [WS] status={status}")
                            if status in terminal_states:
                                received_terminal.set()
                                break
            except Exception as exc:  # noqa: BLE001
                print(f"      [WS] connection error: {exc}")
                received_terminal.set()

        listener_task = asyncio.create_task(_listen())
        await asyncio.wait_for(received_terminal.wait(), timeout=20.0)
        listener_task.cancel()

        # 5. Final status poll ------------------------------------------
        print("\n[5/5] Final status poll …")
        resp = await http.get(f"/status/{execution_id}")
        resp.raise_for_status()
        final = resp.json()
        print(f"      status  = {final['status']}")
        if final.get("output"):
            print(f"      output  =\n        {final['output'].strip()}")
        if final.get("error"):
            print(f"      error   = {final['error']}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
