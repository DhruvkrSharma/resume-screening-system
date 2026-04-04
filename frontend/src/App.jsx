import { Component, useState, useEffect, useRef, useCallback } from 'react'
import Editor from '@monaco-editor/react'

// Use a relative path so that:
//  - In dev:  Vite proxies /api → http://localhost:8000/api
//  - In prod: nginx proxies /api → http://backend:8000/api
const API_BASE = '/api'

const LANGUAGE_OPTIONS = [
  { value: 'python', label: 'Python' },
  { value: 'c', label: 'C' },
  { value: 'cpp', label: 'C++' },
]

const STARTER_CODE = {
  python: `# Python starter
print("Hello, World!")
`,
  c: `// C starter
#include <stdio.h>
int main() {
    printf("Hello, World!\\n");
    return 0;
}
`,
  cpp: `// C++ starter
#include <iostream>
int main() {
    std::cout << "Hello, World!" << std::endl;
    return 0;
}
`,
}

const MONACO_LANGUAGE = {
  python: 'python',
  c: 'c',
  cpp: 'cpp',
}

// ---------------------------------------------------------------------------
// Error boundary – catches Monaco loader failures and renders a plain textarea
// ---------------------------------------------------------------------------
class MonacoErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) {
      return (
        <textarea
          className="ide-fallback-editor"
          value={this.props.fallbackValue}
          onChange={(e) => this.props.onFallbackChange(e.target.value)}
          spellCheck={false}
        />
      )
    }
    return this.props.children
  }
}

export default function App() {
  const [language, setLanguage] = useState('python')
  const [code, setCode] = useState(STARTER_CODE['python'])
  const [stdin, setStdin] = useState('')
  const [output, setOutput] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const editorRef = useRef(null)
  const outputRef = useRef(null)

  const handleLanguageChange = (e) => {
    const lang = e.target.value
    setLanguage(lang)
    setCode(STARTER_CODE[lang])
    setOutput(null)
    setError(null)
  }

  const handleEditorMount = (editor) => {
    editorRef.current = editor
  }

  const handleRun = useCallback(async () => {
    const rawCode = editorRef.current ? editorRef.current.getValue() : code
    // Normalize Windows line endings so C's scanf and Python's input() behave
    // consistently across all browsers/OSes.
    const normalizedCode = rawCode.replace(/\r\n/g, '\n')
    setLoading(true)
    setOutput(null)
    setError(null)

    try {
      const res = await fetch(`${API_BASE}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: normalizedCode,
          language,
          timeout: 10,
          stdin: stdin || null,
        }),
      })
      if (!res.ok) {
        throw new Error(`Server error: ${res.status} ${res.statusText}`)
      }
      const data = await res.json()
      setOutput(data)
    } catch (err) {
      setError(err.message || 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [language, stdin, code]) // editorRef and state setters are stable

  // Scroll the output panel back to the top whenever new results arrive
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = 0
    }
  }, [output])

  // Ctrl+Enter / Cmd+Enter triggers Run
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !loading) {
        e.preventDefault()
        handleRun()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [loading, handleRun])

  return (
    <div className="ide-root">
      <header className="ide-header">
        <span className="ide-title">⚡ Production IDE</span>
        <span className="ide-badge">MVP v0</span>
      </header>

      <div className="ide-toolbar">
        <label htmlFor="lang-select" className="ide-label">
          Language:
        </label>
        <select
          id="lang-select"
          className="ide-select"
          value={language}
          onChange={handleLanguageChange}
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <button
          className={`ide-run-btn ${loading ? 'ide-run-btn--loading' : ''}`}
          onClick={handleRun}
          disabled={loading}
          title="Run (Ctrl+Enter)"
        >
          {loading ? '⏳ Running…' : '▶ Run'}
        </button>
      </div>

      <div className="ide-editor-wrapper">
        <MonacoErrorBoundary fallbackValue={code} onFallbackChange={setCode}>
          <Editor
            height="100%"
            language={MONACO_LANGUAGE[language]}
            value={code}
            theme="vs-dark"
            onChange={(val) => setCode(val || '')}
            onMount={handleEditorMount}
            options={{
              fontSize: 14,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
          />
        </MonacoErrorBoundary>
      </div>

      <div className="ide-stdin-panel">
        <div className="ide-output-header">Stdin (optional)</div>
        <textarea
          className="ide-stdin-textarea"
          value={stdin}
          onChange={(e) => setStdin(e.target.value)}
          placeholder="Input to feed the program via stdin…"
          spellCheck={false}
        />
      </div>

      <div className="ide-output-panel">
        <div className="ide-output-header">Output</div>

        {error && (
          <div className="ide-output-error">
            <strong>Error:</strong> {error}
          </div>
        )}

        {!error && !output && !loading && (
          <div className="ide-output-placeholder">
            Click <strong>▶ Run</strong> (or press{' '}
            <kbd className="ide-kbd">Ctrl</kbd>+<kbd className="ide-kbd">Enter</kbd>)
            to execute your code.
          </div>
        )}

        {loading && (
          <div className="ide-output-placeholder">Running…</div>
        )}

        {output && (
          <div className="ide-output-results" ref={outputRef}>
            {output.error && (
              <div className="ide-output-error">
                <strong>Execution error:</strong> {output.error}
              </div>
            )}

            <div className="ide-output-meta">
              Exit code: <code>{output.exit_code}</code> &nbsp;|&nbsp; Time:{' '}
              <code>{output.execution_time}s</code>
              {output.truncated && (
                <span className="ide-output-truncated">
                  &nbsp;|&nbsp; ⚠ output truncated
                </span>
              )}
            </div>

            {output.stdout && (
              <section>
                <div className="ide-output-label">stdout</div>
                <pre className="ide-output-pre ide-output-pre--stdout">
                  {output.stdout}
                </pre>
              </section>
            )}

            {output.stderr && (
              <section>
                <div className="ide-output-label ide-output-label--err">
                  stderr
                </div>
                <pre className="ide-output-pre ide-output-pre--stderr">
                  {output.stderr}
                </pre>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
