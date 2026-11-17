import { useMemo, useRef } from 'react'

const W = 900, H = 520
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))

// Native SVG topology. mode="edit": drag nodes, click nodes/links. mode="view": shows playback overlay.
export default function NetworkCanvas({
  nodes, links, mode = 'view', selected, pendingFrom,
  onNodeMove, onNodeClick, onLinkClick, onBackgroundClick, overlay, selectedPacket,
}) {
  const svgRef = useRef(null)
  const drag = useRef(null)
  const byId = useMemo(() => Object.fromEntries(nodes.map(n => [n.id, n])), [nodes])

  function point(e) {
    const svg = svgRef.current
    const pt = svg.createSVGPoint()
    pt.x = e.clientX; pt.y = e.clientY
    return pt.matrixTransform(svg.getScreenCTM().inverse())
  }
  function down(e, n) {
    if (mode !== 'edit') return
    e.stopPropagation()
    svgRef.current.setPointerCapture(e.pointerId)
    const p = point(e)
    drag.current = { id: n.id, sx: p.x, sy: p.y, dx: p.x - n.x, dy: p.y - n.y, moved: false }
  }
  function move(e) {
    const d = drag.current
    if (!d) return
    const p = point(e)
    if (!d.moved && Math.hypot(p.x - d.sx, p.y - d.sy) < 4) return
    d.moved = true
    onNodeMove(d.id, clamp(p.x - d.dx, 24, W - 24), clamp(p.y - d.dy, 24, H - 24))
  }
  function up() {
    const d = drag.current
    drag.current = null
    if (d && !d.moved) onNodeClick(d.id)
  }

  return (
    <svg ref={svgRef} className="canvas" viewBox={`0 0 ${W} ${H}`} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      <rect width={W} height={H} fill="transparent" onPointerDown={() => onBackgroundClick && onBackgroundClick()} />

      {links.map(l => {
        const a = byId[l.a], b = byId[l.b]
        if (!a || !b) return null
        const failed = overlay ? overlay.failed.has(l.id) : l.status === 'failed'
        const congested = overlay && (overlay.congestion[l.id] || 0) >= 0.5
        const active = overlay && overlay.activeLinks.has(l.id)
        const isSel = selected && selected.type === 'link' && selected.id === l.id
        let stroke = '#94a3b8', width = 3, dash
        if (active) { stroke = '#2563eb'; width = 5 }
        if (congested) { stroke = '#f97316'; width = 5 }
        if (failed) { stroke = '#dc2626'; width = 3; dash = '7 5' }
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2
        const q = overlay ? overlay.queues[l.id] : null
        return (
          <g key={l.id}>
            {isSel && <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#bfdbfe" strokeWidth={12} strokeLinecap="round" />}
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={stroke} strokeWidth={width} strokeDasharray={dash} strokeLinecap="round" />
            {mode === 'edit' && (
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={16}
                style={{ cursor: 'pointer' }} onClick={() => onLinkClick(l.id)} />
            )}
            <text x={mx} y={my - 8} className="link-label">
              {q != null && q > 0 ? `queue ${q}/${l.buffer}` : `c${l.capacity} d${l.delay} b${l.buffer}`}
            </text>
          </g>
        )
      })}

      {nodes.map(n => {
        const isSel = selected && selected.type === 'node' && selected.id === n.id
        const isPending = pendingFrom === n.id
        const stroke = isSel || isPending ? '#1e3a8a' : '#2563eb'
        return (
          <g key={n.id} onPointerDown={e => down(e, n)} style={{ cursor: mode === 'edit' ? 'grab' : 'default' }}>
            {n.type === 'router'
              ? <circle cx={n.x} cy={n.y} r={22} fill="#dbeafe" stroke={stroke} strokeWidth={isSel || isPending ? 4 : 2} />
              : <rect x={n.x - 22} y={n.y - 18} width={44} height={36} rx={4} fill="#2563eb" stroke={stroke} strokeWidth={isSel || isPending ? 4 : 2} />}
            <text x={n.x} y={n.y + 4} className={n.type === 'router' ? 'node-text' : 'node-text host-text'}>{n.label}</text>
          </g>
        )
      })}

      {overlay && (
        <g>
          {overlay.deliveries.map(d => byId[d.node] && (
            <circle key={'d' + d.id} cx={byId[d.node].x} cy={byId[d.node].y} r={28} fill="none" stroke="#16a34a" strokeWidth={3} opacity={0.8} />
          ))}
          {overlay.drops.map(d => byId[d.node] && (
            <g key={'x' + d.id} onClick={() => overlay.onMarkerClick(d.id)} style={{ cursor: 'pointer' }}>
              <circle cx={byId[d.node].x + 14} cy={byId[d.node].y - 24} r={6} fill="#dc2626" />
              <text x={byId[d.node].x + 14} y={byId[d.node].y - 21} className="drop-x">×</text>
            </g>
          ))}
          {overlay.markers.map(m => (
            <g key={m.id} onClick={() => overlay.onMarkerClick(m.id)} style={{ cursor: 'pointer' }}>
              <circle cx={m.x} cy={m.y} r={10} fill="transparent" />
              <circle cx={m.x} cy={m.y} r={selectedPacket === m.id ? 7 : 4.5} fill="#2563eb"
                stroke={selectedPacket === m.id ? '#0f172a' : '#fff'} strokeWidth={selectedPacket === m.id ? 2 : 1} />
            </g>
          ))}
        </g>
      )}
    </svg>
  )
}
