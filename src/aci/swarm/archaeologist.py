"""
ACI :: Archaeologist Agent
===========================
Analyzes git history to understand code evolution, churn hotspots,
co-change patterns, and temporal causality (STDP-inspired).

Inspired by: Alexandria's MomentumAgent + STDP temporal causal weights.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aci.swarm.architect import Finding

logger = logging.getLogger(__name__)

try:
    from git import Repo
    HAS_GIT = True
except ImportError:
    HAS_GIT = False


@dataclass
class FileHistory:
    """Git history summary for one file."""
    path: str
    total_commits: int
    last_modified: Optional[datetime]
    first_created: Optional[datetime]
    authors: List[str]
    churn_30d: int  # commits in last 30 days


class ArchaeologistAgent:
    """Analyzes git history for temporal patterns."""

    def __init__(self, project_root: str, max_commits: int = 500):
        self.root = Path(project_root).resolve()
        self.max_commits = max_commits
        self._repo = None
        self._history: Optional[Dict[str, FileHistory]] = None

    @property
    def repo(self):
        if self._repo is None and HAS_GIT:
            try:
                self._repo = Repo(str(self.root))
            except Exception:
                logger.warning("Not a git repository")
        return self._repo

    def _build_history(self) -> Dict[str, FileHistory]:
        """Scan git log and build per-file history."""
        if self._history is not None:
            return self._history

        self._history = {}
        if not self.repo:
            return self._history

        now = datetime.now(timezone.utc)
        cutoff_30d = now - timedelta(days=30)

        file_commits: Dict[str, List[datetime]] = defaultdict(list)
        file_authors: Dict[str, set] = defaultdict(set)

        try:
            for commit in self.repo.iter_commits(max_count=self.max_commits):
                ts = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)
                author = str(commit.author)
                for path in commit.stats.files:
                    file_commits[path].append(ts)
                    file_authors[path].add(author)
        except Exception as e:
            logger.warning("Git history scan failed")
            return self._history

        for path, timestamps in file_commits.items():
            timestamps.sort()
            churn_30d = sum(1 for t in timestamps if t >= cutoff_30d)
            self._history[path] = FileHistory(
                path=path,
                total_commits=len(timestamps),
                last_modified=timestamps[-1] if timestamps else None,
                first_created=timestamps[0] if timestamps else None,
                authors=list(file_authors.get(path, set())),
                churn_30d=churn_30d,
            )

        return self._history

    def find_churn_hotspots(self, top_k: int = 15) -> List[Finding]:
        """Find files with highest recent change frequency."""
        history = self._build_history()
        if not history:
            return [Finding(
                agent="archaeologist", severity="info", category="no_git",
                file="", message="No git history available",
            )]

        ranked = sorted(history.values(), key=lambda h: -h.churn_30d)
        findings = []
        for h in ranked[:top_k]:
            if h.churn_30d < 2:
                break
            findings.append(Finding(
                agent="archaeologist",
                severity="medium" if h.churn_30d > 5 else "low",
                category="churn_hotspot",
                file=h.path,
                message=f"{h.churn_30d} commits in last 30 days — high churn indicates instability",
                details={
                    "total_commits": h.total_commits,
                    "churn_30d": h.churn_30d,
                    "authors": h.authors,
                },
            ))
        return findings

    def find_stale_code(self, months: int = 6) -> List[Finding]:
        """Find files not modified in N months."""
        history = self._build_history()
        if not history:
            return []

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=months * 30)
        findings = []

        for h in history.values():
            if h.last_modified and h.last_modified < cutoff:
                age_days = (now - h.last_modified).days
                findings.append(Finding(
                    agent="archaeologist",
                    severity="info",
                    category="stale_code",
                    file=h.path,
                    message=f"Not modified in {age_days} days ({age_days // 30} months)",
                    details={"last_modified": h.last_modified.isoformat(), "age_days": age_days},
                ))
        return findings

    def find_bus_factor_risks(self) -> List[Finding]:
        """Find files with only one author (bus factor = 1)."""
        history = self._build_history()
        findings = []
        for h in history.values():
            if len(h.authors) == 1 and h.total_commits > 3:
                findings.append(Finding(
                    agent="archaeologist",
                    severity="low",
                    category="bus_factor",
                    file=h.path,
                    message=f"Only 1 author ({h.authors[0]}) across {h.total_commits} commits",
                ))
        return findings

    def analyze(self) -> List[Finding]:
        """Run all history analyses."""
        findings = []
        findings.extend(self.find_churn_hotspots())
        findings.extend(self.find_stale_code())
        findings.extend(self.find_bus_factor_risks())
        return findings
