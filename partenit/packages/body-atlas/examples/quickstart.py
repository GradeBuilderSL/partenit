"""partenit-body-atlas quickstart — three lines to a body passport."""
from partenit_body_atlas import build_atlas

atlas = build_atlas("../../vendor/franka_panda/urdf/panda.urdf",
                     robot_id="panda")

print(f"{atlas.robot_id}: {atlas.embodiment_class}, n_dof={atlas.n_dof}")
print(f"backend: {atlas.metadata.get('dynamics_backend')}")
print(f"morphology: {[round(x, 2) for x in atlas.morphology_descriptor]}")
print()
print("Leading 5 spectral modes:")
for i, m in enumerate(atlas.modes[:5]):
    lbl = m.get("label") or {}
    print(f"  {i}: λ={m['eigenvalue']:.4f}  "
          f"region={lbl.get('region')}  "
          f"structure={lbl.get('structure')}")
