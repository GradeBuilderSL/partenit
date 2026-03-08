# sim_camera.py - Camera setup and viewport for Isaac Sim
# Reusable for different robots (H1, etc.) via config and robot_prim_path.
# All settings from .env: CAMERA_PRIM, CAMERA_PITCH, CAMERA_FOCAL_LENGTH, etc.

import os
import time
from dataclasses import dataclass

import numpy as np
import omni
from isaacsim.core.utils.rotations import euler_angles_to_quat
from isaacsim.sensors.camera import Camera
from pxr import Gf, Sdf, UsdGeom

_CAMERA_ENV_LOADED = False


def _load_camera_env():
    """Load .env into os.environ (once). Isaac Sim may run from different cwd — sim_camera loads its own .env."""
    global _CAMERA_ENV_LOADED
    if _CAMERA_ENV_LOADED:
        return
    for base in [
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        os.getcwd(),
    ]:
        path = os.path.join(base, ".env")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k.startswith("CAMERA_") and v:
                            os.environ.setdefault(k, v)
            _CAMERA_ENV_LOADED = True
            return


def _env_float(key: str, default: float) -> float:
    _load_camera_env()
    return float(os.getenv(key, str(default)))


def _env_int(key: str, default: int) -> int:
    _load_camera_env()
    return int(os.getenv(key, str(default)))


# Fallbacks when .env vars missing (used only in from_env)
_DEFAULT_PITCH = -15.0
_DEFAULT_PITCH_NEAR = -15.0  # walking / near: floor + cubes in frame (not just floor)
_DEFAULT_PITCH_FAR = -5.0  # scanning / far: slightly above horizon
_DEFAULT_PRIM = "torso_link"
# USD camera: +Y up, -Z forward. Pitch (tilt up/down) = rotate around X. Y = yaw (pan).
_DEFAULT_PITCH_AXIS = "x"
_DEFAULT_FOCAL = 24  # was 10.0 - увеличено для уменьшения fish-eye эффекта
_DEFAULT_FOCUS = 0
_DEFAULT_WIDTH = 854
_DEFAULT_HEIGHT = 480


@dataclass
class CameraConfig:
    """Camera config. from_env() reads .env (CAMERA_*); defaults only when var missing."""

    prim_name: str = _DEFAULT_PRIM
    pitch_deg: float = _DEFAULT_PITCH
    pitch_near: float = _DEFAULT_PITCH_NEAR  # walking / near: look down
    pitch_far: float = _DEFAULT_PITCH_FAR  # scanning / far: look forward
    width: int = _DEFAULT_WIDTH
    height: int = _DEFAULT_HEIGHT
    focal_length: float = _DEFAULT_FOCAL
    pitch_axis: str = _DEFAULT_PITCH_AXIS
    focus_distance: float = _DEFAULT_FOCUS
    dual_viewport: bool = True

    @classmethod
    def from_env(cls) -> "CameraConfig":
        """Read all values from .env (CAMERA_* vars). Fallbacks only when var missing."""
        _load_camera_env()
        cfg = cls(
            prim_name=(os.getenv("CAMERA_PRIM", _DEFAULT_PRIM) or _DEFAULT_PRIM).strip().lower(),
            pitch_deg=_env_float("CAMERA_PITCH", _DEFAULT_PITCH),
            pitch_near=_env_float("CAMERA_PITCH_NEAR", _DEFAULT_PITCH_NEAR),
            pitch_far=_env_float("CAMERA_PITCH_FAR", _DEFAULT_PITCH_FAR),
            width=_env_int("CAMERA_WIDTH", _DEFAULT_WIDTH),
            height=_env_int("CAMERA_HEIGHT", _DEFAULT_HEIGHT),
            focal_length=_env_float("CAMERA_FOCAL_LENGTH", _DEFAULT_FOCAL),
            pitch_axis=(os.getenv("CAMERA_PITCH_AXIS", _DEFAULT_PITCH_AXIS) or _DEFAULT_PITCH_AXIS)
            .lower()
            .strip()[:1],
            focus_distance=_env_float("CAMERA_FOCUS_DISTANCE", _DEFAULT_FOCUS),
            dual_viewport=os.getenv("DUAL_VIEWPORT", "1") == "1",
        )
        if os.getenv("VLM_DEBUG") or os.getenv("CAMERA_DEBUG"):
            print(
                f"[Camera] from .env: prim={cfg.prim_name} pitch={cfg.pitch_deg} focal={cfg.focal_length} focus={cfg.focus_distance}"
            )
        return cfg


