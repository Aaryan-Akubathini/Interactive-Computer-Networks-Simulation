// Turns the backend result into what should be drawn at (fractional) tick T.
// Nothing here is random: every marker comes from a recorded packet hop.

export function prepare(result) {
  const topo = result.configuration.topology
  const pos = Object.fromEntries(topo.nodes.map(n => [n.id, n]))
  const linkOf = {}
  topo.links.forEach(l => { linkOf[l.a + '|' + l.b] = l.id; linkOf[l.b + '|' + l.a] = l.id })
  const segments = [], drops = [], deliveries = []
  for (const p of result.packets) {
    for (const h of p.hops) if (h[3] != null && h[4] != null) segments.push({ id: p.id, from: h[0], to: h[1], dep: h[3], arr: h[4] })
    if (p.status === 'dropped') drops.push({ id: p.id, tick: p.dropped, node: p.drop_at })
    if (p.status === 'delivered') deliveries.push({ id: p.id, tick: p.delivered, node: p.dst })
  }
  return { topo, pos, linkOf, segments, drops, deliveries }
}

const MAX_MARKERS = 150   // keeps the animation smooth; all packets still count in the metrics

export function deriveView(result, prep, T) {
  const t0 = Math.max(0, Math.min(Math.floor(T), result.total_ticks - 1))

  const activeLinks = new Set()
  const latest = {}
  for (const c of result.route_changes) if (c.tick <= T) latest[c.flow] = c
  for (const c of Object.values(latest)) {
    if (!c.path) continue
    for (let i = 0; i < c.path.length - 1; i++) activeLinks.add(prep.linkOf[c.path[i] + '|' + c.path[i + 1]])
  }

  const failed = new Set(prep.topo.links.filter(l => l.status === 'failed').map(l => l.id))
  for (const e of result.link_events) {
    if (e.tick > T) break
    if (e.action === 'fail_link') failed.add(e.link_id); else failed.delete(e.link_id)
  }

  const congestion = {}, queues = {}
  for (const l of prep.topo.links) {
    const q = result.link_queues[l.id][t0] || 0
    queues[l.id] = q
    congestion[l.id] = q / l.buffer
  }

  const markers = []
  for (const s of prep.segments) {
    if (s.dep <= T && T < s.arr) {
      const a = prep.pos[s.from], b = prep.pos[s.to], f = (T - s.dep) / (s.arr - s.dep)
      markers.push({ id: s.id, x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f })
      if (markers.length >= MAX_MARKERS) break
    }
  }
  const drops = prep.drops.filter(d => d.tick <= T && T - d.tick <= 1.5).slice(0, 40)
  const deliveries = prep.deliveries.filter(d => d.tick <= T && T - d.tick <= 1).slice(0, 40)
  return { activeLinks, failed, congestion, queues, markers, drops, deliveries }
}
