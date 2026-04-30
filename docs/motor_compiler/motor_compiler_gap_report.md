# Motor Compiler — Bible vs implementation gap report

> Generated 2026-04-30 from a side-by-side audit of `partenit_motor_compiler.md`,
> `MOTOR_COMPILER_PLAN.md`, and the live code under
> `libs/motor_compiler/` and `services/motor_compiler/`.
>
> Status legend (4 levels, not 2):
>
> | Symbol | Meaning |
> |--------|---------|
> | 🟦 Implemented | Code exists, imports, passes unit tests |
> | 🟨 Wired | Component is in the pipeline, but only exercised through mock / null / smoke |
> | 🟧 Tested in sim | End-to-end run in MuJoCo / Isaac with a saved log |
> | 🟩 Validated with metric | Measured number on held-out scenarios, JSON / PNG persisted |
> | ⬜ Missing | Not implemented |
> | ⚠️ Parsed but ignored | DSL field accepted by parser, runtime drops it |

---

## 1. Vendor URDFs (manipulator-first MVP)

| Robot | URDF path | Status |
|-------|-----------|--------|
| Franka Panda | [vendor/franka_panda/urdf/panda.urdf](vendor/franka_panda/urdf/panda.urdf) | 🟦 Implemented |
| UR5e | — | ⬜ **Missing** |
| Kinova Gen3 | [vendor/kinova_gen3/urdf/gen3_7dof.urdf](vendor/kinova_gen3/urdf/gen3_7dof.urdf) | 🟦 Implemented |
| Anymal B / C | `vendor/anymal_b/`, `vendor/anymal_c/` | 🟦 Implemented (quadruped, not on the manipulator MVP path) |
| Unitree G1 | `vendor/unitree_g1/urdf/g1_29dof.urdf` | 🟦 Implemented |
| Unitree Go2 | `vendor/unitree_go2/` | 🟦 Implemented |

**Action:** vendor UR5e from `mujoco_menagerie/universal_robots_ur5e` so the
MVP-3 cross-manipulator narrative works.

---

## 2. End-to-end MuJoCo chain via `trust_layer_bridge`

| Layer | Status | Evidence |
|-------|--------|----------|
| `mujoco_bridge` ↔ `robot_bridge` ↔ `motor_compiler` 3-process boot | 🟧 Tested in sim | [tools/scenario_full_chain.py](tools/scenario_full_chain.py) — 3/3 PASS, peak_dev=0.18–0.29 rad, 0 safety events |
| `TrustLayerBridgeAdapter.read_state` ↔ `joint_names` mapping | 🟦 Implemented | Fixed 2026-04-30 (commit `8a9db9b`) — bridge ships `joint_names`, adapter remaps by name |
| `joint_velocity` per-tick HTTP wire | 🟦 Implemented | 50 Hz pacing in [services/motor_compiler/main.py](services/motor_compiler/main.py) `_run()` |
| Run-start re-centering of oscillator/CPG goal | 🟦 Implemented | Same commit; without it `posture: home` resolved to q=0, MPC drove humanoid against CBF |
| Same chain on a **manipulator** (Franka/UR/Kinova) in MuJoCo | ⬜ Missing | Only exercised on G1 and Anymal so far; no manipulator MJCF wired |

**Action:** wire MJCF for Franka into `mujoco_bridge` (or run a separate mujoco_bridge instance on a side port) so the chain can be evaluated on a 7-DOF arm.

---

## 3. Body Atlas Builder

