import { useState, useRef } from 'react'
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

export default function App() {
  const [language, setLanguage] = useState('python')
  const [code, setCode] = useState(STARTER_CODE['python'])
  const [output, setOutput] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const editorRef = useRef(null)

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

  const handleRun = async () => {
    const currentCode = editorRef.current ? editorRef.current.getValue() : code
    setLoading(true)
    setOutput(null)
    setError(null)

    try {
      const res = await fetch(`${API_BASE}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: currentCode, language, timeout: 10 }),
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
  }

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
        >
          {loading ? '⏳ Running…' : '▶ Run'}
        </button>
      </div>

      <div className="ide-editor-wrapper">
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
            Click <strong>▶ Run</strong> to execute your code.
          </div>
        )}

        {loading && (
          <div className="ide-output-placeholder">Running…</div>
        )}

        {output && (
          <div className="ide-output-results">
            {output.error && (
              <div className="ide-output-error">
                <strong>Execution error:</strong> {output.error}
              </div>
            )}

            <div className="ide-output-meta">
              Exit code: <code>{output.exit_code}</code> &nbsp;|&nbsp; Time:{' '}
              <code>{output.execution_time}s</code>
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
