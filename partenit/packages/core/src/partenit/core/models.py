"""
partenit-core — canonical data contracts.

These types are the open standard for Partenit. They must not be redefined
in other packages. Import from here.

Breaking changes require a major version bump.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


class StructuredObservation(BaseModel):
    """
    Output of one sensor detection cycle for a single detected object.

    Produced by the perception-edge node and consumed by trust-engine
    and agent-guard.
    """

    object_id: str = Field(description="Stable identifier for this tracked object")
    class_best: str = Field(description="Most likely class label (e.g. 'human', 'forklift')")
    class_set: list[str] = Field(
        default_factory=list,
        description="Prediction set from conformal prediction (enterprise) or top-k classes",
    )
    position_3d: tuple[float, float, float] = Field(
        description="(x, y, z) in meters, robot-centric frame"
    )
    velocity: tuple[float, float, float] = Field(
        default=(0.0, 0.0, 0.0),
        description="(vx, vy, vz) in m/s",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence [0, 1]")
    depth_variance: float = Field(
        default=0.0, ge=0.0, description="Depth sensor noise indicator"
    )
    sensor_trust: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Trust level of the source sensor [0, 1]"
    )
    location_uncertain: bool = Field(
        default=False,
        description="True when confidence has decayed below 0.1 (object may have moved)",
    )
    treat_as_human: bool = Field(
        default=False,
        description="True when 'human' appears in class_set (conservative safety measure)",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    frame_hash: str | None = Field(
        default=None,
        description="SHA256 of the raw sensor frame for auditability",
    )
    source_id: str = Field(
        default="unknown",
        description="Sensor or camera identifier",
    )

    @model_validator(mode="after")
    def set_treat_as_human(self) -> "StructuredObservation":
        if "human" in self.class_set:
            object.__setattr__(self, "treat_as_human", True)
        return self

    def distance(self) -> float:
        """Euclidean distance from robot origin."""
        x, y, z = self.position_3d
        return (x**2 + y**2 + z**2) ** 0.5


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class PolicyPriority(str, Enum):
    """Safety rule priority levels (highest first)."""

    SAFETY_CRITICAL = "safety_critical"
    LEGAL = "legal"
    TASK = "task"
    EFFICIENCY = "efficiency"

    @property
    def numeric(self) -> int:
        return {
            PolicyPriority.SAFETY_CRITICAL: 1000,
            PolicyPriority.LEGAL: 500,
            PolicyPriority.TASK: 100,
            PolicyPriority.EFFICIENCY: 10,
        }[self]


class PolicyCondition(BaseModel):
    """
    A condition block from a PolicyRule.

    Supports 'threshold' (simple metric comparison) and
    'compound' (AND/OR of sub-conditions).
    """

    type: str = Field(description="'threshold' | 'compound'")
    metric: str | None = Field(
        default=None,
        description="Dot-path to metric in context (e.g. 'human.distance')",
    )
    operator: str | None = Field(
        default=None,
        description="'less_than' | 'greater_than' | 'equals' | 'in_set'",
    )
    value: Any = Field(default=None, description="Threshold value to compare against")
    unit: str | None = Field(default=None)
    logic: str | None = Field(
        default=None, description="'and' | 'or' for compound conditions"
    )
    conditions: list["PolicyCondition"] = Field(
        default_factory=list,
        description="Sub-conditions for compound type",
    )


class PolicyAction(BaseModel):
    """
    The enforcement action a policy rule applies when its condition fires.
    """

    type: str = Field(description="'clamp' | 'block' | 'rewrite'")
    parameter: str | None = Field(
        default=None,
        description="Action parameter to modify (e.g. 'max_velocity')",
    )
    value: Any = Field(default=None, description="New clamped / rewritten value")
    unit: str | None = Field(default=None)


class PolicyRelease(BaseModel):
    """
    Conditions under which the rule's action is lifted.
    """

    type: str = Field(description="'threshold' | 'compound' | 'timeout'")
    conditions: list[PolicyCondition] = Field(default_factory=list)
    elapsed_seconds: float | None = Field(
        default=None,
        description="Minimum time before release can trigger",
    )


class PolicyRule(BaseModel):
    """
    One safety rule. Written by safety engineers in YAML.

    Immutable once loaded — any modification requires a new rule_id.
    """

    rule_id: str
    name: str
    priority: PolicyPriority
    condition: PolicyCondition
    action: PolicyAction
    release: PolicyRelease | None = None
    provenance: str = Field(
        default="",
        description="Source standard or regulation (e.g. 'ISO 3691-4 section 5.2')",
    )
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class PolicyBundle(BaseModel):
    """
    A versioned, immutable collection of PolicyRules.

    The bundle_hash covers all rule content and is used for audit trails.
    """

    bundle_id: str = Field(default_factory=lambda: str(uuid4()))
    version: str = Field(default="0.1.0")
    rules: list[PolicyRule]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    bundle_hash: str = Field(default="")

    @model_validator(mode="after")
    def compute_hash(self) -> "PolicyBundle":
        if not self.bundle_hash:
            content = json.dumps(
                [r.model_dump(mode="json") for r in self.rules],
                sort_keys=True,
                default=str,
            )
            h = hashlib.sha256(content.encode()).hexdigest()
            object.__setattr__(self, "bundle_hash", h)
        return self


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


class RiskScore(BaseModel):
    """
    Composite risk score for a candidate action.

    value ∈ [0, 1].  1.0 = maximum risk.
    contributors maps feature name → weight used in scoring.
    """

    value: float = Field(ge=0.0, le=1.0)
    contributors: dict[str, float] = Field(
        default_factory=dict,
        description="Feature → contribution breakdown",
    )
    plan_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Guard Decision
# ---------------------------------------------------------------------------


class GuardDecision(BaseModel):
    """
    Result returned by AgentGuard for a single action request.

    allowed=True  → execute (possibly with modified_params)
    allowed=False → do not execute; see rejection_reason
    """

    allowed: bool
    modified_params: dict[str, Any] | None = Field(
        default=None,
        description="Rewritten params if guard clamped values (e.g. speed reduced)",
    )
    rejection_reason: str | None = None
    risk_score: RiskScore
    applied_policies: list[str] = Field(
        default_factory=list,
        description="rule_id list of all policies that fired",
    )
    suggested_alternative: dict[str, Any] | None = Field(
        default=None,
        description="Guard-proposed alternative action params",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float = Field(default=0.0)


# ---------------------------------------------------------------------------
# Trust
# ---------------------------------------------------------------------------


class TrustMode(str, Enum):
    """Sensor trust quality modes."""

    NOMINAL = "nominal"         # trust > 0.8
    DEGRADED = "degraded"       # 0.5 – 0.8
    UNRELIABLE = "unreliable"   # 0.2 – 0.5
    FAILED = "failed"           # < 0.2

    @classmethod
    def from_value(cls, trust: float) -> "TrustMode":
        if trust > 0.8:
            return cls.NOMINAL
        if trust > 0.5:
            return cls.DEGRADED
        if trust > 0.2:
            return cls.UNRELIABLE
        return cls.FAILED


class TrustState(BaseModel):
    """
    Current trust level of a single sensor.

    Produced by SensorTrustModel in partenit-trust-engine.
    """

    sensor_id: str
    trust_value: float = Field(ge=0.0, le=1.0)
    mode: TrustMode = TrustMode.NOMINAL
    degradation_reasons: list[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def set_mode(self) -> "TrustState":
        object.__setattr__(self, "mode", TrustMode.from_value(self.trust_value))
        return self


# ---------------------------------------------------------------------------
# Safety Event
# ---------------------------------------------------------------------------


class SafetyEventType(str, Enum):
    STOP = "stop"
    SLOWDOWN = "slowdown"
    VIOLATION = "violation"
    RULE_FIRED = "rule_fired"
    SENSOR_DEGRADED = "sensor_degraded"
    TRUST_FAILED = "trust_failed"
    POLICY_CONFLICT = "policy_conflict"
    LLM_BLOCKED = "llm_blocked"


class SafetyEvent(BaseModel):
    """
    A safety-relevant event emitted during a guard or edge decision.

    Always logged — even on safe stop.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: SafetyEventType
    triggered_by: str = Field(description="rule_id or sensor_id that caused this event")
    severity: float = Field(ge=0.0, le=1.0, default=0.5)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    context: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decision Packet (open standard)
