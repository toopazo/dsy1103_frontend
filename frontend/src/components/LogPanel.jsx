import { useEffect, useRef } from 'react'

const TYPE_CLASS = {
  header:  'log-header',
  section: 'log-section',
  pass:    'log-pass',
  fail:    'log-fail',
  info:    'log-info',
}

export default function LogPanel({ lines, evaluating }) {
  const panelRef = useRef(null)

  useEffect(() => {
    if (panelRef.current) {
      panelRef.current.scrollTop = panelRef.current.scrollHeight
    }
  }, [lines])

  function exportTxt() {
    const text = lines.map(l => l.text).join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `evaluacion-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="log-panel-wrapper">
      <div className="log-toolbar">
        <span className="log-title">
          {evaluating ? '⏳ Evaluando...' : 'Log de evaluación'}
        </span>
        {lines.length > 0 && (
          <button className="btn-export" onClick={exportTxt}>
            Exportar .txt
          </button>
        )}
      </div>

      <div className="log-panel" ref={panelRef}>
        {lines.length === 0 ? (
          <span className="log-empty">
            Sin actividad — presiona Evaluar para comenzar
          </span>
        ) : (
          lines.map(line => (
            <div key={line.id} className={`log-line ${TYPE_CLASS[line.type] ?? 'log-info'}`}>
              {line.text}
            </div>
          ))
        )}
        {evaluating && <span className="log-cursor">▋</span>}
      </div>
    </div>
  )
}
