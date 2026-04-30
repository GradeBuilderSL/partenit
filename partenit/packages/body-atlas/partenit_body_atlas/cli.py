"""partenit-atlas CLI — `partenit-atlas build robot.urdf`.

Equivalent to `python -m motor_compiler.atlas <urdf>`, just with a
standalone entry point so `pip install partenit-body-atlas` users
get a useful command-line tool.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import build_atlas


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="partenit-atlas",
        description="URDF → BodyAtlas (spectral basis + morphology + safety)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build", help="build atlas from URDF")
    pb.add_argument("urdf")
    pb.add_argument("--robot-id", default=None)
    pb.add_argument("--out", default=None,
                     help="write atlas JSON here")
    pb.add_argument("--top-modes", type=int, default=20)

    pi = sub.add_parser("inspect",
                          help="print the atlas summary to stdout")
    pi.add_argument("urdf")
    pi.add_argument("--robot-id", default=None)

    args = parser.parse_args()
    if args.cmd == "build":
        atlas = build_atlas(args.urdf, robot_id=args.robot_id,
                              top_modes=args.top_modes)
        out_path = args.out or f"{atlas.robot_id}_atlas.json"
        Path(out_path).write_text(
            json.dumps(atlas.to_serialisable(), indent=2),
        )
        print(f"wrote {out_path} ({atlas.n_dof} DOF, "
              f"{atlas.embodiment_class}, "
              f"backend={atlas.metadata.get('dynamics_backend')})")
        return 0
    if args.cmd == "inspect":
        atlas = build_atlas(args.urdf, robot_id=args.robot_id)
        print(f"robot_id: {atlas.robot_id}")
        print(f"embodiment: {atlas.embodiment_class}")
        print(f"n_dof: {atlas.n_dof}")
        print(f"backend: {atlas.metadata.get('dynamics_backend')}")
        print(f"top modes:")
        for i, m in enumerate(atlas.modes[:5]):
            lbl = m.get("label") or {}
            print(f"  {i}: λ={m['eigenvalue']:.3f}  "
                   f"region={lbl.get('region')}  "
                   f"struct={lbl.get('structure')}")
        print(f"morphology_descriptor: {atlas.morphology_descriptor}")
        print(f"safety_bounds.joint_lower: "
              f"{atlas.safety_bounds.get('joint_lower')}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
