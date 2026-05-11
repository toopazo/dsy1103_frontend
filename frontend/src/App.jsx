import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from './api'
import ServiceCard from './components/ServiceCard'
import LogPanel from './components/LogPanel'
import './App.css'

const POLL_MS = 3000

export default function App() {
  const [backendOk, setBackendOk] = useState(null)
  const [imageExists, setImageExists] = useState(null)
  const [groups, setGroups] = useState([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [groupConfig, setGroupConfig] = useState(null)
  const [level, setLevel] = useState('easy')
  const [svcStatuses, setSvcStatuses] = useState({})
  const [logLines, setLogLines] = useState([])
  const [evalScore, setEvalScore] = useState(null)
  const [busy, setBusy] = useState({ building: false, starting: false, evaluating: false, stopping: false })

  const evalSourceRef = useRef(null)
  const pollRef = useRef(null)
  const logIdRef = useRef(0)

  const addLog = useCallback((type, text) => {
    const id = logIdRef.current++
    setLogLines(prev => [...prev, { id, type, text }])
  }, [])

  useEffect(() => {
    checkBackend()
    loadGroups()
  }, [])

  useEffect(() => {
    if (!selectedGroup) {
      setGroupConfig(null)
      setSvcStatuses({})
      return
    }
    api.getGroup(selectedGroup).then(setGroupConfig).catch(() => {})
  }, [selectedGroup])

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (!groupConfig) return
    const poll = () => pollStatuses(groupConfig)
    poll()
    pollRef.current = setInterval(poll, POLL_MS)
    return () => clearInterval(pollRef.current)
  }, [groupConfig])

  async function checkBackend() {
    try {
      await api.health()
      setBackendOk(true)
      const { exists } = await api.imageStatus()
      setImageExists(exists)
    } catch {
      setBackendOk(false)
    }
  }

  async function loadGroups() {
    try {
      setGroups(await api.listGroups())
    } catch {}
  }

  async function pollStatuses(config) {
    try {
      const running = await api.listServices()
      const runMap = Object.fromEntries(running.map(c => [c.name, c]))
      const next = {}
      await Promise.all(
        config.services.map(async svc => {
          const c = runMap[svc.name]
          if (!c) {
            // preserve 'cloning' state set during handleStartServices
            next[svc.name] = svcStatuses[svc.name]?.dockerStatus === 'cloning'
              ? svcStatuses[svc.name]
              : { dockerStatus: 'not_found', healthy: false }
            return
          }
          let healthy = false
          if (c.status === 'running') {
            try {
              const s = await api.serviceStatus(svc.name, svc.port)
              healthy = s.healthy
            } catch {}
          }
          next[svc.name] = { dockerStatus: c.status, healthy }
        })
      )
      setSvcStatuses(next)
    } catch {}
  }

  async function handleBuildImage() {
    setBusy(b => ({ ...b, building: true }))
    addLog('info', 'Construyendo imagen dsy1103-spring-runner...')
    try {
      const r = await api.buildImage()
      setImageExists(true)
      addLog('pass', `Imagen lista: ${r.image}`)
    } catch (e) {
      addLog('fail', `Error al construir imagen: ${e.message}`)
    } finally {
      setBusy(b => ({ ...b, building: false }))
    }
  }

  async function handleStartServices() {
    if (!groupConfig) return
    setBusy(b => ({ ...b, starting: true }))
    addLog('header', `Clonando y levantando ${groupConfig.services.length} servicios para ${groupConfig.group_name}...`)

    // Mark all as 'cloning' immediately
    setSvcStatuses(prev => {
      const next = { ...prev }
      for (const svc of groupConfig.services) next[svc.name] = { dockerStatus: 'cloning', healthy: false }
      return next
    })

    await Promise.all(
      groupConfig.services.map(async svc => {
        try {
          await api.startService(svc.name, svc.repo, svc.port, null, svc.env_vars ?? null)
          addLog('pass', `  ✓ ${svc.name} → :${svc.port}`)
        } catch (e) {
          addLog('fail', `  ✗ ${svc.name}: ${e.message}`)
          setSvcStatuses(prev => ({ ...prev, [svc.name]: { dockerStatus: 'error', healthy: false } }))
        }
      })
    )

    setBusy(b => ({ ...b, starting: false }))
    addLog('info', 'Servicios iniciados. Compilando en segundo plano — espera health checks verdes...')
  }

  function handleEvaluate() {
    if (!selectedGroup || busy.evaluating) return
    if (evalSourceRef.current) evalSourceRef.current.close()

    setBusy(b => ({ ...b, evaluating: true }))
    setEvalScore(null)
    setLogLines([])

    const es = api.openEvalStream(selectedGroup, level)
    evalSourceRef.current = es

    es.onmessage = (e) => {
      const ev = JSON.parse(e.data)
      switch (ev.type) {
        case 'eval_start':
          addLog('header', `=== ${ev.group} / ${ev.project} / ${ev.level.toUpperCase()} | ${ev.scenario_count} escenario(s) ===`)
          break
        case 'scenario_start':
          addLog('section', `── ${ev.scenario}`)
          break
        case 'step_result':
          if (ev.status === 'pass') {
            addLog('pass', `  ✓ ${ev.name}  ${ev.method} [${ev.http_status}]  ${ev.duration_ms}ms`)
          } else {
            addLog('fail', `  ✗ ${ev.name}  ${ev.method} [${ev.http_status ?? '?'}]  ${ev.error}`)
          }
          break
        case 'scenario_result':
          addLog('info', `  → ${ev.scenario}: ${ev.passed} pass / ${ev.failed} fail`)
          break
        case 'eval_result':
          setEvalScore({ passed: ev.total_passed, failed: ev.total_failed, total: ev.total_steps })
          addLog('header', `=== RESULTADO: ${ev.total_passed}/${ev.total_steps} steps ===`)
          setBusy(b => ({ ...b, evaluating: false }))
          break
        case 'eval_error':
          addLog('fail', `ERROR: ${ev.message}`)
          setBusy(b => ({ ...b, evaluating: false }))
          break
      }
    }
    es.onerror = () => {
      es.close()
      setBusy(b => ({ ...b, evaluating: false }))
    }
  }

  async function handleStopAll() {
    setBusy(b => ({ ...b, stopping: true }))
    addLog('info', 'Deteniendo todos los servicios...')
    try {
      await api.stopAll()
      addLog('pass', 'Todos los servicios detenidos.')
      setSvcStatuses({})
    } catch (e) {
      addLog('fail', `Error: ${e.message}`)
    } finally {
      setBusy(b => ({ ...b, stopping: false }))
    }
  }

  const anyBusy = Object.values(busy).some(Boolean)

  return (
    <div className="app">
      <header className="header">
        <span className="header-title">■ DSY1103 Evaluador</span>
        <span className={`backend-status ${backendOk === true ? 'ok' : backendOk === false ? 'err' : ''}`}>
          {backendOk === true ? '● Backend OK' : backendOk === false ? '● Backend offline' : '● conectando...'}
        </span>
      </header>

      <div className="main">
        <aside className="sidebar">

          <section className="sidebar-section">
            <label className="label">GRUPO</label>
            <select
              className="select"
              value={selectedGroup}
              onChange={e => setSelectedGroup(e.target.value)}
              disabled={anyBusy}
            >
              <option value="">— seleccionar —</option>
              {groups.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
            {groupConfig && (
              <div className="group-meta">
                <div className="group-name">{groupConfig.group_name}</div>
                {groupConfig.students?.length > 0 && (
                  <div className="muted">{groupConfig.students.join(', ')}</div>
                )}
                <div className="muted">{groupConfig.services?.length} servicios · {groupConfig.project}</div>
              </div>
            )}
          </section>

          <section className="sidebar-section">
            <label className="label">DIFICULTAD</label>
            <div className="level-pills">
              {['easy', 'medium', 'hard'].map(l => (
                <button
                  key={l}
                  className={`pill ${level === l ? 'active' : ''}`}
                  onClick={() => setLevel(l)}
                  disabled={busy.evaluating}
                >
                  {l === 'easy' ? 'Fácil' : l === 'medium' ? 'Medio' : 'Difícil'}
                </button>
              ))}
            </div>
          </section>

          <section className="sidebar-section">
            <label className="label">ACCIONES</label>
            <div className="actions">
              <button
                className="btn"
                onClick={handleBuildImage}
                disabled={busy.building || imageExists === true}
                title={imageExists ? 'La imagen ya existe' : 'Construir imagen Docker spring-runner'}
              >
                {busy.building ? '⏳ Construyendo...' : imageExists ? '✓ Imagen OK' : '⚙ Build Imagen'}
              </button>
              <button
                className="btn"
                onClick={handleStartServices}
                disabled={!selectedGroup || busy.starting || !imageExists}
                title="Clonar repos y levantar todos los servicios del grupo"
              >
                {busy.starting ? '⏳ Clonando...' : '⚡ Clonar y Levantar'}
              </button>
              <button
                className="btn primary"
                onClick={handleEvaluate}
                disabled={!selectedGroup || busy.evaluating}
                title="Correr escenarios de evaluación"
              >
                {busy.evaluating ? '⏳ Evaluando...' : '▶ Evaluar'}
              </button>
              <button
                className="btn danger"
                onClick={handleStopAll}
                disabled={busy.stopping}
                title="Detener y eliminar todos los contenedores dsy1103-*"
              >
                {busy.stopping ? '⏳ Deteniendo...' : '■ Detener Todo'}
              </button>
            </div>
          </section>

          {evalScore && (
            <section className="sidebar-section">
              <label className="label">RESULTADO</label>
              <div className={`score ${evalScore.failed === 0 ? 'green' : evalScore.passed === 0 ? 'red' : 'yellow'}`}>
                {evalScore.passed} / {evalScore.total}
              </div>
              <div className="muted">{evalScore.passed} pass · {evalScore.failed} fail</div>
            </section>
          )}

        </aside>

        <div className="content">
          {groupConfig ? (
            <div className="service-grid">
              {groupConfig.services.map(svc => (
                <ServiceCard
                  key={svc.name}
                  name={svc.name}
                  port={svc.port}
                  status={svcStatuses[svc.name]}
                />
              ))}
            </div>
          ) : (
            <div className="empty-grid">Selecciona un grupo para ver los servicios</div>
          )}
          <LogPanel lines={logLines} evaluating={busy.evaluating} />
        </div>
      </div>
    </div>
  )
}
