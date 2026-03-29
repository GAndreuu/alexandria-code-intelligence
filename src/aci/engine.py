"""
ACI :: Engine
==============
Central orchestrator that connects perception, graph, contract, and swarm.
Lazy initialization — components are built on first use.
Light operations (parse, audit) work WITHOUT building the full graph.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from aci.perception.ast_parser import ASTParser, ModuleInfo
from aci.contract.contract import ContractLoader, QualityContract
from aci.swarm.critic import CriticAgent, Scorecard

logger = logging.getLogger(__name__)


class ACIEngine:
    """Central engine for Alexandria Code Intelligence.

    Light ops (parse, audit) are instant — no graph needed.
    Graph ops (deps, bridges) trigger lazy graph build (~2-5s).
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        contract_path: Optional[str] = None,
    ):
        self._root = Path(
            project_root
            or os.environ.get("ACI_PROJECT_ROOT", "")
            or os.getcwd()
        ).resolve()

        self._contract_path = contract_path
        self._parser = ASTParser()

        # Lazy state
        self._import_graph = None
        self._code_graph = None
        self._contract: Optional[QualityContract] = None
        self._critic: Optional[CriticAgent] = None
        self._test_files: Optional[List[str]] = None
        self._py_files: Optional[List[Path]] = None
        self._last_graph_mtime: float = 0.0

        logger.info("ACI Engine initialized")

    # ── Lazy Properties ───────────────────────────────────────

    @property
    def contract(self) -> QualityContract:
        if self._contract is None:
            loader = ContractLoader()
            if self._contract_path:
                self._contract = loader.load(self._contract_path)
            else:
                self._contract = loader.find_contract(str(self._root))
        return self._contract

    @property
    def critic(self) -> CriticAgent:
        if self._critic is None:
            self._critic = CriticAgent(self.contract)
        return self._critic

    @property
    def test_files(self) -> List[str]:
        if self._test_files is None:
            self._test_files = [str(f) for f in self._scan_files("test_*.py")]
            self._test_files += [str(f) for f in self._scan_files("*_test.py")]
        return self._test_files

    @property
    def py_files(self) -> List[Path]:
        if self._py_files is None:
            self._py_files = self._scan_files("*.py")
        return self._py_files

    def _ensure_graph(self):
        """Build graph on demand — only when graph tools are called."""
        # Auto-invalidate if any known file has been modified
        if self._code_graph is not None and self._py_files is not None:
            max_mtime = max((f.stat().st_mtime for f in self._py_files if f.exists()), default=0)
            if max_mtime > self._last_graph_mtime:
                logger.info("Auto-invalidating AST Graph (files modified)")
                self.invalidate()

        if self._code_graph is None:
            from aci.perception.import_resolver import ImportResolver
            from aci.graph.code_graph import CodeGraphBuilder
            resolver = ImportResolver(str(self._root))
            self._import_graph = resolver.build_graph()
            builder = CodeGraphBuilder()
            self._code_graph = builder.build(self._import_graph)
            self._last_graph_mtime = max((f.stat().st_mtime for f in self.py_files if f.exists()), default=0)

    def invalidate(self) -> None:
        """Reset cached state."""
        self._import_graph = None
        self._code_graph = None
        self._test_files = None
        self._py_files = None

    # ── File scanning (fast) ──────────────────────────────────

    _SKIP = {
        "__pycache__", ".git", ".venv", "venv", "node_modules", ".tox",
        ".eggs", "build", "dist", ".mypy_cache", ".pytest_cache",
        ".ruff_cache", "mcp", ".aci", ".gemini", ".github",
    }

    def _scan_files(self, pattern: str = "*.py") -> List[Path]:
        """Fast file scan excluding non-source dirs."""
        results = []
        for f in self._root.rglob(pattern):
            if not any(d in f.parts for d in self._SKIP):
                results.append(f)
        return results

    # ═════════════════════════════════════════════════════════
    # D1: CODE ANALYSIS (NO GRAPH NEEDED)
    # ═════════════════════════════════════════════════════════

    def get_module_info(self, file_path: str) -> Dict[str, Any]:
        """Get structural info for a module. Fast — no graph build."""
        resolved = self._resolve_path(file_path)
        if not resolved:
            return {"error": f"File not found: {file_path}"}

        info = self._parser.parse_file(str(resolved))
        if not info:
            return {"error": f"Failed to parse: {file_path}"}

        rel = self._relative(str(resolved))
        return {
            "path": rel,
            "loc": info.loc,
            "classes": [
                {
                    "name": c.name,
                    "loc": c.loc,
                    "bases": c.bases,
                    "methods": len(c.methods),
                    "is_dataclass": c.is_dataclass,
                    "has_docstring": c.has_docstring,
                }
                for c in info.classes
            ],
            "functions": [
                {
                    "name": f.name,
                    "args": f.args,
                    "has_docstring": f.has_docstring,
                    "has_type_hints": f.has_type_hints,
                }
                for f in info.functions
            ],
            "imports": {
                "count": len(info.imports),
                "modules": sorted(info.import_modules),
            },
            "patterns": {
                "has_logger": info.has_logger,
                "has_metrics": info.has_metrics,
                "has_eventbus": info.has_eventbus,
                "has_docstring": info.has_docstring,
            },
            "anti_patterns": {
                "magic_numbers": len(info.magic_numbers),
                "bare_excepts": info.bare_excepts,
                "print_statements": info.print_statements,
                "fstring_logs": info.fstring_logs,
            },
        }

    def search_code(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search for modules/classes/functions by name. Fast scan."""
        query_lower = query.lower()
        results: List[Dict[str, Any]] = []

        for f in self.py_files:
            rel = self._relative(str(f))
            if query_lower in rel.lower():
                results.append({
                    "type": "module",
                    "name": f.stem,
                    "file": rel,
                })
            if len(results) >= max_results * 3:
                break

        # Deep search: parse matching files for class/function names
        for r in list(results):
            info = self._parser.parse_file(str(self._root / r["file"]))
            if not info:
                continue
            for cls in info.classes:
                if query_lower in cls.name.lower():
                    results.append({
                        "type": "class",
                        "name": cls.name,
                        "file": r["file"],
                        "line": cls.lineno,
                        "loc": cls.loc,
                    })
            for func in info.functions:
                if query_lower in func.name.lower():
                    results.append({
                        "type": "function",
                        "name": func.name,
                        "file": r["file"],
                        "line": func.lineno,
                    })

        # Dedupe and sort
        seen = set()
        unique = []
        for r in results:
            key = f"{r['type']}:{r.get('name', '')}:{r.get('file', '')}"
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique[:max_results]

    # ═════════════════════════════════════════════════════════
    # D2: QUALITY VALIDATION (NO GRAPH NEEDED)
    # ═════════════════════════════════════════════════════════

    def audit_module(self, file_path: str) -> Dict[str, Any]:
        """Audit a module against the quality contract. Fast."""
        resolved = self._resolve_path(file_path)
        if not resolved:
            return {"error": f"File not found: {file_path}"}

        info = self._parser.parse_file(str(resolved))
        if not info:
            return {"error": f"Failed to parse: {file_path}"}

        scorecard = self.critic.audit(info, self.test_files)
        return scorecard.to_dict()

    def find_anti_patterns(self, scope: str = "all") -> Dict[str, Any]:
        """Find anti-patterns across codebase. Scans files directly."""
        if scope == "all":
            files = self.py_files
        else:
            resolved = self._resolve_path(scope)
            if resolved and resolved.is_dir():
                files = [f for f in self.py_files if str(f).startswith(str(resolved))]
            elif resolved:
                files = [resolved]
            else:
                return {"error": f"Path not found: {scope}"}

        findings: Dict[str, List] = {
            "bare_excepts": [],
            "print_statements": [],
            "magic_numbers": [],
            "god_classes": [],
        }

        for f in files:
            info = self._parser.parse_file(str(f))
            if not info:
                continue
            rel = self._relative(str(f))

            if info.bare_excepts:
                findings["bare_excepts"].append({"file": rel, "lines": info.bare_excepts})
            if info.print_statements:
                findings["print_statements"].append({"file": rel, "lines": info.print_statements})
            if len(info.magic_numbers) > 5:
                findings["magic_numbers"].append({
                    "file": rel, "count": len(info.magic_numbers),
                })
            for cls in info.classes:
                if cls.loc > self.contract.max_loc_per_class:
                    findings["god_classes"].append({
                        "file": rel, "class": cls.name, "loc": cls.loc,
                    })

        total = sum(len(v) for v in findings.values())
        return {"total_findings": total, "findings": findings}

    def check_layer_rule(self, source_file: str, target_file: str) -> Dict[str, Any]:
        """Check if an import respects the layer hierarchy."""
        lr = self.contract.layer_rule
        if not lr:
            return {"result": "skip", "reason": "No layer rule defined"}

        src = self._resolve_path(source_file)
        tgt = self._resolve_path(target_file)
        if not src or not tgt:
            return {"error": "File(s) not found"}

        src_rel = self._relative(str(src))
        tgt_rel = self._relative(str(tgt))
        src_layer = self._classify_layer(src_rel, lr)
        tgt_layer = self._classify_layer(tgt_rel, lr)

        layers_ordered = list(lr.layers.keys())
        src_idx = layers_ordered.index(src_layer) if src_layer in layers_ordered else -1
        tgt_idx = layers_ordered.index(tgt_layer) if tgt_layer in layers_ordered else -1

        passed = src_idx >= tgt_idx if lr.direction == "up" else src_idx <= tgt_idx

        return {
            "result": "pass" if passed else "VIOLATION",
            "source": {"path": src_rel, "layer": src_layer},
            "target": {"path": tgt_rel, "layer": tgt_layer},
            "message": "" if passed else f"{src_layer} cannot import {tgt_layer}",
        }

    # ═════════════════════════════════════════════════════════
    # D3: DEPENDENCY GRAPH (BUILDS GRAPH ON DEMAND)
    # ═════════════════════════════════════════════════════════

    def get_dependency_graph(self, file_path: str, depth: int = 2) -> Dict[str, Any]:
        """Get dependency subgraph. Triggers graph build on first call."""
        self._ensure_graph()
        resolved = self._resolve_path(file_path)
        if not resolved:
            return {"error": f"File not found: {file_path}"}

        sub = self._code_graph.subgraph(str(resolved), depth)
        center = self._relative(str(resolved))

        return {
            "center": center,
            "depth": depth,
            "nodes": [
                {
                    "path": self._relative(p),
                    "loc": n.loc,
                    "instability": round(n.instability, 3),
                }
                for p, n in sub.nodes.items()
            ],
            "edges": [
                {"from": self._relative(e.source), "to": self._relative(e.target)}
                for e in sub.edges
            ],
        }

    def find_circular_deps(self) -> Dict[str, Any]:
        """Find circular dep chains. Triggers graph build."""
        self._ensure_graph()
        cycles = self._code_graph.find_cycles()
        return {
            "count": len(cycles),
            "cycles": [[self._relative(p) for p in c] for c in cycles[:20]],
        }

    def find_bridge_modules(self, top_k: int = 10) -> List[Dict[str, Any]]:
        """Find high-impact bridge modules. Triggers graph build."""
        self._ensure_graph()
        bridges = self._code_graph.find_bridges(top_k)
        return [
            {
                "path": self._relative(p),
                "bridge_score": round(s, 2),
            }
            for p, s in bridges if p in self._code_graph.nodes
        ]

    def get_codebase_health(self) -> Dict[str, Any]:
        """Codebase health dashboard. No full graph needed."""
        sample = self.py_files[:80]
        scores = []
        grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}

        for f in sample:
            info = self._parser.parse_file(str(f))
            if not info:
                continue
            sc = self.critic.audit(info, self.test_files)
            scores.append(sc.percentage)
            grade_dist[sc.grade] += 1

        total_loc = 0
        for f in self.py_files:
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                total_loc += len([l for l in lines if l.strip() and not l.strip().startswith("#")])
            except Exception:
                pass

        avg_score = sum(scores) / max(len(scores), 1)

        return {
            "project_root": str(self._root),
            "contract": self.contract.name,
            "total_files": len(self.py_files),
            "total_loc": total_loc,
            "sample_audited": len(scores),
            "avg_compliance": round(avg_score, 1),
            "grade_distribution": grade_dist,
        }

    # ── Helpers ────────────────────────────────────────────────

    def _resolve_path(self, file_path: str) -> Optional[Path]:
        """Resolve a file path against the project root."""
        p = Path(file_path)
        if p.is_absolute() and p.exists():
            return p.resolve()
        candidate = self._root / file_path
        if candidate.exists():
            return candidate.resolve()
        # Partial match
        for f in self.py_files:
            if file_path.replace("/", os.sep) in str(f):
                return f.resolve()
        return None

    def _relative(self, path: str) -> str:
        try:
            return str(Path(path).resolve().relative_to(self._root)).replace("\\", "/")
        except ValueError:
            return path

    def _classify_layer(self, rel_path: str, lr) -> Optional[str]:
        rel_fwd = rel_path.replace("\\", "/")
        for layer_name, prefixes in lr.layers.items():
            for prefix in prefixes:
                if rel_fwd.startswith(prefix.rstrip("/")):
                    return layer_name
        return None
