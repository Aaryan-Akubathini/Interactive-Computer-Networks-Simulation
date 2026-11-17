// Minimal reusable SVG line chart: axes, gridlines, labels. data = array of y values (index = tick).
export default function SimpleChart({ title, data, xLabel, yLabel, color = '#2563eb' }) {
  const W = 560, H = 240, L = 50, R = 16, T = 12, B = 40
  if (!data || data.length === 0) return <div className="card"><h3>{title}</h3><p className="muted">No data.</p></div>
  const yMax = Math.max(1, Math.ceil(Math.max(...data) * 1.1))
  const x = i => L + (i / Math.max(1, data.length - 1)) * (W - L - R)
  const y = v => T + (1 - v / yMax) * (H - T - B)
  const points = data.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const yTicks = [0, 1, 2, 3, 4].map(i => (yMax * i) / 4)
  const xTicks = [0, 1, 2, 3, 4].map(i => Math.round(((data.length - 1) * i) / 4))
  return (
    <div className="card">
      <h3>{title}</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart">
        {yTicks.map(v => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="#e5e7eb" />
            <text x={L - 6} y={y(v) + 4} textAnchor="end" className="axis">{Number.isInteger(v) ? v : v.toFixed(1)}</text>
          </g>
        ))}
        {xTicks.map(v => <text key={v} x={x(v)} y={H - B + 16} textAnchor="middle" className="axis">{v}</text>)}
        <line x1={L} x2={L} y1={T} y2={H - B} stroke="#9ca3af" />
        <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke="#9ca3af" />
        <polyline points={points} fill="none" stroke={color} strokeWidth={2} />
        <text x={(L + W - R) / 2} y={H - 6} textAnchor="middle" className="axis">{xLabel}</text>
        <text transform={`translate(12 ${(T + H - B) / 2}) rotate(-90)`} textAnchor="middle" className="axis">{yLabel}</text>
      </svg>
    </div>
  )
}
