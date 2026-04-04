# Cloud Runtime – VSCode Extension

Submits your active Python file (or selection) to the Cloud Runtime backend and streams live execution status directly inside VSCode.

## Requirements

- VSCode 1.80+
- Node.js 18+
- The [Cloud Runtime backend](../README.md#cloud-notebook-runtime--mvp) running locally or remotely

## Install & Build

```bash
cd vscode-extension
npm install
npm run compile
```

To open the extension in a development host:

1. Open the `vscode-extension/` folder in VSCode.
2. Press **F5** to launch the Extension Development Host.

## Configuration

| Setting | Default | Description |
|---|---|---|
| `cloudRuntime.serverUrl` | `http://localhost:8000` | Base URL of the Cloud Runtime API server |
| `cloudRuntime.apiToken` | *(empty)* | Bearer token for API auth (leave empty when `API_TOKEN` is not set on the server) |

Set these in **File → Preferences → Settings** (search for `Cloud Runtime`).

## Usage

1. Open a `.py` file (or select a code block).
2. Click the **▶ Run on Cloud** button in the status bar, **or** open the Command Palette (`Ctrl+Shift+P`) and run **"Run on Cloud Runtime"**.
3. Watch the **Cloud Runtime** output channel for live status updates:
   ```
   [Cloud Runtime] Submitting to http://localhost:8000…
   [Cloud Runtime] Session:   kaggle-session-a1b2c3d4  (provider: kaggle)
   [Cloud Runtime] Execution: exec-<uuid>
   [Cloud Runtime] Status:    queued
   [Cloud Runtime] Status:    running
   [Cloud Runtime] Status:    completed

   --- Output ---
   Hello from the cloud notebook runtime!
   ```

## Known Limitations

| Limitation | Notes |
|---|---|
| Real Kaggle cold start | When using Kaggle credentials, kernels take 30–120 s to start. The extension waits via WebSocket and will show "Running…" during that time. |
| No mid-run cancel UI | Use `POST /cancel/{execution_id}` via the API directly, or implement a cancel button in a future version. |
| Python only | The editor title button only appears for `.py` files. Other languages can still be submitted via the Command Palette. |
