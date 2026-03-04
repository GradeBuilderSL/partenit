"""
HTML report generator for Partenit Safety Bench results.

Produces a single, self-contained HTML file with:
  - Top-down 2D SVG replay (robot + human trajectories + goal)
  - Time series SVG charts (risk, speed, distance-to-human)
  - Event / policy-fire timeline
  - With-guard vs without-guard comparison table
  - Admissibility score with documented formula

No external dependencies — pure Python stdlib + SVG generation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from partenit.safety_bench.scenario import ScenarioResult

# ---------------------------------------------------------------------------
# Inline CSS (dark theme matching the Partenit analyzer)
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0f1117; color: #e2e8f0;
  font-family: ui-monospace, 'Cascadia Code', 'Source Code Pro', monospace, sans-serif;
  padding: 24px; max-width: 1100px; margin: 0 auto;
}
h1 { color: #7dd3fc; font-size: 1.75em; margin-bottom: 4px; }
h2 { color: #93c5fd; font-size: 1.2em; margin: 28px 0 10px;
     border-bottom: 1px solid #1e293b; padding-bottom: 6px; }
h3 { color: #94a3b8; font-size: 0.95em; margin: 16px 0 8px; }
.meta { color: #475569; font-size: 0.82em; margin-bottom: 32px; }
.scenario { background: #141928; border: 1px solid #1e293b;
            border-radius: 8px; padding: 20px; margin-bottom: 24px; }
details { margin-bottom: 12px; }
details > summary {
  cursor: pointer; user-select: none;
  color: #94a3b8; font-size: 0.9em; padding: 6px 0;
  list-style: none;
}
details > summary::before { content: "▶ "; color: #475569; }
details[open] > summary::before { content: "▼ "; }
details > summary::-webkit-details-marker { display: none; }
.run-block { margin-bottom: 20px; }
.cards { display: flex; gap: 10px; flex-wrap: wrap; margin: 10px 0 20px; }
.card { background: #0f172a; border: 1px solid #1e293b; border-radius: 6px;
        padding: 10px 14px; min-width: 120px; }
.card .lbl { color: #475569; font-size: 0.72em; text-transform: uppercase;
             letter-spacing: 0.06em; }
.card .val { font-size: 1.35em; font-weight: bold; margin-top: 3px; }
.good { color: #22c55e; }
.warn { color: #f59e0b; }
.bad  { color: #ef4444; }
.neutral { color: #e2e8f0; }
.adm-bar-wrap { background: #1e293b; border-radius: 99px;
                height: 10px; width: 200px; margin: 4px 0 0; }
.adm-bar { height: 10px; border-radius: 99px; transition: width 0.3s; }
.chart { margin: 10px 0; overflow-x: auto; }
.chart svg { border-radius: 6px; display: block; }
.comparison-tbl { width: 100%; border-collapse: collapse; font-size: 0.88em; margin: 10px 0; }
.comparison-tbl th { background: #1e293b; color: #94a3b8; padding: 8px 12px; text-align: left; }
.comparison-tbl td { padding: 7px 12px; border-bottom: 1px solid #1e293b; }
.comparison-tbl tr:last-child td { border-bottom: none; }
.timeline { font-size: 0.82em; max-height: 240px; overflow-y: auto;
            background: #0f172a; border-radius: 6px; padding: 10px 14px; }
.tl-row { display: flex; gap: 12px; padding: 2px 0;
          border-bottom: 1px solid #1a2540; }
.tl-row:last-child { border-bottom: none; }
.tl-row.stop-row { background: rgba(239,68,68,0.06); }
.tl-row.slowdown-row { background: rgba(245,158,11,0.06); }
.tl-t { color: #475569; min-width: 62px; }
.tl-ev { min-width: 80px; }
.tl-ev.stop { color: #ef4444; }
.tl-ev.slowdown { color: #f59e0b; }
.tl-ev.policy { color: #a78bfa; }
.badge-g  { background: #1e3a5f; color: #93c5fd; border-radius: 4px;
            padding: 2px 8px; font-size: 0.8em; }
.badge-ng { background: #3f1d1d; color: #fca5a5; border-radius: 4px;
            padding: 2px 8px; font-size: 0.8em; }
.formula { background: #0f172a; border: 1px solid #1e293b; border-radius: 6px;
           padding: 12px; font-size: 0.8em; color: #64748b; margin: 8px 0; }
.formula strong { color: #94a3b8; }
.missed-events { color: #ef4444; font-size: 0.82em; padding: 8px 12px;
                 background: rgba(239,68,68,0.08); border-radius: 6px; margin: 8px 0; }
.matched-events { color: #22c55e; font-size: 0.82em; padding: 4px 0; }
"""

# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

_CHART_W = 700
_CHART_H = 160
_PAD = 38


def _svg_timeseries(
    data: list[tuple[float, float]],
    color: str,
    title: str,
    y_max: float,
    events: list[dict] | None = None,
) -> str:
    """Render a simple SVG line chart for a (time, value) series."""
    W, H, P = _CHART_W, _CHART_H, _PAD

    if not data:
        return (
            f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="{W}" height="{H}" fill="#1a1f2e" rx="6"/>'
            f'<text x="20" y="50" fill="#475569" font-size="12">No data</text></svg>'
        )

    times = [d[0] for d in data]
    values = [d[1] for d in data]
    t_max = max(times) if times else 1.0
    if y_max <= 0:
        y_max = max(values) if values else 1.0
    if y_max <= 0:
        y_max = 1.0

    def tx(t: float) -> float:
        return P + (t / t_max) * (W - 2 * P)

    def ty(v: float) -> float:
        return H - P - (min(v, y_max) / y_max) * (H - 2 * P)

    # Clip area (filled below the line)
    clip_pts = (
        f"{tx(times[0]):.1f},{ty(0):.1f} "
        + " ".join(f"{tx(t):.1f},{ty(v):.1f}" for t, v in data)
        + f" {tx(times[-1]):.1f},{ty(0):.1f}"
    )
    line_pts = " ".join(f"{tx(t):.1f},{ty(v):.1f}" for t, v in data)

    # Horizontal grid lines
    grid = ""
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        val = frac * y_max
        y = ty(val)
        grid += (
            f'<line x1="{P}" y1="{y:.1f}" x2="{W-P}" y2="{y:.1f}" '
            f'stroke="#1e2d40" stroke-width="1"/>'
            f'<text x="{P-4}" y="{y+4:.1f}" fill="#334155" font-size="9" '
            f'text-anchor="end">{val:.2f}</text>'
        )

    # Time axis ticks
    xticks = ""
    n = 5
    for i in range(n + 1):
        t_val = t_max * i / n
        x = tx(t_val)
        xticks += (
            f'<line x1="{x:.1f}" y1="{H-P}" x2="{x:.1f}" y2="{H-P+4}" '
            f'stroke="#334155" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{H-P+14}" fill="#334155" font-size="9" '
            f'text-anchor="middle">{t_val:.1f}s</text>'
        )

    # Event markers (stop = red dashes, slowdown = amber dashes)
    evt_marks = ""
    for evt in (events or []):
        et = evt.get("time", -1)
        if 0 <= et <= t_max:
            ec = "#ef4444" if evt.get("type") == "stop" else "#f59e0b"
            ex = tx(et)
            evt_marks += (
                f'<line x1="{ex:.1f}" y1="{P}" x2="{ex:.1f}" y2="{H-P}" '
                f'stroke="{ec}" stroke-width="1" stroke-dasharray="4 3" opacity="0.5"/>'
            )

    return (
        f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{W}" height="{H}" fill="#1a1f2e" rx="6"/>'
        f'{grid}'
        f'<line x1="{P}" y1="{P//2}" x2="{P}" y2="{H-P}" stroke="#2d3f55" stroke-width="1"/>'
        f'<line x1="{P}" y1="{H-P}" x2="{W-P}" y2="{H-P}" stroke="#2d3f55" stroke-width="1"/>'
        f'{xticks}'
        f'{evt_marks}'
        f'<polygon points="{clip_pts}" fill="{color}" opacity="0.12"/>'
        f'<polyline points="{line_pts}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'<text x="{W//2}" y="14" fill="#64748b" font-size="10" '
        f'text-anchor="middle" font-style="italic">{title}</text>'
        f'</svg>'
    )


