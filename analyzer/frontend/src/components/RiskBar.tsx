import { riskBg, riskColor } from '../lib/utils'

interface Props {
  value: number
  showLabel?: boolean
}

export default function RiskBar({ value, showLabel = true }: Props) {
  const pct = Math.round(value * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${riskBg(value)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className={`text-xs font-mono tabular-nums ${riskColor(value)}`}>
          {(value).toFixed(2)}
        </span>
      )}
    </div>
  )
}
