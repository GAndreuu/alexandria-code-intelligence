"""
ACI :: Code Physics Engine
==========================
Calculates the biological physics of the Alexandria Codebase.
- Free Energy Principle: Surprise/Prediction Errors against the Development Guide
- Hebbian Learning: Co-churn weights from git history
- STDP: Causal directed weights from EventBus Pub/Sub chains
"""
from __future__ import annotations

import logging
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class CodePhysics:
    """Calculates thermodynamic and biological metrics for the codebase."""

    def __init__(self, root: Path):
        self.root = root

    # ════════════════════════════════════════════════════════════
    # FEP: FREE ENERGY PRINCIPLE (PRIORS vs SURPRISE)
    # ════════════════════════════════════════════════════════════

    def compute_free_energy(self, module_path: str, audit_results: Dict[str, Any], loc: int) -> float:
        """Calculate the Free Energy of a module based on Karl Friston's FEP.

        F = Surprise (Prediction Error) - Complexity Cost
        Priors: The rules inside contract.yaml (Expectations).
        Input: The actual AST structure and metrics.

        Scale: -1.0 (Entropy Zero / Perfect Order) to +1.0 (Maximum Surprise / God Class)
        
        Args:
            module_path: Path to the module
            audit_results: The results from CriticAgent
            loc: Lines of code for the module

        Returns:
            Free Energy Float [-1.0, 1.0]
        """
        # 1. Base Energy: Large files naturally have more entropy.
        # Max limit is usually 500 LOC. 
        base_energy = min(1.0, loc / 500.0)

        # 2. Prediction Errors (Surprise): Each failed check violates a prior
        errors = 0
        warnings = 0
        passed = 0
        
        checks = audit_results.get("checks", {})
        for name, result in checks.items():
            if result.get("passed"):
                passed += 1
            else:
                sev = result.get("severity", "warning")
                if sev == "error":
                    errors += 1
                else:
                    warnings += 1

        total_checks = max(1, passed + errors + warnings)
        
        # Surprise factor: Higher weight for critical errors
        surprise = ((errors * 2.0) + warnings) / (total_checks * 2.0)

        # 3. Predictability (Negative Energy): Perfect alignment drives energy down
        precision = passed / total_checks

        # Free Energy Equation Approximation:
        # F = (Surprise * Complexity) - Precision
        # This maps roughly to: chaos pulls it to +1, precision pulls it to -1
        free_energy = (surprise * (1.0 + base_energy)) - precision

        # Normalize to [-1.0, 1.0]
        free_energy = max(-1.0, min(1.0, free_energy))
        
        return round(free_energy, 4)

    # ════════════════════════════════════════════════════════════
    # HEBBIAN LEARNING: CO-CHURN WEIGHTS
    # ════════════════════════════════════════════════════════════

    def compute_hebbian_weights(self, max_commits: int = 500) -> Dict[Tuple[str, str], float]:
        """Neurons that fire together, wire together.
        
        Uses git log to find files modified in the same commits.
        Returns a dictionary of (file_a, file_b) -> weight boost.
        """
        weights: Dict[Tuple[str, str], float] = defaultdict(float)
        try:
            # Get list of files changed in last N commits
            cmd = ["git", "log", f"-n_{max_commits}", "--name-only", "--format=COMMIT"]
            result = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, check=True)
            commits = result.stdout.split("COMMIT")
            
            for commit in commits:
                files = [f.strip() for f in commit.splitlines() if f.strip() and f.strip().endswith(".py")]
                # O(N^2) combinations for the files in this commit
                for i, f1 in enumerate(files):
                    for f2 in files[i+1:]:
                        # Ensure f1 < f2 for undirected pairs
                        pair = tuple(sorted([f1, f2]))
                        weights[pair] += 0.5  # Each co-occurrence adds 0.5 weight

            return dict(weights)
        except Exception as e:
            logger.warning(f"Hebbian weights ignored (Git error): {e}")
            return {}

    # ════════════════════════════════════════════════════════════
    # STDP: SPIKE-TIMING-DEPENDENT PLASTICITY
    # ════════════════════════════════════════════════════════════

    def compute_stdp_weights(self) -> Dict[Tuple[str, str], float]:
        """Causal directionality (A happens before B).

        Maps the EventBus. If A publishes X, and B subscribes to X,
        A causally drives B. The directed edge A -> B gets STDP weight.
        """
        stdp_directed_weights: Dict[Tuple[str, str], float] = defaultdict(float)
        
        publishers = defaultdict(list)
        subscribers = defaultdict(list)
        
        skip = {"__pycache__", ".git", ".venv", "node_modules", "mcp", ".aci"}
        py_files = [f for f in self.root.rglob("*.py") if not any(s in f.parts for s in skip)]
        
        from concurrent.futures import ThreadPoolExecutor
        
        def scan_file(f_path: Path) -> tuple[str, list[str], list[str]]:
            try:
                text = f_path.read_text(encoding="utf-8", errors="replace")
                pubs = [m.group(1) for m in re.finditer(r'\.publish\(\s*(\w+)', text)]
                subs = [m.group(1) for m in re.finditer(r'\.subscribe\(\s*(\w+)', text)]
                return self._relative(f_path), pubs, subs
            except Exception:
                return self._relative(f_path), [], []

        with ThreadPoolExecutor(max_workers=8) as executor:
            for rel_path, pubs, subs in executor.map(scan_file, py_files):
                for p in pubs:
                    publishers[p].append(rel_path)
                for s in subs:
                    subscribers[s].append(rel_path)
                
        # Link STDP
        for topic in publishers:
            if topic in subscribers:
                for pub in publishers[topic]:
                    for sub in subscribers[topic]:
                        if pub != sub:
                            # Causal flow: pub -> sub gets +2.0 weight
                            stdp_directed_weights[(pub, sub)] += 2.0
                            
        return dict(stdp_directed_weights)

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()