class CameraWrapper:
    """Wraps Isaac Sim Camera for capture and VLM. Robot-agnostic via prim_path."""

    def __init__(self, prim_path=None, name="head_camera", config: CameraConfig = None):
        self.config = config or CameraConfig.from_env()
        if prim_path is None:
            prim_path = self._default_prim_path()
        self.prim_path = prim_path
        self.name = name
        self.camera = None
        self.initialized = False
        self._pitch_deg = self.config.pitch_deg

    def _default_prim_path(self) -> str:
        if self.config.prim_name == "torso_link":
            return "/World/H1_0/torso_link/camera"
        return "/World/H1_0/pelvis/pelvis/chest/chest/neck/neck/head/head/head_camera"

    def _update_pose(self):
        """Apply _pitch_deg to camera. For torso_link/head: update USD prim directly."""
        if not self.camera:
            return
        # X = pitch (tilt up/down in USD: -Z forward, +Y up). Y = yaw (pan).
        if self.config.pitch_axis == "x":
            rot_xyz = (self._pitch_deg, 0.0, 0.0)
        else:
            rot_xyz = (0.0, self._pitch_deg, 0.0)
        if self.config.prim_name in ("torso_link", "head"):
            # Update USD prim rotation (Isaac Camera may not apply set_local_pose for child prims)
            try:
                stage = omni.usd.get_context().get_stage()
                prim = stage.GetPrimAtPath(self.prim_path)
                if prim.IsValid():
                    xf = UsdGeom.Xformable(prim)
                    for op in xf.GetOrderedXformOps():
                        if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
                            op.Set(Gf.Vec3f(*rot_xyz))
                            return
                    # No RotateXYZ op: add one
                    xf.AddRotateXYZOp().Set(Gf.Vec3f(*rot_xyz))
            except Exception as e:
                if os.getenv("CAMERA_DEBUG"):
                    print(f"[Camera] _update_pose USD: {e}")
        else:
            euler = np.array([float(rot_xyz[0]), float(rot_xyz[1]), float(rot_xyz[2])])
            self.camera.set_local_pose(
                translation=np.array([0.18, 0.0, 0.15]),
                orientation=euler_angles_to_quat(euler, degrees=True),
            )

    def set_pitch(self, deg: float):
        self._pitch_deg = float(deg)
        self._update_pose()

    def set_pitch_mode(self, mode: str):
        """mode: 'near' = look down (walking, cubes), 'far' = look forward (scanning)."""
        if mode == "near":
            self.set_pitch(self.config.pitch_near)
        elif mode == "far":
            self.set_pitch(self.config.pitch_far)
        else:
            self.set_pitch(self.config.pitch_deg)

    def initialize(self, created_prim_path: str = None):
        """Initialize camera. Use created_prim_path if camera prim was created externally (e.g. create_h1_camera_prim)."""
        try:
            stage = omni.usd.get_context().get_stage()
            if created_prim_path and stage.GetPrimAtPath(created_prim_path).IsValid():
                self.prim_path = created_prim_path
            elif self.config.prim_name == "torso_link":
                self.prim_path = "/World/H1_0/torso_link/camera"
            else:
                for p in [
                    "/World/H1_0/pelvis/pelvis/chest/chest/neck/neck/head/head",
                    "/World/H1_0/head_link",
                ]:
                    if stage.GetPrimAtPath(p).IsValid():
                        self.prim_path = p + "/head_camera"
                        break
                else:
                    self.prim_path = "/World/H1_0/torso_link/camera"
                    print("[Camera] Head link not found, using torso_link")
            pitch_deg = float(self.config.pitch_deg)
            # X = pitch (tilt up/down). Y = yaw (pan). USD: -Z forward, +Y up.
            euler = (
                np.array([pitch_deg, 0.0, 0.0])
                if self.config.pitch_axis == "x"
                else np.array([0.0, pitch_deg, 0.0])
            )
            self.camera = Camera(
                prim_path=self.prim_path,
                name=self.name,
                position=np.array([0.1, 0.0, 1.2]),
                resolution=(self.config.width, self.config.height),
                orientation=euler_angles_to_quat(euler, degrees=True),
                render_product_path=None,
            )
            self.camera.initialize()
            # Aperture: Already set in create_h1_camera_prim to avoid warnings
            try:
                self.camera.add_rgb_to_frame()
            except Exception:
                pass  # "Annotator rgb already attached" - non-fatal
            try:
                self.camera.set_clipping_range(0.05, 100.0)
            except Exception:
                pass
            self.initialized = True
            print(f"[Camera] Initialized at {self.prim_path} (prim={self.config.prim_name})")
        except Exception as e:
            print(f"[Camera] Init error: {e}")
            self.initialized = False

    def capture_image(self):
        """Capture RGB frame. MUST be called from main/simulation thread."""
        if not self.initialized or self.camera is None:
            return None
        last_arr = None
        for attempt in range(5):
            try:
                rgb = self.camera.get_rgb()
                if rgb is None and hasattr(self.camera, "get_rgba"):
                    rgba = self.camera.get_rgba()
                    if rgba is not None:
                        rgb = rgba[:, :, :3] if rgba.ndim == 3 and rgba.shape[-1] >= 3 else rgba
                if rgb is None and hasattr(self.camera, "get_current_frame"):
                    frame = self.camera.get_current_frame()
                    if isinstance(frame, dict) and "rgb" in frame:
                        rgb = frame["rgb"]
                if rgb is None:
                    time.sleep(0.02)
                    continue
                arr = np.asarray(rgb)
                arr = (
                    (arr * 255).astype(np.uint8) if arr.dtype != np.uint8 else arr.astype(np.uint8)
                )
                if arr.ndim == 3 and arr.shape[-1] in (3, 4) and arr.size > 0:
                    if arr.shape[-1] == 4:
                        arr = arr[:, :, :3]
                    last_arr = arr
                    if arr.mean() >= 2:
                        break
                    time.sleep(0.02)
            except Exception:
                time.sleep(0.02)
        if last_arr is not None and os.getenv("VLM_DEBUG"):
            try:
                from PIL import Image

                Image.fromarray(last_arr).save("/tmp/vlm_capture_debug.png")
                print("[VLM] Debug: saved to /tmp/vlm_capture_debug.png")
            except Exception:
                pass
        return last_arr

    def process_image_for_vlm(self, image):
        """Convert RGB numpy to PNG bytes for Gemini/VLM."""
        if image is None:
            return None
        try:
            import io

            from PIL import Image

            if image.dtype != np.uint8:
                image = (
                    (image * 255).astype(np.uint8) if image.max() <= 1 else image.astype(np.uint8)
                )
            pil = Image.fromarray(image)
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            print(f"[VLM] process_image error: {e}")
            return None


