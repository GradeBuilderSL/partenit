"""
Partenit Safety Overlay — NVIDIA Isaac Sim Extension (template).

This is a skeleton Omniverse Extension.  To activate it:
1. Copy this directory into your Isaac Sim extensions folder:
       ~/isaac-sim/exts/partenit.safety_overlay/
2. Enable it in Isaac Sim: Window → Extensions → search "Partenit"
3. Ensure partenit-agent-guard and partenit-adapters are installed in
   Isaac Sim's Python environment:
       ~/.local/share/ov/pkg/<isaac_version>/python.sh -m pip install \
           partenit-core partenit-policy-dsl partenit-trust-engine \
           partenit-agent-guard partenit-adapters

Architecture:
    Isaac Sim
        ↓ (HTTP gateway or direct Python API)
    IsaacSimAdapter.get_observations()
        ↓
    AgentGuard.check_action()
        ↓
    UI overlay: risk score, policy badges, sensor trust

For HTTP gateway setup, see:
    partenit/packages/adapters/src/partenit/adapters/isaac_sim.py
"""

from __future__ import annotations

import threading
import time

# Omniverse imports (only available inside Isaac Sim)
try:
    import omni.ext
    import omni.ui as ui
    _HAS_OMNI = True
except ImportError:
    _HAS_OMNI = False

# Partenit imports
try:
    from partenit.adapters.isaac_sim import IsaacSimAdapter
    from partenit.agent_guard import AgentGuard
    _HAS_PARTENIT = True
except ImportError:
    _HAS_PARTENIT = False


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
_POLL_INTERVAL_S = 0.5    # How often to poll observations from Isaac Sim
_DEFAULT_GATEWAY  = "http://localhost:7000"
_DEFAULT_POLICIES = ""    # Set to path of your policies YAML


# --------------------------------------------------------------------------- #
# Extension entry point
# --------------------------------------------------------------------------- #
if _HAS_OMNI:
    class PartenitSafetyOverlayExtension(omni.ext.IExt):
        """
        Omniverse Extension: Partenit Safety Overlay.

        Displays real-time guard state as a HUD panel in the Isaac Sim viewport.
        """

        def on_startup(self, ext_id: str) -> None:
            self._ext_id = ext_id
            self._window: ui.Window | None = None
            self._guard: AgentGuard | None = None
            self._adapter: IsaacSimAdapter | None = None
            self._running = False
            self._thread: threading.Thread | None = None

            self._setup_guard()
            self._build_ui()
            self._start_poll()

        def on_shutdown(self) -> None:
            self._running = False
            if self._thread:
                self._thread.join(timeout=2.0)

        # ------------------------------------------------------------------ #
        # Guard setup
        # ------------------------------------------------------------------ #

        def _setup_guard(self) -> None:
            if not _HAS_PARTENIT:
                print("[Partenit] partenit-adapters not installed — overlay inactive")
                return

            self._adapter = IsaacSimAdapter(base_url=_DEFAULT_GATEWAY)
            self._guard = AgentGuard()
            if _DEFAULT_POLICIES:
                self._guard.load_policies(_DEFAULT_POLICIES)
            print("[Partenit] Safety guard initialized")

        # ------------------------------------------------------------------ #
        # UI
        # ------------------------------------------------------------------ #

        def _build_ui(self) -> None:
            self._window = ui.Window(
                "Partenit Safety Overlay",
                width=320,
                height=240,
            )
            with self._window.frame:
                with ui.VStack(spacing=4):
                    ui.Label("Partenit Safety Guard", style={"font_size": 16})
                    self._lbl_status   = ui.Label("Status: initializing…")
                    self._lbl_risk     = ui.Label("Risk:   —")
                    self._lbl_policy   = ui.Label("Policy: —")
                    self._lbl_speed    = ui.Label("Speed:  —")
                    self._lbl_trust    = ui.Label("Trust:  —")

        # ------------------------------------------------------------------ #
        # Polling loop
        # ------------------------------------------------------------------ #

        def _start_poll(self) -> None:
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()

        def _poll_loop(self) -> None:
            while self._running:
                try:
                    self._tick()
                except Exception as exc:
                    print(f"[Partenit] poll error: {exc}")
                time.sleep(_POLL_INTERVAL_S)

        def _tick(self) -> None:
            if not _HAS_PARTENIT or self._adapter is None or self._guard is None:
                return

            obs = self._adapter.get_observations()
            context = {}
            if obs:
                # Build basic context
                humans = [o for o in obs if getattr(o, "treat_as_human", False)]
                if humans:
                    context["human"] = {"distance": min(getattr(h, "distance", 99) for h in humans)}

            # Check with current speed (placeholder — integrate with your controller)
            decision = self._guard.check_action(
                action="navigate_to",
                params={"speed": 1.0},
                context=context,
                observations=obs,
            )

            self._update_ui(decision, context)

        def _update_ui(self, decision, context: dict) -> None:
            """Update HUD labels (must be called from main thread or with omni.kit.app)."""
            risk = decision.risk_score.value if decision.risk_score else 0.0
            policies = ", ".join(decision.applied_policies) if decision.applied_policies else "—"
            status = "ALLOWED" if decision.allowed else "BLOCKED"
            dist = context.get("human", {}).get("distance", None)
            dist_str = f"{dist:.2f} m" if dist is not None else "—"

            if self._lbl_status:
                self._lbl_status.text = f"Status: {status}"
            if self._lbl_risk:
                self._lbl_risk.text = f"Risk:   {risk:.2f}"
            if self._lbl_policy:
                self._lbl_policy.text = f"Policy: {policies}"
            if self._lbl_speed:
                self._lbl_speed.text = f"Human:  {dist_str}"


# --------------------------------------------------------------------------- #
# Standalone usage (outside Isaac Sim, for testing)
# --------------------------------------------------------------------------- #

def demo() -> None:
    """
    Run the guard overlay logic standalone (without Isaac Sim UI).

    Polls observations from the HTTP gateway and prints guard state to stdout.
    Useful for testing the connection before enabling the full extension.

    Usage:
        python extension.py
    """
    if not _HAS_PARTENIT:
        print("ERROR: partenit not installed. Run: pip install partenit-core partenit-agent-guard partenit-adapters")
        return

    print("Partenit Safety Overlay — standalone demo")
    print(f"Connecting to Isaac gateway: {_DEFAULT_GATEWAY}\n")

    adapter = IsaacSimAdapter(base_url=_DEFAULT_GATEWAY)
    guard = AgentGuard()
    if _DEFAULT_POLICIES:
        guard.load_policies(_DEFAULT_POLICIES)

    while True:
        try:
            obs = adapter.get_observations()
            humans = [o for o in obs if getattr(o, "treat_as_human", False)]
            context = {}
            if humans:
                context["human"] = {"distance": min(getattr(h, "distance", 99) for h in humans)}

            decision = guard.check_action("navigate_to", {"speed": 1.0}, context, obs)
            risk = decision.risk_score.value if decision.risk_score else 0.0
            status = "ALLOWED" if decision.allowed else "BLOCKED"
            policies = ", ".join(decision.applied_policies) if decision.applied_policies else "none"
            print(f"[{status}] risk={risk:.2f}  policies={policies}")
        except Exception as exc:
            print(f"[ERROR] {exc}")
        time.sleep(_POLL_INTERVAL_S)


if __name__ == "__main__":
    demo()