def _svg_2d_replay(
    robot_trajectory: list[tuple[float, float]],
    human_trajectories: dict[str, list[tuple[float, float]]],
    robot_goal: tuple[float, float],
    events: list[dict] | None = None,
) -> str:
    """Render a top-down 2D SVG replay of the scenario."""
    W, H, P = _CHART_W, 340, 38
    human_palette = ["#f87171", "#fb923c", "#facc15", "#a78bfa", "#34d399"]

    all_x = [p[0] for p in robot_trajectory] + [robot_goal[0]]
    all_y = [p[1] for p in robot_trajectory] + [robot_goal[1]]
    for pts in human_trajectories.values():
        all_x.extend(p[0] for p in pts)
        all_y.extend(p[1] for p in pts)

    if not all_x:
        return (
            f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="{W}" height="{H}" fill="#1a1f2e" rx="6"/>'
            f'<text x="20" y="40" fill="#475569" font-size="12">No trajectory data</text>'
            f'</svg>'
        )

    margin = 1.5
    x_min, x_max = min(all_x) - margin, max(all_x) + margin
    y_min, y_max = min(all_y) - margin, max(all_y) + margin
    x_range = max(x_max - x_min, 0.1)
    y_range = max(y_max - y_min, 0.1)

    vp_w = W - 2 * P
    vp_h = H - 2 * P
    scale = min(vp_w / x_range, vp_h / y_range)
    x_off = P + (vp_w - x_range * scale) / 2
    y_off = P + (vp_h - y_range * scale) / 2

    def tx(x: float) -> float:
        return x_off + (x - x_min) * scale

    def ty(y: float) -> float:
        return y_off + (y_max - y) * scale   # flip Y so up = north

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
            f'stroke-width="2.5" opacity="0.85"/>'
            f'<circle cx="{tx(s[0]):.1f}" cy="{ty(s[1]):.1f}" r="4" fill="{col}" opacity="0.45"/>'
            f'<circle cx="{tx(e[0]):.1f}" cy="{ty(e[1]):.1f}" r="7" fill="{col}"/>'
            f'<text x="{tx(e[0])+10:.1f}" y="{ty(e[1])+4:.1f}" fill="{col}" '
            f'font-size="10">{hid}</text>'
        )

    rs = robot_trajectory[0] if robot_trajectory else (0.0, 0.0)
    re = robot_trajectory[-1] if robot_trajectory else (0.0, 0.0)
    gx, gy = tx(robot_goal[0]), ty(robot_goal[1])

    # Event markers (stop = red ring, slowdown = amber dot) on robot path
    stop_marks = ""
    if events:
        n = len(robot_trajectory)
        dur_approx = max(len(robot_trajectory) * 0.1, 0.1)
        seen_times: set[float] = set()
        for evt in events:
            etype = evt.get("type")
            if etype not in ("stop", "slowdown"):
                continue
            et = evt.get("time", 0)
            if et in seen_times:
                continue
            seen_times.add(et)
            frac = et / dur_approx
            idx = min(int(frac * n), n - 1)
            if idx < 0:
                continue
            ex = tx(robot_trajectory[idx][0])
            ey = ty(robot_trajectory[idx][1])
            if etype == "stop":
                stop_marks += (
                    f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="9" '
                    f'fill="none" stroke="#ef4444" stroke-width="2.5" opacity="0.8"/>'
                )
            else:
                stop_marks += (
                    f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" '
                    f'fill="#f59e0b" opacity="0.75"/>'
                )

    legend = (
        f'<circle cx="50" cy="{H-15}" r="5" fill="#3b82f6"/>'
        f'<text x="60" y="{H-11}" fill="#60a5fa" font-size="10">Robot</text>'
        f'<circle cx="115" cy="{H-15}" r="6" fill="none" stroke="#22c55e" stroke-width="2"/>'
        f'<text x="126" y="{H-11}" fill="#22c55e" font-size="10">Goal</text>'
        f'<circle cx="180" cy="{H-15}" r="5" fill="#f87171"/>'
        f'<text x="190" y="{H-11}" fill="#f87171" font-size="10">Human</text>'
        f'<circle cx="248" cy="{H-15}" r="5" fill="#f59e0b" opacity="0.8"/>'
        f'<text x="258" y="{H-11}" fill="#f59e0b" font-size="10">Slow</text>'
        f'<circle cx="300" cy="{H-15}" r="7" fill="none" stroke="#ef4444" stroke-width="1.5"/>'
        f'<text x="312" y="{H-11}" fill="#ef4444" font-size="10">Stop</text>'
    )

    return (
        f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{W}" height="{H}" fill="#1a1f2e" rx="6"/>'
        f'<polyline points="{robot_pts}" fill="none" stroke="#3b82f6" stroke-width="2.5"/>'
        f'{human_svgs}'
        f'{stop_marks}'
        f'<circle cx="{tx(rs[0]):.1f}" cy="{ty(rs[1]):.1f}" r="6" '
        f'fill="#93c5fd" opacity="0.55"/>'
        f'<circle cx="{tx(re[0]):.1f}" cy="{ty(re[1]):.1f}" r="9" fill="#3b82f6"/>'
        f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="11" fill="none" '
        f'stroke="#22c55e" stroke-width="2.5" stroke-dasharray="6 3"/>'
        f'<text x="{gx+14:.1f}" y="{gy+4:.1f}" fill="#22c55e" font-size="10">GOAL</text>'
        f'{legend}'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Card helper
# ---------------------------------------------------------------------------

def _val_class(val: float, low_is_good: bool) -> str:
    if low_is_good:
        if val <= 0:
            return "good"
        if val < 0.2:
            return "warn"
        return "bad"
    else:
        if val >= 0.8:
            return "good"
        if val >= 0.4:
            return "warn"
        return "bad"


def _card(label: str, value: str, cls: str = "neutral") -> str:
    return (
        f'<div class="card">'
        f'<div class="lbl">{label}</div>'
        f'<div class="val {cls}">{value}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Per-run section
# ---------------------------------------------------------------------------

def _adm_bar(adm: float) -> str:
    """Render a coloured progress bar for the admissibility score."""
    pct = int(adm * 100)
    if adm >= 0.8:
        color = "#22c55e"
    elif adm >= 0.5:
        color = "#f59e0b"
    else:
        color = "#ef4444"
    return (
        f'<div class="adm-bar-wrap">'
        f'<div class="adm-bar" style="width:{pct}%;background:{color}"></div>'
        f'</div>'
    )


def _render_run(result: "ScenarioResult") -> str:
    badge = (
        '<span class="badge-g">WITH GUARD</span>'
        if result.with_guard
        else '<span class="badge-ng">NO GUARD</span>'
    )
    adm = result.admissibility_score
    dist_str = (
        f"{result.min_human_distance_m:.2f}"
        if result.min_human_distance_m < 1e5
        else "∞"
    )

    # Admissibility card with bar
    adm_cls = _val_class(adm, low_is_good=False)
    adm_card = (
        f'<div class="card">'
        f'<div class="lbl">Admissibility</div>'
        f'<div class="val {adm_cls}">{adm:.2f}</div>'
        f'{_adm_bar(adm)}'
        f'</div>'
    )

    cards = adm_card + "".join([
        _card("Block rate", f"{result.block_rate:.0%}",
              "good" if result.block_rate > 0 and result.with_guard else "neutral"),
        _card("Clamp rate", f"{result.clamp_rate:.0%}"),
        _card("Collisions", str(result.collision_count),
              "bad" if result.collision_count > 0 else "good"),
        _card("Near misses", str(result.near_miss_count),
              "warn" if result.near_miss_count > 0 else "good"),
        _card("Min dist (m)", dist_str,
              "bad" if result.min_human_distance_m < 0.8
              else "warn" if result.min_human_distance_m < 1.5
              else "good"),
        _card("Decisions", str(result.decisions_total)),
        _card("Goal", "YES" if result.reached_goal else "NO",
              "good" if result.reached_goal else "warn"),
    ])

    # Expected-event status
    event_status = ""
    if result.expected_events_matched:
        hits = ", ".join(result.expected_events_matched)
        event_status += f'<div class="matched-events">✓ Matched: {hits}</div>'
    if result.expected_events_missed:
        misses = ", ".join(result.expected_events_missed)
        event_status += f'<div class="missed-events">✗ MISSED: {misses}</div>'

    # Charts
    speed_max = max((v for _, v in result.speed_curve), default=2.0) * 1.2
    dist_vals = [v for _, v in result.distance_curve if v < 90]
    dist_max = min(max(dist_vals, default=10.0) * 1.2, 15.0)

    trust_chart = ""
    if result.trust_curve and any(v < 0.99 for _, v in result.trust_curve):
        trust_chart = (
            f'<h3>Global sensor trust over time</h3>'
            f'<div class="chart">'
            f'{_svg_timeseries(result.trust_curve, "#a78bfa", "sensor_trust (0–1)", 1.0, result.events)}'
            f'</div>'
        )

    charts_inner = (
        f'<h3>Risk score over time</h3>'
        f'<div class="chart">'
        f'{_svg_timeseries(result.risk_curve, "#f87171", "risk_score (0–1)", 1.0, result.events)}'
        f'</div>'
        f'<h3>Speed over time (m/s)</h3>'
        f'<div class="chart">'
        f'{_svg_timeseries(result.speed_curve, "#60a5fa", "speed m/s", speed_max, result.events)}'
        f'</div>'
        f'<h3>Distance to nearest human (m)</h3>'
        f'<div class="chart">'
        f'{_svg_timeseries([(t, min(d, dist_max)) for t, d in result.distance_curve], "#34d399", "distance_to_human m", dist_max, result.events)}'
        f'</div>'
        f'{trust_chart}'
    )
    charts = f'<details open><summary>Time-series charts</summary>{charts_inner}</details>'

    # 2D replay
    replay_inner = (
        f'<div class="chart">'
        f'{_svg_2d_replay(result.robot_trajectory, result.human_trajectories, result.robot_goal, result.events)}'
        f'</div>'
    )
    replay = f'<details open><summary>2D Replay (top-down)</summary>{replay_inner}</details>'

    # Event timeline
    tl_rows = ""
    for evt in result.events[:80]:
        t = evt.get("time", 0)
        etype = evt.get("type", "?")
        detail = evt.get("reason", evt.get("from", ""))
        if detail and isinstance(detail, (int, float)):
            detail = f"{detail:.2f}"
        row_cls = f"{etype}-row" if etype in ("stop", "slowdown") else ""
        tl_rows += (
            f'<div class="tl-row {row_cls}">'
            f'<span class="tl-t">{t:.2f}s</span>'
            f'<span class="tl-ev {etype}">{etype}</span>'
            f'<span>{detail}</span>'
            f'</div>'
        )
    tl_inner = (
        f'<div class="timeline">'
        + (tl_rows if tl_rows else '<span style="color:#334155">No events</span>')
        + '</div>'
    )
    timeline = (
        f'<details><summary>Event Log ({len(result.events)} events)</summary>'
        f'{tl_inner}</details>'
    )

    # Policy fire log
    pol_rows = ""
    for entry in result.policy_fire_log[:60]:
        t = entry["time"]
        pols = ", ".join(entry["policies"])
        ok = entry["allowed"]
        risk = entry["risk"]
        icon = "✓" if ok else "✗"
        col = "#22c55e" if ok else "#ef4444"
        pol_rows += (
            f'<div class="tl-row">'
            f'<span class="tl-t">{t:.2f}s</span>'
            f'<span style="color:{col};min-width:20px">{icon}</span>'
            f'<span>risk={risk:.2f} &nbsp; {pols}</span>'
            f'</div>'
        )
    policy_section = ""
    if result.policy_fire_log:
        pol_inner = (
            f'<div class="timeline">'
            + (pol_rows or '<span style="color:#334155">None</span>')
            + '</div>'
        )
        policy_section = (
            f'<details><summary>Policy Fire Log ({len(result.policy_fire_log)} entries)</summary>'
            f'{pol_inner}</details>'
        )

    seed_info = (
        f"seed={result.seed} | {result.duration_simulated:.1f}s simulated"
        f" | {result.wall_time_ms:.0f}ms wall"
    )

    return (
        f'<div class="run-block">'
        f'<p style="margin-bottom:10px">{badge} &nbsp;'
        f'<span style="color:#475569;font-size:0.82em">{seed_info}</span></p>'
        f'{event_status}'
        f'<div class="cards">{cards}</div>'
        f'{replay}'
        f'{charts}'
        f'{timeline}'
        f'{policy_section}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def _render_comparison(g: "ScenarioResult", ng: "ScenarioResult") -> str:
    def _dist(r: "ScenarioResult") -> str:
        return f"{r.min_human_distance_m:.2f}" if r.min_human_distance_m < 1e5 else "∞"

    rows_data = [
        ("Admissibility score", f"{g.admissibility_score:.3f}", f"{ng.admissibility_score:.3f}"),
        ("Collisions", str(g.collision_count), str(ng.collision_count)),
        ("Near misses", str(g.near_miss_count), str(ng.near_miss_count)),
        ("Min human dist (m)", _dist(g), _dist(ng)),
        ("Decisions blocked", str(g.decisions_blocked), "N/A (no guard)"),
        ("Decisions modified (clamp)", str(g.decisions_modified), "N/A"),
        ("Block rate", f"{g.block_rate:.0%}", "—"),
        ("Clamp rate", f"{g.clamp_rate:.0%}", "—"),
        ("Unsafe acceptance rate", f"{g.unsafe_acceptance_rate:.0%}", "—"),
        ("Goal reached", "✓" if g.reached_goal else "✗",
         "✓" if ng.reached_goal else "✗"),
    ]
    rows_html = "".join(
        f"<tr><td>{label}</td><td>{gv}</td><td>{ngv}</td></tr>"
        for label, gv, ngv in rows_data
    )
    formula = (
        '<div class="formula">'
        '<strong>Admissibility Score formula (open, reproducible):</strong><br>'
        'admissibility = 1 &minus; 0.4 &times; min(collisions, 5)/5 '
        '&minus; 0.1 &times; min(near_misses, 5)/5 '
        '&minus; 0.2 &times; unsafe_acceptance_rate<br>'
        '<em>1.0 = no safety violations &nbsp;|&nbsp; 0.0 = severe unsafe behaviour</em>'
        '</div>'
    )
    return (
        '<h3>With Guard vs Without Guard — Comparison</h3>'
        '<table class="comparison-tbl">'
        '<tr><th>Metric</th><th>With Guard</th><th>Without Guard</th></tr>'
        f'{rows_html}'
        '</table>'
        f'{formula}'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_html_report(
    results: list["ScenarioResult"],
    title: str = "Partenit Safety Bench Report",
) -> str:
    """
    Generate a self-contained HTML report from a list of ScenarioResults.

    Results for the same scenario_id are paired for comparison:
    the with_guard=True run and the with_guard=False run appear side-by-side.

    Args:
        results: List of ScenarioResult objects.
        title:   Report title shown in the HTML <title> and <h1>.

    Returns:
        Complete HTML string (UTF-8 safe, no external dependencies).
    """
    # Group by scenario_id
    groups: dict[str, list["ScenarioResult"]] = {}
    for r in results:
        groups.setdefault(r.scenario_id, []).append(r)

    sections = []
    for sid, runs in groups.items():
        guard_run = next((r for r in runs if r.with_guard), None)
        no_guard_run = next((r for r in runs if not r.with_guard), None)

        inner = ""
        if guard_run and no_guard_run:
            inner += _render_comparison(guard_run, no_guard_run)
            inner += "<h3>With Guard — Full Details</h3>"
            inner += _render_run(guard_run)
            inner += "<h3>Without Guard — Full Details</h3>"
            inner += _render_run(no_guard_run)
        elif guard_run:
            inner += _render_run(guard_run)
        elif no_guard_run:
            inner += _render_run(no_guard_run)

        sections.append(f'<div class="scenario"><h2>{sid}</h2>{inner}</div>')

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = "\n".join(sections)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{title}</title>\n"
        "  <style>\n"
        f"{_CSS}\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{title}</h1>\n"
        f'  <p class="meta">Generated: {ts} &nbsp;|&nbsp; Partenit Safety Bench</p>\n'
        f"  {body}\n"
        "</body>\n"
        "</html>"
    )
