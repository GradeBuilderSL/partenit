import type { GuardDecision } from '../lib/api'

interface Props {
  decision: GuardDecision
}

export default function StatusBadge({ decision }: Props) {
  if (!decision.allowed) {
    return <span className="badge-blocked">BLOCKED</span>
  }
  if (decision.modified_params) {
    return <span className="badge-modified">MODIFIED</span>
  }
  return <span className="badge-allowed">ALLOWED</span>
}
