"""
Eval HTML report generator.

Produces a standalone HTML file with:
- Grade badges per controller
- Score breakdown bars (safety / efficiency / ai / overall)
- 2D top-down trajectory SVG (robot path, human path, stop/slowdown markers)
- Time-series SVG charts: distance to human, speed, risk score
- Policy fire timeline
- Controller comparison table per scenario
- Score formula explanation
"""

from __future__ import annotations

from datetime import UTC, datetime

from partenit.safety_bench.eval.metrics import EvalMetrics
from partenit.safety_bench.eval.runner import EvalReport

# --- Chart dimensions ---
_W = 420   # chart width px
_H = 120   # timeseries chart height px
_PAD = 28  # padding

_GRADE_COLORS = {
    "A": ("#16a34a", "#dcfce7"),  # green
    "B": ("#0d9488", "#ccfbf1"),  # teal
    "C": ("#ca8a04", "#fef9c3"),  # yellow
    "D": ("#ea580c", "#ffedd5"),  # orange
    "F": ("#dc2626", "#fee2e2"),  # red
}

_CSS = """
:root{--bg:#0f1117;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'JetBrains Mono',Consolas,monospace;background:var(--bg);color:var(--text);padding:2rem;font-size:14px;line-height:1.5;}
h1{color:#60a5fa;font-size:1.6rem;margin-bottom:.25rem;}
.meta{color:var(--muted);font-size:.85rem;margin-bottom:2rem;}
h2{color:#93c5fd;margin:2rem 0 .75rem;}
h3{color:#cbd5e1;font-size:.95rem;margin:1.5rem 0 .5rem;}
.scenario-block{background:var(--surface);border:1px solid var(--border);border-radius:.5rem;padding:1.5rem;margin-bottom:2rem;}
.grade-badge{display:inline-block;padding:.25rem .75rem;border-radius:.25rem;font-weight:bold;font-size:1.1rem;margin-right:.5rem;}
.ctrl-row{display:flex;align-items:center;gap:1rem;margin:.5rem 0;}
.ctrl-name{font-weight:bold;min-width:14rem;}
.score-bar-wrap{flex:1;display:flex;flex-direction:column;gap:.3rem;}
.bar-line{display:flex;align-items:center;gap:.5rem;}
.bar-label{width:9rem;color:var(--muted);font-size:.8rem;}
.bar-track{flex:1;background:#1e293b;border-radius:2px;height:8px;}
.bar-fill{height:8px;border-radius:2px;transition:width .3s;}
.bar-val{width:3rem;text-align:right;font-size:.8rem;color:var(--muted);}
table.cmp{width:100%;border-collapse:collapse;margin:.75rem 0;}
table.cmp th{background:#1e293b;padding:.4rem .75rem;text-align:left;color:var(--muted);font-weight:normal;font-size:.85rem;}
table.cmp td{padding:.4rem .75rem;border-bottom:1px solid var(--border);font-size:.85rem;}
table.cmp td:first-child{color:var(--muted);}
.formula{background:#1a2535;border-left:3px solid #334155;padding:.75rem 1rem;font-size:.8rem;color:var(--muted);margin-top:1rem;line-height:1.8;}
.best{color:#34d399;font-weight:bold;}
.charts-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:1rem;margin:1rem 0;}
.chart-cell{background:#111827;border:1px solid #1e293b;border-radius:.4rem;padding:.5rem;}
.chart-title{font-size:.75rem;color:#64748b;margin-bottom:.3rem;}
.ctrl-section{margin-top:1.5rem;border-top:1px solid var(--border);padding-top:1rem;}
.ctrl-label{font-size:.85rem;font-weight:bold;color:#93c5fd;margin-bottom:.5rem;}
.policy-timeline{font-size:.75rem;color:var(--muted);margin-top:.5rem;line-height:1.7;}
.policy-fire{display:inline-block;background:#1e293b;border-left:3px solid #60a5fa;padding:.1rem .4rem;margin:.1rem 0;border-radius:0 .2rem .2rem 0;}
.fire-allowed{border-left-color:#f59e0b;}
.fire-blocked{border-left-color:#ef4444;}
details{margin-top:.75rem;}
details>summary{cursor:pointer;color:#60a5fa;font-size:.85rem;user-select:none;}
details>summary:hover{color:#93c5fd;}
"""