def create_h1_camera_prim(stage, config: CameraConfig = None) -> str:
    """
    Create H1 camera prim in USD stage. Returns created prim path or None.
    Call before CameraWrapper.initialize(); pass result as created_prim_path.
    """
    config = config or CameraConfig.from_env()
    if config.prim_name == "torso_link":
        cam_path = "/World/H1_0/torso_link/camera"
        parent = stage.GetPrimAtPath("/World/H1_0/torso_link")
        if not parent.IsValid():
            print("[Camera] torso_link not found")
            return None
        cam_prim = stage.DefinePrim(cam_path, "Camera")
        xf = UsdGeom.Xformable(cam_prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(-0.8, 0.0, 1.25))
        # X = pitch (tilt up/down). Y = yaw. USD: -Z forward, +Y up.
        rot = (
            (float(config.pitch_deg), 0.0, 0.0)
            if config.pitch_axis == "x"
            else (0.0, float(config.pitch_deg), 0.0)
        )
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
        UsdGeom.Camera(cam_prim).GetFocalLengthAttr().Set(config.focal_length)
        if config.focus_distance > 0:
            try:
                UsdGeom.Camera(cam_prim).GetFocusDistanceAttr().Set(config.focus_distance)
            except Exception:
                pass

        # aperture fix
        w, h = config.width, config.height
        aspect = w / h if h else 1.778
        hap = 20.955  # Standard 35mm film horiz aperture in mm
        vap = hap / aspect
        UsdGeom.Camera(cam_prim).GetHorizontalApertureAttr().Set(hap)
        UsdGeom.Camera(cam_prim).GetVerticalApertureAttr().Set(vap)
        print(f"[Camera] Prim at {cam_path} (torso_link)")
        return cam_path
    # head
    head_parent = None
    for p in [
        "/World/H1_0/pelvis/pelvis/chest/chest/neck/neck/head/head",
        "/World/H1_0/head_link",
    ]:
        if stage.GetPrimAtPath(p).IsValid():
            head_parent = p
            break
    if not head_parent:
        for prim in stage.Traverse():
            path_str = str(prim.GetPath())
            if path_str.startswith("/World/H1_0") and "head" in path_str.lower():
                if prim.GetTypeName() != "Camera" and "camera" not in path_str.lower():
                    head_parent = path_str
                    break
    if not head_parent:
        cam_path = "/World/H1_0/torso_link/camera"
        parent = stage.GetPrimAtPath("/World/H1_0/torso_link")
        if parent.IsValid():
            cam_prim = stage.DefinePrim(cam_path, "Camera")
            xf = UsdGeom.Xformable(cam_prim)
            xf.ClearXformOpOrder()
            xf.AddTranslateOp().Set(Gf.Vec3d(-0.8, 0.0, 1.25))
            rot = (
                (float(config.pitch_deg), 0.0, 0.0)
                if config.pitch_axis == "x"
                else (0.0, float(config.pitch_deg), 0.0)
            )
            xf.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
            UsdGeom.Camera(cam_prim).GetFocalLengthAttr().Set(config.focal_length)
            if config.focus_distance > 0:
                try:
                    UsdGeom.Camera(cam_prim).GetFocusDistanceAttr().Set(config.focus_distance)
                except Exception:
                    pass
            print(f"[Camera] Prim at {cam_path} (fallback torso_link)")
            return cam_path
        return None
    cam_path = head_parent + "/head_camera"
    cam_prim = stage.DefinePrim(cam_path, "Camera")
    xf = UsdGeom.Xformable(cam_prim)
    xf.ClearXformOpOrder()
    if head_parent == "/World/H1_0":
        xf.AddTranslateOp().Set(Gf.Vec3d(0.15, 0.0, 0.1))
        xf.AddRotateXYZOp().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    else:
        xf.AddTranslateOp().Set(Gf.Vec3d(0.2, 0.0, 0.15))
        # X = pitch (tilt up/down). Y = yaw. USD: -Z forward, +Y up.
        rot = (
            (float(config.pitch_deg), 0.0, 0.0)
            if config.pitch_axis == "x"
            else (0.0, float(config.pitch_deg), 0.0)
        )
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
    UsdGeom.Camera(cam_prim).GetFocalLengthAttr().Set(config.focal_length)
    if config.focus_distance > 0:
        try:
            UsdGeom.Camera(cam_prim).GetFocusDistanceAttr().Set(config.focus_distance)
        except Exception:
            pass

    # aperture fix
    w, h = config.width, config.height
    aspect = w / h if h else 1.778
    hap = 20.955  # Standard 35mm film horiz aperture in mm
    vap = hap / aspect
    UsdGeom.Camera(cam_prim).GetHorizontalApertureAttr().Set(hap)
    UsdGeom.Camera(cam_prim).GetVerticalApertureAttr().Set(vap)

    print(f"[Camera] Prim at {cam_path} (head)")
    return cam_path


_head_viewport_created = False


def create_head_camera_viewport(camera_wrapper: CameraWrapper, config: CameraConfig = None) -> bool:
    """
    Create second viewport showing robot head camera. Main = external, second = head POV.
    Returns True if created.
    Note: DLSS warning "below minimal 300" — set CAMERA_HEIGHT=600 if needed.
    """
    global _head_viewport_created
    config = config or CameraConfig.from_env()
    if not config.dual_viewport or _head_viewport_created or not camera_wrapper.initialized:
        return False
    try:
        from omni.kit.viewport.utility import create_viewport_window

        cam_path = camera_wrapper.prim_path
        stage = omni.usd.get_context().get_stage()
        if not stage.GetPrimAtPath(cam_path).IsValid():
            return False
        create_viewport_window(
            name="H1 Head Camera",
            width=config.width,
            height=config.height,
            position_x=1620,
            position_y=400,
            camera_path=Sdf.Path(cam_path),
        )
        _head_viewport_created = True
        print("[Camera] Head camera viewport created (dual view)")
        return True
    except Exception as e:
        print(f"[Camera] Viewport failed: {e}")
        return False
