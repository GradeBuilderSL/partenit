"""
PolicyEvaluator — evaluates which rules fire for a given context.

Reuses condition evaluation logic from _old/_ontorobotic/rules_dsl.py,
adapted for the Partenit PolicyCondition schema.

Context is a flat or nested dict with dot-notation access.
Example: {"human": {"distance": 1.2}, "robot": {"speed": 1.5}}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from partenit.core.models import PolicyCondition, PolicyRule


def _get_value(context: dict[str, Any], path: str) -> Any:
    """
    Retrieve a value from a nested dict using dot-notation.
    E.g. 'human.distance' → context['human']['distance']
    """
    parts = path.split(".")
    value: Any = context
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        elif hasattr(value, part):
            value = getattr(value, part)
        else:
            return None
        if value is None:
            return None
    return value


def _evaluate_condition(condition: PolicyCondition, context: dict[str, Any]) -> bool:
    """Recursively evaluate a PolicyCondition against context."""
    if condition.type == "compound":
        if not condition.conditions:
            return False
        results = [_evaluate_condition(c, context) for c in condition.conditions]
        logic = condition.logic or "and"
        if logic == "and":
            return all(results)
        if logic == "or":
            return any(results)
        return False

    # Threshold condition
    if not condition.metric or not condition.operator:
        return False

    actual = _get_value(context, condition.metric)
    if actual is None:
        return False

    threshold = condition.value
    op = condition.operator

    try:
        if op == "less_than":
            return float(actual) < float(threshold)
        if op == "greater_than":
            return float(actual) > float(threshold)
        if op == "equals":
            return actual == threshold
        if op == "not_equals":
            return actual != threshold
        if op == "less_equal":
            return float(actual) <= float(threshold)
        if op == "greater_equal":
            return float(actual) >= float(threshold)
        if op == "in_set":
            return actual in threshold
        if op == "not_in_set":
            return actual not in threshold
    except (TypeError, ValueError):
        return False

    return False


@dataclass
class EvaluationResult:
    """Result of evaluating all rules against a context."""

    fired_rules: list[PolicyRule] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def has_violations(self) -> bool:
        """True if any blocking rule fired."""
        return any(r.action.type == "block" for r in self.fired_rules)

    @property
    def applied_policy_ids(self) -> list[str]:
        return [r.rule_id for r in self.fired_rules]

    def get_clamps(self) -> dict[str, Any]:
        """
        Return parameter → value for all clamp/rewrite actions,
        resolved by priority (highest wins).
        """
        clamps: dict[str, tuple[int, Any]] = {}
        for rule in sorted(self.fired_rules, key=lambda r: r.priority.numeric, reverse=True):
            if rule.action.type in ("clamp", "rewrite") and rule.action.parameter:
                param = rule.action.parameter
                priority = rule.priority.numeric
                if param not in clamps or priority > clamps[param][0]:
                    clamps[param] = (priority, rule.action.value)
        return {k: v for k, (_, v) in clamps.items()}


class PolicyEvaluator:
    """
    Evaluates a list of PolicyRules against an observation context.

    Rules are sorted by priority before evaluation so that higher-priority
    rules are processed first and their effects take precedence.
    """

    def evaluate(
        self,
        rules: list[PolicyRule],
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        Evaluate all enabled rules against context.

        Args:
            rules: List of PolicyRule objects (from a PolicyBundle)
            context: Dict representing the current world state.
                     Supports dot-notation keys e.g. {'human': {'distance': 1.2}}

        Returns:
            EvaluationResult with fired rules and resolved clamps
        """
        enabled_sorted = sorted(
            [r for r in rules if r.enabled],
            key=lambda r: r.priority.numeric,
            reverse=True,
        )
        fired: list[PolicyRule] = []
        for rule in enabled_sorted:
            if _evaluate_condition(rule.condition, context):
                fired.append(rule)

        return EvaluationResult(fired_rules=fired, context=context)
