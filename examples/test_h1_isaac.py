"""
H1 Isaac Sim — полный тест всех инструментов Partenit.

Требует запущенного h1_bridge_partenit.py (Isaac Sim на порту 8000).

Запуск:
    python examples/test_h1_isaac.py

Что тестируется:
    Шаг 1 — IsaacSimAdapter: get_health() / get_observations()
    Шаг 2 — GuardedRobot: управление реальным H1, видим clamp/block в консоли
    Шаг 3 — partenit-eval: grade A-F (mock-сим, детерминированный эталон)
    Шаг 4 — partenit-log replay: таймлайн решений из шага 2
    Шаг 5 — partenit-policy sim: какие правила срабатывают при конкретной дистанции

Примечание:
    Шаги 1-2 взаимодействуют с настоящим Isaac Sim через HTTP.
    Шаг 3 запускает собственную mock-симуляцию (воспроизводимый эталон).
    Шаги 4-5 работают с записанными данными и YAML, Isaac Sim не нужен.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from partenit.adapters.isaac_sim import IsaacSimAdapter
from partenit.agent_guard import GuardedRobot
from partenit.safety_bench.eval import ControllerConfig, EvalRunner
from partenit.safety_bench.eval.report_eval import generate_eval_html

BRIDGE_URL = "http://localhost:8000"
POLICY_PATH = str(Path(__file__).parent / "warehouse" / "policies.yaml")
SCENARIO = str(Path(__file__).parent / "benchmarks" / "human_crossing_path.yaml")
SESSION = "h1_test"
REPORT_PATH = "h1_eval.html"

SEP = "─" * 62
SEP2 = "═" * 62


def step(n: int, title: str) -> None:
    print(f"\n{SEP}\n  Шаг {n}: {title}\n{SEP}")


def main() -> None:
    # ──────────────────────────────────────────────────────────
    # Шаг 1 — подключение к мосту
    # ──────────────────────────────────────────────────────────
    step(1, "IsaacSimAdapter — подключение к Isaac Sim")

    adapter = IsaacSimAdapter(base_url=BRIDGE_URL)

    health = adapter.get_health()
    print(f"  health: {health}")
    if health.get("status") != "ok":
        print(
            "\n  ОШИБКА: мост недоступен.\n"
            "  Сначала запусти в Isaac Sim:\n"
            "    cd examples/isaac_sim/\n"
            "    <Isaac Sim python.sh> h1_bridge.py\n"
            "  См. examples/isaac_sim/README.md и docs/guides/isaac-sim.md\n"
        )
        raise SystemExit(1)

    # Wait for physics loop to start (Isaac Sim loads scene asynchronously).
    # Use urllib directly — bypasses IsaacSimAdapter CircuitBreaker which opens
    # after 3 timeouts and blocks polling for 30s cooldown periods.
    if not health.get("ready", False):
        print("  Ожидаем запуска физики Isaac Sim", end="", flush=True)
        deadline = time.time() + 120  # max 2 minutes
        ready = False
        while time.time() < deadline:
            time.sleep(2.0)
            try:
                with urllib.request.urlopen(f"{BRIDGE_URL}/partenit/health", timeout=3) as resp:
                    data = json.loads(resp.read())
                    if data.get("ready"):
                        ready = True
                        break
            except (urllib.error.URLError, OSError):
                pass
            print(".", end="", flush=True)
        if not ready:
            print("\n  ОШИБКА: физика не запустилась за 2 минуты")
            raise SystemExit(1)
        print(" готово!")
        time.sleep(3.0)  # let H1 stabilize at start position before commands

    obs = adapter.get_observations()
    print(f"  observations: {len(obs)} объект(ов)")
    for o in obs:
        print(
            f"    class={o.class_best}  dist={o.distance():.2f}m  "
            f"pos_3d={tuple(round(v, 2) for v in o.position_3d)}"
        )
    print("  ✓ OK")

    # ──────────────────────────────────────────────────────────
    # Шаг 2 — GuardedRobot с реальным H1
    # ──────────────────────────────────────────────────────────
    step(2, "GuardedRobot — H1 едет к человеку, guard блокирует")

    robot = GuardedRobot(
        adapter=adapter,
        policy_path=POLICY_PATH,
        session_name=SESSION,
    )

    print(f"  Сессия:   decisions/{SESSION}/")
    print(f"  Политики: {POLICY_PATH}\n")
    hdr = f"  {'speed':>5}  {'dist':>5}  {'result':>10}  {'final':>5}  {'risk':>5}  policies"
    print(hdr)
    print(f"  {'─' * 5}  {'─' * 5}  {'─' * 10}  {'─' * 5}  {'─' * 5}  {'─' * 16}")

    for requested_speed in [0.3, 0.6, 1.0, 1.5, 2.0]:
        d = robot.navigate_to(zone="forward", speed=requested_speed)

        obs_now = adapter.get_observations()
        dist = obs_now[0].distance() if obs_now else 0.0
        risk = d.risk_score.value if d.risk_score else 0.0

        if not d.allowed:
            result = "BLOCKED"
            final = 0.0
        elif d.modified_params:
            result = "MODIFIED"
            final = float(d.modified_params.get("speed", requested_speed))
        else:
            result = "allowed"
            final = requested_speed

        policies = ", ".join(d.applied_policies) if d.applied_policies else "—"
        print(
            f"  {requested_speed:>5.1f}  {dist:>5.2f}  {result:>10}"
            f"  {final:>5.1f}  {risk:>5.2f}  {policies}"
        )
        time.sleep(2.5)  # give H1 time to move noticeably between steps

    robot.stop()
    print(f"\n  ✓ OK — решения записаны в decisions/{SESSION}/")

    # ──────────────────────────────────────────────────────────
    # Шаг 3 — partenit-eval
    # ──────────────────────────────────────────────────────────
    step(3, f"partenit-eval — grade A-F (mock-сим) → {REPORT_PATH}")
    print("  (детерминированная симуляция, не зависит от физики Isaac Sim)")

    report = EvalRunner().run_scenario(
        SCENARIO,
        controllers=[
            ControllerConfig("baseline", policy_paths=[]),
            ControllerConfig("guarded", policy_paths=[POLICY_PATH]),
        ],
    )

    print()
    print(report.summary_table())

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(generate_eval_html(report))

    print(f"\n  Открой в браузере: {REPORT_PATH}")
    print("  (SVG-траектории, графики risk/speed/distance, таблица контроллеров)")
    print("  ✓ OK")

    # ──────────────────────────────────────────────────────────
    # Шаг 4 — partenit-log replay
    # ──────────────────────────────────────────────────────────
    step(4, f"partenit-log replay — таймлайн сессии '{SESSION}'")

    r = subprocess.run(["partenit-log", "replay", f"decisions/{SESSION}"])
    if r.returncode != 0:
        print(f"  (нет файлов в decisions/{SESSION})")
    else:
        print("  ✓ OK")

    # ──────────────────────────────────────────────────────────
    # Шаг 5 — partenit-policy sim
    # ──────────────────────────────────────────────────────────
    step(5, "partenit-policy sim — правила при distance=1.0 м, speed=2.0")

    subprocess.run(
        [
            "partenit-policy",
            "sim",
            "--action",
            "navigate_to",
            "--speed",
            "2.0",
            "--human-distance",
            "1.0",
            "--policy-path",
            POLICY_PATH,
        ]
    )
    print("  ✓ OK")

    # ──────────────────────────────────────────────────────────
    print(f"\n{SEP2}")
    print("  Все шаги выполнены.")
    print(f"  HTML-отчёт : {REPORT_PATH}")
    print(f"  Решения    : decisions/{SESSION}/")
    print(f"  Replay HTML: partenit-log replay decisions/{SESSION}/ --output h1_replay.html")
    print(f"{SEP2}\n")


if __name__ == "__main__":
    main()
