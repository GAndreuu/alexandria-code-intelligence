"""
ACI :: Code Graph (Hebbian-inspired)
=====================================
Models the codebase as a weighted graph where:
- Nodes = Python modules (files)
- Edges = import relationships + structural similarity

Edge weights use a Hebbian-inspired rule:
  w(A,B) = import_weight + co_change_weight + similarity_weight

Supports community detection and coupling metrics.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from aci.perception.import_resolver import ImportGraph, ResolvedImport

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the code graph (one Python module)."""
    path: str
    loc: int
    total_classes: int
    total_functions: int
    layer: Optional[str] = None
    community: Optional[int] = None

    # Coupling metrics (computed later)
    afferent: int = 0   # incoming deps (who imports me)
    efferent: int = 0   # outgoing deps (who I import)

    @property
    def instability(self) -> float:
        """Martin's instability metric: Ce / (Ca + Ce). 0=stable, 1=unstable."""
        total = self.afferent + self.efferent
        return self.efferent / total if total > 0 else 0.5


@dataclass
class GraphEdge:
    """A weighted edge between two modules."""
    source: str
    target: str
    weight: float = 1.0
    edge_type: str = "import"  # import | co_change | similarity


@dataclass
class CodeGraph:
    """Hebbian-inspired code dependency graph."""
    nodes: Dict[str, GraphNode]
    edges: List[GraphEdge]
    root: str

    def neighbors(self, path: str) -> List[Tuple[str, float]]:
        """Get all neighbors of a node with weights."""
        result = []
        for e in self.edges:
            if e.source == path:
                result.append((e.target, e.weight))
            elif e.target == path:
                result.append((e.source, e.weight))
        return result

    def dependents_of(self, path: str) -> List[str]:
        """Modules that import this one."""
        return [e.source for e in self.edges if e.target == path and e.edge_type == "import"]

    def dependencies_of(self, path: str) -> List[str]:
        """Modules this one imports."""
        return [e.target for e in self.edges if e.source == path and e.edge_type == "import"]

    def subgraph(self, path: str, depth: int = 2) -> "CodeGraph":
        """Extract local neighborhood subgraph."""
        visited: Set[str] = set()
        frontier = {path}

        for _ in range(depth):
            next_frontier: Set[str] = set()
            for node in frontier:
                if node in visited:
                    continue
                visited.add(node)
                for neighbor, _ in self.neighbors(node):
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
            frontier = next_frontier

        visited.add(path)
        sub_nodes = {p: n for p, n in self.nodes.items() if p in visited}
        sub_edges = [
            e for e in self.edges
            if e.source in visited and e.target in visited
        ]
        return CodeGraph(nodes=sub_nodes, edges=sub_edges, root=self.root)

    def find_cycles(self) -> List[List[str]]:
        """Detect circular dependencies using DFS."""
        cycles: List[List[str]] = []
        adj: Dict[str, List[str]] = defaultdict(list)
        for e in self.edges:
            if e.edge_type == "import":
                adj[e.source].append(e.target)

        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {n: WHITE for n in self.nodes}
        path: List[str] = []

        def dfs(u: str) -> None:
            color[u] = GRAY
            path.append(u)
            for v in adj.get(u, []):
                if v not in color:
                    continue
                if color[v] == GRAY:
                    idx = path.index(v)
                    cycles.append(path[idx:] + [v])
                elif color[v] == WHITE:
                    dfs(v)
            path.pop()
            color[u] = BLACK

        for node in self.nodes:
            if color.get(node, WHITE) == WHITE:
                dfs(node)

        return cycles

    def find_bridges(self, top_k: int = 10) -> List[Tuple[str, float]]:
        """Find bridge nodes (high betweenness approximation).

        Uses a simplified approach: nodes whose removal would
        disconnect the most edges.
        """
        scores: Dict[str, float] = {}
        for path in self.nodes:
            in_edges = len(self.dependents_of(path))
            out_edges = len(self.dependencies_of(path))
            # Bridge score: product of in/out (high when connecting many)
            scores[path] = math.sqrt(in_edges * out_edges) if in_edges and out_edges else 0.0

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return ranked[:top_k]

    def find_orphans(self) -> List[str]:
        """Modules with no dependents (nobody imports them)."""
        imported = set()
        for e in self.edges:
            if e.edge_type == "import":
                imported.add(e.target)

        return [
            p for p in self.nodes
            if p not in imported
            and not p.endswith("__init__.py")
            and not p.endswith("__main__.py")
        ]

    def stats(self) -> Dict[str, Any]:
        """Summary statistics."""
        import_edges = [e for e in self.edges if e.edge_type == "import"]
        total_loc = sum(n.loc for n in self.nodes.values())
        return {
            "total_modules": len(self.nodes),
            "total_edges": len(import_edges),
            "total_loc": total_loc,
            "avg_loc": total_loc / max(len(self.nodes), 1),
            "orphan_count": len(self.find_orphans()),
            "cycle_count": len(self.find_cycles()),
        }


class CodeGraphBuilder:
    """Builds a CodeGraph from an ImportGraph."""

    def build(self, import_graph: ImportGraph) -> CodeGraph:
        """Convert ImportGraph → CodeGraph with weighted edges."""
        from aci.graph.physics import CodePhysics
        from pathlib import Path
        
        physics = CodePhysics(Path(import_graph.root))
        hebbian_weights = physics.compute_hebbian_weights()
        stdp_weights = physics.compute_stdp_weights()

        nodes: Dict[str, GraphNode] = {}
        edges: List[GraphEdge] = []

        # Create nodes
        for path, info in import_graph.nodes.items():
            nodes[path] = GraphNode(
                path=path,
                loc=info.loc,
                total_classes=info.total_classes,
                total_functions=info.total_functions,
            )

        # Create edges from internal imports
        import_pairs = set()
        for imp in import_graph.internal_edges:
            if imp.target_path and imp.target_path in nodes:
                pair = (imp.source_path, imp.target_path)
                import_pairs.add(pair)
                
                h_weight = hebbian_weights.get(tuple(sorted([imp.source_path, imp.target_path])), 0.0)
                s_weight = stdp_weights.get(pair, 0.0)

                edges.append(GraphEdge(
                    source=imp.source_path,
                    target=imp.target_path,
                    weight=1.0 + h_weight + s_weight,
                    edge_type="import",
                ))

        # Add biological invisible edges (STDP Pub/Sub)
        for (f1, f2), w in stdp_weights.items():
            if (f1, f2) not in import_pairs and f1 in nodes and f2 in nodes:
                edges.append(GraphEdge(source=f1, target=f2, weight=w, edge_type="stdp_causality"))
                
        # Add biological invisible edges (Hebbian Co-Churn)
        for (f1, f2), w in hebbian_weights.items():
            if (f1, f2) not in import_pairs and (f2, f1) not in import_pairs and f1 in nodes and f2 in nodes:
                edges.append(GraphEdge(source=f1, target=f2, weight=w, edge_type="hebbian_cochurn"))

        # Compute coupling metrics
        for path, node in nodes.items():
            node.afferent = len(import_graph.dependents_of(path))
            node.efferent = len(import_graph.dependencies_of(path))

        graph = CodeGraph(nodes=nodes, edges=edges, root=import_graph.root)

        logger.info(
            "Code graph built")
        return graph
