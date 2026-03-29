"""
ACI :: Architect Agent
=======================
Analyzes structural patterns, layer violations, and coupling.
Focuses on the MACRO view: is the architecture sound?

Inspired by: Alexandria's DirectAgent + GradientAgent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from aci.perception.ast_parser import ASTParser, ModuleInfo
from aci.contract.contract import QualityContract, LayerRule

logger = logging.getLogger(__name__)


@dataclass
class Finding:
    """A single finding from an agent."""
    agent: str
    severity: str  # critical | high | medium | low | info
    category: str
    file: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ArchitectAgent:
    """Analyzes architectural compliance and structural health."""

    def __init__(self, contract: QualityContract, project_root: str):
        self.contract = contract
        self.root = Path(project_root).resolve()
        self.parser = ASTParser()

    def analyze_file(self, filepath: str) -> List[Finding]:
        """Analyze a single file for architectural issues."""
        info = self.parser.parse_file(filepath)
        if not info:
            return []

        rel = self._relative(filepath)
        findings: List[Finding] = []

        # God class detection
        for cls in info.classes:
            if cls.loc > self.contract.max_loc_per_class:
                findings.append(Finding(
                    agent="architect",
                    severity="high",
                    category="god_class",
                    file=rel,
                    message=f"Class '{cls.name}' has {cls.loc} LOC (max {self.contract.max_loc_per_class}). "
                            f"Consider decomposing into subpackage with facade pattern §5.8.",
                    details={
                        "class": cls.name,
                        "loc": cls.loc,
                        "methods": len(cls.methods),
                        "suggestion": f"Create {cls.name.lower()}/ subpackage",
                    },
                ))

        # File too large
        if info.loc > self.contract.max_loc_per_file:
            findings.append(Finding(
                agent="architect",
                severity="medium",
                category="large_file",
                file=rel,
                message=f"File has {info.loc} LOC (max {self.contract.max_loc_per_file})",
            ))

        # Too many classes in one file
        if len(info.classes) > 3:
            findings.append(Finding(
                agent="architect",
                severity="medium",
                category="too_many_classes",
                file=rel,
                message=f"File has {len(info.classes)} classes. Consider splitting.",
            ))

        # Layer violations (self-check: does this file import above its layer?)
        if self.contract.layer_rule:
            findings.extend(self._check_layer_imports(info, rel))

        return findings

    def analyze_project(self, files: List[str]) -> List[Finding]:
        """Analyze entire project for architectural issues."""
        all_findings: List[Finding] = []
        for f in files:
            all_findings.extend(self.analyze_file(f))
        return all_findings

    def _check_layer_imports(self, info: ModuleInfo, rel: str) -> List[Finding]:
        """Check if this module's imports violate the layer rule."""
        lr = self.contract.layer_rule
        if not lr:
            return []

        src_layer = self._classify(rel, lr)
        if not src_layer:
            return []

        layers_ordered = list(lr.layers.keys())
        src_idx = layers_ordered.index(src_layer) if src_layer in layers_ordered else -1

        findings = []
        for imp in info.imports:
            # Convert module path to file-like path for classification
            imp_path = imp.module.replace(".", "/")
            tgt_layer = self._classify(imp_path, lr)
            if not tgt_layer:
                continue
            tgt_idx = layers_ordered.index(tgt_layer) if tgt_layer in layers_ordered else -1

            if tgt_idx > src_idx:  # Lower layer importing upper layer
                findings.append(Finding(
                    agent="architect",
                    severity="critical",
                    category="layer_violation",
                    file=rel,
                    message=f"LAYER VIOLATION: {src_layer} imports {tgt_layer} "
                            f"(import {imp.module}). Lower layers cannot import upper layers.",
                    details={"source_layer": src_layer, "target_layer": tgt_layer, "import": imp.module},
                ))
        return findings

    def _classify(self, rel_path: str, lr: LayerRule) -> Optional[str]:
        rel_fwd = rel_path.replace("\\", "/")
        for layer_name, prefixes in lr.layers.items():
            for prefix in prefixes:
                clean_pref = prefix.rstrip("/")
                if rel_fwd == clean_pref or rel_fwd.startswith(clean_pref + "/"):
                    return layer_name
        return None

    def _relative(self, path: str) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return path
