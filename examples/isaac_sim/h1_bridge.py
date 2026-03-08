#!/usr/bin/env python3
"""
Partenit H1 Bridge for Isaac Sim.

Runs inside NVIDIA Isaac Sim and exposes two APIs on port 8000:

  Original bridge API (manual control / ROS2):
    GET  /robot/state        → H1 position, velocity, heading
    POST /control/move       → {"vx": 0.5, "vy": 0.0, "wz": 0.0}
    POST /control/stop       → stop immediately
    GET  /camera/latest      → PNG frame from H1 head camera

  Partenit robot API (IsaacSimAdapter contract):
    GET  /partenit/health        → bridge status
    GET  /partenit/observations  → human position in robot-centric frame
    POST /partenit/command       → GuardDecision → applied as cmd_vel to H1

Scene: Simple Warehouse + Unitree H1 robot + static human mannequin at (3.5, 0, 0).

Dependencies (in this directory):
    env_loader.py    — load .env settings
    sim_frontend.py  — Omniverse UI panel (chat, scenarios, controls)
    sim_camera.py    — H1 head camera capture

Run from the Isaac Sim Python environment:
    cd examples/isaac_sim/
    python h1_bridge.py

Then in a separate terminal:
    python examples/test_h1_isaac.py
"""

import os
import sys
import threading
import json
import numpy as np
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": False, "width": 1600, "height": 900})

from env_loader import load_project_env
load_project_env(script_dir=os.path.dirname(os.path.abspath(__file__)))

from pxr import Usd, UsdGeom, Gf, UsdPhysics, PhysxSchema
from isaacsim.core.api import World
from isaacsim.core.utils.prims import define_prim
from isaacsim.robot.policy.examples.robots import H1FlatTerrainPolicy
from isaacsim.core.utils.stage import add_reference_to_stage
import omni
import carb
import omni.appwindow
from sim_frontend import PartenitDemoGUI, SimGUICallbacks

# World coordinates of the human mannequin (set in scene below)
_HUMAN_WORLD_POS = (3.5, 0.0, 0.0)


class SharedState:
    cmd_vel = [0.0, 0.0, 0.0]  # vx, vy, wz
    cmd_lock = threading.Lock()
    robot_status = {"battery": 100.0, "mode": "sim", "joint_states": {}}
    chat_queue = []
    incoming_chat = []
    camera_bytes = None
    physics_ready: bool = False  # True only after world.reset() + physics callback registered


state = SharedState()

