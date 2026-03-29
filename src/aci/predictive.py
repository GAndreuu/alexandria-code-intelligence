"""
ACI :: Predictive Observability Model
=====================================
Heuristic engine that anticipates missing observability signals
(telemetry, event bus, structured logging) based on structural
DNA and topological role of a mapped module.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict


class PredictiveObservability:
    """Calculates an expected observability score vs actual signals."""

    def __init__(self, root: Path):
        self.root = root

    def predict_observability(self, filepath: str) -> Dict[str, Any]:
        """Analyze a file and predict expected observability signals."""
        full_path = self.root / filepath
        if not full_path.exists():
            return {"error": f"File not found: {filepath}"}

        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except Exception as e:
            return {"error": f"Failed to parse AST: {e}"}

        # 1. Deduce Context/Topology Rules (The Heuristic Layer)
        is_l4_loop = "loop" in filepath
        is_l5_action = "actions" in filepath
        is_l6_swarm = "swarm" in filepath

        # 2. Extract Code DNA Indicators
        dna = {
            "has_loops": 0,
            "has_try_except": 0,
            "has_db_io": 0,
            "has_alexandria_error_raise": 0,
            "total_methods": 0
        }

        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                dna["has_loops"] += 1
            elif isinstance(node, ast.Try):
                dna["has_try_except"] += 1
            elif isinstance(node, ast.Raise):
                dna["has_alexandria_error_raise"] += 1
            elif isinstance(node, ast.FunctionDef):
                dna["total_methods"] += 1
            elif isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id
                
                if func_name in ("commit", "execute", "save", "write", "open"):
                    dna["has_db_io"] += 1

        # 3. Predict Expected Score (Arbitrary 0-100 heuristic scale)
        expected_score = 0
        predictions = []

        if is_l4_loop:
            expected_score += 30
            predictions.append("L4 Loop Module: Should have metrics.record() for cycle telemetry.")
        if is_l5_action or is_l6_swarm:
            expected_score += 30
            predictions.append("L5/L6 Module: Should emit bus.publish() state changes.")
        
        if dna["has_loops"] > 2:
            expected_score += 15
            predictions.append("Complex Loop Detected: Expected logger.debug or metrics.counter inside loops.")
        
        if dna["has_try_except"] > 0 or dna["has_alexandria_error_raise"] > 0:
            expected_score += 25
            predictions.append("Error Bound Detected: Expected logger.error/warning on exceptions.")

        if expected_score == 0 and dna["total_methods"] > 0:
            expected_score = 10
            predictions.append("Standard Logic: Minimum structured logger.info expected.")

        expected_score = min(100, expected_score)

        # 4. Measure Actual Signals Found
        actual_score = 0
        found_signals = []

        if re.search(r"logger\.(info|debug|warning|error)", text):
            actual_score += 20 if (dna["has_loops"] == 0 and dna["has_try_except"] == 0) else 40
            found_signals.append("Structured Logging")
        
        if ".publish(" in text:
            actual_score += 30
            found_signals.append("EventBus Publish")
        
        if "metrics." in text or "record_metric" in text or "timing" in text:
            actual_score += 30
            found_signals.append("Metrics/Telemetry")

        actual_score = min(100, actual_score)

        gap = max(0, expected_score - actual_score)

        return {
            "module": filepath,
            "layer_context": {
                "loop": is_l4_loop,
                "actions": is_l5_action,
                "swarm": is_l6_swarm
            },
            "code_dna": dna,
            "telemetry_expected": f"{expected_score}%",
            "telemetry_found": f"{actual_score}%",
            "gap": f"{gap}%",
            "health": "POOR" if gap > 30 else ("OK" if gap > 0 else "EXCELLENT"),
            "predictions": predictions,
            "found_signals": found_signals
        }
