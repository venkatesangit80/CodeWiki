import os
import sys
import ast
import yaml
import click
import asyncio
import logging
from typing import Dict, List, Any

# Local imports
from codedoc_generator.config import GeneratorConfig, RepoConfig
from codedoc_generator.ingestion import IngestionEngine
from codedoc_generator.analyzer import PythonASTVisitor, SemanticResolver, JavaSimpleParser
from codedoc_generator.vector_store import LocalVectorStore
from codedoc_generator.orchestrator import GeneratorOrchestrator
from codedoc_generator.document_assembler import DocumentAssembler

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("codedoc_generator")

@click.group()
def cli():
    """Automated HLDD/LLDD/Feature Walkthrough Generator CLI"""
    pass

@cli.command()
@click.option("--repo-path", default=".", help="Path to the repository to document")
@click.option("--repo-id", default="org/repo", help="Identifier for the repository")
def init(repo_path: str, repo_id: str):
    """Initializes a new codedoc_config.yaml in the current directory"""
    config_path = "codedoc_config.yaml"
    if os.path.exists(config_path):
        click.echo(f"Config file {config_path} already exists.")
        return

    # Create default configuration targeting the repo
    config = GeneratorConfig()
    config.repos = [RepoConfig(repo_id=repo_id, local_path=repo_path)]
    config.save_to_yaml(config_path)
    click.echo(f"Initialized default configuration in {config_path}")

