import { useState } from 'react'

// Number input that validates on blur / Enter and shows a message instead of applying bad values.
function NumField({ label, value, min, max, onCommit }) {
  const [err, setErr] = useState('')
  function commit(e) {
    const n = Number(e.target.value)
    if (e.target.value === '' || !Number.isInteger(n) || n < min || n > max) {
      setErr(`${label}: whole number ${min}–${max}`)
      e.target.value = value
    } else { setErr(''); if (n !== value) onCommit(n) }
  }
  return (
    <label className="field">{label}
      <input key={value} type="number" defaultValue={value} min={min} max={max}
        onBlur={commit} onKeyDown={e => e.key === 'Enter' && e.target.blur()} />
      {err && <span className="error-text">{err}</span>}
    </label>
  )
}

export function TopologyControls({
  nodes, links, selected, tool, setTool, onAdd, onDelete, onReset, onUpdateLink, onUpdateNode,
  saveName, setSaveName, onSave, onUpdateSaved, loadedName,
}) {
  const link = selected?.type === 'link' ? links.find(l => l.id === selected.id) : null
  const node = selected?.type === 'node' ? nodes.find(n => n.id === selected.id) : null
  return (
    <div className="panel">
      <div className="card">
        <h3>Build</h3>
        <div className="row">
          <button onClick={() => onAdd('router')}>Add router</button>
          <button onClick={() => onAdd('host')}>Add host</button>
        </div>
        <div className="row">
          <button className={tool === 'connect' ? 'active' : ''} onClick={() => setTool(tool === 'connect' ? 'select' : 'connect')}>
            {tool === 'connect' ? 'Connect mode: ON' : 'Connect mode'}
          </button>
          <button onClick={onDelete} disabled={!selected}>Delete selected</button>
        </div>
        <button onClick={onReset}>Reset to default topology</button>
        <p className="muted small">
          {tool === 'connect' ? 'Click two nodes to link them.' : 'Drag nodes to move them. Click a node or link to select it.'}
        </p>
      </div>

      {link && (
        <div className="card">
          <h3>Link {link.a} – {link.b}</h3>
          <NumField label="Capacity (packets/tick)" value={link.capacity} min={1} max={100} onCommit={v => onUpdateLink(link.id, { capacity: v })} />
          <NumField label="Propagation delay (ticks)" value={link.delay} min={1} max={50} onCommit={v => onUpdateLink(link.id, { delay: v })} />
          <NumField label="Buffer (packets)" value={link.buffer} min={1} max={200} onCommit={v => onUpdateLink(link.id, { buffer: v })} />
          <label className="field">Status
            <select value={link.status} onChange={e => onUpdateLink(link.id, { status: e.target.value })}>
              <option value="active">active</option><option value="failed">failed</option>
            </select>
          </label>
        </div>
      )}
      {node && (
        <div className="card">
          <h3>{node.type === 'router' ? 'Router' : 'Host'} {node.id}</h3>
          <label className="field">Label
            <input value={node.label} maxLength={12} onChange={e => onUpdateNode(node.id, { label: e.target.value || node.id })} />
          </label>
        </div>
      )}

      <div className="card">
        <h3>Save topology</h3>
        <input value={saveName} onChange={e => setSaveName(e.target.value)} placeholder="Name" maxLength={100} />
        <div className="row">
          <button className="primary" onClick={onSave}>Save as new</button>
          {loadedName && <button onClick={onUpdateSaved}>Update “{loadedName}”</button>}
        </div>
      </div>
    </div>
  )
}

export function SimulationControls({
  hosts, source, setSource, destination, setDestination, mode, setMode, rate, setRate,
  duration, setDuration, onRun, busy, scenarios, onScenario, scenarioInfo,
}) {
  return (
    <div className="panel">
      <div className="card">
        <h3>Custom simulation</h3>
        <label className="field">Source host
          <select value={source} onChange={e => setSource(e.target.value)}>
            <option value="">select…</option>{hosts.map(h => <option key={h.id} value={h.id}>{h.label}</option>)}
          </select>
        </label>
        <label className="field">Destination host
          <select value={destination} onChange={e => setDestination(e.target.value)}>
            <option value="">select…</option>{hosts.map(h => <option key={h.id} value={h.id}>{h.label}</option>)}
          </select>
        </label>
        <label className="field">Routing algorithm
          <select value={mode} onChange={e => setMode(e.target.value)}>
            <option value="dijkstra">Dijkstra (fixed shortest path)</option>
            <option value="bellman_ford">Bellman-Ford (fixed shortest path)</option>
            <option value="adaptive">Congestion-aware (adaptive Dijkstra)</option>
          </select>
        </label>
        <label className="field">Traffic rate (packets/tick, 0–10)
          <input type="number" step="0.5" min="0" max="10" value={rate} onChange={e => setRate(e.target.value)} />
        </label>
        <label className="field">Duration (ticks, 1–300)
          <input type="number" min="1" max="300" value={duration} onChange={e => setDuration(e.target.value)} />
        </label>
        <button className="primary" onClick={onRun} disabled={busy}>{busy ? 'Running…' : 'Start simulation'}</button>
      </div>

      <div className="card">
        <h3>Scenarios</h3>
        <div className="col">
          {scenarios.map(s => <button key={s.key} onClick={() => onScenario(s)} disabled={busy}>{s.name}</button>)}
        </div>
        {scenarioInfo && <p className="small">{scenarioInfo.description}</p>}
      </div>
    </div>
  )
}

export function PlaybackBar({ tick, total, playing, speed, setSpeed, onPlayPause, onReset, onSeek, disabled }) {
  return (
    <div className="card playback">
      <div className="row">
        <button onClick={onPlayPause} disabled={disabled}>{playing ? 'Pause' : tick > 0 && tick < total ? 'Resume' : 'Play'}</button>
        <button onClick={onReset} disabled={disabled}>Reset</button>
        <label className="inline">Speed
          <select value={speed} onChange={e => setSpeed(Number(e.target.value))}>
            {[0.5, 1, 2, 4].map(s => <option key={s} value={s}>{s}×</option>)}
          </select>
        </label>
        <span className="muted small">tick {Math.floor(tick)} / {total}</span>
      </div>
      <input type="range" min="0" max={total || 1} step="0.05" value={tick} disabled={disabled}
        onChange={e => onSeek(Number(e.target.value))} style={{ width: '100%' }} />
      <div className="legend small">
        <span><i style={{ background: '#2563eb' }} /> active route / packet</span>
        <span><i style={{ background: '#f97316' }} /> congested link</span>
        <span><i style={{ background: '#dc2626' }} /> failed link / drop</span>
        <span><i style={{ background: '#16a34a' }} /> delivered</span>
      </div>
    </div>
  )
}
