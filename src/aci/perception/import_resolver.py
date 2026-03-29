"""
ACI :: Import Resolver
=======================
Resolves Python imports to actual file paths and builds the import graph.
Handles relative imports, package imports, and stdlib detection.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from aci.perception.ast_parser import ASTParser, ImportInfo, ModuleInfo

logger = logging.getLogger(__name__)

# Common stdlib top-level modules (not exhaustive, but covers 95%+)
_STDLIB_TOP = frozenset({
    "abc", "ast", "asyncio", "base64", "bisect", "builtins", "collections",
    "concurrent", "configparser", "contextlib", "copy", "csv", "ctypes",
    "dataclasses", "datetime", "decimal", "difflib", "enum", "errno",
    "fnmatch", "fractions", "functools", "gc", "getpass", "glob", "gzip",
    "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect",
    "io", "itertools", "json", "logging", "math", "multiprocessing", "os",
    "pathlib", "pickle", "platform", "pprint", "queue", "random", "re",
    "shutil", "signal", "socket", "sqlite3", "statistics", "string",
    "struct", "subprocess", "sys", "tempfile", "textwrap", "threading",
    "time", "timeit", "traceback", "types", "typing", "unittest", "urllib",
    "uuid", "warnings", "weakref", "xml", "zipfile",
})


@dataclass
class ResolvedImport:
    """An import resolved to its target."""
    source_path: str
    target_module: str
    target_path: Optional[str]  # None if external/stdlib
    category: str  # "internal" | "stdlib" | "external"
    names: List[str]


@dataclass
class ImportGraph:
    """Complete import graph for a project."""
    nodes: Dict[str, ModuleInfo]  # path → ModuleInfo
    edges: List[ResolvedImport]
    root: str  # project root path

    @property
    def internal_edges(self) -> List[ResolvedImport]:
        return [e for e in self.edges if e.category == "internal"]

    def dependents_of(self, path: str) -> List[str]:
        """Who imports this module?"""
        norm = self._normalize(path)
        return [
            e.source_path for e in self.internal_edges
            if e.target_path and self._normalize(e.target_path) == norm
        ]

    def dependencies_of(self, path: str) -> List[str]:
        """What does this module import?"""
        norm = self._normalize(path)
        return [
            e.target_path for e in self.internal_edges
            if self._normalize(e.source_path) == norm and e.target_path
        ]

    def _normalize(self, p: str) -> str:
        return str(Path(p).resolve())


class ImportResolver:
    """Resolves imports and builds the project import graph."""

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.parser = ASTParser()
        self._module_cache: Dict[str, Path] = {}

    def build_graph(self, include_patterns: Optional[List[str]] = None) -> ImportGraph:
        """Scan project and build complete import graph.

        Args:
            include_patterns: Glob patterns for files to include.
                             Defaults to all .py files.

        Returns:
            ImportGraph with all modules and resolved imports.
        """
        patterns = include_patterns or ["**/*.py"]
        py_files: List[Path] = []
        for pattern in patterns:
            py_files.extend(self.root.glob(pattern))

        # Filter out common non-source dirs
        skip_dirs = {
            "__pycache__", ".git", ".venv", "venv", "node_modules", ".tox",
            ".eggs", "build", "dist", ".mypy_cache", ".pytest_cache",
            ".ruff_cache", "mcp", "docs", "scripts", "benchmarks",
            "migrations", ".aci",
        }
        py_files = [
            f for f in py_files
            if not any(d in f.parts for d in skip_dirs)
        ]

        # Parse all files with 8 Workers
        nodes: Dict[str, ModuleInfo] = {}
        from concurrent.futures import ThreadPoolExecutor
        
        def parse_single_file(f_path: Path) -> tuple[str, Optional[ModuleInfo]]:
            return str(f_path), self.parser.parse_file(str(f_path))

        with ThreadPoolExecutor(max_workers=8) as executor:
            for path_str, info in executor.map(parse_single_file, py_files):
                if info:
                    nodes[path_str] = info

        # Build module lookup cache
        self._build_module_cache(py_files)

        # Resolve imports
        edges: List[ResolvedImport] = []
        for path, info in nodes.items():
            for imp in info.imports:
                resolved = self._resolve_import(path, imp)
                edges.append(resolved)

        graph = ImportGraph(nodes=nodes, edges=edges, root=str(self.root))

        logger.info(
            "Import graph built")
        return graph

    def _resolve_import(self, source: str, imp: ImportInfo) -> ResolvedImport:
        """Resolve a single import to its target file."""
        module = imp.module
        top = module.split(".")[0] if module else ""

        # Check stdlib
        if top in _STDLIB_TOP:
            return ResolvedImport(
                source_path=source,
                target_module=module,
                target_path=None,
                category="stdlib",
                names=imp.names,
            )

        # Try to resolve to internal file
        target = self._find_module_file(module)
        if target:
            return ResolvedImport(
                source_path=source,
                target_module=module,
                target_path=str(target),
                category="internal",
                names=imp.names,
            )

        # External package
        return ResolvedImport(
            source_path=source,
            target_module=module,
            target_path=None,
            category="external",
            names=imp.names,
        )

    def _find_module_file(self, module: str) -> Optional[Path]:
        """Find the file that implements a dotted module path."""
        if module in self._module_cache:
            return self._module_cache[module]

        parts = module.split(".")

        # Try as package: module/path/__init__.py
        pkg_path = self.root / Path(*parts) / "__init__.py"
        if pkg_path.exists():
            return pkg_path

        # Try as module: module/path.py
        mod_path = self.root / Path(*parts[:-1]) / f"{parts[-1]}.py" if len(parts) > 1 else self.root / f"{parts[0]}.py"
        if mod_path.exists():
            return mod_path

        # Try parent package
        if len(parts) > 1:
            parent = ".".join(parts[:-1])
            return self._find_module_file(parent)

        return None

    def _build_module_cache(self, files: List[Path]) -> None:
        """Build a map of dotted module names to file paths."""
        for f in files:
            try:
                rel = f.resolve().relative_to(self.root)
                parts = list(rel.parts)
                if parts[-1] == "__init__.py":
                    parts = parts[:-1]
                else:
                    parts[-1] = parts[-1].replace(".py", "")
                dotted = ".".join(parts)
                self._module_cache[dotted] = f.resolve()
            except (ValueError, IndexError):
                continue
