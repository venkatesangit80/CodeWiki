import json
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class DocumentAssembler:
    @staticmethod
    def clean_json_string(raw: str) -> str:
        # Strip code blocks ```json or ``` if present
        clean = raw.strip()
        if clean.startswith("```"):
            # Remove start
            clean = re.sub(r"^```(json)?\n", "", clean)
            # Remove end
            clean = re.sub(r"\n```$", "", clean)
        return clean.strip()

    @classmethod
    def render_mermaid_diagram(cls, raw_json_str: str) -> str:
        """
        Parses structured JSON diagram specs and deterministically outputs 
        syntactically correct Mermaid markup.
        """
        try:
            cleaned = cls.clean_json_string(raw_json_str)
            data = json.loads(cleaned)
        except Exception as e:
            logger.error(f"Error parsing diagram JSON: {e}. Raw: {raw_json_str}")
            return "```\n[Diagram JSON parse error - verify source manually]\n```"

        diagram_type = data.get("type", "flowchart").lower()
        
        if diagram_type == "flowchart":
            lines = ["flowchart TD"]
            # Declare nodes with escaped labels to prevent syntax issues
            nodes = data.get("nodes", [])
            for node in nodes:
                nid = node.get("id", "").replace(".", "_").replace("::", "_").replace(" ", "_")
                label = node.get("label", "").replace('"', '\\"')
                lines.append(f'    {nid}["{label}"]')
                
            # Declare edges
            edges = data.get("edges", [])
            for edge in edges:
                u = edge.get("from", "").replace(".", "_").replace("::", "_").replace(" ", "_")
                v = edge.get("to", "").replace(".", "_").replace("::", "_").replace(" ", "_")
                label = edge.get("label", "")
                if label:
                    lines.append(f'    {u} -->|"{label}"| {v}')
                else:
                    lines.append(f'    {u} --> {v}')
                    
            return "```mermaid\n" + "\n".join(lines) + "\n```"
            
        elif diagram_type == "sequence":
            lines = ["sequenceDiagram"]
            participants = data.get("participants", [])
            for p in participants:
                p_id = p.replace(".", "_").replace(" ", "_")
                lines.append(f'    participant {p_id} as {p}')
                
            steps = data.get("steps", [])
            for step in steps:
                u = step.get("from", "").replace(".", "_").replace(" ", "_")
                v = step.get("to", "").replace(".", "_").replace(" ", "_")
                msg = step.get("message", "").replace('"', '\\"')
                lines.append(f'    {u}->>{v}: {msg}')
                
            return "```mermaid\n" + "\n".join(lines) + "\n```"
            
        return "```\n[Unknown diagram type in JSON schema]\n```"

    @classmethod
    def assemble_hldd(cls, hldd_data: Dict[str, str]) -> str:
        """
        Assembles HLDD sections and diagram into a cohesive Markdown document.
        """
        overview = hldd_data.get("overview", "# High-Level Design Document\n\nNo overview generated.")
        components = hldd_data.get("components", "## Component Inventory\n\nNo components inventory.")
        diagram_json = hldd_data.get("diagram_json", "")
        tech_stack = hldd_data.get("tech_stack", "## Technology Stack\n\nNo tech stack specified.")
        
        mermaid_chart = cls.render_mermaid_diagram(diagram_json)
        
        assembled = (
            f"{overview}\n\n"
            "## Architecture Diagram\n\n"
            f"{mermaid_chart}\n\n"
            f"{components}\n\n"
            f"{tech_stack}\n"
        )
        return assembled

    @classmethod
    def assemble_lldd(cls, lldd_modules: List[Dict[str, Any]]) -> str:
        """
        Assembles LLDD modules into a singular comprehensive Markdown document.
        """
        assembled_sections = ["# Low-Level Design Document (LLDD)\n"]
        
        for idx, mod in enumerate(lldd_modules):
            name = mod.get("module_name", f"Module {idx}")
            details = mod.get("details", "No details available.")
            diag_json = mod.get("diagram_json", "")
            
            mermaid = cls.render_mermaid_diagram(diag_json)
            
            section = (
                f"## Module: {name}\n\n"
                f"### Relationships & Calls\n\n"
                f"{mermaid}\n\n"
                f"{details}\n\n"
                "---"
            )
            assembled_sections.append(section)
            
        return "\n".join(assembled_sections)
