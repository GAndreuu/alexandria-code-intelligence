"""
ACI :: Explorer Agent
======================
Discovers hidden patterns: orphan modules, similar unconnected code,
dead imports, and curiosity-driven exploration of under-analyzed zones.

Inspired by: Alexandria's ExplorerAgent + PsychedelicAgent.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from aci.perception.ast_parser import ASTParser, ModuleInfo
from aci.swarm.architect import Finding

logger = logging.getLogger(__name__)


class ExplorerAgent:
    """Discovers hidden patterns and orphaned code."""

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.parser = ASTParser()

    def find_orphan_inits(self, files: List[str]) -> List[Finding]:
        """Find __init__.py files that are empty or just re-exports."""
        findings = []
        for f in files:
            p = Path(f)
            if p.name != "__init__.py":
                continue
            info = self.parser.parse_file(f)
            if not info:
                continue
            if info.loc == 0:
                findings.append(Finding(
                    agent="explorer",
                    severity="info",
                    category="empty_init",
                    file=self._relative(f),
                    message="Empty __init__.py — package has no public API?",
                ))
        return findings

    def find_duplicate_names(self, files: List[str]) -> List[Finding]:
        """Find classes/functions with the same name in different files."""
        name_to_files: Dict[str, List[str]] = {}
        for f in files:
            info = self.parser.parse_file(f)
            if not info:
                continue
            rel = self._relative(f)
            for cls in info.classes:
                name_to_files.setdefault(cls.name, []).append(rel)
            for func in info.functions:
                if func.is_public:
                    name_to_files.setdefault(func.name, []).append(rel)

        findings = []
        for name, locs in name_to_files.items():
            if len(locs) > 1 and name not in {"__init__", "__repr__", "__str__", "create", "build"}:
                findings.append(Finding(
                    agent="explorer",
                    severity="low",
                    category="duplicate_name",
                    file=locs[0],
                    message=f"Name '{name}' defined in {len(locs)} files: {', '.join(locs[:3])}. "
                            "Could indicate duplication worth consolidating.",
                    details={"name": name, "files": locs},
                ))
        return findings

    def find_large_functions(self, files: List[str], max_loc: int = 50) -> List[Finding]:
        """Find functions that are too long (complexity smell)."""
        findings = []
        for f in files:
            info = self.parser.parse_file(f)
            if not info:
                continue
            rel = self._relative(f)
            all_funcs = list(info.functions)
            for cls in info.classes:
                all_funcs.extend(cls.methods)
            for func in all_funcs:
                if func.loc > max_loc:
                    findings.append(Finding(
                        agent="explorer",
                        severity="medium",
                        category="large_function",
                        file=rel,
                        message=f"Function '{func.name}' has {func.loc} LOC (suggested max {max_loc})",
                        details={"function": func.name, "loc": func.loc, "line": func.lineno},
                    ))
        return findings

    def find_missing_type_hints(self, files: List[str]) -> List[Finding]:
        """Find public functions without type hints."""
        findings = []
        for f in files:
            info = self.parser.parse_file(f)
            if not info:
                continue
            rel = self._relative(f)
            missing = []
            for func in info.functions:
                if func.is_public and not func.has_type_hints:
                    missing.append(func.name)
            for cls in info.classes:
                for method in cls.methods:
                    if method.is_public and not method.has_type_hints:
                        missing.append(f"{cls.name}.{method.name}")
            if len(missing) > 3:
                findings.append(Finding(
                    agent="explorer",
                    severity="low",
                    category="missing_type_hints",
                    file=rel,
                    message=f"{len(missing)} public functions without type hints",
                    details={"functions": missing[:10]},
                ))
        return findings

    def analyze(self, files: List[str]) -> List[Finding]:
        """Run all exploration analyses."""
        findings = []
        findings.extend(self.find_orphan_inits(files))
        findings.extend(self.find_duplicate_names(files))
        findings.extend(self.find_large_functions(files))
        findings.extend(self.find_missing_type_hints(files))
        return findings

    def _relative(self, path: str) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return path
