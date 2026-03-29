"""
ACI :: Quality Contract
========================
Defines and parses quality rules from YAML contract files.
The contract is the "law" — the scoring function for code quality.

Supports both built-in rules and custom project-specific rules.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


@dataclass
class CustomPattern:
    """A custom regex-based anti-pattern rule."""
    pattern: str
    message: str
    severity: str = "warning"


@dataclass
class LayerRule:
    """Layer hierarchy rule for architectural validation."""
    layers: Dict[str, List[str]]  # layer_name → path prefixes
    direction: str = "up"  # "up" = higher layers can import lower


@dataclass
class QualityContract:
    """The quality contract — all rules in one place."""
    # Structural limits
    max_loc_per_class: int = 300
    max_loc_per_file: int = 500
    max_function_args: int = 6

    # Required patterns
    require_docstrings: bool = True
    require_type_hints: bool = False
    require_test_file: bool = True
    require_logger: bool = True
    require_config_dataclass: bool = False

    # Forbidden patterns
    forbid_bare_except: bool = True
    forbid_print_statements: bool = True
    forbid_magic_numbers: bool = True
    forbid_fstring_logs: bool = False

    # Architecture
    layer_rule: Optional[LayerRule] = None

    # Custom patterns
    custom_patterns: List[CustomPattern] = field(default_factory=list)

    # Metadata
    name: str = "default"
    version: str = "1.0"

    def active_checks(self) -> List[str]:
        """List all enabled check names."""
        checks = []
        if self.max_loc_per_class > 0:
            checks.append("max_loc_per_class")
        if self.max_loc_per_file > 0:
            checks.append("max_loc_per_file")
        if self.require_docstrings:
            checks.append("require_docstrings")
        if self.require_type_hints:
            checks.append("require_type_hints")
        if self.require_test_file:
            checks.append("require_test_file")
        if self.require_logger:
            checks.append("require_logger")
        if self.require_config_dataclass:
            checks.append("require_config_dataclass")
        if self.forbid_bare_except:
            checks.append("forbid_bare_except")
        if self.forbid_print_statements:
            checks.append("forbid_print_statements")
        if self.forbid_magic_numbers:
            checks.append("forbid_magic_numbers")
        if self.forbid_fstring_logs:
            checks.append("forbid_fstring_logs")
        if self.layer_rule:
            checks.append("layer_rule")
        checks.extend(f"custom:{p.pattern[:30]}" for p in self.custom_patterns)
        return checks


class ContractLoader:
    """Loads quality contracts from YAML files."""

    def load(self, path: str) -> QualityContract:
        """Load contract from a YAML file.

        Args:
            path: Path to .aci/contract.yaml or similar.

        Returns:
            QualityContract with parsed rules.
        """
        p = Path(path)
        if not p.exists():
            logger.info("No contract file found at %s, using defaults", path)
            return QualityContract()

        if yaml is None:
            logger.warning("pyyaml not installed, using default contract")
            return QualityContract()

        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to parse contract %s: %s", path, e)
            return QualityContract()

        if not isinstance(raw, dict):
            return QualityContract()

        rules = raw.get("rules", raw)
        contract = QualityContract(name=raw.get("name", p.stem))

        # Simple fields
        for attr in [
            "max_loc_per_class", "max_loc_per_file", "max_function_args",
            "require_docstrings", "require_type_hints", "require_test_file",
            "require_logger", "require_config_dataclass",
            "forbid_bare_except", "forbid_print_statements",
            "forbid_magic_numbers", "forbid_fstring_logs",
        ]:
            if attr in rules:
                setattr(contract, attr, rules[attr])

        # Layer rule
        layers = rules.get("layers")
        if layers and isinstance(layers, dict):
            contract.layer_rule = LayerRule(
                layers=layers,
                direction=rules.get("layer_direction", "up"),
            )

        # Custom patterns
        customs = rules.get("custom", [])
        for item in customs:
            if isinstance(item, dict) and "pattern" in item:
                contract.custom_patterns.append(CustomPattern(
                    pattern=item["pattern"],
                    message=item.get("message", "Custom pattern violation"),
                    severity=item.get("severity", "warning"),
                ))

        logger.info(
            "Contract loaded")
        return contract

    def find_contract(self, project_root: str) -> QualityContract:
        """Auto-discover contract file in a project.

        Searches for: .aci/contract.yaml, .aci/contract.yml, aci.yaml
        """
        root = Path(project_root)
        candidates = [
            root / ".aci" / "contract.yaml",
            root / ".aci" / "contract.yml",
            root / "aci.yaml",
            root / ".aci.yaml",
        ]
        for c in candidates:
            if c.exists():
                return self.load(str(c))

        logger.info("No contract found, using defaults")
        return QualityContract()