# ---------------------------------------------------------------------------


class DecisionPacket(BaseModel):
    """
    Full audit record for one decision cycle.

    This is the Partenit open standard. Its JSON Schema is published at
    /schemas/DecisionPacket.schema.json. No breaking changes without major
    version bump.
    """

    packet_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Decision content
    mission_goal: str = Field(default="")
    action_requested: str
    action_params: dict[str, Any] = Field(default_factory=dict)
    guard_decision: GuardDecision

    # Audit refs
    observation_hashes: list[str] = Field(
        default_factory=list,
        description="SHA256 hashes of StructuredObservations used",
    )
    world_state_hash: str | None = None
    policy_bundle_version: str | None = None
    model_versions: dict[str, str] = Field(
        default_factory=dict,
        description="{'trust_engine': '0.1.0', ...}",
    )

    # Latency breakdown
    latency_ms: dict[str, float] = Field(
        default_factory=dict,
        description="{'policy_check': 2.1, 'risk_score': 0.8, 'total': 3.1}",
    )

    # Conflict resolution
    conflicts_resolved: list[dict[str, Any]] = Field(default_factory=list)
    violations_checked: list[str] = Field(
        default_factory=list,
        description="List of rule_ids evaluated",
    )

    # Fingerprint (filled by DecisionLogger)
    fingerprint: str = Field(default="")

    def compute_fingerprint(self) -> str:
        """Compute SHA256 fingerprint over all packet content except fingerprint itself."""
        data = self.model_dump(mode="json", exclude={"fingerprint"})
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()


class DecisionFingerprint(BaseModel):
    """
    Detached cryptographic fingerprint for a DecisionPacket.
    Can be stored separately and used to verify packet integrity.
    """

    fingerprint: str
    packet_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def verify(self, packet: DecisionPacket) -> bool:
        """Return True if the packet's computed fingerprint matches this record."""
        return packet.compute_fingerprint() == self.fingerprint
