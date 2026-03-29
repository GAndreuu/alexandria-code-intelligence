"""
ACI :: Dream Engine
====================
SFL-inspired consolidation cycle that orchestrates all swarm agents
and produces a unified dream report.

6-stage cycle:
1. REPLAY — Reinforce good patterns
2. DECAY  — Flag stale / obsolete code
3. MICROGLIA — Dead code detection
4. DETECT — Architecture gap detection
5. DREAM  — Swarm analysis (5 agents)
6. SYNTHESIZE — Produce consolidated report
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from aci.swarm.architect import Finding

logger = logging.getLogger(__name__)


@dataclass
class DreamReport:
    """Output of one dream cycle."""
    timestamp: str
    project_root: str
    duration_seconds: float
    total_files_analyzed: int
    total_findings: int
    findings_by_severity: Dict[str, int]
    findings_by_agent: Dict[str, int]
    findings_by_category: Dict[str, int]
    top_findings: List[Dict[str, Any]]
    health_metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            f"# ACI Dream Report — {self.timestamp}",
            "",
            f"**Files analyzed:** {self.total_files_analyzed}",
            f"**Total findings:** {self.total_findings}",
            f"**Duration:** {self.duration_seconds:.1f}s",
            "",
            "## Findings by Severity",
            "",
        ]
        for sev, count in sorted(self.findings_by_severity.items()):
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}.get(sev, "⚪")
            lines.append(f"- {icon} **{sev}**: {count}")

        lines.extend(["", "## Top Findings", ""])
        for i, f in enumerate(self.top_findings[:20], 1):
            lines.append(f"{i}. **[{f['severity']}]** `{f['file']}` — {f['message']}")

        return "\n".join(lines)


class DreamEngine:
    """Orchestrates the dream cycle."""

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()

    def dream(self, contract_path: Optional[str] = None) -> DreamReport:
        """Execute a full dream cycle.

        Returns a DreamReport with all findings consolidated.
        """
        import time
        t0 = time.time()

        from aci.contract.contract import ContractLoader
        from aci.swarm.architect import ArchitectAgent
        from aci.swarm.critic import CriticAgent
        from aci.swarm.explorer import ExplorerAgent
        from aci.swarm.archaeologist import ArchaeologistAgent
        from aci.swarm.dreamer import DreamerAgent

        # Load contract
        loader = ContractLoader()
        if contract_path:
            contract = loader.load(contract_path)
        else:
            contract = loader.find_contract(str(self.root))

        # Scan files
        files = self._scan_files()
        file_paths = [str(f) for f in files]

        # Stage 1: REPLAY — Count good patterns
        health = self._stage_replay(file_paths, contract)

        # Stage 2-3: DECAY + MICROGLIA — via Archaeologist
        archaeologist = ArchaeologistAgent(str(self.root))
        arch_findings = archaeologist.analyze()

        # Stage 4: DETECT — via Architect
        architect = ArchitectAgent(contract, str(self.root))
        architect_findings = architect.analyze_project(file_paths)

        # Stage 5: DREAM — Explorer + Dreamer
        explorer = ExplorerAgent(str(self.root))
        explorer_findings = explorer.analyze(file_paths)

        dreamer = DreamerAgent(str(self.root))
        dreamer_findings = dreamer.analyze(file_paths)

        # Stage 6: SYNTHESIZE
        all_findings: List[Finding] = (
            arch_findings + architect_findings + explorer_findings + dreamer_findings
        )

        # Rank by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        all_findings.sort(key=lambda f: severity_order.get(f.severity, 5))

        by_severity = Counter(f.severity for f in all_findings)
        by_agent = Counter(f.agent for f in all_findings)
        by_category = Counter(f.category for f in all_findings)

        duration = time.time() - t0

        report = DreamReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            project_root=str(self.root),
            duration_seconds=round(duration, 1),
            total_files_analyzed=len(file_paths),
            total_findings=len(all_findings),
            findings_by_severity=dict(by_severity),
            findings_by_agent=dict(by_agent),
            findings_by_category=dict(by_category),
            top_findings=[
                {
                    "agent": f.agent,
                    "severity": f.severity,
                    "category": f.category,
                    "file": f.file,
                    "message": f.message,
                }
                for f in all_findings[:30]
            ],
            health_metrics=health,
        )

        # Save report
        self._save_report(report)

        return report

    def _stage_replay(self, files: List[str], contract) -> Dict[str, Any]:
        """Stage 1: Count how many modules follow good patterns."""
        from aci.perception.ast_parser import ASTParser
        parser = ASTParser()

        good = 0
        total = 0
        total_loc = 0

        for f in files:
            info = parser.parse_file(f)
            if not info:
                continue
            total += 1
            total_loc += info.loc

            # "Good" = has docstring + logger + no bare except
            if info.has_docstring and info.has_logger and not info.bare_excepts:
                good += 1

        return {
            "total_modules": total,
            "total_loc": total_loc,
            "good_patterns": good,
            "compliance_rate": round(good / max(total, 1) * 100, 1),
        }

    def _scan_files(self) -> List[Path]:
        skip = {
            "__pycache__", ".git", ".venv", "venv", "node_modules",
            ".tox", ".eggs", "build", "dist", ".mypy_cache",
            ".pytest_cache", ".ruff_cache", "mcp", ".aci", ".gemini",
        }
        results = []
        for f in self.root.rglob("*.py"):
            if not any(d in f.parts for d in skip):
                results.append(f)
        return results

    def _save_report(self, report: DreamReport) -> None:
        """Persist dream report to .aci/dreams/"""
        dreams_dir = self.root / ".aci" / "dreams"
        dreams_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # JSON
        json_path = dreams_dir / f"dream_{ts}.json"
        json_path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
        # Markdown
        md_path = dreams_dir / f"dream_{ts}.md"
        md_path.write_text(report.to_markdown(), encoding="utf-8")

        logger.info("Dream report saved")

        # Record to session memory for trend tracking
        try:
            from aci.memory.session_memory import SessionMemory
            mem = SessionMemory(str(self.root))
            mem.record_dream_score(
                score=report.health_metrics.get("compliance_rate", 0),
                total_findings=report.total_findings,
                details=report.to_dict(),
            )
        except Exception as e:
            logger.warning("Failed to record dream to memory")
