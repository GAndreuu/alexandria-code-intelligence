"""
ACI :: MCP Server
==================
FastMCP server that exposes Alexandria Code Intelligence as MCP tools.
This is the entry point — all tools are registered here.

Usage:
    fastmcp run mcp/src/aci/server.py
    python mcp/src/aci/server.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP


# ── Safe Logging ──────────────────────────────────────────────
# FastMCP uses a strict logging handler that doesn't tolerate
# extra dict keys that conflict with reserved LogRecord fields.
# We install a filter that sanitizes these before they hit the handler.

class _SafeExtraFilter(logging.Filter):
    """Strip reserved LogRecord keys from extra dicts."""
    _RESERVED = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "process", "processName", "message",
    })

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(vars(record)):
            if key in self._RESERVED:
                continue  # Don't delete actual reserved fields
        return True


# Suppress all ACI logs to stderr (FastMCP captures stdout for protocol)
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s: %(message)s",
)
# Silence ACI loggers completely in MCP mode
logging.getLogger("aci").setLevel(logging.ERROR)


logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Alexandria Code Intelligence",
    instructions=(
        "ACI analyzes Python codebases with surgical precision. "
        "Use audit_module to score compliance, get_module_info for structure, "
        "get_dependency_graph for impact analysis, and dream for consolidation."
    ),
)


# ─── Lazy Singleton ────────────────────────────────────────────

_engine: Optional["ACIEngine"] = None


def _get_engine() -> "ACIEngine":
    global _engine
    if _engine is None:
        from aci.engine import ACIEngine
        _engine = ACIEngine()
    return _engine


# ═══════════════════════════════════════════════════════════════
# D1: CODE ANALYSIS TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def get_module_info(file_path: str) -> str:
    """Get complete structural info for a Python module.

    Returns: classes, functions, imports, LOC, layer, dependencies, dependents.
    Use this FIRST when you need to understand a module before editing it.

    Args:
        file_path: Path to the .py file (absolute or relative to project root).
    """
    engine = _get_engine()
    info = engine.get_module_info(file_path)
    return json.dumps(info, indent=2, default=str)


@mcp.tool
def search_code(query: str, max_results: int = 10) -> str:
    """Search for modules, classes, or functions by name or pattern.

    Use this to find where something is defined or used in the codebase.

    Args:
        query: Search term (module name, class name, function name, or pattern).
        max_results: Maximum results to return.
    """
    engine = _get_engine()
    results = engine.search_code(query, max_results)
    return json.dumps(results, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# D2: QUALITY VALIDATION TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def audit_module(file_path: str) -> str:
    """Audit a module against the quality contract. Returns a scorecard.

    The scorecard checks: LOC limits, docstrings, logger, config dataclass,
    bare excepts, print statements, magic numbers, test file existence, etc.

    Each check is pass/fail with severity (error/warning/info).
    Overall grade: A (90%+) to F (<40%).

    Args:
        file_path: Path to the .py file to audit.
    """
    engine = _get_engine()
    scorecard = engine.audit_module(file_path)
    return json.dumps(scorecard, indent=2, default=str)


@mcp.tool
def find_anti_patterns(scope: str = "all") -> str:
    """Scan for anti-patterns across the codebase or a specific path.

    Detects: bare excepts, print statements, magic numbers, f-string logging,
    missing docstrings, god classes (>300 LOC), and custom contract violations.

    Args:
        scope: "all" for entire codebase, or a specific file/directory path.
    """
    engine = _get_engine()
    findings = engine.find_anti_patterns(scope)
    return json.dumps(findings, indent=2, default=str)


@mcp.tool
def check_layer_rule(source_file: str, target_file: str) -> str:
    """Check if an import from source to target respects the layer hierarchy.

    Returns pass/fail with explanation of which layers are involved.

    Args:
        source_file: The file doing the importing.
        target_file: The file being imported.
    """
    engine = _get_engine()
    result = engine.check_layer_rule(source_file, target_file)
    return json.dumps(result, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# D3: DEPENDENCY GRAPH TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def get_dependency_graph(file_path: str, depth: int = 2) -> str:
    """Get the dependency graph around a module.

    Shows who this module imports and who imports it, up to specified depth.
    Essential for understanding the IMPACT of changes before refactoring.

    Args:
        file_path: Center module path.
        depth: How many levels of dependencies to traverse (1-5).
    """
    engine = _get_engine()
    graph = engine.get_dependency_graph(file_path, min(depth, 5))
    return json.dumps(graph, indent=2, default=str)


@mcp.tool
def find_circular_deps() -> str:
    """Find all circular dependency chains in the codebase.

    Circular deps are architectural violations that cause import errors
    and tight coupling. Returns the cycles found as lists of module paths.
    """
    engine = _get_engine()
    cycles = engine.find_circular_deps()
    return json.dumps(cycles, indent=2, default=str)


@mcp.tool
def find_bridge_modules(top_k: int = 10) -> str:
    """Find modules that act as bridges between subsystems.

    Bridge modules connect many parts of the codebase — they are
    high-impact targets for refactoring (risky to change).

    Args:
        top_k: How many bridge modules to return.
    """
    engine = _get_engine()
    bridges = engine.find_bridge_modules(top_k)
    return json.dumps(bridges, indent=2, default=str)


@mcp.tool
def get_codebase_health() -> str:
    """Get overall codebase health dashboard.

    Returns: total modules, total LOC, average compliance score,
    orphan count, cycle count, top violations, and per-layer stats.
    """
    engine = _get_engine()
    health = engine.get_codebase_health()
    return json.dumps(health, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# D4: SWARM INTELLIGENCE TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def run_swarm(scope: str = "all") -> str:
    """Run ALL 5 swarm agents on the codebase: Architect, Critic, Explorer,
    Archaeologist, and Dreamer. Returns consolidated findings sorted by severity.

    Use this for a comprehensive multi-perspective analysis of code quality.

    Args:
        scope: "all" for entire codebase, or a specific directory path.
    """
    import os
    engine = _get_engine()
    root = str(engine._root)
    files = [str(f) for f in engine.py_files]

    if scope != "all":
        resolved = engine._resolve_path(scope)
        if resolved:
            files = [f for f in files if str(resolved) in f]

    from aci.swarm.architect import ArchitectAgent
    from aci.swarm.explorer import ExplorerAgent
    from aci.swarm.archaeologist import ArchaeologistAgent
    from aci.swarm.dreamer import DreamerAgent

    all_findings = []
    all_findings.extend(ArchitectAgent(engine.contract, root).analyze_project(files))
    all_findings.extend(ExplorerAgent(root).analyze(files))
    all_findings.extend(ArchaeologistAgent(root).analyze())
    all_findings.extend(DreamerAgent(root).analyze(files))

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    all_findings.sort(key=lambda f: severity_order.get(f.severity, 5))

    return json.dumps({
        "total": len(all_findings),
        "findings": [
            {"agent": f.agent, "severity": f.severity, "category": f.category,
             "file": f.file, "message": f.message}
            for f in all_findings[:40]
        ],
    }, indent=2, default=str)


@mcp.tool
def find_churn_hotspots(top_k: int = 15) -> str:
    """Find files with highest recent change frequency using git history.

    High churn = instability. These files change too often and may need
    architectural attention (better abstraction, clearer API, etc).

    Args:
        top_k: How many hotspots to return.
    """
    engine = _get_engine()
    from aci.swarm.archaeologist import ArchaeologistAgent
    agent = ArchaeologistAgent(str(engine._root))
    findings = agent.find_churn_hotspots(top_k)
    return json.dumps([
        {"file": f.file, "severity": f.severity, "message": f.message,
         "details": f.details}
        for f in findings
    ], indent=2, default=str)


@mcp.tool
def suggest_refactoring(file_path: str) -> str:
    """Get refactoring suggestions for a specific module.

    Combines Architect (structural), Explorer (patterns), and Dreamer
    (hypotheses) to produce actionable improvement suggestions.

    Args:
        file_path: Path to the .py file to analyze.
    """
    engine = _get_engine()
    resolved = engine._resolve_path(file_path)
    if not resolved:
        return json.dumps({"error": f"File not found: {file_path}"})

    root = str(engine._root)
    files = [str(resolved)]

    from aci.swarm.architect import ArchitectAgent
    from aci.swarm.explorer import ExplorerAgent
    from aci.swarm.dreamer import DreamerAgent

    findings = []
    findings.extend(ArchitectAgent(engine.contract, root).analyze_file(str(resolved)))
    findings.extend(ExplorerAgent(root).analyze(files))
    findings.extend(DreamerAgent(root).analyze(files))

    # Also include audit
    audit = engine.audit_module(file_path)

    return json.dumps({
        "audit": audit,
        "suggestions": [
            {"agent": f.agent, "severity": f.severity, "category": f.category,
             "message": f.message, "details": f.details}
            for f in findings
        ],
    }, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# D5: DREAM TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def dream() -> str:
    """Execute a full dream cycle — the SFL-inspired code consolidation.

    This runs ALL 5 agents across the ENTIRE codebase and produces a
    comprehensive report with findings sorted by severity, health metrics,
    and pattern analysis. The report is also saved to .aci/dreams/.

    Takes ~10-30 seconds depending on codebase size.
    """
    engine = _get_engine()
    from aci.dream.engine import DreamEngine
    dream_engine = DreamEngine(str(engine._root))
    report = dream_engine.dream()
    return json.dumps(report.to_dict(), indent=2, default=str)


@mcp.tool
def get_dream_report() -> str:
    """Get the most recent dream report from .aci/dreams/.

    Returns the last dream cycle results without re-running analysis.
    """
    engine = _get_engine()
    dreams_dir = engine._root / ".aci" / "dreams"
    if not dreams_dir.exists():
        return json.dumps({"error": "No dream reports found. Run dream() first."})

    json_files = sorted(dreams_dir.glob("dream_*.json"), reverse=True)
    if not json_files:
        return json.dumps({"error": "No dream reports found."})

    latest = json_files[0]
    return latest.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# D6: MEMORY TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def get_score_trend() -> str:
    """Get compliance score trend across dream sessions.

    Shows how the codebase quality is evolving over time.
    Requires at least 2 dream runs to show a trend.
    """
    from aci.memory.session_memory import SessionMemory
    engine = _get_engine()
    mem = SessionMemory(str(engine._root))
    trend = mem.get_score_trend()
    return json.dumps(trend, indent=2, default=str)


@mcp.tool
def save_insight(insight: str, category: str = "general") -> str:
    """Save a development insight for future reference.

    Insights persist across sessions and are included in dream reports.
    Categories: architecture, pattern, bug, decision, todo, general.

    Args:
        insight: The insight text to save.
        category: Category for filtering later.
    """
    from aci.memory.session_memory import SessionMemory
    engine = _get_engine()
    mem = SessionMemory(str(engine._root))
    mem.save_insight(insight, category)
    return json.dumps({"saved": True, "insight": insight, "category": category})


@mcp.tool
def get_insights(category: str = "", limit: int = 20) -> str:
    """Retrieve saved development insights.

    Args:
        category: Filter by category (empty = all).
        limit: Max insights to return.
    """
    from aci.memory.session_memory import SessionMemory
    engine = _get_engine()
    mem = SessionMemory(str(engine._root))
    insights = mem.get_insights(category or None, limit)
    return json.dumps(insights, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# D7: LLM INTELLIGENCE TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def analyze_logic(file_path: str) -> str:
    """Deep logic analysis of a module using LLM.

    Goes beyond AST — identifies algorithmic flaws, mathematical errors,
    missing edge cases, and suggests better design patterns.

    Requires an LLM provider (Anthropic/OpenAI/Ollama) configured.
    Falls back to structural-only analysis if no LLM available.

    Args:
        file_path: Path to the .py file to analyze deeply.
    """
    engine = _get_engine()
    resolved = engine._resolve_path(file_path)
    if not resolved:
        return json.dumps({"error": f"File not found: {file_path}"})

    # Get structural context first
    info = engine.get_module_info(file_path)
    audit = engine.audit_module(file_path)

    # Read actual code
    try:
        code = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return json.dumps({"error": "Cannot read file"})

    # LLM analysis
    from aci.llm.provider import LLMProvider, LOGIC_ANALYSIS_SYSTEM
    llm = LLMProvider()

    if not llm.available:
        return json.dumps({
            "structural_analysis": info,
            "audit": audit,
            "llm_analysis": "[No LLM configured — set ANTHROPIC_API_KEY or OPENAI_API_KEY for deep logic analysis]",
            "setup_hint": "pip install anthropic && set ANTHROPIC_API_KEY=your_key",
        }, indent=2, default=str)

    rel = engine._relative(str(resolved))
    llm_result = llm.analyze(
        system=LOGIC_ANALYSIS_SYSTEM,
        user=f"Analyze this Python module for logic flaws:\n\nFile: {rel}\n\n```python\n{code[:12000]}\n```",
        context={"audit_score": audit, "module_info": info},
    )

    return json.dumps({
        "structural_analysis": info,
        "audit": audit,
        "llm_analysis": llm_result,
    }, indent=2, default=str)


@mcp.tool
def evolve_contract() -> str:
    """Suggest quality contract improvements based on codebase patterns.

    Uses dream history and codebase analysis to propose rule changes.
    Requires LLM for intelligent suggestions; falls back to data-only analysis.
    """
    engine = _get_engine()

    # Gather data for contract evolution
    from aci.memory.session_memory import SessionMemory
    mem = SessionMemory(str(engine._root))
    trend = mem.get_score_trend()
    insights = mem.get_insights(limit=50)

    # Get current anti-pattern stats
    anti = engine.find_anti_patterns("all")

    # Get current contract
    contract_info = {
        "name": engine.contract.name,
        "checks": engine.contract.active_checks(),
        "max_loc_per_class": engine.contract.max_loc_per_class,
        "max_loc_per_file": engine.contract.max_loc_per_file,
    }

    # Data-driven suggestions (no LLM needed)
    suggestions = []

    # Check if god_classes are common → maybe threshold is too low
    god_count = len(anti.get("findings", {}).get("god_classes", []))
    if god_count > 20:
        suggestions.append({
            "type": "adjust",
            "rule": "max_loc_per_class",
            "current": engine.contract.max_loc_per_class,
            "suggested": engine.contract.max_loc_per_class + 50,
            "reason": f"{god_count} god classes found — threshold may be too strict",
        })

    bare = len(anti.get("findings", {}).get("bare_excepts", []))
    if bare == 0:
        suggestions.append({
            "type": "info",
            "rule": "forbid_bare_except",
            "reason": "No violations found — rule is universally followed. Consider promoting to error.",
        })

    # LLM-powered suggestions
    from aci.llm.provider import LLMProvider, CONTRACT_EVOLUTION_SYSTEM
    llm = LLMProvider()

    llm_suggestions = ""
    if llm.available:
        llm_suggestions = llm.analyze(
            system=CONTRACT_EVOLUTION_SYSTEM,
            user="Analyze the codebase patterns and suggest contract improvements.",
            context={
                "current_contract": contract_info,
                "anti_pattern_stats": anti,
                "score_trend": trend,
                "recent_insights": insights[-10:],
            },
        )

    return json.dumps({
        "current_contract": contract_info,
        "data_driven_suggestions": suggestions,
        "llm_suggestions": llm_suggestions or "[Set ANTHROPIC_API_KEY for AI-driven suggestions]",
    }, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# RESOURCES
# ═══════════════════════════════════════════════════════════════

@mcp.resource("aci://contract")
def get_contract() -> str:
    """The active quality contract rules."""
    engine = _get_engine()
    return json.dumps({
        "name": engine.contract.name,
        "checks": engine.contract.active_checks(),
        "max_loc_per_class": engine.contract.max_loc_per_class,
        "max_loc_per_file": engine.contract.max_loc_per_file,
        "require_docstrings": engine.contract.require_docstrings,
        "forbid_bare_except": engine.contract.forbid_bare_except,
    }, indent=2)


# ═══════════════════════════════════════════════════════════════
# D8: CROSS-FILE VERIFICATION (§5.4, §5.5, §7)
# ═══════════════════════════════════════════════════════════════


def _get_cross_verifier():
    """Lazy-init cross-file verifier."""
    from aci.cross_file import CrossFileVerifier
    return CrossFileVerifier(_get_engine()._root)


@mcp.tool()
def verify_config_pipeline(file_path: str) -> str:
    """Verify a module's config is properly registered across the pipeline.

    Checks the 4-step config pipeline from DEVELOPMENT_GUIDE §5.5:
    1. Config @dataclass exists in the module
    2. Registered in core/hyperparams/_config_map.py
    3. Has constraints in core/hyperparams/_constraints.py
    4. Has section in config.yaml

    Args:
        file_path: Path to the .py file to verify.
    """
    verifier = _get_cross_verifier()
    result = verifier.verify_config_pipeline(file_path)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def verify_eventbus_wiring() -> str:
    """Check EventBus health across the codebase.

    Verifies DEVELOPMENT_GUIDE §5.4:
    - All topics in topics.py have publishers
    - All published topics have subscribers in wiring/
    - No string literals used instead of topic constants

    Returns orphan topics, unsubscribed publishers, and violations.
    """
    verifier = _get_cross_verifier()
    result = verifier.verify_eventbus_wiring()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def verify_persistence(scope: str = "all") -> str:
    """Check persistence safety across the codebase.

    Verifies DEVELOPMENT_GUIDE §7:
    - No unsafe open(path, 'w') without atomic write pattern
    - State files include format_version
    - torch.load uses weights_only=True

    Args:
        scope: "all" for entire codebase, or a specific directory path.
    """
    verifier = _get_cross_verifier()
    result = verifier.verify_persistence(scope)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def verify_ghost_configs() -> str:
    """Find @dataclass configurations not registered in _config_map.py.

    Returns the list of ghost/orphan configurations across the codebase
    that are not plugged into the central config memory system.
    """
    verifier = _get_cross_verifier()
    result = verifier.find_ghost_configs()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def verify_dead_api_routes() -> str:
    """Find API routes defined in api/routes/ but never included in app.py.

    Returns a list of 'dead' REST endpoints that are unreachable.
    """
    verifier = _get_cross_verifier()
    result = verifier.find_dead_api_routes()
    return json.dumps(result, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# D9: PREDICTIVE OBSERVABILITY
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def predict_observability(file_path: str) -> str:
    """Calculate an expected observability score vs actual signals.

    Heuristic engine that anticipates missing observability signals
    (telemetry, event bus, structured logging) based on structural
    DNA and topological role of a mapped module.

    Args:
        file_path: Path to the .py file to predict observability gaps.
    """
    from aci.predictive import PredictiveObservability
    predictor = PredictiveObservability(_get_engine()._root)
    result = predictor.predict_observability(file_path)
    return json.dumps(result, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# D10: CODE PHYSICS (FEP, HEBBIAN, STDP)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def get_code_physics(file_path: str) -> str:
    """Calculate the biological physics of a module within the codebase.

    Returns the Free Energy Principle metric (-1.0 to +1.0) predicting chaos,
    and STDP causality links representing EventBus pub/sub wiring.
    
    Args:
        file_path: Relative path to the .py file to analyze.
    """
    from aci.graph.physics import CodePhysics
    
    engine = _get_engine()
    physics = CodePhysics(engine._root)
    
    # We run the internal audit to get the priors vs reality matrix for FEP
    audit_res = engine.audit_module(file_path)
    info = engine.get_module_info(file_path)
    loc = info.get("total_loc", 100) if "error" not in info else 100
    
    fep_score = physics.compute_free_energy(file_path, audit_res, loc)
    
    # Pluck out the STDP causal connections specifically for this file
    all_stdp = physics.compute_stdp_weights()
    file_stdp_in = {k[0]: v for k, v in all_stdp.items() if k[1] == file_path}
    file_stdp_out = {k[1]: v for k, v in all_stdp.items() if k[0] == file_path}
    
    result = {
        "module": file_path,
        "free_energy_index": fep_score,
        "interpretation": "Chaos / Surpresa Alta" if fep_score > 0.3 else "Ordem Perfeita",
        "stdp_causality_drivers_in": file_stdp_in,
        "stdp_causality_effects_out": file_stdp_out,
    }
    
    return json.dumps(result, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# D11: MOTOR CORTEX (ACTIVE INFERENCE)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def microglia_heal_ghost_configs() -> str:
    """Motor Cortex: Autonomously heals all ghost configurations.

    Acts as the codebase immune system. Injects unmapped @dataclass
    configurations directly into the static _config_map.py dictionary.
    """
    from aci.motor_cortex.microglia import MicrogliaHealer
    
    engine = _get_engine()
    healer = MicrogliaHealer(engine._root)
    result = healer.heal_ghost_configs()
    
    return json.dumps(result, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════


def main():
    """Run the ACI MCP server."""
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