| Item | Status | Code |
|------|--------|------|
| URDF parser | 🟦 Implemented | `libs/motor_compiler/atlas/urdf_parser.py` |
| Pinocchio handle attached to atlas | 🟦 Implemented | `libs/motor_compiler/atlas/builder.py` exposes `pinocchio_handle = (model, data, perm)` in `atlas.metadata` |
| Gravity Hessian → spectral modes | 🟦 Implemented | `libs/motor_compiler/atlas/dynamics.py` |
| Self-collision (BBox-from-inertia) | 🟦 Implemented | `libs/motor_compiler/atlas/self_collision.py:20-35` (FCL backend, conservative) |
| Self-collision (URDF mesh load via assimp) | ⬜ Missing | Plan §3.2.7 — assimp is in deps but mesh path not wired |
| MeshCat / RViz visual demo of modes | ⬜ Missing | No `mvp1_atlas_demo.py`-style script; ASCII frames in `vlm_label.py` are for the VLM labeller, not for humans |
| Semantic mode labelling | 🟦 Implemented | `libs/motor_compiler/atlas/labeller.py` |

**Action:** add `tools/mvp1_atlas_demo.py` that builds atlas + renders the
top-6 modes as PNG snapshots through MeshCat headless or matplotlib +
forward-kinematics frames, plus a `report.md` per robot.

---

## 4. Body Calibrator

| Item | Status | Code |
|------|--------|------|
| Information-driven babbling (empowerment) | 🟦 Implemented | `libs/motor_compiler/calibrator/runner.py`, `domain_randomization.py` |
| EDMD fit, K & B matrices | 🟦 Implemented | `libs/motor_compiler/calibrator/edmd.py` |
| One-step RMSE on training set | 🟦 Implemented | `runner.py:111` — `model.one_step_rmse` |
| Spectral radius ρ(K) reported | 🟦 Implemented | `runner.py:165` — saved into quality_report |
| Persistent excitation rank | 🟦 Implemented | quality_report field |
| Multi-horizon prediction error (1-step / 0.1s / 0.3s / 0.5s / 1.0s) on **held-out** | ⬜ Missing | `_validate_one_step` is computed internally but never split + saved |
| `prediction_error_vs_horizon.png` artefact | ⬜ Missing | No plotting code |
| `koopman_spectrum.png`, `babbling_state_coverage.png` | ⬜ Missing | — |
| Run on a **manipulator** in MuJoCo end-to-end | ⬜ Missing | Currently only exercised on humanoid + NullAdapter |

**Bible §6: "95% prediction accuracy at 0.5s horizon".** This is a
theoretical target, not a measured number. MVP-2 must measure honestly
and update the bible / pitch with whatever falls out (could be 80%, could be
50% on first pass — the point is the number is real).

**Action:** add `tools/mvp2_calibrate_franka.py` that does babble → split →
fit → predict → plot.

---

## 5. Skill Compiler

| Item | Status | Code |
|------|--------|------|
| DSL parser (schema + dataclass) | 🟦 Implemented | `libs/motor_compiler/dsl/schema.py` |
| Mode resolver (semantic alias → atlas mode) | 🟦 Implemented | `libs/motor_compiler/compiler/mode_resolver.py` |
| Lifted MPC (K, B, Q, R, horizon, u_min/max) | 🟦 Implemented | `libs/motor_compiler/compiler/mpc.py` |
| CBF QP barrier filter | 🟦 Implemented | `libs/motor_compiler/compiler/cbf.py` (joint-limit + velocity-cap; adaptive margin for narrow joints fixed 2026-04-30) |
| CPG (Matsuoka cells + symmetric/antiphase/ring coupling) | 🟦 Implemented | `libs/motor_compiler/compiler/cpg.py` |
| Periodic oscillator (sin Σ Aₖ φₖ) | 🟦 Implemented | `compile.py:_update_periodic_goal` |
| Reflex layer (overload, near_limit, on_slip, on_unexpected_contact) | 🟦 Implemented | `compile.py:944-960`, `reflex.py` |
| Switched Koopman per contact regime | 🟦 Implemented | `compiler/switched_koopman.py` |
| Online residual K-adapter | 🟦 Implemented | `compiler/online_adapt.py`, gated by DSL `online_adapt: true` |
| End-effector IK (LM via Pinocchio) | 🟦 Implemented | `atlas/ik.py` (tol_pos=5 mm, tol_rot=0.5°) |
| Compound skill composer (sequence + preconditions/postconditions) | 🟦 Implemented | `compiler/compound.py:76-128` |
| Stability gate (ρ(K) ≤ 1) | 🟧 Soft only | `compile.py:289-298` warns; **no strict mode, no auto-stabilize** |
| `reach_to_point` end-to-end on a manipulator | ⬜ Missing | DSL exists, IK works, but never executed against MJCF Franka/UR/Kinova |

