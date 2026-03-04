import { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { api, type DecisionPacket, type HealthResponse } from '../lib/api'
import { formatTs, riskColor, shortId } from '../lib/utils'
import StatusBadge from '../components/StatusBadge'
import RiskBar from '../components/RiskBar'

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [packets, setPackets] = useState<DecisionPacket[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [h, d] = await Promise.all([
          api.health(),
          api.decisions(20, 0),
        ])
        setHealth(h)
        setPackets(d.items)
      } finally {
        setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  const blocked = packets.filter(p => !p.guard_decision.allowed).length
  const modified = packets.filter(
    p => p.guard_decision.allowed && p.guard_decision.modified_params
  ).length
  const blockRate = packets.length ? ((blocked / packets.length) * 100).toFixed(0) : '0'

  const chartData = [...packets]
    .reverse()
    .map((p, i) => ({
      i,
      risk: +(p.guard_decision.risk_score.value * 100).toFixed(0),
      action: p.action_requested,
    }))

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {loading && <p className="text-gray-500 text-sm">Loading…</p>}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total decisions" value={health?.decisions_in_memory ?? 0} />
        <StatCard label="Block rate" value={`${blockRate}%`} accent={blocked > 0 ? 'red' : 'green'} />
        <StatCard label="Modified" value={modified} accent="yellow" />
        <StatCard label="Active policies" value={health?.active_policies ?? 0} />
      </div>

      {/* Risk timeline */}
      {chartData.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-400 mb-4">Risk score timeline (last 20 decisions)</h2>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="riskGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="i" hide />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(v: number) => [`${v}`, 'Risk']}
              />
              <Area
                type="monotone"
                dataKey="risk"
                stroke="#6366f1"
                fill="url(#riskGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent decisions table */}
      <div className="card overflow-hidden">
        <h2 className="text-sm font-semibold text-gray-400 mb-4">Recent decisions</h2>
        {packets.length === 0 ? (
          <p className="text-gray-600 text-sm">No decisions yet. Try the Guard Tester.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs border-b border-gray-800">
                <th className="text-left pb-2">ID</th>
                <th className="text-left pb-2">Action</th>
                <th className="text-left pb-2">Status</th>
                <th className="text-left pb-2">Risk</th>
                <th className="text-left pb-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {packets.map(p => (
                <tr key={p.packet_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-2 font-mono text-xs text-gray-500">{shortId(p.packet_id)}</td>
                  <td className="py-2 font-mono">{p.action_requested}</td>
                  <td className="py-2"><StatusBadge decision={p.guard_decision} /></td>
                  <td className="py-2 w-32">
                    <RiskBar value={p.guard_decision.risk_score.value} />
                  </td>
                  <td className="py-2 text-gray-500 text-xs">{formatTs(p.timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, accent = 'brand' }: {
  label: string
  value: string | number
  accent?: 'brand' | 'red' | 'green' | 'yellow'
}) {
  const colors = {
    brand: 'text-brand-400',
    red: 'text-red-400',
    green: 'text-green-400',
    yellow: 'text-yellow-400',
  }
  return (
    <div className="card flex flex-col gap-1">
      <span className="text-xs text-gray-500 uppercase tracking-wide">{label}</span>
      <span className={`text-3xl font-bold ${colors[accent]}`}>{value}</span>
    </div>
  )
}
