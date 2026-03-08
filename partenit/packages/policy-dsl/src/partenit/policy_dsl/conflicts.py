"""
ConflictDetector — finds overlapping rules with conflicting actions.

Priority resolution: safety_critical > legal > task > efficiency.
Higher priority always wins — deterministic and logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from partenit.core.models import PolicyRule


@dataclass
class PolicyConflict:
    """A detected conflict between two rules."""

    rule_a: PolicyRule
    rule_b: PolicyRule
    reason: str
    winner: PolicyRule = field(init=False)

    def __post_init__(self) -> None:
        # Higher numeric priority wins
        if self.rule_a.priority.numeric >= self.rule_b.priority.numeric:
            self.winner = self.rule_a
        else:
            self.winner = self.rule_b

    def describe(self) -> str:
        loser = self.rule_b if self.winner is self.rule_a else self.rule_a
        return (
            f"CONFLICT: '{self.rule_a.rule_id}' ({self.rule_a.priority.value}) "
            f"vs '{self.rule_b.rule_id}' ({self.rule_b.priority.value})\n"
            f"  Reason:  {self.reason}\n"
            f"  Winner:  '{self.winner.rule_id}' (priority {self.winner.priority.numeric})\n"
            f"  Loser:   '{loser.rule_id}'"
        )


class ConflictDetector:
    """
    Detects rules with overlapping conditions and conflicting actions.

    Two rules conflict when:
    - They share the same metric in their condition
    - Their actions produce different (incompatible) effects on the same parameter

    In such cases, the higher-priority rule wins deterministically.
    """

    def detect(self, rules: list[PolicyRule]) -> list[PolicyConflict]:
        """Return all conflicts found among the provided rules."""
        conflicts: list[PolicyConflict] = []
        enabled = [r for r in rules if r.enabled]

        for i, rule_a in enumerate(enabled):
            for rule_b in enabled[i + 1 :]:
                conflict = self._check_pair(rule_a, rule_b)
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    def _check_pair(self, rule_a: PolicyRule, rule_b: PolicyRule) -> PolicyConflict | None:
        """Check a pair of rules for conflict."""
        # Both rules fire on the same metric
        metric_a = rule_a.condition.metric
        metric_b = rule_b.condition.metric
        if not metric_a or not metric_b or metric_a != metric_b:
            return None

        # Both actions affect the same parameter
        param_a = rule_a.action.parameter
        param_b = rule_b.action.parameter
        if param_a and param_b and param_a == param_b:
            # Both clamp/rewrite same parameter to different values
            if rule_a.action.type in ("clamp", "rewrite") and rule_b.action.type in (
                "clamp",
                "rewrite",
            ):
                if rule_a.action.value != rule_b.action.value:
                    return PolicyConflict(
                        rule_a=rule_a,
                        rule_b=rule_b,
                        reason=(
                            f"Both rules clamp '{param_a}' on metric '{metric_a}' "
                            f"but to different values: "
                            f"{rule_a.action.value} vs {rule_b.action.value}"
                        ),
                    )

        # One blocks, the other allows/modifies (by same metric)
        types = {rule_a.action.type, rule_b.action.type}
        if "block" in types and len(types) > 1:
            return PolicyConflict(
                rule_a=rule_a,
                rule_b=rule_b,
                reason=(
                    f"Conflicting actions on metric '{metric_a}': one blocks, the other modifies"
                ),
            )

        return None
