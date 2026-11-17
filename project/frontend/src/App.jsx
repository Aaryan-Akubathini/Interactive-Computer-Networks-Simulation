import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api.js'
import { prepare, deriveView } from './playback.js'
import NetworkCanvas from './components/NetworkCanvas.jsx'
import { TopologyControls, SimulationControls, PlaybackBar } from './components/Controls.jsx'
import { MetricCards, ComparisonTable } from './components/Metrics.jsx'
import SimpleChart from './components/SimpleChart.jsx'
import PacketInspector from './components/PacketInspector.jsx'

const TABS = ['Topology', 'Simulation', 'Results', 'Saved Networks']
const TICKS_PER_SECOND = 4

const nextId = (items, prefix) => { let i = 1; while (items.some(x => x.id === prefix + i)) i++; return prefix + i }

// Basic sanity check for topologies loaded from MySQL.
function validTopology(t) {
  if (!t || !Array.isArray(t.nodes) || !Array.isArray(t.links)) return false
  const ids = new Set(t.nodes.map(n => n.id))
  return t.nodes.every(n => n.id && ['host', 'router'].includes(n.type) && Number.isFinite(n.x) && Number.isFinite(n.y))
    && t.links.every(l => ids.has(l.a) && ids.has(l.b))
}

export default function App() {
  const [tab, setTab] = useState('Topology')
  const [topology, setTopology] = useState({ nodes: [], links: [] })
  const [selected, setSelected] = useState(null)
  const [tool, setTool] = useState('select')
  const [pending, setPending] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const [scenarios, setScenarios] = useState([])
  const [source, setSource] = useState('')
  const [destination, setDestination] = useState('')
  const [mode, setMode] = useState('dijkstra')
  const [rate, setRate] = useState(1)
  const [duration, setDuration] = useState(60)

  const [result, setResult] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [lastBase, setLastBase] = useState(null)
  const [selectedPacket, setSelectedPacket] = useState(null)

  const [tick, setTick] = useState(0)
  const tickRef = useRef(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)

  const [saved, setSaved] = useState([])
  const [runs, setRuns] = useState([])
  const [saveName, setSaveName] = useState('My network')
  const [loaded, setLoaded] = useState(null)       // {id, name} of the saved topology being edited
  const [renaming, setRenaming] = useState(null)   // {id, name}

  const fail = e => { setError(e.message || String(e)); setNotice('') }
  const hosts = topology.nodes.filter(n => n.type === 'host')

  // ---- initial data --------------------------------------------------------
  useEffect(() => {
    api.defaultTopology().then(t => { setTopology(t); setSource('A'); setDestination('B') }).catch(fail)
    api.scenarios().then(setScenarios).catch(() => {})
  }, [])

  // ---- topology editing ----------------------------------------------------
  const addNode = type => {
    const prefix = type === 'router' ? 'R' : 'H'
    const id = nextId(topology.nodes, prefix)
    const k = topology.nodes.length
    setTopology(t => ({ ...t, nodes: [...t.nodes, { id, type, label: id, x: 120 + (k * 67) % 660, y: 70 + (k * 89) % 380 }] }))
    setSelected({ type: 'node', id })
  }
  const moveNode = (id, x, y) => setTopology(t => ({ ...t, nodes: t.nodes.map(n => (n.id === id ? { ...n, x, y } : n)) }))
  const updateNode = (id, patch) => setTopology(t => ({ ...t, nodes: t.nodes.map(n => (n.id === id ? { ...n, ...patch } : n)) }))
  const updateLink = (id, patch) => setTopology(t => ({ ...t, links: t.links.map(l => (l.id === id ? { ...l, ...patch } : l)) }))
  const nodeClick = id => {
    if (tool === 'connect') {
      if (!pending) { setPending(id); return }
      if (pending === id) { setPending(null); return }
      if (topology.links.some(l => (l.a === pending && l.b === id) || (l.a === id && l.b === pending))) {
        setError('These two nodes are already connected.'); setPending(null); return
      }
      setError('')
      setTopology(t => ({ ...t, links: [...t.links, { id: nextId(t.links, 'L'), a: pending, b: id, capacity: 3, delay: 2, buffer: 10, status: 'active' }] }))
      setPending(null)
    } else setSelected({ type: 'node', id })
  }
  const deleteSelected = useCallback(() => {
    if (!selected) return
    setTopology(t => selected.type === 'node'
      ? { nodes: t.nodes.filter(n => n.id !== selected.id), links: t.links.filter(l => l.a !== selected.id && l.b !== selected.id) }
      : { ...t, links: t.links.filter(l => l.id !== selected.id) })
    setSelected(null)
  }, [selected])
  useEffect(() => {
    const onKey = e => { if (tab === 'Topology' && e.key === 'Delete' && !['INPUT', 'SELECT'].includes(e.target.tagName)) deleteSelected() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tab, deleteSelected])
  const resetTopology = () => api.defaultTopology().then(t => { setTopology(t); setSelected(null); setLoaded(null); setError('') }).catch(fail)

  // ---- save / load ---------------------------------------------------------
  const refreshSaved = () => { api.topologies().then(setSaved).catch(fail); api.runs().then(setRuns).catch(() => {}) }
  useEffect(() => { if (tab === 'Saved Networks') refreshSaved() }, [tab])
  const saveTopology = () => api.saveTopology({ name: saveName, nodes: topology.nodes, links: topology.links })
    .then(t => { setLoaded({ id: t.id, name: t.name }); setNotice(`Saved “${t.name}”.`); setError('') }).catch(fail)
  const updateSaved = () => api.updateTopology(loaded.id, { name: saveName, nodes: topology.nodes, links: topology.links })
    .then(t => { setLoaded({ id: t.id, name: t.name }); setNotice(`Updated “${t.name}”.`); setError('') }).catch(fail)
  const loadTopology = id => api.topology(id).then(t => {
    if (!validTopology(t)) throw new Error('This saved topology is invalid and cannot be loaded.')
    setTopology({ nodes: t.nodes_json || t.nodes, links: t.links_json || t.links })
    setLoaded({ id: t.id, name: t.name }); setSaveName(t.name); setSelected(null); setResult(null); setComparison(null)
    const h = (t.nodes || []).filter(n => n.type === 'host')
    setSource(h[0]?.id || ''); setDestination(h[1]?.id || '')
    setTab('Topology'); setError('')
  }).catch(fail)
  const renameSaved = () => api.updateTopology(renaming.id, { name: renaming.name })
    .then(() => { setRenaming(null); refreshSaved() }).catch(fail)
  const deleteSaved = id => api.deleteTopology(id).then(() => { if (loaded?.id === id) setLoaded(null); refreshSaved() }).catch(fail)

  // ---- simulation ----------------------------------------------------------
  const seek = v => { tickRef.current = v; setTick(v) }
  const execute = async ({ topo, m, flows, events, dur, scenario, alsoCompare }) => {
    setBusy(true); setError(''); setNotice('')
    const base = { topology: { nodes: topo.nodes, links: topo.links }, flows, events, duration: dur, scenario }
    try {
      const [res, cmp] = await Promise.all([
        api.simulate({ ...base, routing_mode: m, topology_id: loaded?.id ?? null }),
        alsoCompare ? api.compare(base) : Promise.resolve(null),
      ])
      setResult(res); setComparison(cmp); setLastBase(base); setSelectedPacket(null)
      if (res.warning) setNotice(res.warning)
      seek(0); setPlaying(true); setTab('Simulation')
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const runCustom = () => {
    if (topology.nodes.length === 0) return setError('The topology is empty. Add some nodes first.')
    if (!source) return setError('Select a source host.')
    if (!destination) return setError('Select a destination host.')
    if (source === destination) return setError('Source and destination must be different hosts.')
    const r = Number(rate), d = Number(duration)
    if (!(r >= 0 && r <= 10)) return setError('Traffic rate must be between 0 and 10 packets/tick.')
    if (!Number.isInteger(d) || d < 1 || d > 300) return setError('Duration must be a whole number between 1 and 300 ticks.')
    execute({ topo: topology, m: mode, flows: [{ source, destination, rate: r, start_tick: 0, end_tick: null }], events: [], dur: d, scenario: 'custom' })
  }
  const runScenario = s => {
    setTopology(s.topology); setSelected(null); setLoaded(null)
    setSource(s.flows[0].source); setDestination(s.flows[0].destination); setMode(s.suggested_mode)
    setRate(s.flows[0].rate); setDuration(s.duration)
    execute({ topo: s.topology, m: s.suggested_mode, flows: s.flows, events: s.events, dur: s.duration, scenario: s.key, alsoCompare: true })
  }
  const runComparison = () => {
    if (!lastBase) return
    setBusy(true); setError('')
    api.compare(lastBase).then(setComparison).catch(fail).finally(() => setBusy(false))
  }
  const openRun = id => api.run(id).then(r => {
    setResult(r.timeline_json); setComparison(null); setLastBase(null); setSelectedPacket(null)
    seek(0); setPlaying(false); setTab('Results'); setError('')
  }).catch(fail)

  // ---- playback loop (requestAnimationFrame) ------------------------------
  useEffect(() => {
    if (!playing || !result) return
    let last = performance.now(), raf
    const loop = now => {
      const n = tickRef.current + ((now - last) / 1000) * speed * TICKS_PER_SECOND
      last = now
      if (n >= result.total_ticks) { tickRef.current = result.total_ticks; setTick(result.total_ticks); setPlaying(false); return }
      tickRef.current = n; setTick(n)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [playing, result, speed])
  const playPause = () => {
    if (!playing && result && tickRef.current >= result.total_ticks) seek(0)
    setPlaying(p => !p)
  }

  const prep = useMemo(() => (result ? prepare(result) : null), [result])
  const view = useMemo(() => (result && prep ? deriveView(result, prep, tick) : null), [result, prep, tick])
  const overlay = view && { ...view, onMarkerClick: id => setSelectedPacket(id) }
  const scenarioInfo = result && scenarios.find(s => s.key === result.configuration.scenario)

  // ---- render --------------------------------------------------------------
  return (
    <div className="app">
      <nav className="tabs">
        {TABS.map(t => <button key={t} className={t === tab ? 'tab active' : 'tab'} onClick={() => setTab(t)}>{t}</button>)}
      </nav>
      {error && <div className="banner error" onClick={() => setError('')}>{error}</div>}
      {notice && <div className="banner notice" onClick={() => setNotice('')}>{notice}</div>}

      {tab === 'Topology' && (
        <div className="layout">
          <div className="card main">
            <NetworkCanvas nodes={topology.nodes} links={topology.links} mode="edit" selected={selected} pendingFrom={pending}
              onNodeMove={moveNode} onNodeClick={nodeClick} onLinkClick={id => setSelected({ type: 'link', id })}
              onBackgroundClick={() => { setSelected(null); setPending(null) }} />
            <p className="muted small">Link labels: c = capacity (packets/tick), d = propagation delay (ticks), b = buffer (packets). Red dashed = failed.</p>
          </div>
          <TopologyControls nodes={topology.nodes} links={topology.links} selected={selected} tool={tool}
            setTool={t => { setTool(t); setPending(null) }} onAdd={addNode} onDelete={deleteSelected} onReset={resetTopology}
            onUpdateLink={updateLink} onUpdateNode={updateNode} saveName={saveName} setSaveName={setSaveName}
            onSave={saveTopology} onUpdateSaved={updateSaved} loadedName={loaded?.name} />
        </div>
      )}

      {tab === 'Simulation' && (
        <div className="layout">
          <div className="main">
            <div className="card">
              {result
                ? <NetworkCanvas nodes={prep.topo.nodes} links={prep.topo.links} overlay={overlay} selectedPacket={selectedPacket} />
                : <NetworkCanvas nodes={topology.nodes} links={topology.links} />}
              {result && result.routing[0] && (
                <p className="small">
                  Initial routes —
                  {' '}Dijkstra: {result.routing[0].dijkstra ? `${result.routing[0].dijkstra.path.join(' → ')} (cost ${result.routing[0].dijkstra.cost}, ${result.routing[0].dijkstra.hops} hops)` : 'no route'};
                  {' '}Bellman-Ford: {result.routing[0].bellman_ford ? `${result.routing[0].bellman_ford.path.join(' → ')} (cost ${result.routing[0].bellman_ford.cost})` : 'no route'}.
                  {' '}Mode used: <b>{result.configuration.routing_mode}</b>.
                </p>
              )}
            </div>
            <PlaybackBar tick={tick} total={result?.total_ticks || 0} playing={playing} speed={speed} setSpeed={setSpeed}
              onPlayPause={playPause} onReset={() => { setPlaying(false); seek(0) }} onSeek={v => { setPlaying(false); seek(v) }} disabled={!result} />
          </div>
          <SimulationControls hosts={hosts} source={source} setSource={setSource} destination={destination} setDestination={setDestination}
            mode={mode} setMode={setMode} rate={rate} setRate={setRate} duration={duration} setDuration={setDuration}
            onRun={runCustom} busy={busy} scenarios={scenarios} onScenario={runScenario} scenarioInfo={scenarioInfo} />
        </div>
      )}

      {tab === 'Results' && (
        !result ? <div className="card"><p>No results yet. Run a simulation or a scenario first.</p></div> : (
          <div className="results">
            <div className="card">
              <h3>Summary ({result.configuration.scenario}, {result.configuration.routing_mode})</h3>
              <MetricCards metrics={result.metrics} />
              <p className="muted small">Metrics come from the simulated packet events. Delay is in ticks, throughput in delivered packets per tick.
                The run lasts {result.configuration.duration} ticks of traffic plus {result.configuration.drain} drain ticks.</p>
            </div>
            <div className="charts">
              <SimpleChart title="Throughput over time" data={result.charts.throughput} xLabel="Simulation tick" yLabel="Delivered packets / tick" color="#16a34a" />
              <SimpleChart title="Network congestion" data={result.charts.queued} xLabel="Simulation tick" yLabel="Total queued packets" color="#f97316" />
            </div>
            <div className="row"><button onClick={runComparison} disabled={!lastBase || busy}>Compare all routing modes</button>
              {!lastBase && <span className="muted small">Re-run the simulation to enable comparison.</span>}</div>
            {comparison && <ComparisonTable comparison={comparison} />}
            <PacketInspector result={result} packetId={selectedPacket} onSelect={setSelectedPacket} />
          </div>
        )
      )}

      {tab === 'Saved Networks' && (
        <div className="results">
          <div className="card">
            <h3>Saved topologies</h3>
            {saved.length === 0 ? <p className="muted">Nothing saved yet (or MySQL is not reachable).</p> : (
              <table><thead><tr><th>Name</th><th>Nodes</th><th>Links</th><th>Updated</th><th></th></tr></thead>
                <tbody>{saved.map(s => (
                  <tr key={s.id}>
                    <td>{renaming?.id === s.id
                      ? <input value={renaming.name} onChange={e => setRenaming({ id: s.id, name: e.target.value })} />
                      : s.name}</td>
                    <td>{s.node_count}</td><td>{s.link_count}</td><td>{String(s.updated_at).replace('T', ' ').slice(0, 16)}</td>
                    <td className="actions">
                      <button onClick={() => loadTopology(s.id)}>Load</button>
                      {renaming?.id === s.id
                        ? <button onClick={renameSaved}>Save name</button>
                        : <button onClick={() => setRenaming({ id: s.id, name: s.name })}>Rename</button>}
                      <button className="danger" onClick={() => deleteSaved(s.id)}>Delete</button>
                    </td>
                  </tr>))}
                </tbody></table>
            )}
          </div>
          <div className="card">
            <h3>Previous simulation runs</h3>
            {runs.length === 0 ? <p className="muted">No saved runs yet.</p> : (
              <table><thead><tr><th>#</th><th>Scenario</th><th>Routing</th><th>Delivery</th><th>Dropped</th><th>When</th><th></th></tr></thead>
                <tbody>{runs.map(r => (
                  <tr key={r.id}><td>{r.id}</td><td>{r.scenario}</td><td>{r.routing_mode}</td>
                    <td>{r.metrics.delivery_pct}%</td><td>{r.metrics.dropped}</td>
                    <td>{String(r.created_at).replace('T', ' ').slice(0, 16)}</td>
                    <td className="actions"><button onClick={() => openRun(r.id)}>Open</button></td></tr>))}
                </tbody></table>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
