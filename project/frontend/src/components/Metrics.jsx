const fmt = v => (v == null ? '—' : v)

export function MetricCards({ metrics }) {
  const cards = [
    ['Generated', metrics.generated], ['Delivered', metrics.delivered, 'good'],
    ['Dropped', metrics.dropped, metrics.dropped ? 'bad' : ''], ['Pending', metrics.pending],
    ['Delivery %', metrics.delivery_pct + '%'], ['Avg delay (ticks)', fmt(metrics.avg_delay)],
    ['Throughput (pkt/tick)', metrics.throughput], ['Route changes', metrics.route_changes],
  ]
  const reasons = Object.entries(metrics.drops_by_reason || {})
  return (
    <div>
      <div className="metrics">
        {cards.map(([k, v, cls]) => (
          <div key={k} className="metric"><div className="metric-label">{k}</div><div className={'metric-value ' + (cls || '')}>{v}</div></div>
        ))}
      </div>
      {reasons.length > 0 && (
        <p className="muted small">Drops by reason: {reasons.map(([r, n]) => `${r.replace('_', ' ')} = ${n}`).join(', ')}</p>
      )}
    </div>
  )
}

const MODE_NAMES = { dijkstra: 'Dijkstra (fixed)', bellman_ford: 'Bellman-Ford (fixed)', adaptive: 'Congestion-aware' }

export function ComparisonTable({ comparison }) {
  const modes = Object.keys(comparison.results)
  const rows = [
    ['Delivery %', m => m.delivery_pct + '%'], ['Avg delay (ticks)', m => fmt(m.avg_delay)],
    ['Packets dropped', m => m.dropped], ['Throughput (pkt/tick)', m => m.throughput],
    ['Route changes', m => m.route_changes],
  ]
  return (
    <div className="card">
      <h3>Routing comparison</h3>
      <p className="muted small">Identical topology, traffic and failure schedule; only the routing policy differs.
        Dijkstra and Bellman-Ford find the same minimum-cost path on non-negative costs, so their results match.</p>
      <table>
        <thead><tr><th></th>{modes.map(m => <th key={m}>{MODE_NAMES[m]}</th>)}</tr></thead>
        <tbody>
          {rows.map(([label, f]) => (
            <tr key={label}><td>{label}</td>{modes.map(m => <td key={m}>{f(comparison.results[m].metrics)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
