import os
import json
import logging
import re
from typing import Dict, List, Any, Optional, Set

# Local imports
from codedoc_generator.config import GeneratorConfig
from codedoc_generator.vector_store import LocalVectorStore
from codedoc_generator.llm_client import (
    BaseLLMClient,
    HTTPCompletionsClient,
    NatsCompletionsClient,
    PythonFallbackClient
)

logger = logging.getLogger(__name__)

class GeneratorOrchestrator:
    def __init__(self, config: GeneratorConfig, vector_store: LocalVectorStore, dependency_edges: List[Dict[str, Any]], entry_points: List[Dict[str, Any]]):
        self.config = config
        self.vector_store = vector_store
        self.edges = dependency_edges
        self.entry_points = entry_points
        
        # Instantiate pluggable LLM client
        provider = self.config.llm.provider.lower()
        if provider == "nats":
            self.llm_client: BaseLLMClient = NatsCompletionsClient(config)
        elif provider in ["ollama", "vllm", "lmstudio", "openai-compatible"]:
            self.llm_client: BaseLLMClient = HTTPCompletionsClient(config)
        else:
            self.llm_client: BaseLLMClient = PythonFallbackClient(config)

    def _get_package_name(self, file_path: str) -> str:
        parts = os.path.dirname(file_path).split(os.sep)
        if "java" in parts:
            java_idx = parts.index("java")
            pkg = ".".join(parts[java_idx+1:])
            return pkg if pkg else "default_package"
        return os.path.dirname(file_path) if os.path.dirname(file_path) else "root"

    async def generate_hldd(self) -> Dict[str, str]:
        """Runs HLDD generation pass. Uses LLM if configured; otherwise runs programmatic fallback."""
        logger.info(f"Generating HLDD using provider: {self.config.llm.provider}")
        
        # 1. Gather global metrics & unique files
        res = self.vector_store.retrieve("", {"repo_id": self.config.repos[0].repo_id}, top_k=10000)
        unique_files = set()
        classes_count = 0
        methods_count = 0
        file_symbols: Dict[str, List[Dict[str, Any]]] = {}
        package_to_files: Dict[str, List[str]] = {}
        
        for record, _ in res:
            meta = record.metadata
            unique_files.add(record.file_path)
            file_symbols.setdefault(record.file_path, []).append(meta)
            pkg = self._get_package_name(record.file_path)
            if record.file_path not in package_to_files.setdefault(pkg, []):
                package_to_files[pkg].append(record.file_path)
                
            if meta.get("kind") == "class":
                classes_count += 1
            elif meta.get("kind") in ["method", "function"]:
                methods_count += 1

        # 2. Package-collapsed Global Diagram
        unique_packages = sorted(list(package_to_files.keys()))
        pkg_id_map = {pkg: f"pkg_{idx}" for idx, pkg in enumerate(unique_packages)}
        diagram_nodes = [{"id": pid, "label": pkg} for pkg, pid in pkg_id_map.items()]
        diagram_edges = []
        added_pkg_edges = set()
        for edge in self.edges:
            if edge["type"] == "imports":
                pkg_from = self._get_package_name(edge["from"])
                pkg_to = self._get_package_name(edge["to"])
                if pkg_from in pkg_id_map and pkg_to in pkg_id_map and pkg_from != pkg_to:
                    edge_key = f"{pkg_from}->{pkg_to}"
                    if edge_key not in added_pkg_edges:
                        added_pkg_edges.add(edge_key)
                        diagram_edges.append({
                            "from": pkg_id_map[pkg_from],
                            "to": pkg_id_map[pkg_to],
                            "label": "depends on"
                        })
        diagram_json_str = json.dumps({"type": "flowchart", "nodes": diagram_nodes, "edges": diagram_edges})

        # 3. Create subfolder diagrams
        subsystems_md_lines = ["\n## 4. Subsystem Package Diagrams (Chunk-by-Chunk Details)\n"]
        for pkg, files in sorted(package_to_files.items()):
            if len(files) > 1:
                subsystems_md_lines.append(f"### Package: `{pkg}`\n")
                sub_nodes = []
                sub_edges = []
                file_id_map = {}
                for idx, f in enumerate(sorted(files)):
                    fid = f"f_{idx}"
                    file_id_map[f] = fid
                    sub_nodes.append(f'    {fid}["{os.path.basename(f)}"]')
                
                added_sub_edges = set()
                for edge in self.edges:
                    if edge["type"] == "imports":
                        fr = edge["from"]
                        to = edge["to"]
                        if fr in file_id_map and to in file_id_map:
                            edge_key = f"{fr}->{to}"
                            if edge_key not in added_sub_edges:
                                added_sub_edges.add(edge_key)
                                sub_edges.append(f"    {file_id_map[fr]} --> {file_id_map[to]}")
                
                subsystems_md_lines.append("```mermaid\nflowchart TD")
                subsystems_md_lines.extend(sub_nodes)
                if sub_edges:
                    subsystems_md_lines.extend(sub_edges)
                else:
                    subsystems_md_lines.append("    %% No internal module dependencies found")
                subsystems_md_lines.append("```\n")

        # 4. Generate text contents
        is_fallback = isinstance(self.llm_client, PythonFallbackClient)
        
        if is_fallback:
            # Programmatic overview fallback
            overview_md = (
                "# High-Level Design Document (HLDD)\n\n"
                "## 1. Executive Summary & System Context\n\n"
                "This document provides a structurally-derived architectural layout of the repository. "
                "It outlines components, interactions, and entry points analyzed programmatically from the AST and codebase dependencies.\n\n"
                "### Codebase Telemetry Metrics:\n"
                f"- **Analyzed Directory:** `{self.config.repos[0].local_path}`\n"
                f"- **Total Source Files:** {len(unique_files)}\n"
                f"- **Total Classes:** {classes_count}\n"
                f"- **Total Methods / Functions:** {methods_count}\n"
                f"- **Detected System Entry Points:** {len(self.entry_points)}\n"
                f"- **Resolved Dependency Links:** {len(self.edges)}\n"
            )
            
            component_lines = [
                "## 2. Component Inventory & Responsibilities\n\n"
                "| Component File | Size / Location | Type | Public Symbols / Interfaces |",
                "| :--- | :--- | :--- | :--- |"
            ]
            for file_path, syms in sorted(file_symbols.items()):
                symbol_names = [s.get("name", "") for s in syms if s.get("kind") in ["class", "function"]]
                symbols_str = ", ".join(f"`{name}`" for name in symbol_names[:5])
                if len(symbol_names) > 5:
                    symbols_str += f" (+{len(symbol_names)-5} more)"
                kind = "Module Root" if file_path.endswith("__init__.py") else "Implementation File"
                component_lines.append(f"| [`{file_path}`](file://{os.path.join(self.config.repos[0].local_path, file_path)}) | `{file_path}` | {kind} | {symbols_str or '*No classes/functions*'} |")
            components_md = "\n".join(component_lines) + "\n\n" + "\n".join(subsystems_md_lines)

            tech_lines = ["## 3. Technology Stack & Core Imports\n\nThe system relies on the following primary packages:\n"]
            third_party_imports = set()
            for r, _ in res:
                for imp in r.metadata.get("imports", []):
                    root_pkg = imp.split(".")[0]
                    if root_pkg and root_pkg not in self.config.analysis.ignore_paths:
                        third_party_imports.add(root_pkg)
            for pkg in sorted(third_party_imports):
                tech_lines.append(f"- **`{pkg}`** (Core framework / utility module)")
            tech_md = "\n".join(tech_lines)
            
        else:
            # Call LLM to generate professional English descriptions
            context_summary = (
                f"Repository: {self.config.repos[0].repo_id}\n"
                f"File metrics: {len(unique_files)} files, {classes_count} classes, {methods_count} methods.\n"
                f"Detected Entry Points: {json.dumps(self.entry_points[:15], indent=2)}\n"
                f"Core Files List: {list(unique_files)[:30]}"
            )
            
            system_prompt = (
                "You are a professional software architect. Generate the specified section of a High-Level Design Document (HLDD).\n"
                "Write in professional English with deep technical clarity. Ground descriptions in code metrics, citing files where possible.\n"
                "Cite file paths in brackets, e.g. [file.py:L10-25] or [ClassName.java]."
            )
            
            # Overview Section
            overview_task = self.llm_client.generate_completion(
                system_prompt,
                f"Generate Section 1: Executive Summary & System Context. Introduce the repository architecture based on:\n{context_summary}"
            )
            # Component Inventory Section
            comp_task = self.llm_client.generate_completion(
                system_prompt,
                f"Generate Section 2: Component Inventory & Core Module Responsibilities. Summarize key directories and file mappings. Context:\n{context_summary}"
            )
            # Tech Stack Section
            tech_task = self.llm_client.generate_completion(
                system_prompt,
                f"Generate Section 3: Technology Stack & Third-party Integrations. Describe frameworks used (e.g. Spring, FastAPI, tree-sitter). Context:\n{context_summary}"
            )
            
            import asyncio
            overview_md, raw_comp, tech_md = await asyncio.gather(overview_task, comp_task, tech_task)
            components_md = f"{raw_comp}\n\n" + "\n".join(subsystems_md_lines)

        return {
            "overview": overview_md,
            "components": components_md,
            "diagram_json": diagram_json_str,
            "tech_stack": tech_md
        }

    def _analyze_ingress_egress(self, res_records: List[Any]) -> Dict[str, List[str]]:
        ingress = [f"{ep.get('kind', '').capitalize()} `{ep.get('name', '')}` in `{ep.get('file_path', '')}`" for ep in self.entry_points]
        egress_set = set()
        
        # Heuristics for egress detection
        db_keywords = ["jdbc", "jpa", "repository", "db", "session", "connection", "query", "sql", "cursor", "insert", "select", "update"]
        net_keywords = ["http", "client", "request", "post", "get", "api", "url", "kafka", "producer", "publish", "send", "nats", "nc."]
        file_keywords = ["write", "file", "output", "open", "save"]
        xpress_keywords = ["xprs", "xprb", "dashoptimization", "xpress"]
        
        for r in res_records:
            meta = r.metadata
            content = r.chunk_text.lower()
            file_name = r.file_path.lower()
            
            for word in db_keywords:
                if word in content or word in file_name:
                    egress_set.add(f"Database Connectivity (e.g. Repository / Queries in `{r.file_path}`)")
            for word in net_keywords:
                if word in content or word in file_name:
                    if "kafka" in word:
                        egress_set.add(f"Message Queue / Kafka Producer in `{r.file_path}`")
                    elif "nats" in word:
                        egress_set.add(f"NATS Messaging Bus client in `{r.file_path}`")
                    else:
                        egress_set.add(f"Outbound External HTTP/API Client in `{r.file_path}`")
            for word in file_keywords:
                if word in content:
                    egress_set.add(f"File System Writes / Local I/O operations in `{r.file_path}`")
            if re.search(r'\bxpress\b|\bxpr[sb]\b|dashoptimization', content) or re.search(r'\bxpress\b|\bxpr[sb]\b|dashoptimization', file_name):
                egress_set.add(f"In-Process Native C++ Execution (FICO Xpress Optimizer JNI calls in `{r.file_path}`)")
                    
        return {
            "ingress": ingress if ingress else ["*No explicit routes/CLI main triggers detected*"],
            "egress": sorted(list(egress_set)) if egress_set else ["*Standard internal processing (no obvious external egress)*"]
        }

    def _analyze_performance_challenges(self, res_records: List[Any]) -> List[str]:
        challenges = []
        for r in res_records:
            content = r.chunk_text
            file_name = r.file_path
            
            # Simple static heuristics
            if "synchronized" in content or "lock" in content.lower():
                challenges.append(f"Thread Synchronisation / Locking: Detected blocking locks in `{file_name}` which may limit concurrent performance.")
            if "for " in content and content.count("for ") > 1 and ("while" in content or "for " in content[content.find("for ")+4:]):
                challenges.append(f"Nested Loops: Potential O(N^2) or higher computational complexity in `{file_name}`.")
            if "Thread" in content or "Executor" in content or "ThreadPool" in content:
                challenges.append(f"Multi-threading Overhead: Manual thread creation or executor pool configuration in `{file_name}`.")
            if "sleep(" in content or "sleepAsync" in content:
                challenges.append(f"Explicit Sleep/Blocking: Delay execution statements found in `{file_name}`.")
                
        return sorted(list(set(challenges)))[:8]

    def _generate_boundary_flow_mermaid(self, flow_data: Dict[str, List[str]]) -> str:
        lines = ["flowchart LR"]
        
        # Ingress Subgraph
        lines.append("    subgraph Ingress [\"System Ingress (Entry Points)\"]")
        ing_nodes = []
        seen_ingress = set()
        for idx, ing in enumerate(flow_data["ingress"]):
            clean_ing = ing.replace("`", "").split(" in ")[0].strip()
            if clean_ing not in seen_ingress:
                seen_ingress.add(clean_ing)
                node_id = f"ing_{len(seen_ingress)}"
                lines.append(f'        {node_id}["{clean_ing}"]')
                ing_nodes.append(node_id)
        lines.append("    end")
        
        # Execution Subgraph
        lines.append("    subgraph Execution [\"Core Processing Execution\"]")
        lines.append('        exec_ctrl["Controllers / Request Routers"]')
        lines.append('        exec_svc["Service Orchestrators"]')
        lines.append('        exec_solve["Core Logic / Optimization Solver"]')
        lines.append('        exec_ctrl --> exec_svc --> exec_solve')
        lines.append("    end")
        
        # Egress Subgraph
        lines.append("    subgraph Egress [\"System Egress (Outbound Dependencies)\"]")
        eg_nodes = []
        seen_egress = set()
        for idx, eg in enumerate(flow_data["egress"]):
            clean_eg = eg.replace("`", "").split(" in ")[0].strip()
            if clean_eg not in seen_egress:
                seen_egress.add(clean_eg)
                node_id = f"eg_{len(seen_egress)}"
                lines.append(f'        {node_id}["{clean_eg}"]')
                eg_nodes.append(node_id)
        lines.append("    end")
        
        # Connect Ingress to Execution and Execution to Egress
        for ing_node in ing_nodes:
            lines.append(f"    {ing_node} --> exec_ctrl")
        for eg_node in eg_nodes:
            lines.append(f"    exec_solve --> {eg_node}")
            
        return "```mermaid\n" + "\n".join(lines) + "\n```"

    async def generate_architecture_synthesis(self) -> str:
        """Generates a separate comprehensive Architecture & Operations Synthesis Document."""
        logger.info("Generating Architecture & Operations Synthesis Document")
        res = self.vector_store.retrieve("", {"repo_id": self.config.repos[0].repo_id}, top_k=10000)
        
        # Analyze Ingress / Egress and Performance programmatically
        flow_data = self._analyze_ingress_egress([r for r, _ in res])
        perf_data = self._analyze_performance_challenges([r for r, _ in res])
        
        # Collapse the Global diagram to Package-level to keep it highly clean and readable!
        package_to_files = {}
        for r, _ in res:
            pkg = self._get_package_name(r.file_path)
            package_to_files.setdefault(pkg, []).append(r.file_path)
            
        unique_packages = sorted(list(package_to_files.keys()))
        pkg_id_map = {pkg: f"pkg_{idx}" for idx, pkg in enumerate(unique_packages)}
        
        lines = ["flowchart TD"]
        for pkg, pid in pkg_id_map.items():
            lines.append(f'    {pid}["{pkg}"]')
            
        added_pkg_edges = set()
        for edge in self.edges:
            if edge["type"] == "imports":
                pkg_from = self._get_package_name(edge["from"])
                pkg_to = self._get_package_name(edge["to"])
                if pkg_from in pkg_id_map and pkg_to in pkg_id_map and pkg_from != pkg_to:
                    edge_key = f"{pkg_from}->{pkg_to}"
                    if edge_key not in added_pkg_edges:
                        added_pkg_edges.add(edge_key)
                        lines.append(f"    {pkg_id_map[pkg_from]} --> {pkg_id_map[pkg_to]}")
        package_mermaid = "```mermaid\n" + "\n".join(lines) + "\n```"
        boundary_mermaid = self._generate_boundary_flow_mermaid(flow_data)

        is_fallback = isinstance(self.llm_client, PythonFallbackClient)
        
        if is_fallback:
            # Programmatic Document Compilation
            ingress_list = "\n".join(f"- {ing}" for ing in flow_data["ingress"])
            egress_list = "\n".join(f"- {eg}" for eg in flow_data["egress"])
            perf_list = "\n".join(f"- {perf}" for perf in perf_data) if perf_data else "- *No obvious O(N^2) loops or locks found via static AST triggers.*"
            
            doc = (
                "# Architecture & Operations Synthesis Document\n\n"
                "This document details system topology, interface interfaces, and operational characteristics analyzed from the codebase.\n\n"
                "## 1. High-Level Package Interactions\n\n"
                f"{package_mermaid}\n\n"
                "## 2. Ingress, Execution & Egress Boundary Flow\n\n"
                f"{boundary_mermaid}\n\n"
                "## 3. Ingress & Egress Boundaries\n\n"
                "### Ingress Entry Points:\n"
                f"{ingress_list}\n\n"
                "### Egress Systems & Connections:\n"
                f"{egress_list}\n\n"
                "## 4. Performance Challenges & Bottlenecks\n\n"
                "The following code structures were identified as potential bottlenecks or scaling issues:\n"
                f"{perf_list}\n"
            )
            return doc
            
        else:
            key_chunks = self.vector_store.retrieve(
                "performance bottlenecks, nested loops, blocking locks, thread pool concurrency, native memory JNI C++ C allocation, resource release close dispose free leak, controller ingress egress endpoints, connection idle timeout, KafkaConfig, connections.max.idle.ms, liveness probe health check webapp.yaml, singleton state contamination, volatile kill flags, concurrent requests",
                {"repo_id": self.config.repos[0].repo_id},
                top_k=40
            )
            code_context_blocks = []
            for record, _ in key_chunks:
                symbol_name = record.metadata.get("name", "unknown")
                code_context_blocks.append(f"--- File: {record.file_path} (Symbol: {symbol_name}) ---\n{record.chunk_text}\n")
            code_context_str = "\n".join(code_context_blocks)
            
            # Prompt the LLM for deep professional narration of architecture and data flow
            system_prompt = (
                "You are a principal software architect. You are writing the final 'Architecture & Operations Synthesis' report for a system.\n"
                "Analyze the technical stack, data flows, and performance characteristics with extreme technical accuracy and professional tone.\n"
                "Specifically audit the code and configuration for:\n"
                "1. Resource leaks and native memory allocation JNI/C++ risks: Audit for instances where native dynamic objects are allocated but not explicitly disposed or closed in finally blocks. Note: Do not flag native dependencies, database backends, or off-heap state stores that are managed entirely at the framework level as user-code leaks. Only report leaks where the application source code explicitly allocates native/off-heap resources or unmanaged dynamic connections and fails to release them.\n"
                "2. Concurrency hazards, thread safety risks, and singleton state contamination: Audit for shared mutable instances or singleton services that manage request/session state in instance variables without proper thread isolation.\n"
                "3. Ingestion/Loop inefficiencies, specifically auditing for linear scans (O(N) search loops over arrays/lists) performed per record within a streaming environment instead of map-based lookup caching.\n"
                "4. Date/Timezone comparison vulnerabilities, specifically auditing for the usage of simple equality operators (==) or Objects.equals() on date objects/strings (e.g. DateTimeInfo) which can fail due to timezone notation mismatch (e.g., '+00:00' vs 'Z') or differing precision.\n"
                "5. Silent logic fallbacks, specifically auditing for catch-blocks or conditional branches that silently default critical state parameters (e.g., collapsing original indices/timestamps to current/latest ones) without throwing exceptions, logging errors, or emitting warning diagnostics.\n"
                "6. Silent connection drops: Audit configuration settings for connection idle limits (e.g. connections.max.idle.ms) to verify connection recycling policies match broker/event hub idle timeouts.\n"
                "7. Liveness probe and monitoring failures: Audit deployment configurations for health checks or liveness probe intervals that might prematurely kill long-running batch operations or fail to report native/blocked thread hangs.\n"
                "8. Core DFD Risk Overlay: In the Core Data Flow Diagram (DFD) generated in Section 1, you MUST overlay and visually highlight any nodes representing classes or components that contain the High or Critical severity vulnerabilities identified in your Section 3 audit. Style these risk nodes using custom Mermaid styles (e.g., style NodeName fill:#ffcccc,stroke:#ff3333,stroke-width:2px) so they are immediately visible.\n"
                "9. Performance Issues Summary: You MUST include a distinct section titled 'Performance Issues Summary' that lists a concise, 1-line bullet point summary for every performance issue, JNI leak, or technical vulnerability identified in your audit.\n"
                "Be detailed, descriptive, and reference code symbols/files precisely.\n"
                "CRITICAL MERMAID SYNTAX RULE: If you generate any Mermaid diagrams, you MUST wrap any node labels containing parenthesis, brackets, or other special characters in double quotes to prevent rendering syntax errors (e.g. J[\"OptModel (JNI)\"] or K[\"Output Service\"])."
            )
            
            user_content = (
                f"Write a comprehensive professional analysis based on these codebase findings and source code definitions:\n\n"
                f"### Code Context Summary (Key Files & Configuration):\n{code_context_str}\n\n"
                f"### System Ingress (Entry points):\n{json.dumps(flow_data['ingress'], indent=2)}\n\n"
                f"### System Egress (Outgoing dependencies):\n{json.dumps(flow_data['egress'], indent=2)}\n\n"
                "Include sections on:\n"
                "1. Core Data Flow Diagram (DFD) that visually highlights and colors the high-severity risk nodes/components matching the findings from Section 3.\n"
                "2. Performance Issues Summary: A bulleted list of 1-line summaries for each identified issue (including state manager thread safety, connection timeouts, liveness probes, native leaks, and loop/scan bottlenecks).\n"
                "3. Detailed Ingress and Egress interface boundaries.\n"
                "4. Inferred Performance Challenges (specifically audit the code files, identifying CPU bottlenecks, JNI/native heap leaks, blocking thread pools, database locks, or external request delays).\n"
                "Make the explanation thorough and clear."
            )
            
            llm_narrative = await self.llm_client.generate_completion(system_prompt, user_content)
            
            # Post-process to fix any unquoted Mermaid node labels containing parentheses/special characters
            # e.g., L[OptModel (JNI)] -> L["OptModel (JNI)"]
            sanitized_lines = []
            in_mermaid = False
            for line in llm_narrative.splitlines():
                if "```mermaid" in line:
                    in_mermaid = True
                elif in_mermaid and "```" in line:
                    in_mermaid = False
                
                if in_mermaid:
                    match = re.search(r'(\b\w+)(\[|\(|\{)', line)
                    if match:
                        node_id = match.group(1)
                        open_char = match.group(2)
                        start_idx = match.start(2)
                        close_char = ']' if open_char == '[' else ')' if open_char == '(' else '}'
                        end_idx = line.rfind(close_char)
                        if end_idx != -1 and end_idx > start_idx:
                            label = line[start_idx+1:end_idx]
                            if label and not label.startswith('"'):
                                line = line[:start_idx+1] + f'"{label}"' + line[end_idx:]
                sanitized_lines.append(line)
            llm_narrative = "\n".join(sanitized_lines)
            
            doc = (
                "# Architecture & Operations Synthesis Document\n\n"
                "This document details the system design, network routing boundary, and scaling characteristics derived programmatically.\n\n"
                "## 1. System Package Topology Diagram\n\n"
                f"{package_mermaid}\n\n"
                "## 2. Ingress, Execution & Egress Boundary Flow\n\n"
                f"{boundary_mermaid}\n\n"
                f"{llm_narrative}\n"
            )
            return doc

    async def generate_sre_audit(self) -> str:
        """Generates a separate stateful SRE & Performance Audit Document."""
        logger.info("Generating SRE & Performance Audit Document")
        res = self.vector_store.retrieve("", {"repo_id": self.config.repos[0].repo_id}, top_k=10000)
        
        is_fallback = isinstance(self.llm_client, PythonFallbackClient)
        
        if is_fallback:
            # Fallback scanner heuristics
            issues = []
            for r, _ in res:
                content = r.chunk_text
                file_name = r.file_path
                
                # Check for state descriptors without enableTimeToLive
                if "StateDescriptor" in content and "enableTimeToLive" not in content:
                    issues.append(f"- **State TTL Risk in `{file_name}`**: State descriptor initialized but no explicit `enableTimeToLive` found in this chunk. Ensure state cleanups are enabled.")
                
                # Check for deepCopy calls (gc overhead / memory pressure)
                if "deepCopy" in content or "SpecificData" in content:
                    issues.append(f"- **Object Cloning Overhead in `{file_name}`**: Usage of `deepCopy` or `SpecificData` found. Ensure this is not executed per-record in high-throughput streams to avoid GC pressure.")
                
                # Check for locks
                if "synchronized" in content or "lock" in content.lower():
                    issues.append(f"- **Thread Locking / Synchronisation in `{file_name}`**: Synchronization block or manual locking lock found. Check for deadlocks or blocking threads.")
                
                # Check for database clients or connections initialized per-record
                if "class " not in content and ("MongoClients.create" in content or "new MongoClient" in content):
                    issues.append(f"- **Connection Instantiation Risk in `{file_name}`**: Dynamic creation of MongoDB client. Connection-heavy clients should be cached in `open()` and released in `close()`.")
            
            unique_issues = sorted(list(set(issues)))[:15]
            issues_str = "\n".join(unique_issues) if unique_issues else "- *No high-severity SRE configuration or static code risks detected via heuristics.*"
            
            doc = (
                "# SRE & Performance Audit Document\n\n"
                "This document performs a stateful audit of the codebase for memory leaks, connection leaks, and performance bottlenecks.\n\n"
                "## 1. Executive Summary & Telemetry\n\n"
                "- **Audited Components:** Under parent directories\n"
                "- **Scope:** High-throughput streaming operations, state lifecycle, connection scoping\n\n"
                "## 2. Identified Vulnerabilities & Bottlenecks\n\n"
                f"{issues_str}\n\n"
                "## 3. General SRE Recommendations\n\n"
                "1. **State TTL Configuration:** Always configure explicit TTL values for state descriptors (ValueState, MapState, ListState) using `StateTtlConfig` to prevent off-heap/heap state accumulation.\n"
                "2. **Connection Scoping:** Ensure database connections, HTTP clients, or messaging handles are initialized once in lifecycle `open()` methods and closed in `close()` methods.\n"
                "3. **Minimize Object Cloning:** Avoid calling Avro `deepCopy()` or generic Kryo cloning inside high-frequency processing loops (like `flatMap` or `map`).\n"
            )
            return doc
        else:
            sre_chunks = self.vector_store.retrieve(
                "state descriptor enableTimeToLive stateTtlConfig, close connection dispose client, static collection cache thread local, deepCopy SpecificData cloneWrapper, linear scan nested loops synchronized lock, MongoClient, connections.max.idle.ms, liveness probe health check",
                {"repo_id": self.config.repos[0].repo_id},
                top_k=40
            )
            code_context_blocks = []
            for record, _ in sre_chunks:
                symbol_name = record.metadata.get("name", "unknown")
                code_context_blocks.append(f"--- File: {record.file_path} (Symbol: {symbol_name}) ---\n{record.chunk_text}\n")
            code_context_str = "\n".join(code_context_blocks)
            
            system_prompt = (
                "You are an expert SRE and JVM/Flink performance engineer. Perform a deep, thorough SRE & Performance Audit of the codebase.\n"
                "Analyze the provided code and configuration snippets. Specifically search for and report on:\n"
                "1. Flink State TTL leaks: Audit for Flink state descriptors (ValueStateDescriptor, MapStateDescriptor, etc.) initialized without calling enableTimeToLive() on them.\n"
                "2. High memory allocation churn & GC pressure: Audit for expensive dynamic cloning (e.g. SpecificData.get().deepCopy), nested collection allocations, or excessive object creation inside map/flatmap/filter functions.\n"
                "3. Concurrency hazards / Singleton state contamination: Audit for shared mutable instance variables in stateless operators, or static/thread-local cache leaks.\n"
                "4. Unclosed resources: Check if MongoClient, database handles, HTTP clients, or native buffers are dynamically instantiated inside processing loops instead of open()/close() lifecycle methods.\n"
                "5. Inefficient data structures: Check for O(N) linear scans on collections inside streaming operators.\n"
                "Format the response in professional markdown with clear headings, file citations with line ranges in brackets (e.g., [FileName.java:L123-145]), and actionable recommendations."
            )
            
            user_content = (
                f"Perform a detailed SRE & Performance Audit based on the following codebase context:\n\n"
                f"### Codebase Context:\n{code_context_str}\n\n"
                "Generate the report sections:\n"
                "1. SRE Vulnerability Summary: Bullet points with 1-line summaries of each issue found.\n"
                "2. Detailed Vulnerability Analysis (with code snippets and file citations).\n"
                "3. Actionable Remediations & Best Practices."
            )
            
            doc = await self.llm_client.generate_completion(system_prompt, user_content)
            return doc

    async def generate_lldd_module(self, module_name: str, symbols: List[Dict[str, Any]]) -> Dict[str, str]:
        """Runs LLDD generation for a module. Synchronously generates structure, but uses LLM for details if active."""
        logger.info(f"Generating LLDD module: {module_name}")
        
        details_lines = [
            f"### Implementation Structure details\n\n"
            "This section outlines the internal classes, methods, and behaviors within the module.\n"
        ]
        
        diagram_nodes = []
        diagram_edges = []
        node_idx = 0
        symbol_node_map = {}
        
        for s in symbols:
            kind = s.get("kind", "").upper()
            name = s.get("name", "")
            sig = s.get("signature", "")
            doc = s.get("docstring", "").strip() or "*No docstring comments defined.*"
            start = s.get("start_line", 0)
            end = s.get("end_line", 0)
            file_path = s.get("file_path", "")
            
            details_lines.append(
                f"#### {kind}: `{name}`\n"
                f"- **Declared In:** [`{file_path}:L{start}-{end}`](file://{os.path.join(self.config.repos[0].local_path, file_path)}#L{start}-{end})\n"
                f"- **Signature:** `{sig}`\n"
                f"- **Documentation:**\n"
                f"  > {doc}\n"
            )
            
            if kind in ["CLASS", "FUNCTION"]:
                node_id = f"sym_{node_idx}"
                symbol_node_map[name] = node_id
                diagram_nodes.append({"id": node_id, "label": f"{kind}: {name}"})
                node_idx += 1
                
        added_edges = set()
        for s in symbols:
            name = s.get("name", "")
            if name in symbol_node_map:
                for call in s.get("calls", []):
                    target_name = call.replace("self.", "")
                    for potential in symbol_node_map.keys():
                        if potential.endswith(target_name):
                            edge_key = f"{name}->{potential}"
                            if edge_key not in added_edges:
                                added_edges.add(edge_key)
                                diagram_edges.append({
                                    "from": symbol_node_map[name],
                                    "to": symbol_node_map[potential],
                                    "label": "calls"
                                })

        diagram_json = {"type": "flowchart", "nodes": diagram_nodes, "edges": diagram_edges}
        
        is_fallback = isinstance(self.llm_client, PythonFallbackClient)
        details_text = "\n".join(details_lines)
        
        if not is_fallback:
            # Let LLM enhance the module descriptions into professional documentation
            system_prompt = (
                "You are a principal engineer writing a module-level Low-Level Design Document (LLDD).\n"
                "Focus on implementation details, class designs, interface structures, and error handling patterns.\n"
                "Explain the behavior of each class and method in professional English. Cite files exactly, e.g. [file.py:L10-25]."
            )
            enhanced = await self.llm_client.generate_completion(system_prompt, f"Enhance and document the following module components:\n{details_text}")
            details_text = enhanced

        return {
            "module_name": module_name,
            "details": details_text,
            "diagram_json": json.dumps(diagram_json)
        }

    async def generate_feature_walkthrough(self, entry_point: Dict[str, Any]) -> str:
        """Traces call graph and generates walkthrough. Enhanced with LLM if active."""
        logger.info(f"Generating feature walkthrough trace for: {entry_point['unit_id']}")
        
        handler_id = entry_point["unit_id"]
        call_chain = self._traverse_call_graph(handler_id, depth_limit=5)
        
        walkthrough_lines = [
            f"# Feature Walkthrough: {entry_point['kind'].capitalize()} `{entry_point['name']}`\n",
            "This document traces the call sequence statically from the initial handler entry point.\n\n",
            "## 1. Sequence Execution Path\n"
        ]
        
        res = self.vector_store.retrieve("", {"repo_id": self.config.repos[0].repo_id}, top_k=10000)
        symbol_map = {}
        for r, _ in res:
            symbol_map[r.id] = r.metadata
            
        step = 1
        diagram_steps = []
        participants = set()
        code_context = []
        
        for unit_id in call_chain:
            meta = symbol_map.get(unit_id)
            if meta:
                name = meta.get("name", "unknown")
                file_path = meta.get("file_path", "unknown")
                start = meta.get("start_line", 0)
                end = meta.get("end_line", 0)
                sig = meta.get("signature", "")
                doc = meta.get("docstring", "").strip() or "No documentation."
                code_snippet = meta.get("code_content", "")
                
                walkthrough_lines.append(
                    f"### Step {step}: Call to `{name}`\n"
                    f"- **Location:** [`{file_path}:L{start}-{end}`](file://{os.path.join(self.config.repos[0].local_path, file_path)}#L{start}-{end})\n"
                    f"- **Interface:** `{sig}`\n"
                    f"- **Details:** {doc}\n"
                )
                
                code_context.append(f"Step {step}: {name} in {file_path}:\n```\n{code_snippet}\n```")
                module = file_path.split(os.sep)[0]
                participants.add(module)
                
                if step > 1:
                    prev_meta = symbol_map.get(call_chain[step - 2])
                    prev_module = prev_meta.get("file_path", "unknown").split(os.sep)[0] if prev_meta else "client"
                    diagram_steps.append({"from": prev_module, "to": module, "message": name.split(".")[-1]})
                else:
                    diagram_steps.append({"from": "client", "to": module, "message": name.split(".")[-1]})
                step += 1
                
        diagram_json = {
            "type": "sequence",
            "participants": ["client"] + sorted(list(participants)),
            "steps": diagram_steps
        }
        mermaid_markup = self._render_mermaid_sequence(diagram_json)
        
        is_fallback = isinstance(self.llm_client, PythonFallbackClient)
        
        if is_fallback:
            walkthrough_lines.append("\n## 2. Feature Sequence Flowchart\n")
            walkthrough_lines.append(mermaid_markup)
            return "\n".join(walkthrough_lines)
        else:
            # Ask the LLM to write a professional English trace narrative from code snippets
            system_prompt = (
                "You are an engineering guide writing an execution trace narration.\n"
                "Analyze the provided call sequence and code snippets. Explain the execution path, data mutations, "
                "conditionals, and final return outputs in professional English. Cite file lines exactly [file.py:L10-25]."
            )
            user_content = (
                f"Create a professional narration for this feature trace:\n\n"
                f"Entry Point: {entry_point['name']}\n\n"
                "Code Call Sequence:\n" + "\n".join(code_context)
            )
            narrated_text = await self.llm_client.generate_completion(system_prompt, user_content)
            
            doc = (
                f"# Feature Walkthrough: {entry_point['kind'].capitalize()} `{entry_point['name']}`\n\n"
                "This document provides a detailed execution walk of the feature flow.\n\n"
                "## 1. Sequence Execution Diagram\n\n"
                f"{mermaid_markup}\n\n"
                "## 2. Walkthrough Explanation & Narrative\n\n"
                f"{narrated_text}\n"
            )
            return doc

    def _render_mermaid_sequence(self, data: Dict[str, Any]) -> str:
        lines = ["sequenceDiagram"]
        participants = data.get("participants", [])
        for p in participants:
            p_id = p.replace(".", "_").replace(" ", "_").replace("/", "_")
            lines.append(f"    participant {p_id} as {p}")
            
        steps = data.get("steps", [])
        for step in steps:
            u = step.get("from", "").replace(".", "_").replace(" ", "_").replace("/", "_")
            v = step.get("to", "").replace(".", "_").replace(" ", "_").replace("/", "_")
            msg = step.get("message", "").replace('"', '\\"')
            lines.append(f"    {u}->>{v}: {msg}")
            
        return "```mermaid\n" + "\n".join(lines) + "\n```"

    def _traverse_call_graph(self, start_unit: str, depth_limit: int = 5) -> List[str]:
        visited: Set[str] = set()
        queue = [(start_unit, 0)]
        chain = []
        
        call_map = {}
        for edge in self.edges:
            if edge["type"] == "calls":
                call_map.setdefault(edge["from"], []).append(edge["to"])
                
        while queue:
            node, depth = queue.pop(0)
            if node in visited or depth > depth_limit:
                continue
            visited.add(node)
            chain.append(node)
            
            for child in call_map.get(node, []):
                queue.append((child, depth + 1))
                
        return chain
