"""Partenit Body Atlas — freemium standalone build.

Bible §6.1 freemium product: «дай URDF — получи спектральный базис
и morphology descriptor». This package re-exports the relevant
public API of `motor_compiler.atlas` as a thin standalone surface
so users can `pip install partenit-body-atlas` without pulling
the rest of the trust-layer monorepo.

Public API:
    build_atlas(urdf_path, robot_id=None) → BodyAtlas
    BodyAtlas.modes, .mass_matrix, .stiffness_matrix,
        .morphology_descriptor, .safety_bounds, .contact_regimes
    BodyAtlas.to_serialisable() → dict (JSON-friendly)

Optional features (gated on extras):
    [pinocchio]: real M(q) via CRBA. Without it the spectral basis
        comes from a mass-weighted graph Laplacian — close enough
        for visualisation, not enough for control.
    [collision]: self-collision world via python-fcl.
    [viz]: animation rendering via matplotlib.
"""
from __future__ import annotations

__version__ = "0.1.0"

# Re-export from the in-monorepo motor_compiler library if it's on
# PYTHONPATH (developer install), else from this package's bundled
# copy (pip install).
try:
    from motor_compiler.atlas.builder import build_atlas, BodyAtlas
    from motor_compiler.atlas.urdf_parser import (
        parse_urdf, KinematicChain, Joint, Link, Inertia,
    )
    from motor_compiler.atlas.dynamics import compute_dynamics, SpectralMode
    from motor_compiler.atlas.contact import analyse_contacts, ContactAnalysis
    from motor_compiler.atlas.reachability import (
        forward_kinematics, reachability_cube,
    )
    from motor_compiler.atlas.labeller import label_mode, render_hint
    _SOURCE = "motor_compiler"
except ImportError:
    # Standalone mode would copy the relevant files into
    # partenit_body_atlas/_atlas. Out of scope for this commit;
    # developer-install path is the canonical one.
    raise

__all__ = [
    "build_atlas", "BodyAtlas",
    "parse_urdf", "KinematicChain", "Joint", "Link", "Inertia",
    "compute_dynamics", "SpectralMode",
    "analyse_contacts", "ContactAnalysis",
    "forward_kinematics", "reachability_cube",
    "label_mode", "render_hint",
]
