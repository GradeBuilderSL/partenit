# Partenit Monitoring

Minimal observability stack for the Partenit safety guard.

## Quick start

```bash
# 1. Start the Partenit Analyzer backend (exposes /metrics)
cd analyzer && docker-compose up

# 2. Start Prometheus
prometheus --config.file=monitoring/prometheus.yml

# 3. Import Grafana dashboard
# In Grafana UI: Dashboards → Import → upload monitoring/grafana_dashboard.json
```

## Metrics exposed at `GET /metrics`

| Metric | Type | Description |
|---|---|---|
| `partenit_guard_decisions_total` | Counter | Guard evaluations. Labels: `allowed`, `action`, `modified` |
| `partenit_guard_latency_ms` | Histogram | Guard evaluation wall-clock time |
| `partenit_risk_score` | Gauge | Last computed risk score |
| `partenit_sensor_trust_level` | Gauge | Per-sensor trust level. Label: `sensor_id` |
| `partenit_policy_fires_total` | Counter | Rule fires. Label: `rule_id` |

## Grafana Dashboard

`grafana_dashboard.json` covers:
- Decisions / sec + block rate + p99 latency (stat row)
- Allowed / blocked / clamped time series
- Risk score timeline
- Sensor trust level per sensor
- Top fired policies table (last 5 min)

Default refresh: 5 seconds.

## Enabling metrics in the Analyzer backend

Install the optional dependency:

```bash
pip install prometheus_client
```

The `/metrics` endpoint is automatically enabled if `prometheus_client` is installed.
If not installed, the endpoint returns `501 Not Implemented`.
