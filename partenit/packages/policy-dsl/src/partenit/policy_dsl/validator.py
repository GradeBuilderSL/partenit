"""
PolicyValidator — validates rule YAML before parsing.

Checks schema correctness, required fields, type safety, and uniqueness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ValidationError(Exception):
    """Raised when policy validation fails."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


_VALID_PRIORITIES = {"safety_critical", "legal", "task", "efficiency"}
_VALID_CONDITION_TYPES = {"threshold", "compound"}
_VALID_OPERATORS = {
    "less_than",
    "greater_than",
    "equals",
    "not_equals",
    "less_equal",
    "greater_equal",
    "in_set",
    "not_in_set",
}
_VALID_ACTION_TYPES = {"clamp", "block", "rewrite"}


class PolicyValidator:
    """
    Validates policy YAML data.

    Raises ValidationError on schema errors.
    Returns list of warning strings for non-fatal issues.
    """

    def validate_file(self, path: str | Path) -> list[str]:
        """Validate a YAML file. Returns warnings list. Raises ValidationError on errors."""
        path = Path(path)
        if not path.exists():
            raise ValidationError([f"File not found: {path}"])
        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValidationError([f"YAML parse error in {path}: {e}"]) from e
        return self.validate_raw(raw, source=str(path))

    def validate_dir(self, directory: str | Path) -> list[str]:
        """Validate all YAML files in directory. Returns all warnings."""
        directory = Path(directory)
        if not directory.is_dir():
            raise ValidationError([f"Not a directory: {directory}"])
        warnings: list[str] = []
        seen_ids: set[str] = set()
        for path in sorted(directory.glob("**/*.yaml")) + sorted(directory.glob("**/*.yml")):
            w = self.validate_file(path)
            warnings.extend(w)
            # Collect rule_ids for uniqueness check across files
            try:
                with open(path, encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                rules = self._normalize_rules(raw)
                for r in rules:
                    rid = r.get("rule_id", "")
                    if rid in seen_ids:
                        warnings.append(f"Duplicate rule_id '{rid}' found in {path}")
                    else:
                        seen_ids.add(rid)
            except Exception:
                pass
        return warnings

    def validate_raw(self, raw: Any, source: str = "<string>") -> list[str]:
        """Validate raw YAML data. Returns warnings. Raises on errors."""
        errors: list[str] = []
        warnings: list[str] = []
        rules = self._normalize_rules(raw)
        seen_ids: set[str] = set()

        for i, rule in enumerate(rules):
            rule_id = rule.get("rule_id", f"index-{i}")
            prefix = f"Rule '{rule_id}'"

            # Required fields
            if "rule_id" not in rule:
                errors.append(f"{prefix}: missing 'rule_id'")
            if "condition" not in rule:
                errors.append(f"{prefix}: missing 'condition'")
            if "action" not in rule:
                errors.append(f"{prefix}: missing 'action'")
            if "priority" not in rule:
                warnings.append(f"{prefix}: no 'priority' specified, will default to 'task'")

            # Priority validation
            priority = rule.get("priority", "task")
            if priority not in _VALID_PRIORITIES:
                errors.append(
                    f"{prefix}: invalid priority '{priority}'. "
                    f"Must be one of: {sorted(_VALID_PRIORITIES)}"
                )

            # Uniqueness
            if rule_id in seen_ids:
                errors.append(f"{prefix}: duplicate rule_id '{rule_id}'")
            else:
                seen_ids.add(rule_id)

            # Condition validation
            cond = rule.get("condition", {})
            errors.extend(self._validate_condition(cond, f"{prefix}.condition"))

            # Action validation
            action = rule.get("action", {})
            errors.extend(self._validate_action(action, f"{prefix}.action"))

        if errors:
            raise ValidationError(errors)
        return warnings

    def _normalize_rules(self, raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            if "rules" in raw:
                return raw["rules"] if isinstance(raw["rules"], list) else []
            # Treat as a single rule dict (even if rule_id is missing — validator will catch it)
            return [raw]
        if isinstance(raw, list):
            return raw
        return []

    def _validate_condition(self, cond: Any, path: str) -> list[str]:
        errors: list[str] = []
        if not isinstance(cond, dict):
            return [f"{path}: must be a dict"]

        ctype = cond.get("type", "threshold")
        if ctype not in _VALID_CONDITION_TYPES:
            errors.append(
                f"{path}: invalid type '{ctype}'. Must be one of: {sorted(_VALID_CONDITION_TYPES)}"
            )

        if ctype == "threshold":
            if "metric" not in cond:
                errors.append(f"{path}: threshold condition missing 'metric'")
            operator = cond.get("operator")
            if operator and operator not in _VALID_OPERATORS:
                errors.append(
                    f"{path}: invalid operator '{operator}'. "
                    f"Must be one of: {sorted(_VALID_OPERATORS)}"
                )
            if "value" not in cond:
                errors.append(f"{path}: threshold condition missing 'value'")

        if ctype == "compound":
            sub = cond.get("conditions", [])
            if not isinstance(sub, list) or len(sub) < 2:
                errors.append(f"{path}: compound condition needs at least 2 sub-conditions")
            for i, sc in enumerate(sub):
                errors.extend(self._validate_condition(sc, f"{path}.conditions[{i}]"))

        return errors

    def _validate_action(self, action: Any, path: str) -> list[str]:
        errors: list[str] = []
        if not isinstance(action, dict):
            return [f"{path}: must be a dict"]
        atype = action.get("type")
        if not atype:
            errors.append(f"{path}: missing 'type'")
        elif atype not in _VALID_ACTION_TYPES:
            errors.append(
                f"{path}: invalid type '{atype}'. Must be one of: {sorted(_VALID_ACTION_TYPES)}"
            )
        if atype in ("clamp", "rewrite") and "parameter" not in action:
            errors.append(f"{path}: '{atype}' action missing 'parameter'")
        if atype in ("clamp", "rewrite") and "value" not in action:
            errors.append(f"{path}: '{atype}' action missing 'value'")
        return errors
