# sim_frontend.py - UI/frontend for Isaac Sim simulation
# Reusable panel: chat, mode, scenarios, task, debug tunables. Logic via callbacks only.

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import omni.ui as ui


def wrap_text(text: str, width: int = 80) -> str:
    """Wrap long text at word boundaries for readable display."""
    text = str(text).replace("\n", " ")
    words = text.split()
    lines, current, current_len = [], [], 0
    for w in words:
        add = len(w) + (1 if current else 0)
        if current_len + add > width and current:
            lines.append(" ".join(current))
            current, current_len = [w], len(w)
        else:
            current.append(w)
            current_len += add
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines) if lines else ""


@dataclass
class SimGUICallbacks:
    """Callbacks for PartenitDemoGUI. Main script provides implementations. No hasattr in main path."""

    get_latest_camera_bytes: Callable[[], bytes | None]
    add_user_message: Callable[[str], None]  # Show user msg immediately (main thread)
    on_send_command: Callable[[str, bytes | None], None]
    on_toggle_enable: Callable[[], None]
    get_enabled: Callable[[], bool]
    on_scenario_hri: Callable[[], None]
    on_scenario_battery: Callable[[], None]
    on_scenario_handoff: Callable[[], None]
    on_clear: Callable[[], None]
    on_learn_map: Callable[[], None]
    get_trace: Callable[[], str]
    get_chat_history: Callable[[], list[tuple[str, str]]]
    set_trace: Callable[[str], None]
    # Task API - primary input to pipeline
    get_task: Callable[[], str]
    set_task: Callable[[str], None]
    # Sim tunables - for Dev/Debug panel (battery, human, distance, carrying)
    get_sim_tunables: Callable[[], dict[str, Any]]
    set_sim_tunables: Callable[[dict[str, Any]], None]


class PartenitDemoGUI:
    """Partenit decision-making panel. Uses callbacks for all logic."""

    def __init__(self, callbacks: SimGUICallbacks):
        self.callbacks = callbacks
        self.window = ui.Window(
            "PARTENIT", width=420, height=1000, dockPreference=ui.DockPreference.RIGHT
        )
        self.window.deferred_dock_in("Property", ui.DockPolicy.DO_NOTHING)
        self._create_ui()

    def _create_ui(self):
        cb = self.callbacks
        with self.window.frame:
            with ui.VStack(spacing=0, style={"background_color": (0.1, 0.1, 0.1)}):
                with ui.HStack(height=40, spacing=10, padding=5):
                    ui.Label(
                        "PARTENIT. Self-Control Layer",
                        style={"font_size": 20, "font_weight": "bold", "color": (0.3, 0.8, 1.0)},
                    )
                    ui.Spacer()
                    self.enable_btn = ui.Button(
                        "ENABLE BRAIN",
                        clicked_fn=cb.on_toggle_enable,
                        width=120,
                        height=35,
                        style={
                            "background_color": (0.2, 0.6, 0.3),
                            "font_weight": "bold",
                            "font_size": 14,
                        },
                    )

                ui.Separator(height=1, style={"color": (0.3, 0.3, 0.3)})

                with ui.HStack(height=40, spacing=4, padding=2):
                    ui.Label("Scenarios:", style={"font_size": 14, "color": (0.6, 0.6, 0.6)})
                    ui.Button(
                        "HUMAN",
                        clicked_fn=cb.on_scenario_hri,
                        height=26,
                        style={"background_color": (0.3, 0.4, 0.5)},
                    )
                    ui.Button(
                        "LOW BAT",
                        clicked_fn=cb.on_scenario_battery,
                        height=26,
                        style={"background_color": (0.5, 0.3, 0.2)},
                    )
                    ui.Button(
                        "Explore",
                        clicked_fn=cb.on_scenario_handoff,
                        height=26,
                        style={"background_color": (0.2, 0.5, 0.4)},
                    )
                    ui.Button(
                        "Clear chat",
                        clicked_fn=cb.on_clear,
                        height=26,
                        style={"background_color": (0.3, 0.3, 0.3)},
                    )
                    ui.Button(
                        "Load Map",
                        clicked_fn=cb.on_learn_map,
                        height=26,
                        style={"background_color": (0.4, 0.3, 0.5)},
                    )

                ui.Separator(height=1, style={"color": (0.3, 0.3, 0.3)})

                with ui.VStack(spacing=2, padding=3, height=ui.Fraction(1)):
                    self.chat_text = ui.StringField(
                        multiline=True,
                        height=ui.Fraction(1),
                        read_only=True,
                        style={
                            "font_size": 18,
                            "background_color": (0.05, 0.05, 0.05),
                            "color": (0.95, 0.95, 0.95),
                        },
                    )
                    with ui.HStack(height=50, spacing=8):
                        self.cmd_field = ui.StringField(style={"font_size": 18})
                        ui.Button(
                            "SEND",
                            clicked_fn=self._on_send_command,
                            width=100,
                            style={
                                "background_color": (0.2, 0.4, 0.6),
                                "font_size": 15,
                                "font_weight": "bold",
                            },
                        )

    def _sync_tunables_from_state(self):
        """Initialize Advanced sliders from get_sim_tunables()."""
        d = self.callbacks.get_sim_tunables()
        if not d:
            return
        if "battery" in d:
            self._batt_model.set_value(float(d["battery"]))
        if "human_present" in d:
            self._human_model.set_value(bool(d["human_present"]))
        if "human_distance" in d:
            self._dist_model.set_value(float(d["human_distance"]))
        if "carrying_heavy" in d:
            self._carrying_model.set_value(bool(d["carrying_heavy"]))

    def _on_apply_tunables(self):
        """Push Advanced slider values to state via set_sim_tunables."""
        d = {
            "battery": self._batt_model.get_value_as_float(),
            "human_present": self._human_model.get_value_as_bool(),
            "human_distance": self._dist_model.get_value_as_float(),
            "carrying_heavy": self._carrying_model.get_value_as_bool(),
        }
        self.callbacks.set_sim_tunables(d)  # trace written by main (sim_tunables_updated: ...)

    def update_task_display(self, text: str):
        """No-op: Task field removed from UI. Task set via 'task: X' in chat."""
        pass

    def _on_send_command(self):
        txt = self.cmd_field.model.get_value_as_string()
        if not txt.strip():
            return
        self.cmd_field.model.set_value("")
        self.callbacks.add_user_message(txt)
        self.callbacks.on_send_command(txt, self.callbacks.get_latest_camera_bytes())

    def update_view(self):
        """Refresh trace, chat, enable button from callbacks."""
        enabled = self.callbacks.get_enabled()
        self.enable_btn.text = "DISABLE BRAIN" if enabled else "ENABLE BRAIN"
        self.enable_btn.style = {
            "background_color": (0.6, 0.2, 0.2) if enabled else (0.2, 0.6, 0.3),
            "font_weight": "bold",
            "font_size": 14,
        }
        self.callbacks.get_trace() or "READY"
        # trace_text removed from UI
        chat_history = self.callbacks.get_chat_history()
        if chat_history:
            out = []
            for role, text in chat_history[-30:]:
                name = "YOU" if role == "user" else "H1"
                wrapped = wrap_text(text).replace("\n", "\n     ")
                out.append(f"[{name}]: {wrapped}")
            self.chat_text.model.set_value("\n".join(out))
