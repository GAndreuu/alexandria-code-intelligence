"""
ACI :: Critic Agent
====================
Systematic quality auditor. Scores each module against the quality contract.
Produces a per-module scorecard with pass/fail/warning for each rule.

Inspired by: Alexandria's AutisticAgent (deep systematic analysis)
             + CriticalAgent (zero tolerance for violations).
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from aci.perception.ast_parser import ModuleInfo
from aci.contract.contract import QualityContract

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """Result of a single quality check."""
    name: str
    passed: bool
    severity: str = "error"  # error | warning | info
    message: str = ""
    details: Any = None


@dataclass
class Scorecard:
    """Complete audit scorecard for one module."""
    path: str
    checks: List[CheckResult]

    @property
    def score(self) -> int:
        """Number of checks passed."""
        return sum(1 for c in self.checks if c.passed)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def percentage(self) -> float:
        return (self.score / self.total * 100) if self.total > 0 else 0.0

    @property
    def grade(self) -> str:
        p = self.percentage
        if p >= 90:
            return "A"
        if p >= 75:
            return "B"
        if p >= 60:
            return "C"
        if p >= 40:
            return "D"
        return "F"

    @property
    def failures(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "score": f"{self.score}/{self.total}",
            "percentage": round(self.percentage, 1),
            "grade": self.grade,
            "checks": {
                c.name: {
                    "passed": c.passed,
                    "severity": c.severity,
                    "message": c.message,
                }
                for c in self.checks
            },
        }


class CriticAgent:
    """Scores modules against the quality contract."""

    def __init__(self, contract: QualityContract):
        self.contract = contract

    def audit(
        self,
        module: ModuleInfo,
        test_files: Optional[List[str]] = None,
    ) -> Scorecard:
        """Audit a single module against all contract rules.

        Args:
            module: Parsed module information.
            test_files: List of known test file paths for test existence check.

        Returns:
            Scorecard with all check results.
        """
        checks: List[CheckResult] = []
        c = self.contract

        # ── Structural Checks ─────────────────────────────────

        # Max LOC per file
        if c.max_loc_per_file > 0:
            checks.append(CheckResult(
                name="max_loc_per_file",
                passed=module.loc <= c.max_loc_per_file,
                severity="warning",
                message=f"{module.loc} LOC (max {c.max_loc_per_file})",
            ))

        # Max LOC per class
        if c.max_loc_per_class > 0:
            for cls in module.classes:
                if cls.loc > c.max_loc_per_class:
                    checks.append(CheckResult(
                        name="max_loc_per_class",
                        passed=False,
                        severity="error",
                        message=f"Class '{cls.name}' has {cls.loc} LOC (max {c.max_loc_per_class})",
                        details={"class": cls.name, "loc": cls.loc},
                    ))
                    break
            else:
                checks.append(CheckResult(
                    name="max_loc_per_class",
                    passed=True,
                    message="All classes within LOC limit",
                ))

        # ── Required Patterns ─────────────────────────────────

        if c.require_docstrings:
            checks.append(CheckResult(
                name="module_docstring",
                passed=module.has_docstring,
                severity="warning",
                message="" if module.has_docstring else "Missing module docstring",
            ))

            # Check public class/function docstrings
            missing_docs = []
            for cls in module.classes:
                if not cls.has_docstring:
                    missing_docs.append(cls.name)
                for method in cls.methods:
                    if method.is_public and not method.has_docstring:
                        missing_docs.append(f"{cls.name}.{method.name}")
            for func in module.functions:
                if func.is_public and not func.has_docstring:
                    missing_docs.append(func.name)

            checks.append(CheckResult(
                name="public_docstrings",
                passed=len(missing_docs) == 0,
                severity="warning",
                message=f"Missing docstrings: {', '.join(missing_docs[:5])}" if missing_docs else "",
                details=missing_docs,
            ))

        if c.require_logger:
            checks.append(CheckResult(
                name="logger",
                passed=module.has_logger,
                severity="warning",
                message="" if module.has_logger else "No logger = logging.getLogger(__name__)",
            ))

        if c.require_config_dataclass:
            has_config = any(
                cls.is_dataclass and "Config" in cls.name
                for cls in module.classes
            )
            checks.append(CheckResult(
                name="config_dataclass",
                passed=has_config,
                severity="warning",
                message="" if has_config else "No @dataclass Config class found",
            ))

        if c.require_test_file and test_files is not None:
            module_name = Path(module.path).stem
            has_test = any(
                f"test_{module_name}" in t or f"{module_name}_test" in t
                for t in test_files
            )
            checks.append(CheckResult(
                name="test_file",
                passed=has_test,
                severity="warning",
                message="" if has_test else f"No test file for {module_name}",
            ))

        # ── Forbidden Patterns ────────────────────────────────

        if c.forbid_bare_except:
            checks.append(CheckResult(
                name="no_bare_except",
                passed=len(module.bare_excepts) == 0,
                severity="error",
                message=f"Bare except on lines: {module.bare_excepts}" if module.bare_excepts else "",
            ))

        if c.forbid_print_statements:
            checks.append(CheckResult(
                name="no_print",
                passed=len(module.print_statements) == 0,
                severity="warning",
                message=f"print() on lines: {module.print_statements}" if module.print_statements else "",
            ))

        if c.forbid_magic_numbers and module.loc > 50:  # Skip tiny files
            # Allow some (in dataclass defaults, etc.)
            suspicious = [m for m in module.magic_numbers if m["value"] not in {0, 1, 2, -1}]
            checks.append(CheckResult(
                name="no_magic_numbers",
                passed=len(suspicious) <= 3,  # Allow a few
                severity="warning",
                message=f"{len(suspicious)} magic numbers found" if len(suspicious) > 3 else "",
                details=suspicious[:10],
            ))

        if c.forbid_fstring_logs:
            checks.append(CheckResult(
                name="no_fstring_logs",
                passed=len(module.fstring_logs) == 0,
                severity="warning",
                message=f"f-string in logger on lines: {module.fstring_logs}" if module.fstring_logs else "",
            ))

        # ── Metrics & EventBus ────────────────────────────────

        if module.loc > 100:
            checks.append(CheckResult(
                name="has_metrics",
                passed=module.has_metrics,
                severity="info",
                message="" if module.has_metrics else "No inc()/gauge()/timer() instrumentation",
            ))

        # ── Custom Patterns ───────────────────────────────────

        if c.custom_patterns:
            try:
                source = Path(module.path).read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                source = ""

            for custom in c.custom_patterns:
                try:
                    matches = re.findall(custom.pattern, source)
                    checks.append(CheckResult(
                        name=f"custom:{custom.pattern[:30]}",
                        passed=len(matches) == 0,
                        severity=custom.severity,
                        message=custom.message if matches else "",
                        details={"matches": len(matches)},
                    ))
                except re.error:
                    pass

        return Scorecard(path=module.path, checks=checks)