---

## 6. DSL field honesty

Verified line-by-line against `libs/motor_compiler/`:

| DSL field | Schema accepts | Runtime reads | Status |
|-----------|----------------|---------------|--------|
| `goal.approach_direction` | ✓ schema.py:27 | ✓ compile.py:482 (rotation seed for IK) | 🟦 Implemented |
| `goal.release_condition` | ✓ schema.py:28 | ✗ no reference in compile.py | ⚠️ **Parsed but ignored** |
| `reflexes.on_slip` | ✓ via generic reflex map | ✓ compile.py:944 (proxy: scale grip authority) | 🟦 Implemented |
| `reflexes.on_unexpected_contact` | ✓ | ✓ compile.py:953 (stop-and-assess) | 🟦 Implemented |
| `composition.preconditions` | ✓ schema.py:86 | ✓ compound.py:76 (`evaluate(...)` at first step) | 🟦 Implemented |
| `composition.postconditions` | ✓ schema.py:88 | ✓ compound.py:123 | 🟦 Implemented |

Earlier audits flagged `preconditions/postconditions` as parsed-but-ignored
— that is **wrong**. They are wired and evaluated. The genuinely orphaned
field is `release_condition`.

**Action:** decide — implement minimal release-condition semantics (e.g.,
`gripper_force_below_threshold`), or document it explicitly as
"future-work" with the warn-on-compile path from §7 below.

---

## 7. Stability gate (ρ(K) ≤ 1)

