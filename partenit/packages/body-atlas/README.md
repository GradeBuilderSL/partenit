# Partenit Body Atlas

> URDF → spectral basis + morphology descriptor + contact regimes
> + reachability + safety bounds. Zero-data motorics — no training
> data required.

A standalone freemium component of [Partenit Motor Compiler](https://github.com/GradeBuilderSL/trust-layer)
that extracts the *body's mathematical passport* from a robot URDF.

## Install

```bash
pip install partenit-body-atlas
# Recommended — full Pinocchio dynamics:
pip install partenit-body-atlas[pinocchio]
# Self-collision detection:
pip install partenit-body-atlas[collision]
# Everything:
pip install partenit-body-atlas[all]
```

## Usage

```python
from partenit_body_atlas import build_atlas

atlas = build_atlas("vendor/franka_panda/urdf/panda.urdf",
                     robot_id="panda")
print(atlas.embodiment_class)        # 'manipulator'
print(atlas.n_dof)                    # 9
print(atlas.modes[0]["eigenvalue"])   # 0.061
print(atlas.modes[0]["label"])
# {'region': 'other', 'structure': 'single', 'joint_kinds': [...], …}
print(atlas.morphology_descriptor)
# [9.0, 19.7, 0.13, 87.0, 26.0, 0.55]
```

CLI:

```bash
partenit-atlas build vendor/franka_panda/urdf/panda.urdf
# wrote panda_atlas.json (9 DOF, manipulator, backend=pinocchio_crba)

partenit-atlas inspect vendor/franka_panda/urdf/panda.urdf
# robot_id: panda
# embodiment: manipulator
# n_dof: 9
# top modes:
#   0: λ=0.061  region=other  struct=single
#   …
```

## What you get out of the box

| Field | What it is |
|---|---|
| `mass_matrix` | M(q₀) via Pinocchio CRBA, fallback to mass-weighted graph Laplacian |
| `stiffness_matrix` | Gravity-Hessian + graph-Laplacian blend |
| `modes` | Top-K eigenmodes of K φ = λ M φ, structured semantic labels |
| `morphology_descriptor` | 6-D vector: [n_DOF, total_mass, char_length, max_torque, range_sum, topology_hash] |
| `safety_bounds` | joint limits + velocity caps + reachability AABB + self-collision world |
| `contact_regimes` | Per-class regime list with constraint Jacobians J_c |

## What it costs

- **Free** for non-commercial use, research, education.
- **Paid** as part of the [Partenit Motor Compiler](https://partenit.io/motor-compiler) SDK
  for production deployment in commercial robotics products.

## Why

> Roboticists keep re-deriving the same `M(q)` from the same URDFs.
> We package it once, surface it as a portable artefact, and let
> downstream tools (Skill Compiler, fleet planners, sim2real
> bridges) consume it.

— bible §6.1 freemium positioning.

## License

Apache 2.0. Pinocchio extras under their respective licenses
(BSD-2-Clause).
