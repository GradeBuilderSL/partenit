import { useEffect, useState } from 'react'
import { api, type PolicyRule } from '../lib/api'

const PRIORITY_COLORS: Record<string, string> = {
  safety_critical: 'bg-red-900 text-red-300 border-red-700',
  legal: 'bg-orange-900 text-orange-300 border-orange-700',
  task: 'bg-blue-900 text-blue-300 border-blue-700',
  efficiency: 'bg-gray-800 text-gray-400 border-gray-600',
}

export default function Policies() {
  const [rules, setRules] = useState<PolicyRule[]>([])
  const [path, setPath] = useState<string | null>(null)
  const [loadPath, setLoadPath] = useState('')
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')

  const reload = () => {
    api.activePolicies().then(d => {
      setRules(d.rules)
      setPath(d.path)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { reload() }, [])

  const handleLoad = async () => {
    if (!loadPath.trim()) return
    try {
      const r = await api.loadPolicies(loadPath.trim())
      setMsg(`Loaded ${r.loaded} rules`)
      reload()
    } catch (e) {
      setMsg(String(e))
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Policy Viewer</h1>
          {path && <p className="text-xs text-gray-500 mt-0.5">{path}</p>}
        </div>
        <div className="flex gap-2">
          <input
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm w-72 focus:outline-none focus:border-brand-500"
            placeholder="/path/to/policies.yaml"
            value={loadPath}
            onChange={e => setLoadPath(e.target.value)}
          />
          <button
            onClick={handleLoad}
            className="px-4 py-1.5 bg-brand-600 hover:bg-brand-500 rounded-lg text-sm font-medium transition-colors"
          >
            Load
          </button>
        </div>
      </div>

      {msg && <p className="text-sm text-brand-300">{msg}</p>}
      {loading && <p className="text-gray-500 text-sm">Loading…</p>}

      <div className="grid gap-3">
        {rules.map((r) => (
          <RuleCard key={r.rule_id} rule={r} />
        ))}
        {!loading && rules.length === 0 && (
          <p className="text-gray-600 text-sm">No policies loaded. Use the input above to load a YAML file.</p>
        )}
      </div>
    </div>
  )
}

function RuleCard({ rule }: { rule: PolicyRule }) {
  const priorityClass = PRIORITY_COLORS[rule.priority] ?? PRIORITY_COLORS.efficiency
  return (
    <div className="card space-y-2">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="font-mono text-sm font-bold text-white">{rule.rule_id}</span>
          <span className="ml-2 text-gray-400 text-sm">{rule.name}</span>
        </div>
        <span className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${priorityClass}`}>
          {rule.priority}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-gray-500 mb-1">Condition</p>
          <pre className="text-gray-300 font-mono whitespace-pre-wrap">
            {JSON.stringify(rule.condition, null, 2)}
          </pre>
        </div>
        <div>
          <p className="text-gray-500 mb-1">Action</p>
          <pre className="text-gray-300 font-mono whitespace-pre-wrap">
            {JSON.stringify(rule.action, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  )
}