| Mode | Status |
|------|--------|
| Compute ρ(K) at compile time | 🟦 [compile.py:289](libs/motor_compiler/compiler/compile.py#L289) |
| Warn if ρ > 1.001 | 🟦 [compile.py:290-296](libs/motor_compiler/compiler/compile.py#L290-L296) |
| Strict mode (raise `UnstableKoopmanError`) | ⬜ Missing |
| Auto-stabilize (project K to stable manifold) | ⬜ Missing |
| `spectral_radius` field exposed in compile result for clients | 🟧 Wired only inside calibrator's quality_report; not on `CompiledSkill.metadata` |
| Unit test on synthetic unstable K | ⬜ Missing |

**Action:** §8 of the prompt — add `MC_STRICT_STABILITY=1` env / `--strict`
flag, raise on violation; expose `spectral_radius` on `CompiledSkill.metadata`;
add `tests/test_stability_gate.py`.

---

## 8. Coriolis / computed-torque consistency

The plan has two passages that read like a contradiction. They are not.

- **Plan §A** ("dynamics") says: `pin.computeCoriolisMatrix` is reachable
  through `pinocchio_handle` but is **not cached** on `DynamicsResult`.
  This is correct — C(q, q̇) is bilinear in q̇ and meaningless to store at
  q̇ = 0. Compiler does not call it because the default lifted-MPC path is
  velocity-controlled and absorbs Coriolis into the residual.
- **Plan §H** ("computed torque") says: `pin.rnea` computes
  τ = M·q̈* + C·q̇* + g live, per-tick, inside
  [libs/motor_compiler/compiler/torque.py](libs/motor_compiler/compiler/torque.py).
  This module is opt-in via the DSL — it is not on the default code path
  but it does exist and runs.

**Action:** §9.2 of the prompt — clarify the plan in two places:

> Coriolis exposed via `atlas.metadata['pinocchio_handle']`, recomputed
> live inside RNEA (`compiler/torque.py`). Not cached on `DynamicsResult`
> by design — bilinear in q̇.

Then close the corresponding plan checkbox with that wording rather than
an unqualified "[x]".

---

## 9. CPG quadruped trot

| Item | Status |
|------|--------|
| `skills/trot.yaml` DSL | 🟦 [skills/trot.yaml](skills/trot.yaml) |
| Matsuoka CPG with antiphase coupling | 🟦 `compiler/cpg.py` |
| Mode aliases `front_pair`, `hind_pair` | 🟨 `mode_resolver.py` has the alias entries |
| Modes actually resolve on Anymal/Go2 atlas | ⚠️ Mode resolver logs warnings: `mode label 'front_pair' had no match in atlas — skipping`; quadruped's eigenmodes from gravity-Hessian don't naturally split into FL/RR diagonal pairs |
| End-to-end trot in MuJoCo | ⬜ Missing |

**Status quo:** CPG infrastructure is real and would work given a mode
basis that matches the gait. The natural spectral basis from a static
gravity Hessian does **not** give trot-specific modes — it gives whole-body
rocking modes. To make trot work the DSL needs explicit
`leg_FL`, `leg_FR`, `leg_RL`, `leg_RR` aliases (kinematic, not spectral)
and the resolver needs to know how to construct a coupling matrix from
those. Out of scope for this MVP cycle.

**Action:** flag `trot` as "infrastructure ready, basis mismatch — see
gap report §9" and exclude from any commercial claim.

---

## 10. Documentation / outreach pieces

| Item | Status |
|------|--------|
| `partenit_body_atlas` standalone SDK directory | 🟦 `packages/partenit_body_atlas/` exists with own `pyproject.toml`, Apache-2.0 |
| arXiv preprint draft | ⬜ Missing |
| Public GitHub for the SDK | ⬜ Missing |
| Phase 5 sim demo matrix (Franka/G1/quadruped) | 🟧 Anymal/Barkour/Go2 demo grids exist under `docs/demos/motor_compiler/`, but they are pose snapshots, not validated reach metrics |
| Phase 6 live demos | ⬜ Missing (no live hardware run) |

---

## 11. What to do next, in priority order

This list is intentionally narrower than the full bible. It targets the
gap between "math written" and "product claim demonstrable":

1. **UR5e URDF** — vendor it.
2. **Stability gate strict mode** + unit test — 30 lines of code, removes a class of silent failure.
3. **DSL honesty** — warn-on-compile for the orphaned `release_condition` and any other parsed-but-ignored fields, plus `MC_STRICT_DSL` env / flag.
4. **MVP-1 atlas demo** — `tools/mvp1_atlas_demo.py` that produces a `report.md` + per-mode PNGs for Franka/UR5e/Kinova. No MeshCat headless required if matplotlib FK plots are enough — the goal is "show the modes are real and labeled", not photorealism.
5. **MVP-2 calibrator metrics** — split + held-out + PNGs for one robot (Franka). 5–15 min babble in MuJoCo, three plots, one JSON. Use the actual measured numbers in the next pitch revision.
6. **MVP-3 reach matrix** — same `reach_to_point.yaml` on Franka, UR5e, Kinova. Three success rates, three EE errors, one shared YAML SHA.
7. **E2E scenarios 1–8** — extend `tools/scenario_full_chain.py` (already runs the 3-service stack) with a manipulator config + one HTML report covering smoke, pass-through, regulator, babbling, skill exec, cross-robot, long-run, failure recovery.
8. **PLAN.md cleanup** — replace ambiguous `[x]` with the four-level legend; add the truth table from §10 of the prompt.

Items 1–4 + 7 (smoke/pass-through) are achievable without 15-minute babble
runs and without UR5e physics. Items 5–6 require a working manipulator MJCF
in `mujoco_bridge` and 30+ minutes of wall clock per robot.

---

## 12. What this report deliberately does not promise

- "95% prediction accuracy at 0.5s" — bible claim, not yet measured.
- "Same DSL works across manipulators" — the math allows it, the chain runs G1, but Franka/UR/Kinova have not been driven end-to-end yet.
- "Trot works on quadruped" — CPG works, mode basis does not match.
- "Mesh self-collision in production" — BBox only, FCL infra ready.