# ---------------------------------------------------------------------------
# SVG helpers (self-contained, no external deps)
# ---------------------------------------------------------------------------

def _svg_timeseries(
    data: list[tuple[float, float]],
    color: str,
    title: str,
    y_max: float,
    events: list[dict] | None = None,
    threshold_y: float | None = None,
) -> str:
    """Render a compact SVG line chart for a (time, value) series."""
    w, h, p = _W, _H, _PAD
    if not data:
        return (
            f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="{w}" height="{h}" fill="#1a1f2e" rx="4"/>'
            f'<text x="16" y="40" fill="#475569" font-size="11">No data</text></svg>'
        )

    times = [d[0] for d in data]
    values = [d[1] for d in data]
    t_max = max(times) if times else 1.0
    if y_max <= 0:
        y_max = max(values) if values else 1.0
    if y_max <= 0:
        y_max = 1.0

    def tx(t: float) -> float:
        return p + (t / t_max) * (w - 2 * p)

    def ty(v: float) -> float:
        return h - p - (min(v, y_max) / y_max) * (h - 2 * p)

    clip_pts = (
        f"{tx(times[0]):.1f},{ty(0):.1f} "
        + " ".join(f"{tx(t):.1f},{ty(v):.1f}" for t, v in data)
        + f" {tx(times[-1]):.1f},{ty(0):.1f}"
    )
    line_pts = " ".join(f"{tx(t):.1f},{ty(v):.1f}" for t, v in data)

    # Grid lines
    grid = ""
    for frac in (0.0, 0.5, 1.0):
        val = frac * y_max
        y = ty(val)
        grid += (
            f'<line x1="{p}" y1="{y:.1f}" x2="{w - p}" y2="{y:.1f}" '
            f'stroke="#1e2d40" stroke-width="1"/>'
            f'<text x="{p - 3}" y="{y + 3:.1f}" fill="#334155" font-size="8" '
            f'text-anchor="end">{val:.1f}</text>'
        )

    # Time ticks
    xticks = ""
    for i in (0, 2, 4):
        t_val = t_max * i / 4
        x = tx(t_val)
        xticks += (
            f'<line x1="{x:.1f}" y1="{h - p}" x2="{x:.1f}" y2="{h - p + 3}" '
            f'stroke="#334155" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{h - p + 11}" fill="#334155" font-size="8" '
            f'text-anchor="middle">{t_val:.0f}s</text>'
        )

    # Optional threshold line (e.g. danger zone)
    thresh_line = ""
    if threshold_y is not None and 0 < threshold_y <= y_max:
        ty_thresh = ty(threshold_y)
        thresh_line = (
            f'<line x1="{p}" y1="{ty_thresh:.1f}" x2="{w - p}" y2="{ty_thresh:.1f}" '
            f'stroke="#ef4444" stroke-width="1" stroke-dasharray="4 3" opacity="0.5"/>'
        )

    # Event markers
    evt_marks = ""
    for evt in (events or []):
        et = evt.get("time", -1)
        if 0 <= et <= t_max:
            ec = "#ef4444" if evt.get("type") == "stop" else "#f59e0b"
            ex = tx(et)
            evt_marks += (
                f'<line x1="{ex:.1f}" y1="{p}" x2="{ex:.1f}" y2="{h - p}" '
                f'stroke="{ec}" stroke-width="1" stroke-dasharray="3 2" opacity="0.6"/>'
            )

    return (
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{w}" height="{h}" fill="#1a1f2e" rx="4"/>'
        f'{grid}'
        f'<line x1="{p}" y1="{p // 2}" x2="{p}" y2="{h - p}" stroke="#2d3f55" stroke-width="1"/>'
        f'<line x1="{p}" y1="{h - p}" x2="{w - p}" y2="{h - p}" stroke="#2d3f55" stroke-width="1"/>'
        f'{xticks}'
        f'{thresh_line}'
        f'{evt_marks}'
        f'<polygon points="{clip_pts}" fill="{color}" opacity="0.12"/>'
        f'<polyline points="{line_pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'<text x="{w // 2}" y="13" fill="#64748b" font-size="9" '
        f'text-anchor="middle" font-style="italic">{title}</text>'
        f'</svg>'
    )


