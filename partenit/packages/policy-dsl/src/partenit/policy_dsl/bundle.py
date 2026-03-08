"""
PolicyBundleBuilder — assembles a PolicyBundle from rules.

Produces a versioned, hash-signed bundle ready for use in agent-guard.
"""

from __future__ import annotations

import json
from pathlib import Path

from partenit.core.models import PolicyBundle, PolicyRule
from partenit.policy_dsl.parser import PolicyParser
from partenit.policy_dsl.validator import PolicyValidator


class PolicyBundleBuilder:
    """
    Builds a PolicyBundle from YAML files or pre-parsed rules.

    Usage:
        builder = PolicyBundleBuilder()
        bundle = builder.from_dir("./policies/", version="1.0.0")
        builder.export(bundle, "bundle.json")
    """

    def __init__(self) -> None:
        self._parser = PolicyParser()
        self._validator = PolicyValidator()

    def from_dir(
        self,
        directory: str | Path,
        version: str = "0.1.0",
        validate: bool = True,
    ) -> PolicyBundle:
        """Load, validate, and bundle all rules from a directory."""
        if validate:
            self._validator.validate_dir(directory)
        rules = self._parser.load_dir(directory)
        return self._build(rules, version)

    def from_file(
        self,
        path: str | Path,
        version: str = "0.1.0",
        validate: bool = True,
    ) -> PolicyBundle:
        """Load, validate, and bundle rules from a single file."""
        if validate:
            self._validator.validate_file(path)
        rules = self._parser.load_file(path)
        return self._build(rules, version)

    def from_rules(
        self,
        rules: list[PolicyRule],
        version: str = "0.1.0",
    ) -> PolicyBundle:
        """Build a bundle from already-parsed rules."""
        return self._build(rules, version)

    def export(self, bundle: PolicyBundle, path: str | Path) -> None:
        """Write bundle to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = bundle.model_dump(mode="json")
        path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> PolicyBundle:
        """Load a bundle from a previously exported JSON file."""
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return PolicyBundle.model_validate(data)

    def _build(self, rules: list[PolicyRule], version: str) -> PolicyBundle:
        return PolicyBundle(rules=rules, version=version)
