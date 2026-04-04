import * as vscode from 'vscode';
import * as http from 'http';
import * as https from 'https';
import * as WebSocket from 'ws';

let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;

type RunState = 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

const STATUS_ICONS: Record<RunState, string> = {
    idle:      '$(play) Run on Cloud',
    queued:    '$(loading~spin) Queued…',
    running:   '$(loading~spin) Running…',
    completed: '$(check) Completed',
    failed:    '$(error) Failed',
    cancelled: '$(circle-slash) Cancelled',
};

export function activate(context: vscode.ExtensionContext): void {
    outputChannel = vscode.window.createOutputChannel('Cloud Runtime');
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = 'cloudRuntime.run';
    statusBarItem.tooltip = 'Run current file/selection on the cloud runtime';
    context.subscriptions.push(statusBarItem, outputChannel);

    const disposable = vscode.commands.registerCommand('cloudRuntime.run', runOnCloudRuntime);
    context.subscriptions.push(disposable);

    updateStatusBar('idle');
    statusBarItem.show();
}

function updateStatusBar(state: RunState): void {
    statusBarItem.text = STATUS_ICONS[state];
}

async function runOnCloudRuntime(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('Cloud Runtime: No active editor found.');
        return;
    }

    // Use the selection if non-empty, otherwise the whole file.
    const code = editor.selection.isEmpty
        ? editor.document.getText()
        : editor.document.getText(editor.selection);

    const config = vscode.workspace.getConfiguration('cloudRuntime');
    const serverUrl = (config.get<string>('serverUrl') ?? 'http://localhost:8000').replace(/\/$/, '');
    const apiToken = config.get<string>('apiToken') ?? '';

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiToken) {
        headers['Authorization'] = `Bearer ${apiToken}`;
    }

    outputChannel.clear();
    outputChannel.show(true);
    outputChannel.appendLine(`[Cloud Runtime] Submitting to ${serverUrl}…`);
    updateStatusBar('queued');

    try {
        // 1. Create a session
        const sessionResp = await postJson(`${serverUrl}/session/create`, {}, headers);
        const sessionId = String(sessionResp['session_id']);
        const provider = String(sessionResp['provider']);
        outputChannel.appendLine(`[Cloud Runtime] Session:   ${sessionId}  (provider: ${provider})`);

        // 2. Submit the execution
        const execResp = await postJson(
            `${serverUrl}/execute`,
            { session_id: sessionId, code },
            headers,
        );
        const executionId = String(execResp['execution_id']);
        outputChannel.appendLine(`[Cloud Runtime] Execution: ${executionId}`);
        outputChannel.appendLine(`[Cloud Runtime] Status:    ${String(execResp['status'])}`);

        // 3. Open a WebSocket connection and stream live updates
        const clientId = `vscode-${Date.now()}`;
        const wsBase = serverUrl.replace(/^http/, 'ws');
        const wsQuery = apiToken ? `?token=${encodeURIComponent(apiToken)}` : '';
        const wsUrl = `${wsBase}/ws/${clientId}${wsQuery}`;

        await streamUpdates(wsUrl, executionId);
        outputChannel.appendLine('[Cloud Runtime] Done.');
    } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        updateStatusBar('failed');
        outputChannel.appendLine(`[Cloud Runtime] Error: ${msg}`);
        vscode.window.showErrorMessage(`Cloud Runtime: ${msg}`);
    }
}

function streamUpdates(wsUrl: string, executionId: string): Promise<void> {
    return new Promise((resolve) => {
        const terminal = new Set<string>(['completed', 'failed', 'cancelled']);
        const ws = new WebSocket(wsUrl);

        // Send keepalive pings every 5 s
        const pingTimer = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            } else {
                clearInterval(pingTimer);
            }
        }, 5000);

        ws.on('message', (raw: WebSocket.RawData) => {
            let msg: Record<string, unknown>;
            try {
                msg = JSON.parse(raw.toString()) as Record<string, unknown>;
            } catch {
                return;
            }

            // Ignore messages for other executions
            if (msg['execution_id'] !== executionId) {
                return;
            }

            const status = String(msg['status'] ?? '');
            updateStatusBar(status as RunState);
            outputChannel.appendLine(`[Cloud Runtime] Status: ${status}`);

            if (msg['output']) {
                outputChannel.appendLine('\n--- Output ---');
                outputChannel.appendLine(String(msg['output']));
            }
            if (msg['error']) {
                outputChannel.appendLine('\n--- Error ---');
                outputChannel.appendLine(String(msg['error']));
            }

            if (terminal.has(status)) {
                clearInterval(pingTimer);
                ws.close();
                resolve();
            }
        });

        ws.on('error', (err: Error) => {
            outputChannel.appendLine(`[Cloud Runtime] WebSocket error: ${err.message}`);
            clearInterval(pingTimer);
            resolve();
        });

        ws.on('close', () => {
            clearInterval(pingTimer);
            resolve();
        });
    });
}

function postJson(
    url: string,
    body: object,
    headers: Record<string, string>,
): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
        const payload = JSON.stringify(body);
        const parsed = new URL(url);
        const isHttps = parsed.protocol === 'https:';
        const options: http.RequestOptions = {
            hostname: parsed.hostname,
            port: parsed.port !== '' ? parseInt(parsed.port, 10) : (isHttps ? 443 : 80),
            path: parsed.pathname + parsed.search,
            method: 'POST',
            headers: {
                ...headers,
                'Content-Length': Buffer.byteLength(payload),
            },
        };

        const lib = isHttps ? https : http;
        const req = lib.request(options, (res) => {
            let data = '';
            res.on('data', (chunk: string) => { data += chunk; });
            res.on('end', () => {
                const code = res.statusCode ?? 0;
                if (code >= 400) {
                    reject(new Error(`HTTP ${code}: ${data}`));
                } else {
                    try {
                        resolve(JSON.parse(data) as Record<string, unknown>);
                    } catch {
                        reject(new Error(`Invalid JSON response: ${data}`));
                    }
                }
            });
        });
        req.on('error', reject);
        req.write(payload);
        req.end();
    });
}

export function deactivate(): void {
    statusBarItem?.dispose();
    outputChannel?.dispose();
}
