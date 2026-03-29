"""
ACI :: Dreamer Agent
=====================
Generates hypotheses for improvement: missing abstractions, consolidation
opportunities, decomposition proposals, and bridge suggestions.

Inspired by: Alexandria's CollapseAgent + AbductionEngine.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from aci.perception.ast_parser import ASTParser
from aci.swarm.architect import Finding

logger = logging.getLogger(__name__)


class DreamerAgent:
    """Generates creative hypotheses for codebase improvement."""

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.parser = ASTParser()

    def hypothesize_decompositions(self, files: List[str], max_loc: int = 300) -> List[Finding]:
        """Suggest decompositions for god classes."""
        findings = []
        for f in files:
            info = self.parser.parse_file(f)
            if not info:
                continue
            rel = self._relative(f)
            for cls in info.classes:
                if cls.loc > max_loc and len(cls.methods) > 5:
                    # Group methods by prefix to suggest submodules
                    prefixes: Dict[str, List[str]] = {}
                    for m in cls.methods:
                        prefix = m.name.split("_")[0] if "_" in m.name else "core"
                        prefixes.setdefault(prefix, []).append(m.name)

                    suggested_splits = [
                        {"prefix": p, "methods": ms}
                        for p, ms in prefixes.items() if len(ms) >= 2
                    ]
                    findings.append(Finding(
                        agent="dreamer",
                        severity="medium",
                        category="decomposition",
                        file=rel,
                        message=f"Class '{cls.name}' ({cls.loc} LOC, {len(cls.methods)} methods) "
                                f"can be decomposed into {len(suggested_splits)} submodules",
                        details={
                            "class": cls.name,
                            "loc": cls.loc,
                            "suggested_splits": suggested_splits,
                            "pattern": "Create subpackage with facade + domain classes §5.8",
                        },
                    ))
        return findings

    def hypothesize_missing_abstractions(self, files: List[str]) -> List[Finding]:
        """Find repeated patterns that suggest a missing abstraction."""
        # Collect all base classes to find common patterns
        base_usage: Dict[str, List[str]] = {}
        for f in files:
            info = self.parser.parse_file(f)
            if not info:
                continue
            rel = self._relative(f)
            for cls in info.classes:
                for base in cls.bases:
                    base_usage.setdefault(base, []).append(f"{rel}:{cls.name}")

        findings = []
        for base, users in base_usage.items():
            if len(users) >= 4 and base != "?" and base not in {"ABC", "BaseModel", "object"}:
                findings.append(Finding(
                    agent="dreamer",
                    severity="info",
                    category="common_base",
                    file=users[0].split(":")[0],
                    message=f"Base class '{base}' used by {len(users)} classes — "
                            "well-established pattern",
                    details={"base": base, "implementations": users},
                ))
        return findings

    def hypothesize_consolidations(self, files: List[str]) -> List[Finding]:
        """Find small files that might be consolidatable."""
        findings = []
        small_files: Dict[str, List[str]] = {}  # parent_dir → [small files]

        for f in files:
            info = self.parser.parse_file(f)
            if not info or info.loc > 50:
                continue
            if Path(f).name in {"__init__.py", "types.py", "constants.py"}:
                continue
            parent = str(Path(f).parent)
            small_files.setdefault(parent, []).append(self._relative(f))

        for parent, smalls in small_files.items():
            if len(smalls) >= 3:
                findings.append(Finding(
                    agent="dreamer",
                    severity="low",
                    category="consolidation",
                    file=smalls[0],
                    message=f"Directory has {len(smalls)} small files (<50 LOC each). "
                            "Consider consolidating if they serve similar purposes.",
                    details={"files": smalls},
                ))
        return findings

    def analyze(self, files: List[str]) -> List[Finding]:
        """Run all hypothesis generation."""
        findings = []
        findings.extend(self.hypothesize_decompositions(files))
        findings.extend(self.hypothesize_missing_abstractions(files))
        findings.extend(self.hypothesize_consolidations(files))
        return findings

    def _relative(self, path: str) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return path
