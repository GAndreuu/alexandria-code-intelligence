"""
ACI :: AST Parser
==================
Extracts structural information from Python source files.
Classes, functions, imports, docstrings, decorators, config dataclasses.

Zero external dependencies — uses only stdlib ast module.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ─── Data Types ─────────────────────────────────────────────────


@dataclass
class FunctionInfo:
    """Extracted function metadata."""
    name: str
    lineno: int
    end_lineno: int
    args: List[str]
    has_docstring: bool
    has_type_hints: bool
    decorators: List[str]
    is_public: bool

    @property
    def loc(self) -> int:
        return max(0, self.end_lineno - self.lineno + 1)


@dataclass
class ClassInfo:
    """Extracted class metadata."""
    name: str
    lineno: int
    end_lineno: int
    bases: List[str]
    methods: List[FunctionInfo]
    has_docstring: bool
    decorators: List[str]
    is_dataclass: bool

    @property
    def loc(self) -> int:
        return max(0, self.end_lineno - self.lineno + 1)


@dataclass
class ImportInfo:
    """Extracted import metadata."""
    module: str
    names: List[str]
    is_from: bool
    lineno: int


@dataclass
class ModuleInfo:
    """Complete structural info for a Python module."""
    path: str
    loc: int
    classes: List[ClassInfo]
    functions: List[FunctionInfo]
    imports: List[ImportInfo]
    has_docstring: bool
    has_logger: bool
    has_metrics: bool
    has_eventbus: bool
    magic_numbers: List[Dict[str, Any]]
    bare_excepts: List[int]
    fstring_logs: List[int]
    print_statements: List[int]

    @property
    def total_classes(self) -> int:
        return len(self.classes)

    @property
    def total_functions(self) -> int:
        return len(self.functions) + sum(len(c.methods) for c in self.classes)

    @property
    def import_modules(self) -> Set[str]:
        return {imp.module for imp in self.imports}


# ─── Parser ─────────────────────────────────────────────────────


class ASTParser:
    """Parses Python files into structured ModuleInfo."""

    def parse_file(self, filepath: str) -> Optional[ModuleInfo]:
        """Parse a single Python file.

        Args:
            filepath: Absolute or relative path to .py file.

        Returns:
            ModuleInfo or None if parsing fails.
        """
        path = Path(filepath)
        if not path.exists() or path.suffix != ".py":
            return None

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            logger.warning(
                "AST parse failed")
            return None

        lines = source.splitlines()
        loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

        classes = self._extract_classes(tree)
        functions = self._extract_functions(tree, top_level_only=True)
        imports = self._extract_imports(tree)
        magic_numbers = self._find_magic_numbers(tree)
        bare_excepts = self._find_bare_excepts(tree)
        fstring_logs = self._find_fstring_logs(source, lines)
        print_stmts = self._find_print_statements(tree)

        return ModuleInfo(
            path=str(path),
            loc=loc,
            classes=classes,
            functions=functions,
            imports=imports,
            has_docstring=self._has_module_docstring(tree),
            has_logger=self._has_logger(source),
            has_metrics=self._has_metrics(source),
            has_eventbus=self._has_eventbus(source),
            magic_numbers=magic_numbers,
            bare_excepts=bare_excepts,
            fstring_logs=fstring_logs,
            print_statements=print_stmts,
        )

    # ── Extraction ────────────────────────────────────────────

    def _extract_classes(self, tree: ast.Module) -> List[ClassInfo]:
        classes = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                methods = self._extract_functions(node)
                is_dc = any(
                    self._decorator_name(d) == "dataclass"
                    for d in node.decorator_list
                )
                classes.append(ClassInfo(
                    name=node.name,
                    lineno=node.lineno,
                    end_lineno=node.end_lineno or node.lineno,
                    bases=[self._name_of(b) for b in node.bases],
                    methods=methods,
                    has_docstring=self._has_docstring(node),
                    decorators=[self._decorator_name(d) for d in node.decorator_list],
                    is_dataclass=is_dc,
                ))
        return classes

    def _extract_functions(
        self, node: ast.AST, top_level_only: bool = False
    ) -> List[FunctionInfo]:
        funcs = []
        children = ast.iter_child_nodes(node)
        for child in children:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                has_hints = (
                    child.returns is not None
                    or any(a.annotation is not None for a in child.args.args)
                )
                funcs.append(FunctionInfo(
                    name=child.name,
                    lineno=child.lineno,
                    end_lineno=child.end_lineno or child.lineno,
                    args=[a.arg for a in child.args.args if a.arg != "self"],
                    has_docstring=self._has_docstring(child),
                    has_type_hints=has_hints,
                    decorators=[self._decorator_name(d) for d in child.decorator_list],
                    is_public=not child.name.startswith("_"),
                ))
        return funcs

    def _extract_imports(self, tree: ast.Module) -> List[ImportInfo]:
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(ImportInfo(
                        module=alias.name,
                        names=[alias.asname or alias.name],
                        is_from=False,
                        lineno=node.lineno,
                    ))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [a.name for a in (node.names or [])]
                imports.append(ImportInfo(
                    module=module,
                    names=names,
                    is_from=True,
                    lineno=node.lineno,
                ))
        return imports

    # ── Anti-pattern Detection ────────────────────────────────

    def _find_magic_numbers(self, tree: ast.Module) -> List[Dict[str, Any]]:
        """Find hardcoded numeric literals outside safe contexts."""
        safe = {0, 1, 2, -1, 0.0, 1.0, 0.5, 100, 1e-8, 1e-9}
        findings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if node.value not in safe and not isinstance(node.value, bool):
                    # Skip if inside a dataclass field default
                    findings.append({
                        "value": node.value,
                        "lineno": node.lineno,
                    })
        return findings[:20]  # Cap to avoid noise

    def _find_bare_excepts(self, tree: ast.Module) -> List[int]:
        lines = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    lines.append(node.lineno)
        return lines

    def _find_print_statements(self, tree: ast.Module) -> List[int]:
        lines = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    lines.append(node.lineno)
        return lines

    def _find_fstring_logs(self, source: str, lines: List[str]) -> List[int]:
        """Find logger calls using f-strings instead of structured logging."""
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "logger." in stripped and 'f"' in stripped or "f'" in stripped:
                findings.append(i)
        return findings

    # ── Helpers ────────────────────────────────────────────────

    def _has_module_docstring(self, tree: ast.Module) -> bool:
        return self._has_docstring(tree)

    def _has_docstring(self, node: ast.AST) -> bool:
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr):
            if isinstance(body[0].value, ast.Constant) and isinstance(
                body[0].value.value, str
            ):
                return True
        return False

    def _has_logger(self, source: str) -> bool:
        return "logging.getLogger" in source

    def _has_metrics(self, source: str) -> bool:
        return any(k in source for k in ("inc(", "gauge(", "timer("))

    def _has_eventbus(self, source: str) -> bool:
        return "event_bus" in source or "EventBus" in source

    def _decorator_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return self._decorator_name(node.func)
        return "unknown"

    def _name_of(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._name_of(node.value)}.{node.attr}"
        return "?"