@cli.command()
@click.option("--config", "config_file", default="codedoc_config.yaml", help="Path to configuration YAML")
def generate(config_file: str):
    """Scans code, builds graphs, indexes vectors, and generates documents"""
    if not os.path.exists(config_file):
        click.echo(f"Config file '{config_file}' not found. Run 'codedoc-gen init' first.")
        sys.exit(1)

    logger.info(f"Loading configuration from {config_file}")
    config = GeneratorConfig.load_from_yaml(config_file)
    
    if not config.repos:
        logger.error("No repositories configured in YAML.")
        sys.exit(1)

    # We will process the first repo configured
    repo_cfg = config.repos[0]
    repo_id = repo_cfg.repo_id
    local_path = repo_cfg.local_path or "."

    # Initialize components
    state_dir = os.path.join(local_path, ".codedoc")
    ingestor = IngestionEngine(
        repo_id=repo_id,
        local_path=local_path,
        ignore_paths=config.analysis.ignore_paths,
        state_dir=state_dir
    )

    # 1. Scan Repository (Incremental Ingestion)
    logger.info("Scanning repository files...")
    new_files, changed_files, deleted_files = ingestor.scan_repository()
    logger.info(f"Scan complete: {len(new_files)} new files, {len(changed_files)} changed files, {len(deleted_files)} deleted files detected.")

    # Initialize Local Vector Store
    vector_store = LocalVectorStore(
        db_path=config.vector_store.path,
        embedding_provider=config.embedding.provider,
        embedding_model=config.embedding.model,
        embedding_endpoint=config.embedding.endpoint
    )

    # Handle deleted files in vector store
    for df in deleted_files:
        vector_store.delete_by_filepath(repo_id, df)

    # 2. Structural & AST Analysis
    logger.info("Running AST parsing and building semantic resolution maps...")
    resolver = SemanticResolver(repo_id, local_path)
    
    # We must scan all files (even unchanged ones) to build a complete dependency graph,
    # but we only regenerate vector embeddings for new or changed files.
    # So we parse every file's AST structure for the graph builder.
    all_files = [os.path.join(r, f) for r, _, fs in os.walk(local_path) for f in fs]
    
    parsed_count = 0
    for root, _, files in os.walk(local_path):
        for file in files:
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, local_path)
            
            if ingestor._should_ignore(filepath) or ingestor._is_binary_file(filepath):
                continue
                
            if file.endswith((".py", ".java")):
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    if file.endswith(".py"):
                        parser = PythonASTVisitor(rel_path, repo_id, content)
                        parser.visit(ast_parse(content))
                    else:
                        parser = JavaSimpleParser(rel_path, repo_id, content)
                        
                    resolver.add_symbols_from_file(rel_path, parser)
                    
                    # Update vector store if new or changed
                    if rel_path in new_files or rel_path in changed_files:
                        # Clear old vectors for the file
                        vector_store.delete_by_filepath(repo_id, rel_path)
                        # Add new vectors
                        for symbol in parser.symbols:
                            chunk_text = f"{symbol.signature}\n\nDocstring:\n{symbol.docstring}\n\nSource Code:\n{symbol.code_content}"
                            vector_store.upsert(
                                record_id=symbol.unit_id,
                                repo_id=repo_id,
                                file_path=rel_path,
                                metadata=symbol.to_dict(),
                                chunk_text=chunk_text
                            )
                    parsed_count += 1
                except Exception as e:
                    logger.error(f"Error parsing file {rel_path}: {e}")

    logger.info(f"Parsed {parsed_count} source files.")

    # Resolve dependencies to build call edges
    logger.info("Resolving symbol reference relationships...")
    dependency_edges = resolver.resolve_dependencies()
    logger.info(f"Resolved {len(dependency_edges)} dependency edges.")

    # Find entry points
    entry_points = []
    for file_path, symbols in resolver.file_symbols.items():
        for symbol in symbols:
            if symbol.is_entry_point:
                entry_points.append(symbol.to_dict())

    logger.info(f"Detected {len(entry_points)} entry points.")

    # 3. Document Generation
    logger.info("Starting documentation generation orchestration...")
    orchestrator = GeneratorOrchestrator(config, vector_store, dependency_edges, entry_points)
    
    # Run async orchestrator logic
    loop = asyncio.get_event_loop()
    hldd_data = loop.run_until_complete(orchestrator.generate_hldd())
    
    # Group symbols by directory modules to generate LLDD per-module
    modules_map: Dict[str, List[Dict[str, Any]]] = {}
    for file_path, symbols in resolver.file_symbols.items():
        # Module name = parent directory name
        parts = file_path.split(os.sep)
        module_name = parts[0] if len(parts) > 1 else "root"
        modules_map.setdefault(module_name, []).extend([s.to_dict() for s in symbols])
        
    lldd_modules = []
    for mod_name, mod_symbols in modules_map.items():
        lldd_res = loop.run_until_complete(orchestrator.generate_lldd_module(mod_name, mod_symbols))
        lldd_modules.append(lldd_res)
        
    # Generate feature walkthroughs for all detected entry points
    feature_docs = []
    for ep in entry_points:
        feat_doc = loop.run_until_complete(orchestrator.generate_feature_walkthrough(ep))
        feature_docs.append((ep.get("name", "Unknown Feature"), feat_doc))

    # 4. Document Assembly
    logger.info("Assembling generated sections into final documents...")
    os.makedirs(config.output.output_dir, exist_ok=True)
    
    hldd_doc = DocumentAssembler.assemble_hldd(hldd_data)
    hldd_path = os.path.join(config.output.output_dir, f"HLDD_{repo_id.replace('/', '__')}.md")
    with open(hldd_path, "w") as f:
        f.write(hldd_doc)
    logger.info(f"Written HLDD to {hldd_path}")
    
    lldd_doc = DocumentAssembler.assemble_lldd(lldd_modules)
    lldd_path = os.path.join(config.output.output_dir, f"LLDD_{repo_id.replace('/', '__')}.md")
    with open(lldd_path, "w") as f:
        f.write(lldd_doc)
    logger.info(f"Written LLDD to {lldd_path}")

    # Generate Architecture Synthesis Document
    synthesis_doc = loop.run_until_complete(orchestrator.generate_architecture_synthesis())
    synth_path = os.path.join(config.output.output_dir, f"Architecture_Synthesis_{repo_id.replace('/', '__')}.md")
    with open(synth_path, "w") as f:
        f.write(synthesis_doc)
    logger.info(f"Written Architecture Synthesis to {synth_path}")
    
    for feat_name, doc in feature_docs:
        feat_file = f"Feature_{feat_name.replace('.', '_')}.md"
        feat_path = os.path.join(config.output.output_dir, feat_file)
        with open(feat_path, "w") as f:
            f.write(doc)
        logger.info(f"Written Feature Walkthrough to {feat_path}")

    # Commit hashing state for subsequent incremental runs
    ingestor.commit_state()
    logger.info("Documentation generation successfully completed!")

def ast_parse(content: str) -> ast.AST:
    # A helper that handles empty files or parsing failures
    try:
        return ast.parse(content)
    except SyntaxError:
        # Retry by cleaning up syntax errors or fallback to empty module
        return ast.parse("")
