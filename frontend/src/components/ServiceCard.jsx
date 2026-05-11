export default function ServiceCard({ name, port, status }) {
  const dockerStatus = status?.dockerStatus ?? 'unknown'
  const healthy = status?.healthy ?? false

  let badgeClass = 'unknown'
  let label = 'Sin contenedor'
  let dot = '○'

  if (dockerStatus === 'cloning') {
    badgeClass = 'cloning'
    label = 'Clonando...'
    dot = '◌'
  } else if (dockerStatus === 'running' && healthy) {
    badgeClass = 'healthy'
    label = 'Activo'
    dot = '●'
  } else if (dockerStatus === 'running') {
    badgeClass = 'starting'
    label = 'Iniciando'
    dot = '◑'
  } else if (dockerStatus === 'exited') {
    badgeClass = 'error'
    label = 'Detenido'
    dot = '✕'
  } else if (dockerStatus === 'error') {
    badgeClass = 'error'
    label = 'Error'
    dot = '✕'
  }

  return (
    <div className="service-card">
      <div className="svc-name" title={name}>{name}</div>
      <div className="svc-port">:{port}</div>
      <div className={`svc-badge ${badgeClass}`}>
        <span>{dot}</span>
        <span>{label}</span>
      </div>
    </div>
  )
}
