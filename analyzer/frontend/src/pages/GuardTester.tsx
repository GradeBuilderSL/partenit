import { useState } from 'react'
import { api, type GuardDecision } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import RiskBar from '../components/RiskBar'

const DEFAULT_ACTION = 'navigate_to'
const DEFAULT_PARAMS = '{"zone": "shipping", "speed": 2.0}'
const DEFAULT_CONTEXT = '{"human": {"distance": 1.2}}'

export default function GuardTester() {
  const [action, setAction] = useState(DEFAULT_ACTION)
  const [params, setParams] = useState(DEFAULT_PARAMS)
  const [context, setContext] = useState(DEFAULT_CONTEXT)
  const [result, setResult] = useState<{
    decision: GuardDecision
    packet_id?: string
    fingerprint?: string
    verified?: boolean
  } | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleCheck = async () => {
    setError('')
    setLoading(true)
    try {
      const p = JSON.parse(params) as Record<string, unknown>
      const c = JSON.parse(context) as Record<string, unknown>
      const r = await api.guardCheck(action, p, c)
      setResult(r)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold">Live Guard Tester</h1>
        <p className="text-sm text-gray-500 mt-1">
          Send an action + context to the running AgentGuard and see the decision in real time.
        </p>
      </div>

      <div className="card space-y-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Action name</label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-500"
            value={action}
            onChange={e => setAction(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">Parameters (JSON)</label>
          <textarea
            rows={3}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-500 resize-none"
            value={params}
            onChange={e => setParams(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">Context (JSON)</label>
          <textarea
            rows={3}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-500 resize-none"
            value={context}
            onChange={e => setContext(e.target.value)}
          />
        </div>

        <button
          onClick={handleCheck}
          disabled={loading}
          className="w-full py-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 rounded-lg font-medium text-sm transition-colors"
        >
          {loading ? 'Checking…' : 'Check Action'}
        </button>
      </div>

      {error && (
        <div className="card border-red-800">
          <p className="text-red-400 text-sm font-mono">{error}</p>
        </div>
      )}

      {result && (
        <div className="card space-y-4">
          <div className="flex items-center gap-3">
            <StatusBadge decision={result.decision} />
            <span className="text-sm text-gray-400">
              Latency: {result.decision.latency_ms.toFixed(1)}ms
            </span>
          </div>

          <div>
            <p className="text-xs text-gray-500 mb-1">Risk score</p>
            <RiskBar value={result.decision.risk_score.value} />
          </div>

          {result.decision.rejection_reason && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Rejection reason</p>
              <p className="text-red-300 text-sm">{result.decision.rejection_reason}</p>
            </div>
          )}

          {result.decision.modified_params && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Modified parameters</p>
              <pre className="text-xs text-green-300 font-mono">
                {JSON.stringify(result.decision.modified_params, null, 2)}
              </pre>
            </div>
          )}

          {result.decision.applied_policies.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Applied policies</p>
              <div className="flex flex-wrap gap-1">
                {result.decision.applied_policies.map(p => (
                  <span key={p} className="px-2 py-0.5 bg-brand-900 text-brand-300 border border-brand-700 rounded text-xs font-mono">
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}

          {result.fingerprint && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Decision packet fingerprint</p>
              <p className="text-xs font-mono text-gray-400 break-all">{result.fingerprint}</p>
              <p className={`text-xs mt-0.5 ${result.verified ? 'text-green-400' : 'text-red-400'}`}>
                {result.verified ? '✓ Verified' : '✗ Verification failed'}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
