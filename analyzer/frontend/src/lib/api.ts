/**
 * Partenit Analyzer API client.
 * All calls go through the Vite proxy /api → http://localhost:8000
 */

const BASE = '/api'

export interface RiskScore {
  value: number
  contributors: Record<string, number>
  plan_id: string | null
  timestamp: string
}

export interface GuardDecision {
  allowed: boolean
  modified_params: Record<string, unknown> | null
  rejection_reason: string | null
  risk_score: RiskScore
  applied_policies: string[]
  suggested_alternative: Record<string, unknown> | null
  latency_ms: number
}

export interface DecisionPacket {
  packet_id: string
  timestamp: string
  action_requested: string
  action_params: Record<string, unknown>
  guard_decision: GuardDecision
  mission_goal: string
  observation_hashes: string[]
  fingerprint: string
  _verified?: boolean
}

export interface TrustState {
  sensor_id: string
  trust_value: number
  degradation_reasons: string[]
  last_updated: string
  mode: string
}

export interface PolicyRule {
  rule_id: string
  name: string
  priority: string
  condition: unknown
  action: unknown
}

export interface HealthResponse {
  status: string
  decisions_in_memory: number
  active_policies: number
  trust_sensors: number
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`POST ${path} failed: ${res.status} — ${err}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => get<HealthResponse>('/health'),

  decisions: (limit = 50, offset = 0) =>
    get<{ total: number; items: DecisionPacket[] }>(
      `/decisions?limit=${limit}&offset=${offset}`
    ),

  decision: (id: string) =>
    get<DecisionPacket & { _verified: boolean }>(`/decisions/${id}`),

  verify: (id: string) =>
    get<{ packet_id: string; fingerprint: string; verified: boolean }>(
      `/decisions/${id}/verify`
    ),

  trustCurrent: () =>
    get<{ count: number; sensors: TrustState[] }>('/trust/current'),

  activePolicies: () =>
    get<{ count: number; path: string | null; rules: PolicyRule[] }>(
      '/policies/active'
    ),

  loadPolicies: (path: string) =>
    post<{ loaded: number; path: string }>('/policies/load', { path }),

  guardCheck: (action: string, params: Record<string, unknown>, context: Record<string, unknown>) =>
    post<{
      decision: GuardDecision
      packet_id?: string
      fingerprint?: string
      verified?: boolean
    }>('/guard/check', { action, params, context }),

  runScenario: (scenario_yaml: string, with_guard = true) =>
    post<Record<string, unknown>>('/scenarios/run', { scenario_yaml, with_guard }),

  scenarioResults: () =>
    get<{ count: number; results: Record<string, unknown>[] }>('/scenarios/results'),
}
