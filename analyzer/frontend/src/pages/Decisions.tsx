import { useEffect, useState } from 'react'
import { api, type DecisionPacket } from '../lib/api'
import { formatTs, shortId } from '../lib/utils'
import StatusBadge from '../components/StatusBadge'
import RiskBar from '../components/RiskBar'

export default function Decisions() {
  const [packets, setPackets] = useState<DecisionPacket[]>([])
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState<DecisionPacket | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.decisions(50, 0).then(d => {
      setPackets(d.items)
      setTotal(d.total)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex h-full">
      {/* List pane */}
      <div className="w-96 shrink-0 border-r border-gray-800 overflow-y-auto">
        <div className="p-4 border-b border-gray-800">
          <h1 className="text-lg font-bold">Decision Log</h1>
          <p className="text-xs text-gray-500">{total} total packets</p>
        </div>

        {loading && <p className="p-4 text-gray-500 text-sm">Loading…</p>}

        {packets.map(p => (
          <button
            key={p.packet_id}
            onClick={() => setSelected(p)}
            className={`w-full text-left p-3 border-b border-gray-800/50 hover:bg-gray-800/40 transition-colors ${selected?.packet_id === p.packet_id ? 'bg-gray-800' : ''}`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-xs text-gray-500">{shortId(p.packet_id)}</span>
              <StatusBadge decision={p.guard_decision} />
            </div>
            <div className="font-mono text-sm">{p.action_requested}</div>
            <div className="mt-1">
              <RiskBar value={p.guard_decision.risk_score.value} />
            </div>
            <div className="text-xs text-gray-600 mt-1">{formatTs(p.timestamp)}</div>
          </button>
        ))}

        {!loading && packets.length === 0 && (
          <p className="p-4 text-gray-600 text-sm">No packets yet.</p>
        )}
      </div>

      {/* Detail pane */}
      <div className="flex-1 overflow-y-auto p-6">
        {selected ? (
          <DecisionDetail packet={selected} />
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-gray-600">Select a packet to inspect</p>
          </div>
        )}
      </div>
    </div>
  )
}

function DecisionDetail({ packet }: { packet: DecisionPacket }) {
  const d = packet.guard_decision
  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h2 className="text-xl font-bold font-mono">{packet.action_requested}</h2>
          <StatusBadge decision={d} />
        </div>
        <p className="text-xs text-gray-500 font-mono">{packet.packet_id}</p>
        <p className="text-xs text-gray-600">{formatTs(packet.timestamp)}</p>
      </div>

      <Section title="Risk Score">
        <div className="mb-2">
          <RiskBar value={d.risk_score.value} />
        </div>
        {Object.entries(d.risk_score.contributors).map(([k, v]) => (
          <div key={k} className="flex items-center justify-between text-sm py-0.5">
            <span className="text-gray-400">{k}</span>
            <span className="font-mono text-gray-300">{typeof v === 'number' ? v.toFixed(3) : String(v)}</span>
          </div>
        ))}
      </Section>

      {d.rejection_reason && (
        <Section title="Rejection Reason">
          <p className="text-red-300 text-sm">{d.rejection_reason}</p>
        </Section>
      )}

      {d.modified_params && (
        <Section title="Modified Parameters">
          <pre className="text-xs text-green-300 font-mono whitespace-pre-wrap">
            {JSON.stringify(d.modified_params, null, 2)}
          </pre>
        </Section>
      )}

      <Section title="Applied Policies">
        {d.applied_policies.length > 0 ? (
          d.applied_policies.map(p => (
            <span key={p} className="inline-block mr-2 mb-1 px-2 py-0.5 bg-brand-900 text-brand-300 border border-brand-700 rounded text-xs font-mono">
              {p}
            </span>
          ))
        ) : (
          <span className="text-gray-500 text-sm">none</span>
        )}
      </Section>

      <Section title="Request Parameters">
        <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap">
          {JSON.stringify(packet.action_params, null, 2)}
        </pre>
      </Section>

      <Section title="Fingerprint">
        <p className="font-mono text-xs text-gray-400 break-all">{packet.fingerprint}</p>
        {packet._verified !== undefined && (
          <p className={`text-xs mt-1 ${packet._verified ? 'text-green-400' : 'text-red-400'}`}>
            {packet._verified ? '✓ Verified' : '✗ Tampered'}
          </p>
        )}
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h3 className="text-xs text-gray-500 uppercase tracking-wide mb-3">{title}</h3>
      {children}
    </div>
  )
}
