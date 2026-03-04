import { useEffect, useState } from 'react'
import { api, type TrustState } from '../lib/api'
import RiskBar from '../components/RiskBar'

const MODE_COLORS: Record<string, string> = {
  nominal: 'text-green-400',
  degraded: 'text-yellow-400',
  unreliable: 'text-orange-400',
  failed: 'text-red-400',
}

export default function TrustMonitor() {
  const [sensors, setSensors] = useState<TrustState[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = () => api.trustCurrent().then(d => setSensors(d.sensors)).finally(() => setLoading(false))
    load()
    const id = setInterval(load, 3000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Trust Monitor</h1>
      <p className="text-sm text-gray-500">
        Sensor trust values are updated by <code className="text-brand-400">SensorTrustModel</code>.
        Values degrade on noise, lighting drops, and detection inconsistency.
      </p>

      {loading && <p className="text-gray-500 text-sm">Loading…</p>}

      {sensors.length === 0 && !loading && (
        <div className="card">
          <p className="text-gray-600 text-sm">
            No trust data yet. Trust states are populated when the robot adapter
            reports sensor signals.
          </p>
          <p className="text-gray-500 text-xs mt-2">
            In the demo, mock sensors don't push trust updates — this page shows
            live data from a real robot adapter or the trust engine API.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sensors.map(s => (
          <SensorCard key={s.sensor_id} sensor={s} />
        ))}
      </div>
    </div>
  )
}

function SensorCard({ sensor }: { sensor: TrustState }) {
  const modeColor = MODE_COLORS[sensor.mode] ?? 'text-gray-400'
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-mono font-bold">{sensor.sensor_id}</span>
        <span className={`text-sm font-semibold ${modeColor}`}>{sensor.mode}</span>
      </div>
      <div>
        <p className="text-xs text-gray-500 mb-1">Trust level</p>
        <RiskBar value={1 - sensor.trust_value} showLabel={false} />
        <p className="text-right text-xs font-mono text-gray-300 mt-0.5">
          {(sensor.trust_value * 100).toFixed(0)}%
        </p>
      </div>
      {sensor.degradation_reasons.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 mb-1">Degradation reasons</p>
          <div className="flex flex-wrap gap-1">
            {sensor.degradation_reasons.map(r => (
              <span key={r} className="px-1.5 py-0.5 bg-red-950 text-red-400 border border-red-800 rounded text-xs">
                {r}
              </span>
            ))}
          </div>
        </div>
      )}
      <p className="text-xs text-gray-600">Updated: {sensor.last_updated}</p>
    </div>
  )
}