_STATUS_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="2">
<title>Partenit H1 Bridge</title>
<style>
  body{font-family:monospace;background:#111;color:#eee;padding:24px;max-width:700px}
  h1{color:#76b900;margin:0 0 4px}
  .sub{color:#888;margin:0 0 24px;font-size:13px}
  .card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:16px}
  .label{color:#888;font-size:12px;text-transform:uppercase;margin-bottom:6px}
  .val{font-size:18px;font-weight:bold}
  .ok{color:#76b900} .warn{color:#f90} .err{color:#f44}
  .row{display:flex;gap:32px;flex-wrap:wrap}
  .metric{min-width:140px}
  .endpoints{font-size:13px;line-height:1.8;color:#aaa}
  a{color:#76b900}
</style>
</head>
<body>
<h1>Partenit H1 Bridge</h1>
<p class="sub">Auto-refreshes every 2 seconds &nbsp;|&nbsp;
  <a href="/partenit/health">health</a> &nbsp;
  <a href="/partenit/observations">observations</a> &nbsp;
  <a href="/robot/state">robot state</a>
</p>
<div id="content">Loading...</div>
<script>
async function load() {
  const [h, obs, rs] = await Promise.all([
    fetch('/partenit/health').then(r=>r.json()).catch(()=>({})),
    fetch('/partenit/observations').then(r=>r.json()).catch(()=>[]),
    fetch('/robot/state').then(r=>r.json()).catch(()=>({})),
  ]);
  const ready = h.ready;
  const pos = rs.position || {x:0,y:0,z:0};
  const human = obs[0] || null;
  const dist = human ? Math.sqrt(
    Math.pow(human.position_3d[0],2)+Math.pow(human.position_3d[1],2)
  ).toFixed(2) : '—';
  const distColor = !human ? '' : dist>1.5?'ok':dist>0.8?'warn':'err';
  document.getElementById('content').innerHTML = `
  <div class="card">
    <div class="label">Bridge status</div>
    <div class="row">
      <div class="metric"><div class="label">Physics</div>
        <div class="val ${ready?'ok':'warn'}">${ready?'READY':'LOADING...'}</div></div>
      <div class="metric"><div class="label">Robot ID</div>
        <div class="val">${h.robot_id||'—'}</div></div>
    </div>
  </div>
  <div class="card">
    <div class="label">H1 position (world)</div>
    <div class="row">
      <div class="metric"><div class="label">X</div><div class="val">${pos.x?.toFixed(2)||'—'} m</div></div>
      <div class="metric"><div class="label">Y</div><div class="val">${pos.y?.toFixed(2)||'—'} m</div></div>
      <div class="metric"><div class="label">Heading</div>
        <div class="val">${rs.heading_rad!=null?(rs.heading_rad*57.3).toFixed(1)+'°':'—'}</div></div>
    </div>
  </div>
  <div class="card">
    <div class="label">Human observation</div>
    <div class="row">
      <div class="metric"><div class="label">Distance</div>
        <div class="val ${distColor}">${dist} m</div></div>
      <div class="metric"><div class="label">Class</div>
        <div class="val">${human?human.class_best:'—'}</div></div>
      <div class="metric"><div class="label">Confidence</div>
        <div class="val">${human?(human.confidence*100).toFixed(0)+'%':'—'}</div></div>
    </div>
  </div>
  <div class="card endpoints">
    <div class="label">REST endpoints</div>
    GET &nbsp;<a href="/partenit/health">/partenit/health</a><br>
    GET &nbsp;<a href="/partenit/observations">/partenit/observations</a><br>
    POST /partenit/command &nbsp;← GuardDecision JSON<br>
    GET &nbsp;<a href="/robot/state">/robot/state</a><br>
    POST /control/move &nbsp;← {"vx":0.5,"vy":0,"wz":0}<br>
    POST /control/stop<br>
    GET &nbsp;<a href="/camera/latest">/camera/latest</a> &nbsp;← PNG
  </div>`;
}
load();
</script>
</body>
</html>"""


class BridgeHandler(BaseHTTPRequestHandler):

    # ------------------------------------------------------------------
    # POST handlers
    # ------------------------------------------------------------------
    def do_POST(self):
        if self.path == "/control/move":
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length")))
                data = json.loads(body)
                with state.cmd_lock:
                    state.cmd_vel[0] = float(data.get("vx", 0.0))
                    state.cmd_vel[1] = float(data.get("vy", 0.0))
                    state.cmd_vel[2] = float(data.get("wz", 0.0))
                self._send_json({"status": "ok"})
            except Exception as e:
                self._send_error(str(e))

        elif self.path == "/control/stop":
            with state.cmd_lock:
                state.cmd_vel[:] = [0.0, 0.0, 0.0]
            self._send_json({"status": "stopped"})

        elif self.path == "/chat/send":
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length")))
                data = json.loads(body)
                msg = data.get("message", "")
                if msg:
                    state.incoming_chat.append(("robot", msg))
                self._send_json({"status": "received"})
            except Exception as e:
                self._send_error(str(e))

        # --- Partenit: receive GuardDecision and apply to robot ---
        elif self.path == "/partenit/command":
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                decision = json.loads(body)

                allowed = decision.get("allowed", True)
                modified = decision.get("modified_params") or {}

                if not allowed:
                    with state.cmd_lock:
                        state.cmd_vel[:] = [0.0, 0.0, 0.0]
                    reason = decision.get("rejection_reason", "guard block")
                    risk = decision.get("risk_score", {})
                    risk_val = risk.get("value", "?") if isinstance(risk, dict) else "?"
                    print(f"[Partenit] BLOCKED  risk={risk_val}  reason={reason}")
                else:
                    speed = float(
                        modified.get("speed",
                        modified.get("max_velocity", 0.5))
                    )
                    with state.cmd_lock:
                        state.cmd_vel[0] = min(speed, 0.75)  # cap vx at 0.75 m/s
                        state.cmd_vel[1] = 0.0
                        state.cmd_vel[2] = 0.0
                    policies = decision.get("applied_policies", [])
                    risk = decision.get("risk_score", {})
                    risk_val = risk.get("value", "?") if isinstance(risk, dict) else "?"
                    print(f"[Partenit] ALLOWED  speed={speed:.2f}  risk={risk_val}  "
                          f"policies={policies}")

                self._send_json({"status": "ok"})
            except Exception as e:
                self._send_error(str(e))

        else:
            self.send_response(404)
            self.end_headers()

    # ------------------------------------------------------------------
    # GET handlers
    # ------------------------------------------------------------------
    def do_GET(self):
        if self.path == "/robot/state":
            self._send_json(state.robot_status)

        elif self.path == "/chat/read":
            msgs = []
            with state.cmd_lock:
                if state.chat_queue:
                    msgs = state.chat_queue[:]
                    state.chat_queue.clear()
            self._send_json({"messages": msgs})

        elif self.path == "/camera/latest":
            if state.camera_bytes:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                self.wfile.write(state.camera_bytes)
            else:
                self.send_response(404)
                self.end_headers()

        # --- Partenit: health check ---
        elif self.path == "/partenit/health":
            self._send_json({
                "status": "ok",
                "robot_id": "h1_isaac_sim",
                "timestamp": time.time(),
                "is_simulation": True,
                "ready": state.physics_ready,  # False until physics loop is running
            })

        # --- Partenit: observations (human position in robot-centric frame) ---
        elif self.path == "/partenit/observations":
            with state.cmd_lock:
                rpos = state.robot_status.get("position", {"x": 0.0, "y": 0.0, "z": 0.0})
                rvel = state.robot_status.get("velocity", {"vx": 0.0, "vy": 0.0, "vz": 0.0})

            rx = float(rpos.get("x", 0.0))
            ry = float(rpos.get("y", 0.0))

            # Human is static at _HUMAN_WORLD_POS; position_3d is robot-centric
            dx = _HUMAN_WORLD_POS[0] - rx
            dy = _HUMAN_WORLD_POS[1] - ry

            self._send_json([{
                "object_id": "human_0",
                "class_best": "human",
                "class_set": ["human"],          # triggers treat_as_human=True
                "position_3d": [dx, dy, 0.0],    # meters, robot-centric
                "velocity": [0.0, 0.0, 0.0],     # mannequin is static
                "confidence": 0.95,
                "sensor_trust": 0.9,
                "source_id": "isaac_sim_perception",
            }])

        elif self.path in ("/", "/status"):
            self._send_html(_STATUS_PAGE_HTML)

        else:
            self.send_response(404)
            self.end_headers()

    # ------------------------------------------------------------------
    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg):
        body = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return  # silence per-request logs; Partenit prints its own


def run_server():
    server = HTTPServer(("0.0.0.0", 8000), BridgeHandler)
    print("Bridge API  : http://0.0.0.0:8000")
    print("Partenit API: http://0.0.0.0:8000/partenit/{health,observations,command}")
    server.serve_forever()


# ------------------------------------------------------------------
# GUI callbacks (unchanged from h1_bridge.py)
# ------------------------------------------------------------------

class BridgeCallbacks(SimGUICallbacks):
    def __init__(self):
        self.chat_history = [("system", "H1 Bridge + Partenit Ready.")]
        self.enabled = True

    def get_latest_camera_bytes(self):
        return state.camera_bytes

    def add_user_message(self, msg: str):
        self.chat_history.append(("user", msg))
        if len(self.chat_history) > 30:
            self.chat_history.pop(0)

    def on_send_command(self, cmd: str, img: bytes):
        with state.cmd_lock:
            state.chat_queue.append(cmd)

    def on_toggle_enable(self):
        self.enabled = not self.enabled

    def get_enabled(self):
        return self.enabled

    def on_scenario_hri(self):
        with state.cmd_lock:
            state.chat_queue.append("/scenario hri")

    def on_scenario_battery(self):
        with state.cmd_lock:
            state.chat_queue.append("/scenario battery")

    def on_scenario_handoff(self):
        with state.cmd_lock:
            state.chat_queue.append("/scenario handoff")

    def on_clear(self):
        self.chat_history = [("system", "Chat cleared")]

    def on_learn_map(self):
        with state.cmd_lock:
            state.chat_queue.append("/learn_map")

    def get_trace(self):
        return "Partenit Bridge Mode"

    def get_chat_history(self):
        while state.incoming_chat:
            self.chat_history.append(state.incoming_chat.pop(0))
        return self.chat_history

    def set_trace(self, t: str):
        pass

    def get_task(self):
        return "Waiting for Partenit commands"

    def set_task(self, t: str):
        pass

    def get_sim_tunables(self):
        return {}

    def set_sim_tunables(self, d: dict):
        pass

    def on_task_changed(self, new_task: str):
        pass


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    state.incoming_chat = []

    threading.Thread(target=run_server, daemon=True).start()

    try:
        from isaacsim.storage.native import get_assets_root_path
        assets_root_path = get_assets_root_path()
    except Exception:
        try:
            from omni.isaac.core.utils.nucleus import get_assets_root_path
            assets_root_path = get_assets_root_path()
        except Exception:
            assets_root_path = None

    world = World(stage_units_in_meters=1.0, physics_dt=1 / 100, rendering_dt=8 / 100)

    if assets_root_path:
        MAP_USD = assets_root_path + "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd"
        add_reference_to_stage(MAP_USD, "/World")
        print(f"[Bridge] Warehouse: {MAP_USD}")
    else:
        world.scene.add_default_ground_plane()
        define_prim("/World/Light", "DistantLight")
        print("[Bridge] Using default ground plane")

    usd_path = (assets_root_path + "/Isaac/Robots/Unitree/H1/h1.usd"
                if assets_root_path else None)
    h1_policy = H1FlatTerrainPolicy(
        prim_path="/World/H1_0",
        name="H1_0",
        usd_path=usd_path,
        position=np.array([0, 0, 1.05]),
    )

    stage = omni.usd.get_context().get_stage()
    object_paths = []

    def setup_obj(path, type_str, pos, scale, color):
        prim = stage.DefinePrim(path, type_str)
        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
        xf.AddScaleOp().Set(Gf.Vec3d(*scale))
        UsdGeom.Gprim(prim).CreateDisplayColorAttr([Gf.Vec3f(*color)])
        return prim

    setup_obj("/World/Sphere",      "Sphere", (2.5, 0.0, 0.35),  (0.35,)*3, (1.0, 0.9, 0.05))
    setup_obj("/World/Cube_Green",  "Cube",   (-1.5, -3.0, 0.2), (0.2,)*3,  (0.1, 0.8, 0.1))
    setup_obj("/World/Cube_Blue",   "Cube",   (2.0, -1.5, 0.28), (0.28,)*3, (0.1, 0.2, 0.9))
    setup_obj("/World/Cube_Red",    "Cube",   (0.0, -1.5, 0.35), (0.35,)*3, (0.9, 0.1, 0.1))
    setup_obj("/World/Cube_Yellow", "Cube",   (1.5, 1.5, 0.32),  (0.32,)*3, (1.0, 0.85, 0.1))
    object_paths = ["/World/Sphere", "/World/Cube_Green", "/World/Cube_Blue",
                    "/World/Cube_Red", "/World/Cube_Yellow"]

    for _path in object_paths:
        _prim = stage.GetPrimAtPath(_path)
        if _prim.IsValid():
            UsdPhysics.CollisionAPI.Apply(_prim)
            _rb = UsdPhysics.RigidBodyAPI.Apply(_prim)
            _rb.CreateRigidBodyEnabledAttr().Set(False)
            PhysxSchema.PhysxRigidBodyAPI.Apply(_prim)

    # Human mannequin — placed at world (3.5, 0.0, 0.0), matching _HUMAN_WORLD_POS
    HUMAN_USD = (
        "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
        "/Assets/Isaac/5.1/Isaac/People/Characters/original_male_adult_construction_01"
        "/male_adult_construction_01.usd"
    )
    try:
        human_prim = add_reference_to_stage(HUMAN_USD, "/World/Human_0")
        try:
            UsdGeom.Xformable(human_prim).GetTranslateOp().Set(
                Gf.Vec3d(*_HUMAN_WORLD_POS)
            )
        except Exception:
            UsdGeom.Xformable(human_prim).AddTranslateOp().Set(
                Gf.Vec3d(*_HUMAN_WORLD_POS)
            )
        print(f"[Bridge] Human at world {_HUMAN_WORLD_POS}")
    except Exception as e:
        print(f"[Bridge] Human load failed: {e}")

    BOX_USD = (
        "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
        "/Assets/Isaac/5.1/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxA_01.usd"
    )
    box_paths = []
    try:
        for prim_name, scale, pos in [
            ("Box_Red",    0.81, (0.3 - 0.25, -1.3 - 0.25, 0.525 + 0.15 + 0.07 + 0.81 * 0.15)),
            ("Box_Yellow", 0.77, (1.9, 1.9, 0.48 + 0.15 + 0.07 + 0.77 * 0.15)),
        ]:
            bp = add_reference_to_stage(usd_path=BOX_USD, prim_path=f"/World/{prim_name}")
            xf = UsdGeom.Xformable(bp)
            xf.ClearXformOpOrder()
            xf.AddScaleOp().Set(Gf.Vec3d(scale, scale, scale))
            xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
            box_paths.append(f"/World/{prim_name}")
    except Exception as e:
        print(f"[Bridge] Boxes load failed: {e}")

    for _path in box_paths:
        _prim = stage.GetPrimAtPath(_path)
        if _prim.IsValid():
            UsdPhysics.CollisionAPI.Apply(_prim)
            _rb = UsdPhysics.RigidBodyAPI.Apply(_prim)
            _rb.CreateRigidBodyEnabledAttr().Set(False)
            PhysxSchema.PhysxRigidBodyAPI.Apply(_prim)

    from sim_camera import create_h1_camera_prim, CameraWrapper

    sim_state = {
        "first_step": True,
        "reset_needed": False,
        "camera_wrapper": None,
        "gui": None,
        "capture_interval": 10,
        "frame_count": 0,
    }

    def on_physics_step(step_size):
        if sim_state["first_step"]:
            h1_policy.initialize()
            h1_policy.post_reset()
            if hasattr(h1_policy, "robot") and hasattr(h1_policy, "default_pos"):
                h1_policy.robot.set_joints_default_state(h1_policy.default_pos)
            with state.cmd_lock:
                state.cmd_vel[:] = [0.0, 0.0, 0.0]  # clear any stale commands from loading

            cam_path = create_h1_camera_prim(stage)
            wrapper = CameraWrapper(prim_path=cam_path)
            wrapper.initialize(created_prim_path=cam_path)
            sim_state["camera_wrapper"] = wrapper

            sim_state["gui"] = PartenitDemoGUI(BridgeCallbacks())
            print("[Bridge] GUI ready")
            sim_state["first_step"] = False

        elif sim_state["reset_needed"]:
            world.reset(soft=True)
            sim_state["reset_needed"] = False
            sim_state["first_step"] = True

        else:
            base_cmd = np.zeros(3)
            with state.cmd_lock:
                base_cmd[:] = state.cmd_vel

            try:
                h1_policy.forward(step_size, base_cmd)
            except Exception as e:
                print(f"[Bridge] Physics error: {e}")

            try:
                if hasattr(h1_policy, "robot") and h1_policy.robot is not None:
                    pos, orient = h1_policy.robot.get_world_pose()
                    lin_vel = h1_policy.robot.get_linear_velocity()
                    qw, qx, qy, qz = (float(orient[i]) for i in range(4))
                    yaw = np.arctan2(
                        2.0 * (qw * qz + qx * qy),
                        1.0 - 2.0 * (qy * qy + qz * qz),
                    )
                    with state.cmd_lock:
                        state.robot_status.update({
                            "position": {
                                "x": float(pos[0]),
                                "y": float(pos[1]),
                                "z": float(pos[2]),
                            },
                            "velocity": {
                                "vx": float(lin_vel[0]),
                                "vy": float(lin_vel[1]),
                                "vz": float(lin_vel[2]),
                            },
                            "heading_rad": float(yaw),
                            "timestamp_s": time.time(),
                        })
            except Exception:
                pass

    world.reset()
    world.add_physics_callback("partenit_step", on_physics_step)
    state.physics_ready = True
    print("[Bridge] Physics ready — Partenit API accepting commands")

    input_keyboard_mapping = {
        "UP":    [0.75, 0.0, 0.0],
        "DOWN":  [-0.5, 0.0, 0.0],
        "LEFT":  [0.0, 0.0, 0.75],
        "RIGHT": [0.0, 0.0, -0.75],
    }

    def sub_keyboard_event(event, *args, **kwargs) -> bool:
        if event.type == carb.input.KeyboardEventType.KEY_PRESS:
            if event.input.name in input_keyboard_mapping:
                val = input_keyboard_mapping[event.input.name]
                with state.cmd_lock:
                    state.cmd_vel[:] = val
                return True
            if event.input.name == "ESCAPE":
                with state.cmd_lock:
                    state.cmd_vel[:] = [0.0, 0.0, 0.0]
                return True
        elif event.type == carb.input.KeyboardEventType.KEY_RELEASE:
            if event.input.name in input_keyboard_mapping:
                with state.cmd_lock:
                    state.cmd_vel[:] = [0.0, 0.0, 0.0]
                return True
        return True

    appwindow = omni.appwindow.get_default_app_window()
    input_interface = carb.input.acquire_input_interface()
    keyboard = appwindow.get_keyboard()
    keyboard_sub = input_interface.subscribe_to_keyboard_events(keyboard, sub_keyboard_event)
    print("[Bridge] Arrow keys — manual control | Partenit API — autonomous guard")

    while simulation_app.is_running():
        world.step(render=True)

        gui = sim_state["gui"]
        cam_wrapper = sim_state["camera_wrapper"]

        if gui:
            gui.update_view()

        if cam_wrapper and cam_wrapper.initialized:
            sim_state["frame_count"] += 1
            if sim_state["frame_count"] % sim_state["capture_interval"] == 0:
                img = cam_wrapper.capture_image()
                if img is not None:
                    state.camera_bytes = cam_wrapper.process_image_for_vlm(img)

    input_interface.unsubscribe_to_keyboard_events(keyboard, keyboard_sub)
    simulation_app.close()


if __name__ == "__main__":
    main()
