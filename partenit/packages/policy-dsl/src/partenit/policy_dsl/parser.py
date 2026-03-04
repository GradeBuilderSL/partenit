"""
PolicyParser — loads PolicyRule objects from YAML files or strings.

Reuses the condition parsing architecture from _old/_ontorobotic/rules_dsl.py,
adapted to the Partenit YAML DSL format defined in CLAUDE.md.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Union

import yaml

from partenit.core.models import (
    PolicyAction,
    PolicyCondition,
    PolicyPriority,
    PolicyRelease,
    PolicyRule,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Condition parsing
# ---------------------------------------------------------------------------


def _parse_condition(data: dict[str, Any]) -> PolicyCondition:
    """Parse a condition block from YAML data."""
    ctype = data.get("type", "threshold")

    if ctype == "compound":
        logic = data.get("logic", "and")
        raw_conditions = data.get("conditions", [])
        sub = [_parse_condition(c) for c in raw_conditions]
        return PolicyCondition(type="compound", logic=logic, conditions=sub)

    # Simple threshold condition
    return PolicyCondition(
        type="threshold",
        metric=data.get("metric"),
        operator=data.get("operator"),
        value=data.get("value"),
        unit=data.get("unit"),
    )


def _parse_action(data: dict[str, Any]) -> PolicyAction:
    """Parse an action block from YAML data."""
    return PolicyAction(
        type=data.get("type", "block"),
        parameter=data.get("parameter"),
        value=data.get("value"),
        unit=data.get("unit"),
    )


def _parse_release(data: dict[str, Any] | None) -> PolicyRelease | None:
    """Parse an optional release block from YAML data."""
    if data is None:
        return None
    rtype = data.get("type", "threshold")
    conditions: list[PolicyCondition] = []
    for c in data.get("conditions", []):
        # Release conditions may be flat dicts — treat as threshold
        conditions.append(
            PolicyCondition(
                type="threshold",
                metric=c.get("metric"),
                operator=c.get("operator"),
                value=c.get("value"),
                unit=c.get("unit"),
            )
        )
    elapsed = data.get("elapsed_seconds")
    return PolicyRelease(type=rtype, conditions=conditions, elapsed_seconds=elapsed)


def _parse_priority(raw: str) -> PolicyPriority:
    try:
        return PolicyPriority(raw)
    except ValueError:
        logger.warning("Unknown priority '%s', defaulting to 'task'", raw)
        return PolicyPriority.TASK


def _parse_rule(data: dict[str, Any]) -> PolicyRule:
    """Parse a single rule dict into a PolicyRule."""
    condition_data = data.get("condition", {})
    action_data = data.get("action", {})
    release_data = data.get("release")

    return PolicyRule(
        rule_id=data["rule_id"],
        name=data.get("name", data["rule_id"]),
        priority=_parse_priority(data.get("priority", "task")),
        condition=_parse_condition(condition_data),
        action=_parse_action(action_data),
        release=_parse_release(release_data),
        provenance=data.get("provenance", ""),
        enabled=data.get("enabled", True),
        tags=data.get("tags", []),
    )


# ---------------------------------------------------------------------------
# PolicyParser
# ---------------------------------------------------------------------------


class PolicyParser:
    """
    Load PolicyRule objects from YAML files or directory.

    Can parse:
    - A single rule file with one rule at top level
    - A file with a list of rules under a 'rules:' key
    - A directory of .yaml / .yml files
    """

    def load_file(self, path: Union[str, Path]) -> list[PolicyRule]:
        """Load rules from a single YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Policy file not found: {path}")
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return self._parse_raw(raw, source=str(path))

    def load_dir(self, directory: Union[str, Path]) -> list[PolicyRule]:
        """Load all .yaml / .yml rules from a directory."""
        directory = Path(directory)
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")
        rules: list[PolicyRule] = []
        for path in sorted(directory.glob("**/*.yaml")) + sorted(directory.glob("**/*.yml")):
            rules.extend(self.load_file(path))
        return rules

    def parse(self, yaml_str: str) -> list[PolicyRule]:
        """Parse rules from a YAML string."""
        raw = yaml.safe_load(yaml_str)
        return self._parse_raw(raw, source="<string>")

    def _parse_raw(self, raw: Any, source: str) -> list[PolicyRule]:
        """Normalize raw YAML into a list of rule dicts and parse each."""
        if raw is None:
            return []
        if isinstance(raw, dict):
            # Either a single rule or a dict with a 'rules' list
            if "rules" in raw:
                items = raw["rules"]
            elif "rule_id" in raw:
                items = [raw]
            else:
                logger.warning("Unexpected YAML structure in %s", source)
                return []
        elif isinstance(raw, list):
            items = raw
        else:
            logger.warning("Cannot parse YAML content from %s", source)
            return []

        rules: list[PolicyRule] = []
        for i, item in enumerate(items):
            try:
                rules.append(_parse_rule(item))
            except (KeyError, TypeError, ValueError) as exc:
                rule_id = item.get("rule_id", f"index-{i}") if isinstance(item, dict) else f"index-{i}"
                logger.error("Failed to parse rule '%s' from %s: %s", rule_id, source, exc)
        return rules
