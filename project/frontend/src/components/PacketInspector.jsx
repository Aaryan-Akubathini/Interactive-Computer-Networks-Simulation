const REASONS = {
  buffer_overflow: 'buffer overflow (tail drop)', ttl_expired: 'TTL expired',
  link_failed: 'link failed', no_route: 'no available route',
}

// Everything shown here is read from the recorded hops of the selected packet.
export default function PacketInspector({ result, packetId, onSelect }) {
  const packets = result.packets
  const p = packetId ? packets[packetId - 1] : null
  const firstDropped = packets.find(x => x.status === 'dropped')
  const firstDelivered = packets.find(x => x.status === 'delivered')
  const ttl0 = result.configuration.ttl

  let body = <p className="muted">Click a packet in the animation, enter an id, or use the shortcuts above.</p>
  if (packetId && !p) body = <p className="error-text">Packet #{packetId} does not exist (1 – {packets.length}).</p>
  if (p) {
    const visited = [p.src]
    p.hops.forEach(h => { if (h[4] != null) visited.push(h[1]) })
    const end = p.status === 'delivered' ? 'Delivered'
      : p.status === 'dropped' ? `Dropped at ${p.drop_at} (${REASONS[p.drop_reason] || p.drop_reason})`
      : p.status === 'queued' ? 'Still queued' : 'Still in transit'
    let wait = 0, prop = 0
    p.hops.forEach(h => { if (h[3] != null) wait += h[3] - h[2]; if (h[3] != null && h[4] != null) prop += h[4] - h[3] })
    body = (
      <div>
        <div className="journey">Created → {visited.join(' → ')} → <b className={p.status === 'delivered' ? 'good' : p.status === 'dropped' ? 'bad' : ''}>{end}</b></div>
        <table className="small">
          <tbody>
            <tr><td>Source → destination</td><td>{p.src} → {p.dst}</td></tr>
            <tr><td>Planned route</td><td>{p.path.length ? p.path.join(' → ') : 'none'}</td></tr>
            <tr><td>Created at tick</td><td>{p.created}</td></tr>
            <tr><td>Queue waiting (total)</td><td>{wait} ticks</td></tr>
            <tr><td>Propagation (total)</td><td>{prop} ticks</td></tr>
            <tr><td>TTL remaining</td><td>{p.ttl_left} (started at {ttl0})</td></tr>
            <tr><td>Final status</td><td>{p.status}{p.drop_reason ? ` – ${REASONS[p.drop_reason] || p.drop_reason}` : ''}</td></tr>
            <tr><td>Total delay</td><td>{p.delivered != null ? `${p.delivered - p.created} ticks` : '—'}</td></tr>
          </tbody>
        </table>
        {p.hops.length > 0 && (
          <table className="small hops">
            <thead><tr><th>Hop</th><th>Queued</th><th>Wait</th><th>Prop.</th><th>TTL after</th></tr></thead>
            <tbody>
              {p.hops.map((h, i) => (
                <tr key={i}>
                  <td>{h[0]} → {h[1]}</td><td>t={h[2]}</td>
                  <td>{h[3] != null ? h[3] - h[2] : '—'}</td>
                  <td>{h[4] != null ? h[4] - h[3] : '—'}</td>
                  <td>{h[4] != null ? (h[1] === p.dst ? '—' : ttl0 - (i + 1)) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {p.status === 'dropped' && <p className="small bad">Dropped at tick {p.dropped} at {p.drop_at}{p.drop_link ? ` (link ${p.drop_link})` : ''}: {REASONS[p.drop_reason] || p.drop_reason}.</p>}
      </div>
    )
  }
  return (
    <div className="card">
      <h3>Packet journey inspector {p ? `– Packet #${p.id}` : ''}</h3>
      <div className="row">
        <input type="number" min="1" max={packets.length} placeholder="Packet id" value={packetId || ''}
          onChange={e => onSelect(e.target.value ? Number(e.target.value) : null)} style={{ width: 100 }} />
        <button onClick={() => firstDelivered && onSelect(firstDelivered.id)} disabled={!firstDelivered}>First delivered</button>
        <button onClick={() => firstDropped && onSelect(firstDropped.id)} disabled={!firstDropped}>First dropped</button>
      </div>
      {body}
    </div>
  )
}
