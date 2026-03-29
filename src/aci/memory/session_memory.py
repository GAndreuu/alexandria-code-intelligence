"""
ACI :: Session Memory
======================
Persistent memory between sessions. Tracks:
- Dream scores over time (trend analysis)
- Insights saved by the user or agents
- Module audit history (was it getting better or worse?)

Storage: JSON files in .aci/memory/
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionMemory:
    """Persistent cross-session memory for ACI."""

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.memory_dir = self.root / ".aci" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self._scores_file = self.memory_dir / "scores.json"
        self._insights_file = self.memory_dir / "insights.json"
        self._module_history_file = self.memory_dir / "module_history.json"

    # ── Score Tracking ────────────────────────────────────────

    def record_dream_score(self, score: float, total_findings: int, details: Dict[str, Any]) -> None:
        """Record a dream cycle score for trend analysis."""
        scores = self._load_json(self._scores_file, [])
        scores.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "compliance_rate": score,
            "total_findings": total_findings,
            "by_severity": details.get("findings_by_severity", {}),
            "total_modules": details.get("total_files_analyzed", 0),
        })
        # Keep last 100
        self._save_json(self._scores_file, scores[-100:])

    def get_score_trend(self) -> Dict[str, Any]:
        """Get compliance score trend over time."""
        scores = self._load_json(self._scores_file, [])
        if not scores:
            return {"sessions": 0, "message": "No dream history yet. Run dream() first."}

        recent = scores[-10:]  # Last 10
        rates = [s["compliance_rate"] for s in recent]

        trend = "stable"
        if len(rates) >= 2:
            diff = rates[-1] - rates[0]
            if diff > 2:
                trend = "improving"
            elif diff < -2:
                trend = "declining"

        return {
            "sessions": len(scores),
            "current_score": rates[-1] if rates else 0,
            "trend": trend,
            "history": [
                {
                    "timestamp": s["timestamp"],
                    "compliance_rate": s["compliance_rate"],
                    "findings": s["total_findings"],
                }
                for s in recent
            ],
        }

    # ── Insights ──────────────────────────────────────────────

    def save_insight(self, insight: str, category: str = "general", source: str = "user") -> None:
        """Save a development insight for future reference."""
        insights = self._load_json(self._insights_file, [])
        insights.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "insight": insight,
            "category": category,
            "source": source,
        })
        self._save_json(self._insights_file, insights[-200:])

    def get_insights(self, category: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve saved insights, optionally filtered by category."""
        insights = self._load_json(self._insights_file, [])
        if category:
            insights = [i for i in insights if i.get("category") == category]
        return insights[-limit:]

    # ── Module History ────────────────────────────────────────

    def record_module_audit(self, module_path: str, score: float, grade: str) -> None:
        """Record audit result for a module to track improvement."""
        history = self._load_json(self._module_history_file, {})
        key = module_path.replace("\\", "/")
        if key not in history:
            history[key] = []
        history[key].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": score,
            "grade": grade,
        })
        # Keep last 20 per module
        history[key] = history[key][-20:]
        self._save_json(self._module_history_file, history)

    def get_module_trend(self, module_path: str) -> Dict[str, Any]:
        """Get audit trend for a specific module."""
        history = self._load_json(self._module_history_file, {})
        key = module_path.replace("\\", "/")
        entries = history.get(key, [])
        if not entries:
            return {"module": key, "sessions": 0, "message": "No history for this module."}

        scores = [e["score"] for e in entries]
        trend = "stable"
        if len(scores) >= 2:
            diff = scores[-1] - scores[0]
            if diff > 5:
                trend = "improving"
            elif diff < -5:
                trend = "declining"

        return {
            "module": key,
            "sessions": len(entries),
            "current_score": scores[-1],
            "trend": trend,
            "history": entries[-10:],
        }

    # ── Internal ──────────────────────────────────────────────

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def _save_json(self, path: Path, data: Any) -> None:
        try:
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except OSError as e:
            logger.error("Failed to save memory")
