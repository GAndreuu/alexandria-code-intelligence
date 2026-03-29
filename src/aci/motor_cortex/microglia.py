"""
Motor Cortex :: Microglia Healer
================================
Autonomously mutates the codebase AST / text to fix Technical Debt and Prediction Errors.

This is the manifestation of Alexandria's Active Inference (Acting on the Environment).
"""
import logging
import re
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class MicrogliaHealer:
    """The auto-fixing motor agent that mutates project files to enforce invariants."""

    def __init__(self, root: Path):
        self.root = root

    def heal_ghost_configs(self) -> Dict[str, Any]:
        """Auto-injects all ghost configs into `_config_map.py`."""
        from aci.cross_file import CrossFileVerifier
        verifier = CrossFileVerifier(self.root)
        
        # 1. Perceive: Find the surprise (missing configs)
        ghost_res = verifier.find_ghost_configs()
        ghosts = ghost_res.get("ghost_configs", [])
        
        if not ghosts:
            return {"status": "success", "healed_count": 0, "message": "No ghost configs found. Perfect order."}
            
        # 2. Act: Open the Motor Target
        config_map_path = self.root / "core" / "hyperparams" / "_config_map.py"
        if not config_map_path.exists():
            return {"status": "error", "message": "_config_map.py not found"}
            
        text = config_map_path.read_text(encoding="utf-8")
        
        # We need to find the ending bracket `}` of the `_CONFIG_MAP = {` dict.
        match_start = re.search(r"_CONFIG_MAP\s*=\s*\{", text)
        if not match_start:
            return {"status": "error", "message": "Could not locate _CONFIG_MAP dictionary block"}
            
        # Parse and prep lines
        injections = []
        for ghost in ghosts:
            cls_name = ghost["class"]
            # Generate a keyname like `GraphDreamerConfig` -> `graph_dreamer`
            key_name = cls_name.replace("Config", "")
            # Convert CamelCase to snake_case
            key_name = re.sub(r'(?<!^)(?=[A-Z])', '_', key_name).lower()
            if not key_name:
                key_name = cls_name.lower()
                
            # Path formatting: `core/field/solvers/graph_geometry.py` -> `core.field.solvers.graph_geometry`
            f_path = ghost["file"].replace(".py", "").replace("\\", "/").replace("/", ".")
            
            line = f'    "{key_name}": ("{f_path}", "{cls_name}"),'
            injections.append(line)
            
        # Inject at the exact point: the last occurrence of `}` just before EOF or after dict
        lines = text.splitlines()
        
        # Find the line index of `_CONFIG_MAP = {`
        start_idx = -1
        for i, l in enumerate(lines):
            if l.startswith("_CONFIG_MAP = {") or l.strip().startswith("_CONFIG_MAP = {"):
                start_idx = i
                break
                
        if start_idx == -1:
            return {"status": "error", "message": "Could not parse _CONFIG_MAP definition line"}
            
        # Find the closing dict bracket
        end_idx = -1
        bracket_count = 0
        in_dict = False
        for i in range(start_idx, len(lines)):
            l = lines[i]
            if "{" in l:
                bracket_count += l.count("{")
                in_dict = True
            if "}" in l:
                bracket_count -= l.count("}")
                
            if in_dict and bracket_count == 0:
                end_idx = i
                break
                
        if end_idx == -1:
            return {"status": "error", "message": "Malformed dictionary format"}
            
        # Mutate the file
        label = "    # 🦠 Microglia Healed Configs"
        
        lines.insert(end_idx, label)
        for idx, new_line in enumerate(injections, 1):
            lines.insert(end_idx + idx, new_line)
            
        new_text = "\n".join(lines) + "\n"
        
        # 3. Memory Consolidation: Save the modified code
        config_map_path.write_text(new_text, encoding="utf-8")
        
        return {
            "status": "success",
            "healed_count": len(ghosts),
            "affected_file": "_config_map.py",
            "injected_lines": injections
        }
