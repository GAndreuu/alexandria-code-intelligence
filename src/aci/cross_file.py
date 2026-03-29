"""
ACI :: Cross-File Verification
================================
Tools that verify relationships ACROSS multiple files.
These cover the DEVELOPMENT_GUIDE rules that require
cross-referencing between modules.

Covers:
  §5.5 Config Pipeline (4-file check)
  §5.4 EventBus Wiring (3-file check)
  §7   Persistence Safety (per-file deep check)
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class CrossFileVerifier:
    """Verifies cross-file relationships in the Alexandria codebase."""

    def __init__(self, root: Path):
        self.root = root

    # ════════════════════════════════════════════════════════════
    # §5.5 — CONFIG PIPELINE VERIFICATION
    # ════════════════════════════════════════════════════════════

    def verify_config_pipeline(self, module_path: str) -> Dict[str, Any]:
        """Check if a module's config is properly registered across the pipeline.

        Verifies 4 steps:
        1. Config dataclass exists in the module
        2. Registered in _config_map.py
        3. Has constraints in _constraints.py (or sub-files)
        4. Has section in config.yaml

        Args:
            module_path: Relative path to the module (e.g. 'core/reasoning/stdp.py')

        Returns:
            Pipeline verification result with pass/fail per step.
        """
        resolved = self._resolve(module_path)
        if not resolved or not resolved.exists():
            return {"error": f"File not found: {module_path}"}

        # Step 1: Find config dataclasses in the module
        configs = self._find_config_dataclasses(resolved)
        if not configs:
            return {
                "module": module_path,
                "has_config": False,
                "message": "No @dataclass config found — pipeline check N/A",
                "pipeline": "N/A",
            }

        # Step 2: Check _config_map.py
        config_map = self._parse_config_map()

        # Step 3: Check constraints
        constraint_groups = self._parse_constraint_groups()

        # Step 4: Check config.yaml
        yaml_sections = self._parse_config_yaml()

        # Cross-reference each config
        results = []
        for cfg_name, cfg_class in configs:
            # Find if class is registered in _CONFIG_MAP
            registered_group = None
            for group, (mod_path, cls_name) in config_map.items():
                if cls_name == cfg_class:
                    registered_group = group
                    break

            has_constraints = registered_group in constraint_groups if registered_group else False
            has_yaml = registered_group in yaml_sections if registered_group else False

            results.append({
                "config_class": cfg_class,
                "steps": {
                    "1_dataclass_exists": {"passed": True, "detail": cfg_class},
                    "2_in_config_map": {
                        "passed": registered_group is not None,
                        "detail": f"group='{registered_group}'" if registered_group else "NOT FOUND in _CONFIG_MAP",
                    },
                    "3_has_constraints": {
                        "passed": has_constraints,
                        "detail": f"group='{registered_group}'" if has_constraints else "No constraints found",
                    },
                    "4_in_config_yaml": {
                        "passed": has_yaml,
                        "detail": f"section='{registered_group}'" if has_yaml else "No section in config.yaml",
                    },
                },
                "complete": all([
                    registered_group is not None,
                    has_constraints,
                    has_yaml,
                ]),
            })

        total_complete = sum(1 for r in results if r["complete"])
        return {
            "module": module_path,
            "has_config": True,
            "configs_found": len(results),
            "configs_complete": total_complete,
            "pipeline_score": f"{total_complete}/{len(results)}",
            "details": results,
        }

    # ════════════════════════════════════════════════════════════
    # §5.4 — EVENTBUS WIRING VERIFICATION
    # ════════════════════════════════════════════════════════════

    def verify_eventbus_wiring(self) -> Dict[str, Any]:
        """Check EventBus health: topics defined, published, subscribed.

        Verifies:
        1. All topics in topics.py have at least one publisher
        2. All published topics have at least one subscriber in wiring/
        3. No string literals used instead of topic constants

        Returns:
            Wiring verification with orphan topics and missing subscribers.
        """
        # Parse topics.py
        topics_file = self.root / "core" / "infra" / "events" / "topics.py"
        defined_topics = self._parse_topics_file(topics_file)

        # Find all publish calls across codebase
        publishers = self._find_publish_calls()

        # Find all subscribe calls in wiring/
        subscribers = self._find_subscribe_calls()

        # Find string literal topics (anti-pattern)
        string_literals = self._find_string_literal_topics()

        # Topics defined but never published
        published_topic_names = {p["topic_var"] for p in publishers if p["topic_var"]}
        orphan_topics = [
            t for t in defined_topics
            if t["name"] not in published_topic_names
            and "NOTE: Informational" not in t.get("comment", "")
        ]

        # Published topics without subscribers
        subscribed_topic_names = {s["topic_var"] for s in subscribers if s["topic_var"]}
        unsubscribed = [
            p for p in publishers
            if p["topic_var"] and p["topic_var"] not in subscribed_topic_names
        ]

        return {
            "topics_defined": len(defined_topics),
            "publishers_found": len(publishers),
            "subscribers_found": len(subscribers),
            "string_literal_topics": len(string_literals),
            "orphan_topics": [t["name"] for t in orphan_topics[:20]],
            "published_without_subscriber": [
                {"topic": p["topic_var"], "file": p["file"]}
                for p in unsubscribed[:20]
            ],
            "string_literal_violations": [
                {"file": s["file"], "line": s["line"], "value": s["value"]}
                for s in string_literals[:20]
            ],
            "health": "OK" if not string_literals and not unsubscribed else "ISSUES_FOUND",
        }

    # ════════════════════════════════════════════════════════════
    # §7 — PERSISTENCE VERIFICATION
    # ════════════════════════════════════════════════════════════

    def verify_persistence(self, scope: str = "all") -> Dict[str, Any]:
        """Check persistence safety across codebase.

        Verifies:
        1. No unsafe open(path, 'w') without atomic write
        2. Serialized state includes format_version
        3. torch.load uses weights_only=True

        Args:
            scope: 'all' or specific directory path

        Returns:
            Persistence violations found.
        """
        if scope == "all":
            search_root = self.root
        else:
            search_root = self._resolve(scope) or self.root

        findings = {
            "unsafe_writes": [],
            "missing_format_version": [],
            "unsafe_torch_load": [],
        }

        py_files = list(search_root.rglob("*.py"))
        skip = {"__pycache__", ".git", ".venv", "node_modules", "mcp", ".aci"}
        py_files = [f for f in py_files if not any(s in f.parts for s in skip)]

        from concurrent.futures import ThreadPoolExecutor
        
        def check_file(f: Path) -> dict:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return {"unsafe": [], "miss": [], "load": []}

            rel = self._relative(f)
            unsafe, miss, load = [], [], []

            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"): continue
                
                # §7.1: Unsafe writes (open with 'w' mode)
                if re.search(r"open\s*\(.+,\s*['\"]w", line):
                    context = text.splitlines()[max(0, i-5):i+2]
                    if not any("tempfile" in l or "os.replace" in l or "NamedTemporaryFile" in l for l in context):
                        unsafe.append({"file": rel, "line": i, "code": stripped[:100]})

                # §7.3: torch.load without weights_only
                if "torch.load(" in line and "weights_only" not in line:
                    load.append({"file": rel, "line": i, "code": stripped[:100]})

            # §7.2: State save without format_version
            if ("save" in rel.lower() or "persist" in rel.lower() or "serial" in rel.lower()):
                if "format_version" not in text and ("json.dump" in text or "pickle.dump" in text or "np.savez" in text):
                    miss.append({"file": rel, "message": "State file without format_version"})

            return {"unsafe": unsafe, "miss": miss, "load": load}

        with ThreadPoolExecutor(max_workers=8) as executor:
            for res in executor.map(check_file, py_files):
                findings["unsafe_writes"].extend(res["unsafe"])
                findings["missing_format_version"].extend(res["miss"])
                findings["unsafe_torch_load"].extend(res["load"])

        total = sum(len(v) for v in findings.values())
        return {
            "total_findings": total,
            "files_scanned": len(py_files),
            "findings": findings,
            "health": "OK" if total == 0 else "ISSUES_FOUND",
        }

    # ── Internal helpers ──────────────────────────────────────

    def _resolve(self, path: str) -> Optional[Path]:
        p = Path(path)
        if p.is_absolute() and p.exists():
            return p
        candidate = self.root / path
        if candidate.exists():
            return candidate
        return None

    def _relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(path)

    def _find_config_dataclasses(self, filepath: Path) -> List[Tuple[str, str]]:
        """Find @dataclass classes with 'Config' in the name."""
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []

        configs = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                is_dataclass = any(
                    (isinstance(d, ast.Name) and d.id == "dataclass")
                    or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                    or (isinstance(d, ast.Call) and (
                        (isinstance(d.func, ast.Name) and d.func.id == "dataclass")
                        or (isinstance(d.func, ast.Attribute) and d.func.attr == "dataclass")
                    ))
                    for d in node.decorator_list
                )
                if is_dataclass and "Config" in node.name:
                    configs.append((node.name, node.name))
        return configs

    def _parse_config_map(self) -> Dict[str, Tuple[str, str]]:
        """Parse _CONFIG_MAP from _config_map.py."""
        config_map_path = self.root / "core" / "hyperparams" / "_config_map.py"
        if not config_map_path.exists():
            return {}

        text = config_map_path.read_text(encoding="utf-8", errors="replace")
        result = {}
        # Pattern: "group_name": ("module.path", "ClassName"),
        for match in re.finditer(
            r'"(\w+)":\s*\(\s*"([^"]+)"\s*,\s*"(\w+)"\s*\)',
            text,
        ):
            group, mod_path, cls_name = match.groups()
            result[group] = (mod_path, cls_name)
        return result

    def _parse_constraint_groups(self) -> Set[str]:
        """Find all groups that have constraints defined."""
        constraints_dir = self.root / "core" / "hyperparams"
        groups: Set[str] = set()

        for f in constraints_dir.glob("constraints_*.py"):
            text = f.read_text(encoding="utf-8", errors="replace")
            # Pattern: ("group", "param"): {min: ..., max: ...}
            for match in re.finditer(r'\("(\w+)"', text):
                groups.add(match.group(1))

        # Also check _constraints.py itself
        main_constraints = constraints_dir / "_constraints.py"
        if main_constraints.exists():
            text = main_constraints.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r'\("(\w+)"', text):
                groups.add(match.group(1))

        return groups

    def _parse_config_yaml(self) -> Set[str]:
        """Find all top-level sections in config.yaml."""
        yaml_path = self.root / "config.yaml"
        if not yaml_path.exists():
            return set()

        text = yaml_path.read_text(encoding="utf-8", errors="replace")
        sections: Set[str] = set()
        for line in text.splitlines():
            # Top-level keys (not indented, not comments)
            match = re.match(r"^#?\s*(\w+):", line)
            if match:
                sections.add(match.group(1))
        return sections

    def _parse_topics_file(self, path: Path) -> List[Dict[str, str]]:
        """Parse topic constants from topics.py."""
        if not path.exists():
            return []

        topics = []
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            match = re.match(r'^(\w+)\s*=\s*"([^"]+)"', line.strip())
            if match:
                topics.append({
                    "name": match.group(1),
                    "value": match.group(2),
                    "comment": line,
                })
        return topics

    def _find_publish_calls(self) -> List[Dict[str, Any]]:
        """Find all bus.publish() calls across codebase."""
        results = []
        skip = {"__pycache__", ".git", ".venv", "node_modules", "mcp", ".aci"}

        py_files = [f for f in self.root.rglob("*.py") if not any(s in f.parts for s in skip)]
        from concurrent.futures import ThreadPoolExecutor
        
        def check_publish(f: Path) -> list:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return []
            rel = self._relative(f)
            found = []
            for i, line in enumerate(text.splitlines(), 1):
                if ".publish(" in line and "subscribe" not in line:
                    match = re.search(r'\.publish\(\s*(\w+)', line)
                    found.append({"file": rel, "line": i, "topic_var": match.group(1) if match else None})
            return found

        with ThreadPoolExecutor(max_workers=8) as executor:
            for res in executor.map(check_publish, py_files):
                results.extend(res)
        return results

    def _find_subscribe_calls(self) -> List[Dict[str, Any]]:
        """Find all bus.subscribe() calls (primarily in wiring/)."""
        results = []
        # Search in wiring directory and anywhere else
        py_files = [f for f in self.root.rglob("*.py") if "__pycache__" not in f.parts and ".git" not in f.parts]
        from concurrent.futures import ThreadPoolExecutor
        
        def check_subscribe(f: Path) -> list:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return []
            rel = self._relative(f)
            found = []
            for i, line in enumerate(text.splitlines(), 1):
                if ".subscribe(" in line:
                    match = re.search(r'\.subscribe\(\s*(\w+)', line)
                    found.append({"file": rel, "line": i, "topic_var": match.group(1) if match else None})
            return found

        with ThreadPoolExecutor(max_workers=8) as executor:
            for res in executor.map(check_subscribe, py_files):
                results.extend(res)
        return results

    def _find_string_literal_topics(self) -> List[Dict[str, Any]]:
        """Find bus.publish("string.literal") — anti-pattern."""
        results = []
        skip = {"__pycache__", ".git", ".venv", "node_modules", "mcp", ".aci", "topics.py"}

        py_files = [f for f in self.root.rglob("*.py") if not any(s in f.parts or s == f.name for s in skip)]
        from concurrent.futures import ThreadPoolExecutor

        def check_literal(f: Path) -> list:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return []
            rel = self._relative(f)
            found = []
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(r'\.publish\(\s*["\']', line):
                    match = re.search(r'\.publish\(\s*["\']([^"\']+)["\']', line)
                    found.append({"file": rel, "line": i, "value": match.group(1) if match else "?"})
            return found

        with ThreadPoolExecutor(max_workers=8) as executor:
            for res in executor.map(check_literal, py_files):
                results.extend(res)
        return results

    # ════════════════════════════════════════════════════════════
    # §5.5 — GHOST CONFIG VERIFICATION
    # ════════════════════════════════════════════════════════════

    def find_ghost_configs(self) -> Dict[str, Any]:
        """Find @dataclass configurations not registered in _config_map.py."""
        skip = {"__pycache__", ".git", ".venv", "node_modules", "mcp", ".aci"}
        all_configs = []
        for f in self.root.rglob("*.py"):
            if any(s in f.parts for s in skip) or "hyperparams" in f.parts:
                continue
            for name, cls_name in self._find_config_dataclasses(f):
                all_configs.append({"name": cls_name, "file": self._relative(f)})

        registered = self._parse_config_map()
        reg_classes = {r[1] for r in registered.values()}

        ghosts = [c for c in all_configs if c["name"] not in reg_classes]
        
        return {
            "total_configs_found": len(all_configs),
            "total_registered": len(registered),
            "ghosts_count": len(ghosts),
            "ghosts": ghosts,
            "health": "OK" if not ghosts else "ISSUES_FOUND"
        }

    # ════════════════════════════════════════════════════════════
    # L7 — DEAD API ROUTES VERIFICATION
    # ════════════════════════════════════════════════════════════

    def find_dead_api_routes(self) -> Dict[str, Any]:
        """Find API routes defined in api/routes/ but never included in app.py."""
        api_dir = self.root / "api"
        if not api_dir.exists():
            return {"error": "api/ directory not found"}

        # Find all included routers in app.py
        app_file = api_dir / "app.py"
        included_routers = set()
        if app_file.exists():
            text = app_file.read_text(encoding="utf-8", errors="replace")
            # Pattern: .include_router(module_name.router) or .include_router(module)
            for match in re.finditer(r"\.include_router\(([\w\.]+)", text):
                router_name = match.group(1).split(".")[0]
                included_routers.add(router_name)

        # Find all files with '@router' decorators
        routes_dir = api_dir / "routes"
        dead_routes = []
        total_endpoints = 0
        
        if routes_dir.exists():
            for f in routes_dir.rglob("*.py"):
                if f.name == "__init__.py":
                    continue
                
                module_name = f.stem
                text = f.read_text(encoding="utf-8", errors="replace")
                
                endpoints = re.findall(r"@[\w_]*router\.(get|post|put|delete|patch)\(", text)
                if endpoints:
                    total_endpoints += len(endpoints)
                    if module_name not in included_routers and f"{module_name}_router" not in included_routers:
                        dead_routes.append({
                            "module": self._relative(f),
                            "endpoints_count": len(endpoints)
                        })

        return {
            "included_routers_found": len(included_routers),
            "total_endpoints_found": total_endpoints,
            "dead_route_modules_count": len(dead_routes),
            "dead_route_modules": dead_routes,
            "health": "OK" if not dead_routes else "ISSUES_FOUND"
        }
