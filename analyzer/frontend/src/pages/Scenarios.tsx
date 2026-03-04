import { useState } from 'react'
import { api } from '../lib/api'

const EXAMPLE_SCENARIO = `scenario_id: live_test
robot:
  start_position: [0, 0, 0]
  goal_position: [10, 0, 0]
  initial_speed: 1.5
world:
  humans:
    - id: human_01
      start_position: [4, 0.5, 0]
      velocity: [0, -0.5, 0]
      arrival_time: 0.0
policies: []
expected_events: []
duration: 10.0
dt: 0.1
`

export default function Scenarios() {
  const [yaml, setYaml] = useState(EXAMPLE_SCENARIO)
  const [withGuard, setWithGuard] = useState(true)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleRun = async () => {
    setError('')
    setLoading(true)
    try {
      const r = await api.runScenario(yaml, withGuard)
      setResult(r)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">Scenario Replayer</h1>
        <p className="text-sm text-gray-500 mt-1">
          Run a safety scenario inline. Compare behavior with and without the guard.
        </p>
      </div>

      <div className="card space-y-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Scenario YAML</label>
          <textarea
            rows={20}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-500 resize-y"
            value={yaml}
            onChange={e => setYaml(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={withGuard}
              onChange={e => setWithGuard(e.target.checked)}
              className="w-4 h-4 accent-brand-500"
            />
            <span className="text-sm text-gray-300">Enable guard</span>
          </label>

          <button
            onClick={handleRun}
            disabled={loading}
            className="ml-auto px-6 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 rounded-lg font-medium text-sm transition-colors"
          >
            {loading ? 'Running…' : 'Run Scenario'}
          </button>
        </div>
      </div>

      {error && (
        <div className="card border-red-800">
          <p className="text-red-400 text-sm font-mono">{error}</p>
        </div>
      )}

      {result && (
        <div className="card space-y-3">
          <h2 className="text-sm font-semibold text-gray-400">Result: {String(result.scenario_id)}</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Stat label="With guard" value={result.with_guard ? 'Yes' : 'No'} />
            <Stat label="Reached goal" value={result.reached_goal ? 'Yes' : 'No'} />
            <Stat label="Decisions total" value={result.decisions_total} />
            <Stat label="Decisions blocked" value={result.decisions_blocked} />
            <Stat label="Block rate" value={typeof result.block_rate === 'number' ? `${(result.block_rate * 100).toFixed(1)}%` : '—'} />
            <Stat label="Wall time" value={typeof result.wall_time_ms === 'number' ? `${result.wall_time_ms.toFixed(0)}ms` : '—'} />
          </div>
          <details>
            <summary className="cursor-pointer text-xs text-gray-500">Raw JSON</summary>
            <pre className="mt-2 text-xs text-gray-400 font-mono overflow-x-auto">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex justify-between py-1 border-b border-gray-800">
      <span className="text-gray-500">{label}</span>
      <span className="font-mono text-gray-200">{String(value)}</span>
    </div>
  )
}