def _svg_2d_replay(
    robot_trajectory: list[tuple[float, float]],
    human_trajectories: dict[str, list[tuple[float, float]]],
    robot_goal: tuple[float, float],
    events: list[dict] | None = None,
    title: str = "Trajectory",
) -> str:
    """Render a compact top-down 2D SVG replay."""
    w, h, pad = _W, 220, 30
    human_palette = ["#f87171", "#fb923c", "#facc15", "#a78bfa"]

    all_x = [p[0] for p in robot_trajectory] + [robot_goal[0]]
    all_y = [p[1] for p in robot_trajectory] + [robot_goal[1]]
    for pts in human_trajectories.values():
        all_x.extend(p[0] for p in pts)
        all_y.extend(p[1] for p in pts)

    if not all_x:
        return (
            f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="{w}" height="{h}" fill="#1a1f2e" rx="4"/>'
            f'<text x="16" y="40" fill="#475569" font-size="11">No trajectory data</text>'
            f'</svg>'
        )

    margin = 1.5
    x_min, x_max = min(all_x) - margin, max(all_x) + margin
    y_min, y_max = min(all_y) - margin, max(all_y) + margin
    x_range = max(x_max - x_min, 0.1)
    y_range = max(y_max - y_min, 0.1)

    vp_w = w - 2 * pad
    vp_h = h - 2 * pad
    scale = min(vp_w / x_range, vp_h / y_range)
    x_off = pad + (vp_w - x_range * scale) / 2
    y_off = pad + (vp_h - y_range * scale) / 2

    def tx(x: float) -> float:
        return x_off + (x - x_min) * scale

    def ty(y: float) -> float:
        return y_off + (y_max - y) * scale   # flip Y → north=up

    robot_pts = " ".join(f"{tx(p[0]):.1f},{ty(p[1]):.1f}" for p in robot_trajectory)

    human_svgs = ""
    for i, (hid, pts) in enumerate(human_trajectories.items()):
        if not pts:
            continue
        col = human_palette[i % len(human_palette)]
        hpts = " ".join(f"{tx(p[0]):.1f},{ty(p[1]):.1f}" for p in pts)
        s, e = pts[0], pts[-1]
        human_svgs += (
            f'<polyline points="{hpts}" fill="none" stroke="{col}" '
            f'stroke-width="2" opacity="0.85"/>'
            f'<circle cx="{tx(s[0]):.1f}" cy="{ty(s[1]):.1f}" r="3" fill="{col}" opacity="0.4"/>'
            f'<circle cx="{tx(e[0]):.1f}" cy="{ty(e[1]):.1f}" r="5" fill="{col}"/>'
            f'<text x="{tx(e[0]) + 7:.1f}" y="{ty(e[1]) + 3:.1f}" fill="{col}" '
            f'font-size="9">{hid}</text>'
        )

    # Stop/slowdown event markers
    stop_marks = ""
    if events and robot_trajectory:
        n = len(robot_trajectory)
        dur_approx = max(n * 0.1, 0.1)
        seen: set[float] = set()
        for evt in events:
            etype = evt.get("type")
            if etype not in ("stop", "slowdown"):
                continue
            et = evt.get("time", 0.0)
            if et in seen:
                continue
            seen.add(et)
            frac = et / dur_approx
            idx = min(int(frac * n), n - 1)
            if idx < 0:
                continue
            ex, ey = tx(robot_trajectory[idx][0]), ty(robot_trajectory[idx][1])
            if etype == "stop":
                stop_marks += (
                    f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="7" '
                    f'fill="none" stroke="#ef4444" stroke-width="2" opacity="0.8"/>'
                )
            else:
                stop_marks += (
                    f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" '
                    f'fill="#f59e0b" opacity="0.8"/>'
                )

    rs = robot_trajectory[0] if robot_trajectory else (0.0, 0.0)
    re = robot_trajectory[-1] if robot_trajectory else (0.0, 0.0)
    gx, gy = tx(robot_goal[0]), ty(robot_goal[1])

    legend = (
        f'<circle cx="30" cy="{h - 12}" r="4" fill="#3b82f6"/>'
        f'<text x="38" y="{h - 8}" fill="#60a5fa" font-size="8">Robot</text>'
        f'<circle cx="82" cy="{h - 12}" r="5" fill="none" stroke="#22c55e" stroke-width="1.5"/>'
        f'<text x="91" y="{h - 8}" fill="#22c55e" font-size="8">Goal</text>'
        f'<circle cx="130" cy="{h - 12}" r="4" fill="#f87171"/>'
        f'<text x="138" y="{h - 8}" fill="#f87171" font-size="8">Human</text>'
        f'<circle cx="188" cy="{h - 12}" r="3" fill="#f59e0b"/>'
        f'<text x="195" y="{h - 8}" fill="#f59e0b" font-size="8">Slow</text>'
        f'<circle cx="227" cy="{h - 12}" r="5" fill="none" stroke="#ef4444" stroke-width="1.5"/>'
        f'<text x="236" y="{h - 8}" fill="#ef4444" font-size="8">Stop</text>'
    )

    return (
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{w}" height="{h}" fill="#1a1f2e" rx="4"/>'
        f'<polyline points="{robot_pts}" fill="none" stroke="#3b82f6" stroke-width="2"/>'
        f'{human_svgs}'
        f'{stop_marks}'
        f'<circle cx="{tx(rs[0]):.1f}" cy="{ty(rs[1]):.1f}" r="5" fill="#93c5fd" opacity="0.5"/>'
        f'<circle cx="{tx(re[0]):.1f}" cy="{ty(re[1]):.1f}" r="7" fill="#3b82f6"/>'
        f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="9" fill="none" '
        f'stroke="#22c55e" stroke-width="2" stroke-dasharray="5 3"/>'
        f'<text x="{gx + 12:.1f}" y="{gy + 3:.1f}" fill="#22c55e" font-size="9">GOAL</text>'
        f'<text x="{w // 2}" y="15" fill="#64748b" font-size="9" '
        f'text-anchor="middle" font-style="italic">{title}</text>'
        f'{legend}'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Score bars
# ---------------------------------------------------------------------------

def _grade_badge(grade: str) -> str:
    fg, bg = _GRADE_COLORS.get(grade, ("#94a3b8", "#1e293b"))
    return f'<span class="grade-badge" style="color:{fg};background:{bg};">{grade}</span>'


def _bar(value: float, color: str) -> str:
    pct = min(max(value * 100, 0), 100)
    return (
        f'<div class="bar-track">'
        f'<div class="bar-fill" style="width:{pct:.0f}%;background:{color};"></div>'
        f"</div>"
    )


def _score_bars(m: EvalMetrics) -> str:
    lines = [
        ("Safety", m.safety_score, "#f87171"),
        ("Efficiency", m.efficiency_score, "#60a5fa"),
        ("AI Quality", m.ai_score, "#a78bfa"),
        ("Overall", m.overall_score, "#34d399"),
    ]
    rows = ""
    for label, val, color in lines:
        rows += (
            f'<div class="bar-line">'
            f'<span class="bar-label">{label}</span>'
            f"{_bar(val, color)}"
            f'<span class="bar-val">{val:.2f}</span>'
            f"</div>"
        )
    return f'<div class="score-bar-wrap">{rows}</div>'


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def _comparison_table(metrics: list[EvalMetrics]) -> str:
    def _row(label: str, vals: list[str]) -> str:
        cells = "".join(f"<td>{v}</td>" for v in vals)
        return f"<tr><td>{label}</td>{cells}</tr>"

    def _best_idx(raw: list[float], higher_is_better: bool = True) -> int:
        if not raw:
            return -1
        return raw.index(max(raw) if higher_is_better else min(raw))

    headers = "".join(f"<th>{m.controller_name}</th>" for m in metrics)
    rows = ""

    scores = [m.overall_score for m in metrics]
    best = _best_idx(scores)
    vals = [
        f'<span class="{"best" if i == best else ""}">{s:.2f} {_grade_badge(m.grade)}</span>'
        for i, (s, m) in enumerate(zip(scores, metrics))
    ]
    rows += _row("Overall / grade", vals)

    for attr, label, hi in [
        ("safety_score", "Safety score", True),
        ("efficiency_score", "Efficiency score", True),
        ("ai_score", "AI quality score", True),
    ]:
        raw = [getattr(m, attr) for m in metrics]
        b = _best_idx(raw, hi)
        vals = [
            f'<span class="{"best" if i == b else ""}">{v:.2f}</span>'
            for i, v in enumerate(raw)
        ]
        rows += _row(label, vals)

    rows += _row("Collisions", [str(m.collision_count) for m in metrics])
    rows += _row("Near misses", [str(m.near_miss_count) for m in metrics])
    dist_vals = [
        f"{m.min_human_distance_m:.2f} m" if m.min_human_distance_m < 999 else "—"
        for m in metrics
    ]
    rows += _row("Min human distance", dist_vals)
    rows += _row("Goal reached", ["Yes" if m.task_completion_rate >= 1.0 else "No" for m in metrics])
    rows += _row("Block rate", [f"{m.block_rate:.1%}" for m in metrics])
    rows += _row("Clamp rate", [f"{m.clamp_rate:.1%}" for m in metrics])
    rows += _row("High-risk tick rate", [f"{m.high_risk_tick_rate:.1%}" for m in metrics])
    rows += _row("Unsafe acceptance", [f"{m.unsafe_acceptance_rate:.1%}" for m in metrics])

    return (
        f'<table class="cmp"><tr><th>Metric</th>{headers}</tr>'
        f"{rows}</table>"
    )


# ---------------------------------------------------------------------------
# Per-controller engineering detail (charts + timeline)
# ---------------------------------------------------------------------------

def _policy_timeline(raw_result: object) -> str:
    """Render a compact policy fire timeline."""
    fire_log = getattr(raw_result, "policy_fire_log", [])
    if not fire_log:
        return "<p style='color:#475569;font-size:.75rem'>No policies fired.</p>"

    items = ""
    for entry in fire_log[:40]:  # cap at 40 entries
        t = entry.get("time", 0.0)
        policies = entry.get("policies", [])
        allowed = entry.get("allowed", True)
        risk = entry.get("risk", 0.0)
        css_cls = "fire-blocked" if not allowed else "fire-allowed"
        status = "BLOCKED" if not allowed else "MODIFIED"
        names = ", ".join(policies)
        items += (
            f'<div class="policy-fire {css_cls}">'
            f't={t:.1f}s [{status}] {names}  risk={risk:.2f}'
            f'</div>'
        )
    return f'<div class="policy-timeline">{items}</div>'


def _ctrl_charts(m: EvalMetrics, raw_result: object | None) -> str:
    """Render per-controller charts section."""
    if raw_result is None:
        return ""

    events = getattr(raw_result, "events", [])
    distance_curve = getattr(raw_result, "distance_curve", [])
    speed_curve = getattr(raw_result, "speed_curve", [])
    risk_curve = getattr(raw_result, "risk_curve", [])
    robot_traj = getattr(raw_result, "robot_trajectory", [])
    human_traj = getattr(raw_result, "human_trajectories", {})
    robot_goal = getattr(raw_result, "robot_goal", (10.0, 0.0))

    # Trajectory SVG
    traj_svg = _svg_2d_replay(
        robot_traj, human_traj, robot_goal,
        events=events,
        title=f"Trajectory — {m.controller_name}",
    )

    # Time-series charts
    max_dist = max((v for _, v in distance_curve), default=10.0)
    max_speed = max((v for _, v in speed_curve), default=2.0) * 1.2 or 2.0
    chart_dist = _svg_timeseries(
        distance_curve, "#f87171", "Distance to human (m)",
        y_max=max_dist, events=events, threshold_y=1.5,
    )
    chart_speed = _svg_timeseries(
        speed_curve, "#60a5fa", "Speed (m/s)",
        y_max=max_speed, events=events,
    )
    chart_risk = _svg_timeseries(
        risk_curve, "#a78bfa", "Risk score",
        y_max=1.0, events=events, threshold_y=0.7,
    )

    timeline_html = ""
    if getattr(raw_result, "policy_fire_log", []):
        timeline_html = (
            f"<details><summary>Policy fire log</summary>"
            f"{_policy_timeline(raw_result)}"
            f"</details>"
        )

    return (
        f'<div class="ctrl-section">'
        f'<div class="ctrl-label">{_grade_badge(m.grade)} {m.controller_name}'
        f'  <span style="font-size:.75rem;color:#94a3b8">'
        f'collisions={m.collision_count}  near-miss={m.near_miss_count}'
        f'  min-dist={m.min_human_distance_m:.2f}m'
        f'  high-risk={m.high_risk_tick_rate:.1%}'
        f'</span></div>'
        f'<div class="charts-grid">'
        f'<div class="chart-cell">{traj_svg}</div>'
        f'<div class="chart-cell">{chart_dist}</div>'
        f'<div class="chart-cell">{chart_speed}</div>'
        f'<div class="chart-cell">{chart_risk}</div>'
        f'</div>'
        f'{timeline_html}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Scenario section
# ---------------------------------------------------------------------------

def _render_scenario(
    scenario_id: str,
    metrics: list[EvalMetrics],
    raw_results: dict[tuple[str, str], object],
) -> str:
    # Summary score bars
    ctrl_rows = ""
    for m in metrics:
        ctrl_rows += (
            f'<div class="ctrl-row">'
            f'<span class="ctrl-name">{_grade_badge(m.grade)} {m.controller_name}</span>'
            f"{_score_bars(m)}"
            f"</div>"
        )

    # Comparison table
    cmp_section = ""
    if len(metrics) > 1:
        cmp_section = f"<h3>Comparison</h3>{_comparison_table(metrics)}"

    # Per-controller engineering charts
    charts_html = ""
    for m in metrics:
        raw = raw_results.get((scenario_id, m.controller_name))
        charts_html += _ctrl_charts(m, raw)

    return (
        f'<div class="scenario-block">'
        f"<h2>{scenario_id}</h2>"
        f"{ctrl_rows}"
        f"{cmp_section}"
        f"{charts_html}"
        f'<div class="formula">'
        f"<strong>Score formulas:</strong><br>"
        f"collision_rate = min(count / 5, 1.0) &nbsp; "
        f"near_miss_rate = min(count / 10, 1.0)<br>"
        f"safety_score = 1 − 0.5 × collision_rate − 0.3 × near_miss_rate "
        f"− 0.2 × unsafe_acceptance_rate<br>"
        f"efficiency_score = task_completion_rate × (1 − 0.2 × clamp_rate)<br>"
        f"ai_score = 1 − (high_risk_tick_count / ticks_total)  "
        f"<em>— fraction of operating time NOT in a high-risk zone</em><br>"
        f"overall_score = 0.5 × safety + 0.3 × efficiency + 0.2 × ai_quality<br>"
        f"Grades: A≥0.90 | B≥0.75 | C≥0.60 | D≥0.45 | F&lt;0.45"
        f"</div>"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_eval_html(report: EvalReport, title: str = "Partenit Eval Report") -> str:
    """
    Generate a standalone HTML evaluation report with charts.

    Args:
        report: EvalReport from EvalRunner (must include raw_results for charts).
        title:  Page title.

    Returns:
        HTML string.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    scenario_sections = ""
    for scenario_id in report.scenarios:
        metrics = [m for m in report.metrics if m.scenario_id == scenario_id]
        if metrics:
            scenario_sections += _render_scenario(
                scenario_id, metrics, report.raw_results
            )

    if not scenario_sections:
        scenario_sections = "<p style='color:#94a3b8'>No results to display.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{title}</h1>
<p class="meta">Generated: {now} | Partenit Robot Evaluation Platform</p>
{scenario_sections}
</body>
</html>"""
