import os
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil
import uuid
import re
import subprocess
import logging
from pydantic import BaseModel

from codedoc_generator.config import GeneratorConfig
from codedoc_generator.storage import get_storage_provider

logger = logging.getLogger("doc_viewer")

app = FastAPI(title="Everops Wiki Document Viewer")

WORKSPACE_DIR = Path(__file__).parent.resolve()

generation_jobs = {}

class LocalStorageSettings(BaseModel):
    storage_type: str = "efs"
    bucket_name: Optional[str] = None
    region: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    azure_container: Optional[str] = None
    connection_string: Optional[str] = None
    base_path: Optional[str] = None

class LocalNatsSettings(BaseModel):
    nats_url: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None

class GenerateRequest(BaseModel):
    github_url: str
    tech: str = "generic"
    ignore_paths: Optional[List[str]] = None
    github_token: Optional[str] = None
    mode: str = "vault"  # vault | local
    local_storage: Optional[LocalStorageSettings] = None
    local_nats: Optional[LocalNatsSettings] = None

def run_background_generation(req: GenerateRequest, run_id: str):
    import asyncio
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    
    generation_jobs[run_id] = {"status": "running", "error": None}
    temp_dir = os.path.abspath(f"./repos/run_{run_id}")
    
    # Store original Vault state to restore later
    old_use_vault = os.environ.get("USE_VAULT")
    
    try:
        url = req.github_url.strip()
        if not url.startswith("http") and "/" in url:
            url = f"https://github.com/{url}"
        if not url.endswith(".git"):
            url = url + ".git"
            
        os.makedirs(temp_dir, exist_ok=True)
        
        github_token = req.github_token or os.environ.get("GITHUB_PAT")
        auth_url = url
        if github_token:
            auth_url = url.replace("https://", f"https://{github_token}@")
            
        logger.info(f"Cloning {url} into {temp_dir}...")
        subprocess.run(["git", "clone", "--depth", "1", auth_url, temp_dir], check=True)
        
        match = re.search(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
        repo_id = f"{match.group(1)}/{match.group(2)}" if match else f"cloned/repo_{run_id}"
        
        from codedoc_generator.config import GeneratorConfig, RepoConfig, LLMConfig, EmbeddingConfig, VectorStoreConfig, AnalysisConfig, OutputConfig, StorageConfig
        
        if req.mode == "local":
            os.environ["USE_VAULT"] = "False"
            
            nats_settings = req.local_nats or LocalNatsSettings()
            llm_endpoint = nats_settings.nats_url or "nats://localhost:4222"
            nats_user = nats_settings.user or ""
            nats_password = nats_settings.password or ""
            
            storage_settings = req.local_storage or LocalStorageSettings()
            st_type = storage_settings.storage_type.lower()
            if st_type == "s3":
                conn_settings = {
                    "bucket_name": storage_settings.bucket_name,
                    "region": storage_settings.region or "us-west-2",
                    "access_key": storage_settings.access_key,
                    "secret_key": storage_settings.secret_key
                }
            elif st_type == "azure":
                conn_settings = {
                    "azure_container": storage_settings.azure_container,
                    "connection_string": storage_settings.connection_string
                }
            else:
                conn_settings = {
                    "base_path": storage_settings.base_path or "."
                }
            storage_obj = StorageConfig(type=st_type, connection_settings=conn_settings)
        else:
            os.environ["USE_VAULT"] = "True"
            llm_endpoint = os.environ.get("NATS_SERVER_URL", "nats://ec2-54-191-170-106.us-west-2.compute.amazonaws.com:4222")
            nats_user = os.environ.get("NATS_USER", "js_everyops")
            nats_password = os.environ.get("NATS_PASSWORD", "8BcUaUYxOnVG8g1T")
            storage_obj = config.storage if (globals().get("config") and config.storage) else StorageConfig()

        config_obj = GeneratorConfig(
            repos=[
                RepoConfig(
                    repo_id=repo_id,
                    branch="main",
                    local_path=temp_dir,
                    tech=req.tech
                )
            ],
            llm=LLMConfig(
                provider="nats",
                endpoint=llm_endpoint,
                nats_user=nats_user,
                nats_password=nats_password,
                temperature=0.2
            ),
            embedding=EmbeddingConfig(
                provider="mock",
                model="mock-nomic",
                endpoint=""
            ),
            vector_store=VectorStoreConfig(
                backend="sqlite",
                path=":memory:"
            ),
            analysis=AnalysisConfig(
                ignore_paths=req.ignore_paths or [".git", "node_modules", "dist", "build", "__pycache__", "venv", "target", ".mvn", "src/test"],
                module_granularity="directory"
            ),
            output=OutputConfig(
                formats=["markdown"],
                output_dir=os.path.join("repo_docs", req.tech, repo_id.split("/")[-1])
            ),
            storage=storage_obj
        )
        
        from codedoc_generator.cli import _run_generation
        
        _run_generation(config_obj, config_obj.repos[0], None)
        generation_jobs[run_id] = {"status": "completed", "error": None}
        logger.info(f"Background generation completed for run {run_id}")
        
    except Exception as e:
        logger.error(f"Background generation failed for run {run_id}: {e}")
        generation_jobs[run_id] = {"status": "failed", "error": str(e)}
    finally:
        # Restore original Vault switch state
        if old_use_vault is not None:
            os.environ["USE_VAULT"] = old_use_vault
        else:
            os.environ.pop("USE_VAULT", None)
            
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

# Load config if exists
config_path = "sequence_builder_config.yaml"
if not os.path.exists(config_path):
    config_path = "codedoc_config.yaml"

config = None
if os.path.exists(config_path):
    try:
        config = GeneratorConfig.load_from_yaml(config_path)
    except Exception:
        pass

storage = get_storage_provider(config)

def build_tree_from_paths(paths: List[str]) -> List[Dict[str, Any]]:
    tree_root = {}
    for path in paths:
        path = path.replace("\\", "/")
        if path.startswith("repo_docs/"):
            rel_path = path[len("repo_docs/"):]
        else:
            rel_path = path
            
        parts = rel_path.split("/")
        current = tree_root
        for i, part in enumerate(parts):
            if not part:
                continue
            is_file = (i == len(parts) - 1)
            entry_path = "/".join(parts[:i+1])
            if part not in current:
                if is_file:
                    if part.endswith(".md"):
                        current[part] = {
                            "name": part,
                            "type": "file",
                            "path": entry_path
                        }
                else:
                    current[part] = {
                        "name": part,
                        "type": "directory",
                        "path": entry_path,
                        "children": {}
                    }
            if not is_file and part in current:
                current = current[part]["children"]

    def dict_to_list(d):
        lst = []
        for key, val in d.items():
            if val["type"] == "directory":
                val["children"] = dict_to_list(val["children"])
            lst.append(val)
        return sorted(lst, key=lambda e: (e["type"] != "directory", e["name"].lower()))

    return dict_to_list(tree_root)

@app.get("/repo_docs/{doc_path:path}")
def get_document(doc_path: str):
    full_path = os.path.join("repo_docs", doc_path)
    content = storage.read_file(full_path)
    if content is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return PlainTextResponse(content)

@app.get("/api/tree")
def get_tree():
    try:
        paths = storage.list_files(prefix="repo_docs")
        return build_tree_from_paths(paths)
    except Exception as e:
        return []

@app.post("/api/generate")
def trigger_generation(req: GenerateRequest, background_tasks: BackgroundTasks):
    run_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(run_background_generation, req, run_id)
    return {"status": "started", "run_id": run_id}

@app.get("/api/generate/status/{run_id}")
def get_generation_status(run_id: str):
    job = generation_jobs.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/", response_class=HTMLResponse)
def get_index():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Everops Wiki Interactive Viewer</title>
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    
    <!-- React & Babel Standalone -->
    <script src="https://unpkg.com/react@18/umd/react.development.js" crossorigin></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js" crossorigin></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    
    <!-- Marked & DOMPurify -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.8/dist/purify.min.js"></script>
    
    <!-- Highlight.js for Code Highlighting -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    
    <!-- html2pdf for PDF Generation -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    
    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest"></script>
    
    <!-- Mermaid.js for Diagrams -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>

    <style>
        :root {
            --bg-dark: #090d16;
            --bg-sidebar: rgba(13, 20, 35, 0.7);
            --bg-card: #111827;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --primary: #3b82f6;
            --primary-hover: #60a5fa;
            --border-color: rgba(255, 255, 255, 0.08);
            --accent-success: #10b981;
            --accent-warning: #f59e0b;
            --accent-error: #ef4444;
            --font-sans: 'Outfit', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-dark);
            color: var(--text-main);
            font-family: var(--font-sans);
            overflow: hidden;
            height: 100vh;
            display: flex;
        }

        #root {
            display: flex;
            width: 100%;
            height: 100%;
        }

        /* App Layout */
        .app-container {
            display: flex;
            width: 100%;
            height: 100%;
            position: relative;
        }

        /* Left Sidebar styling */
        .sidebar {
            width: 320px;
            background: var(--bg-sidebar);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            height: 100%;
            flex-shrink: 0;
            z-index: 10;
            transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .sidebar.collapsed {
            width: 0px;
            overflow: hidden;
            border-right: none;
        }

        .sidebar.resizing {
            transition: none !important;
        }

        .resize-handle {
            width: 4px;
            cursor: col-resize;
            background: transparent;
            z-index: 20;
            transition: all 0.2s;
            height: 100%;
            flex-shrink: 0;
            margin-left: -2px;
            margin-right: -2px;
        }

        .resize-handle:hover,
        .resize-handle.active {
            background: var(--primary);
            box-shadow: 0 0 8px var(--primary);
        }

        .sidebar-header {
            padding: 1.5rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .sidebar-header h1 {
            font-size: 1.25rem;
            font-weight: 700;
            background: linear-gradient(to right, #3b82f6, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        /* Modal styling */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 100;
        }

        .modal-content {
            background: #111827;
            border: 1px solid #374151;
            border-radius: 12px;
            width: 480px;
            max-width: 90%;
            padding: 2rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }

        .modal-header h2 {
            font-size: 1.25rem;
            font-weight: 700;
            color: #f3f4f6;
            margin: 0;
        }

        .modal-close-btn {
            background: none;
            border: none;
            color: #9ca3af;
            cursor: pointer;
        }

        .form-group {
            margin-bottom: 1.25rem;
        }

        .form-label {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            color: #9ca3af;
            margin-bottom: 0.5rem;
        }

        .form-input, .form-select, .form-textarea {
            width: 100%;
            background: #1f2937;
            border: 1px solid #374151;
            border-radius: 6px;
            color: #f3f4f6;
            padding: 0.625rem;
            font-size: 0.875rem;
            outline: none;
            box-sizing: border-box;
        }

        .form-input:focus, .form-select:focus, .form-textarea:focus {
            border-color: #3b82f6;
        }

        .modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: 0.75rem;
            margin-top: 1.5rem;
        }

        .btn {
            padding: 0.625rem 1.25rem;
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            border: none;
        }

        .btn-secondary {
            background: #374151;
            color: #f3f4f6;
        }

        .btn-primary {
            background: #2563eb;
            color: #ffffff;
        }

        .btn-primary:hover {
            background: #1d4ed8;
        }

        .btn-primary:disabled {
            background: #4b5563;
            cursor: not-allowed;
        }
        
        .generate-btn {
            background: none;
            border: none;
            color: #60a5fa;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0.25rem;
            border-radius: 4px;
            transition: background 0.2s;
        }
        
        .generate-btn:hover {
            background: #1e293b;
        }

        .search-container {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }

        .search-input-wrapper {
            position: relative;
            width: 100%;
        }

        .search-input {
            width: 100%;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0.6rem 1rem 0.6rem 2.5rem;
            color: white;
            font-family: var(--font-sans);
            font-size: 0.9rem;
            outline: none;
            transition: all 0.2s;
        }

        .search-input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
        }

        .search-icon {
            position: absolute;
            left: 0.75rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
        }

        .tree-container {
            flex-grow: 1;
            overflow-y: auto;
            padding: 1.5rem;
        }

        /* Tree Node Styles */
        .tree-node {
            margin-bottom: 0.25rem;
            user-select: none;
        }

        .node-row {
            display: flex;
            align-items: center;
            padding: 0.5rem 0.75rem;
            border-radius: 6px;
            cursor: pointer;
            gap: 0.5rem;
            transition: all 0.2s;
            color: var(--text-muted);
            font-size: 0.95rem;
        }

        .node-row:hover {
            background: rgba(255, 255, 255, 0.04);
            color: var(--text-main);
        }

        .node-row.active {
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            font-weight: 500;
            border-left: 3px solid var(--primary);
            border-top-left-radius: 0;
            border-bottom-left-radius: 0;
        }

        .node-icon {
            flex-shrink: 0;
            opacity: 0.8;
        }

        .node-arrow {
            opacity: 0.5;
            transition: transform 0.2s;
        }

        .node-arrow.expanded {
            transform: rotate(90deg);
        }

        .node-label {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .children-container {
            padding-left: 1.25rem;
            border-left: 1px dashed rgba(255, 255, 255, 0.05);
            margin-left: 0.5rem;
        }

        /* Main Content Viewport */
        .content-area {
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            height: 100%;
            overflow: hidden;
            background: #060910;
        }

        .content-header {
            height: 70px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 2rem;
            background: rgba(13, 20, 35, 0.4);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
        }

        .doc-title-container {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .tech-badge {
            background: rgba(59, 130, 246, 0.1);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.2);
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .date-badge {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-muted);
            border: 1px solid var(--border-color);
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
        }

        .doc-body {
            flex-grow: 1;
            overflow-y: auto;
            padding: 3rem 4rem;
            display: flex;
            justify-content: center;
        }

        .markdown-wrapper {
            max-width: 900px;
            width: 100%;
            font-size: 1.05rem;
            line-height: 1.7;
        }

        /* Placeholder state */
        .placeholder-view {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-muted);
            gap: 1rem;
            text-align: center;
            padding: 2rem;
        }

        .placeholder-logo {
            font-size: 4rem;
            animation: pulse 2s infinite ease-in-out;
        }

        @keyframes pulse {
            0% { transform: scale(1); opacity: 0.6; }
            50% { transform: scale(1.05); opacity: 1; }
            100% { transform: scale(1); opacity: 0.6; }
        }

        /* Premium Markdown Styles */
        .markdown-body h1 {
            font-size: 2.25rem;
            font-weight: 700;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.75rem;
            color: white;
        }

        .markdown-body h2 {
            font-size: 1.6rem;
            font-weight: 600;
            margin-top: 2.5rem;
            margin-bottom: 1.25rem;
            color: white;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.4rem;
        }

        .markdown-body h3 {
            font-size: 1.25rem;
            font-weight: 600;
            margin-top: 2rem;
            margin-bottom: 1rem;
            color: #60a5fa;
        }

        .markdown-body p {
            margin-bottom: 1.25rem;
            color: #d1d5db;
        }

        .markdown-body ul, .markdown-body ol {
            margin-bottom: 1.25rem;
            padding-left: 2rem;
            color: #d1d5db;
        }

        .markdown-body li {
            margin-bottom: 0.5rem;
        }

        /* GFM Blockquotes / Alert Callouts */
        .markdown-body blockquote {
            border-left: 4px solid var(--primary);
            background: rgba(59, 130, 246, 0.05);
            padding: 1rem 1.5rem;
            margin: 1.5rem 0;
            border-radius: 6px;
            color: #d1d5db;
        }

        /* Alert Callouts Specific Custom Styling */
        .markdown-body blockquote p:first-child {
            margin-bottom: 0;
        }

        /* Highlighting Code Blocks */
        .markdown-body pre {
            background: #0d1117 !important;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1.25rem;
            overflow-x: auto;
            margin: 1.5rem 0;
        }

        .markdown-body code {
            font-family: var(--font-mono);
            font-size: 0.9rem;
            background: rgba(255, 255, 255, 0.06);
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            color: #e5e7eb;
        }

        .markdown-body pre code {
            background: none !important;
            padding: 0;
            border-radius: 0;
            color: inherit;
        }

        /* Tables styling */
        .markdown-body table {
            width: 100%;
            border-collapse: collapse;
            margin: 2rem 0;
            font-size: 0.95rem;
            background: rgba(255, 255, 255, 0.01);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow: hidden;
        }

        .markdown-body th {
            background: rgba(255, 255, 255, 0.03);
            font-weight: 600;
            text-align: left;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            color: white;
        }

        .markdown-body td {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            color: #d1d5db;
        }

        .markdown-body tr:hover td {
            background: rgba(255, 255, 255, 0.015);
        }

        /* Horizontal rule */
        .markdown-body hr {
            height: 1px;
            border: none;
            background-color: var(--border-color);
            margin: 3rem 0;
        }

        /* PDF Export Styles (Clean Print Theme) */
        body.pdf-exporting .markdown-wrapper {
            background: #ffffff !important;
            color: #1f2937 !important;
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            padding: 24px !important;
        }
        body.pdf-exporting .markdown-body h1,
        body.pdf-exporting .markdown-body h2,
        body.pdf-exporting .markdown-body h3,
        body.pdf-exporting .markdown-body strong {
            color: #0f172a !important;
        }
        body.pdf-exporting .markdown-body h1 {
            color: #1e3a8a !important; /* Professional Dark Navy for primary headings */
            border-bottom: 2px solid #cbd5e1 !important;
            padding-bottom: 8px !important;
            margin-top: 0 !important;
            page-break-after: avoid !important;
            break-after: avoid !important;
        }
        body.pdf-exporting .markdown-body h2 {
            color: #1e40af !important;
            border-bottom: 1px solid #e2e8f0 !important;
            padding-bottom: 6px !important;
            margin-top: 2rem !important;
            page-break-after: avoid !important;
            break-after: avoid !important;
        }
        body.pdf-exporting .markdown-body h3 {
            color: #2563eb !important;
            margin-top: 1.5rem !important;
            page-break-after: avoid !important;
            break-after: avoid !important;
        }
        body.pdf-exporting .markdown-body p,
        body.pdf-exporting .markdown-body li {
            color: #334155 !important;
            font-size: 0.95rem !important;
            line-height: 1.6 !important;
        }
        body.pdf-exporting .markdown-body pre {
            background-color: #f8fafc !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 6px !important;
            padding: 12px 16px !important;
            margin: 1.25rem 0 !important;
            font-size: 0.85rem !important;
            line-height: 1.5 !important;
            overflow: hidden !important;
            white-space: pre-wrap !important;
            word-break: break-all !important;
            page-break-inside: avoid !important;
            break-inside: avoid !important;
        }
        body.pdf-exporting .markdown-body code {
            font-family: 'JetBrains Mono', monospace !important;
            background: #f1f5f9 !important;
            color: #0f172a !important;
            padding: 2px 4px !important;
            border-radius: 4px !important;
            font-size: 0.85rem !important;
        }
        body.pdf-exporting .markdown-body pre code {
            background: none !important;
            color: #0f172a !important;
            padding: 0 !important;
            font-size: 0.85rem !important;
        }
        body.pdf-exporting .markdown-body blockquote {
            border-left: 4px solid #1e3a8a !important;
            color: #475569 !important;
            background: #f8fafc !important;
            padding: 12px 16px !important;
            margin: 1.25rem 0 !important;
            border-radius: 4px !important;
            page-break-inside: avoid !important;
            break-inside: avoid !important;
        }
        body.pdf-exporting .markdown-body table {
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            width: 100% !important;
            border-collapse: collapse !important;
            margin: 1.5rem 0 !important;
            page-break-inside: avoid !important;
            break-inside: avoid !important;
        }
        body.pdf-exporting .markdown-body th {
            border: 1px solid #cbd5e1 !important;
            background: #f1f5f9 !important;
            color: #0f172a !important;
            font-weight: 600 !important;
            padding: 8px 12px !important;
        }
        body.pdf-exporting .markdown-body td {
            border: 1px solid #cbd5e1 !important;
            color: #334155 !important;
            padding: 8px 12px !important;
        }
        body.pdf-exporting .markdown-body svg {
            background-color: #090d16 !important;
            border-radius: 8px !important;
            padding: 12px !important;
            border: 1px solid #cbd5e1 !important;
            max-width: 100% !important;
        }

        /* Print only header/footer */
        .pdf-only-header,
        .pdf-only-footer {
            display: none !important;
        }

        body.pdf-exporting .pdf-only-header {
            display: block !important;
        }
        body.pdf-exporting .pdf-only-footer {
            display: block !important;
            page-break-after: avoid !important;
            break-after: avoid !important;
        }
    </style>
</head>
<body>
    <div id="root"></div>

    <script type="text/babel">
        const { useState, useEffect } = React;

        // Custom React SVG Icon Component to bypass external DOM manipulations and prevent React DOM reconciliation errors
        const Icon = ({ name, size = 16, className = "" }) => {
            const icons = {
                "chevron-right": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className}>
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                ),
                "chevron-left": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className}>
                        <polyline points="15 18 9 12 15 6"></polyline>
                    </svg>
                ),
                "menu": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className}>
                        <line x1="3" y1="12" x2="21" y2="12"></line>
                        <line x1="3" y1="6" x2="21" y2="6"></line>
                        <line x1="3" y1="18" x2="21" y2="18"></line>
                    </svg>
                ),
                "folder": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className} style={{color: '#60a5fa'}}>
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                    </svg>
                ),
                "folder-open": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className} style={{color: '#93c5fd'}}>
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                        <path d="M2 10h20"></path>
                    </svg>
                ),
                "file-text": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className} style={{color: '#9ca3af'}}>
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                    </svg>
                ),
                "book-open": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className} style={{color: '#3b82f6'}}>
                        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path>
                        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>
                    </svg>
                ),
                "search": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className}>
                        <circle cx="11" cy="11" r="8"></circle>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                    </svg>
                ),
                "loader": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className={`animate-spin ${className}`} style={{animation: 'spin 1s linear infinite'}}>
                        <line x1="12" y1="2" x2="12" y2="6"></line>
                        <line x1="12" y1="18" x2="12" y2="22"></line>
                        <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
                        <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
                        <line x1="2" y1="12" x2="6" y2="12"></line>
                        <line x1="18" y1="12" x2="22" y2="12"></line>
                        <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
                        <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
                    </svg>
                ),
                "download": (
                    <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className={className}>
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                )
            };

            return icons[name] || null;
        };

        const TreeNode = ({ node, searchTerm, selectedPath, onSelectFile, depth = 0 }) => {
            const [isExpanded, setIsExpanded] = useState(depth < 2); // Auto-expand first 2 levels
            
            const hasMatch = (item) => {
                if (item.name.toLowerCase().includes(searchTerm.toLowerCase())) return true;
                if (item.children) return item.children.some(child => hasMatch(child));
                return false;
            };

            if (searchTerm && !hasMatch(node)) return null;

            const isFolder = node.type === "directory";
            const isActive = selectedPath === node.path;

            const handleClick = () => {
                if (isFolder) {
                    setIsExpanded(!isExpanded);
                } else {
                    onSelectFile(node.path);
                }
            };

            return (
                <div className="tree-node">
                    <div 
                        className={`node-row ${isActive ? 'active' : ''}`}
                        onClick={handleClick}
                        style={{ paddingLeft: `${depth * 12 + 10}px` }}
                    >
                        {isFolder ? (
                            <Icon 
                                name="chevron-right" 
                                size={14} 
                                className={`node-arrow ${isExpanded ? 'expanded' : ''}`} 
                            />
                        ) : (
                            <div style={{ width: 14 }} />
                        )}
                        
                        <Icon 
                            name={isFolder ? (isExpanded ? "folder-open" : "folder") : "file-text"} 
                            size={16}
                            className={isFolder ? "text-blue-400" : "text-gray-400"}
                        />
                        
                        <span className="node-label" title={node.name}>{node.name}</span>
                    </div>

                    {isFolder && isExpanded && (
                        <div className="children-container">
                            {node.children.map((child, idx) => (
                                <TreeNode 
                                    key={idx} 
                                    node={child} 
                                    searchTerm={searchTerm} 
                                    selectedPath={selectedPath}
                                    onSelectFile={onSelectFile}
                                    depth={depth + 1}
                                />
                            ))}
                        </div>
                    )}
                </div>
            );
        };

            const App = () => {
                const [tree, setTree] = useState([]);
                const [searchTerm, setSearchTerm] = useState("");
                const [selectedPath, setSelectedPath] = useState("");
                const [docContent, setDocContent] = useState("");
                const [loading, setLoading] = useState(false);
                const [tech, setTech] = useState("");
                const [comp, setComp] = useState("");
                const [date, setDate] = useState("");
                const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
                const [sidebarWidth, setSidebarWidth] = useState(320);
                const [isResizing, setIsResizing] = useState(false);

                const [isModalOpen, setIsModalOpen] = useState(false);
                const [githubUrl, setGithubUrl] = useState("");
                const [techSelect, setTechSelect] = useState("generic");
                const [ignorePathsInput, setIgnorePathsInput] = useState(".git, node_modules, dist, build, __pycache__, venv, target, .mvn, src/test");
                const [jobStatus, setJobStatus] = useState("idle");
                const [jobError, setJobError] = useState("");

                // Local and Vault Tab configuration states
                const [activeTab, setActiveTab] = useState("vault"); // vault | local
                const [githubToken, setGithubToken] = useState("");
                const [localNatsUrl, setLocalNatsUrl] = useState("nats://localhost:4222");
                const [localNatsUser, setLocalNatsUser] = useState("");
                const [localNatsPass, setLocalNatsPass] = useState("");
                const [localStorageType, setLocalStorageType] = useState("efs");
                const [localS3Bucket, setLocalS3Bucket] = useState("");
                const [localS3Region, setLocalS3Region] = useState("us-west-2");
                const [localS3AccessKey, setLocalS3AccessKey] = useState("");
                const [localS3SecretKey, setLocalS3SecretKey] = useState("");
                const [localAzureContainer, setLocalAzureContainer] = useState("");
                const [localAzureConnStr, setLocalAzureConnStr] = useState("");
                const [localEfsBasePath, setLocalEfsBasePath] = useState(".");

                const startResizing = (e) => {
                    e.preventDefault();
                    setIsResizing(true);
                    
                    const handleMouseMove = (moveEvent) => {
                        const newWidth = Math.max(200, Math.min(600, moveEvent.clientX));
                        setSidebarWidth(newWidth);
                    };
                    
                    const handleMouseUp = () => {
                        setIsResizing(false);
                        window.removeEventListener("mousemove", handleMouseMove);
                        window.removeEventListener("mouseup", handleMouseUp);
                    };
                    
                    window.addEventListener("mousemove", handleMouseMove);
                    window.addEventListener("mouseup", handleMouseUp);
                };

                const handleStartGeneration = () => {
                    setJobStatus("running");
                    setJobError("");
                    
                    let payload = {
                        github_url: githubUrl,
                        tech: techSelect,
                        ignore_paths: ignorePathsInput.split(",").map(p => p.trim()).filter(Boolean),
                        mode: activeTab
                    };

                    if (activeTab === "local") {
                        payload.github_token = githubToken || null;
                        payload.local_nats = {
                            nats_url: localNatsUrl || null,
                            user: localNatsUser || null,
                            password: localNatsPass || null
                        };
                        payload.local_storage = {
                            storage_type: localStorageType,
                            bucket_name: localS3Bucket || null,
                            region: localS3Region || null,
                            access_key: localS3AccessKey || null,
                            secret_key: localS3SecretKey || null,
                            azure_container: localAzureContainer || null,
                            connection_string: localAzureConnStr || null,
                            base_path: localEfsBasePath || null
                        };
                    }
                    
                    fetch("/api/generate", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    })
                    .then(res => {
                        if (!res.ok) throw new Error("Failed to contact generation service");
                        return res.json();
                    })
                    .then(data => {
                        if (data.status === "started") {
                            pollJobStatus(data.run_id);
                        } else {
                            throw new Error("Failed to start background generation");
                        }
                    })
                    .catch(err => {
                        setJobStatus("failed");
                        setJobError(err.message || "Request failed");
                    });
                };
                
                const pollJobStatus = (runId) => {
                    const interval = setInterval(() => {
                        fetch(`/api/generate/status/${runId}`)
                            .then(res => {
                                if (!res.ok) throw new Error("Job not found");
                                return res.json();
                            })
                            .then(data => {
                                if (data.status === "completed") {
                                    clearInterval(interval);
                                    setJobStatus("completed");
                                    setIsModalOpen(false);
                                    // Reset inputs
                                    setGithubUrl("");
                                    // Refresh doc tree
                                    fetch("/api/tree")
                                        .then(res => res.json())
                                        .then(treeData => {
                                            setTree(treeData);
                                        });
                                } else if (data.status === "failed") {
                                    clearInterval(interval);
                                    setJobStatus("failed");
                                    setJobError(data.error || "Generation task failed");
                                }
                            })
                            .catch(err => {
                                clearInterval(interval);
                                setJobStatus("failed");
                                setJobError("Status polling failed: " + err.message);
                            });
                    }, 2000);
                };

            useEffect(() => {
                fetch("/api/tree")
                    .then(res => res.json())
                    .then(data => {
                        setTree(data);
                        // Auto-select first markdown if available
                        const firstFile = findFirstFile(data);
                        if (firstFile) {
                            handleSelectFile(firstFile);
                        }
                    })
                    .catch(err => console.error("Error loading tree:", err));
            }, []);

            const findFirstFile = (nodes) => {
                for (let node of nodes) {
                    if (node.type === "file") return node.path;
                    if (node.children) {
                        const path = findFirstFile(node.children);
                        if (path) return path;
                    }
                }
                return null;
            };

            const handleSelectFile = (path) => {
                setSelectedPath(path);
                setLoading(true);
                
                // Parse out technology, component name, and date from the path
                // format: flink/ecs-recoveryobiligation-flink/2026-08-18/HLDD...md
                const parts = path.split("/");
                if (parts.length >= 3) {
                    setTech(parts[0]);
                    setComp(parts[1]);
                    setDate(parts[2]);
                } else {
                    setTech("General");
                    setComp("Everops Wiki");
                    setDate("");
                }

                fetch(`/repo_docs/${path}`)
                    .then(res => {
                        if (!res.ok) throw new Error("File not found");
                        return res.text();
                    })
                    .then(text => {
                        // Configure marked with syntax highlight integration
                        marked.setOptions({
                            highlight: function(code, lang) {
                                if (lang && hljs.getLanguage(lang)) {
                                    return hljs.highlight(code, { language: lang }).value;
                                }
                                return hljs.highlightAuto(code).value;
                            }
                        });
                        
                        const html = marked.parse(text);
                        const cleanHtml = DOMPurify.sanitize(html);
                        setDocContent(cleanHtml);
                        setLoading(false);
                    })
                    .catch(err => {
                        console.error(err);
                        setDocContent(`<div class="text-red-500">Failed to load document content.</div>`);
                        setLoading(false);
                    });
            };

            const handleDownloadPDF = () => {
                const element = document.querySelector('.markdown-wrapper');
                if (!element) return;
                
                document.body.classList.add('pdf-exporting');
                const filename = `${selectedPath.split("/").pop().replace(".md", "")}.pdf`;
                
                const opt = {
                    margin:       20,
                    filename:     filename,
                    image:        { type: 'jpeg', quality: 0.98 },
                    html2canvas:  { scale: 2, useCORS: true, logging: false },
                    jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' },
                    pagebreak:    { mode: ['avoid-all', 'css', 'legacy'] }
                };
                
                html2pdf().set(opt).from(element).save().then(() => {
                    document.body.classList.remove('pdf-exporting');
                }).catch(err => {
                    console.error("PDF generation failed:", err);
                    document.body.classList.remove('pdf-exporting');
                });
            };

            useEffect(() => {
                if (window.mermaid && !loading && docContent) {
                    try {
                        // Initialize mermaid
                        window.mermaid.initialize({
                            startOnLoad: false,
                            theme: 'dark',
                            securityLevel: 'loose',
                            themeVariables: {
                                background: '#0d1117',
                                primaryColor: '#1f2937',
                                primaryTextColor: '#f3f4f6',
                                lineColor: '#3b82f6'
                            }
                        });

                        // Replace all language-mermaid pre blocks with div.mermaid
                        const wrappers = document.querySelectorAll(".markdown-wrapper pre code.language-mermaid");
                        let replaced = false;
                        
                        wrappers.forEach(el => {
                            const pre = el.parentElement;
                            const div = document.createElement("div");
                            div.className = "mermaid";
                            // Decode HTML entities (e.g. &gt;, &lt;) to raw mermaid text
                            const temp = document.createElement("textarea");
                            temp.innerHTML = el.innerHTML;
                            div.textContent = temp.value;
                            pre.replaceWith(div);
                            replaced = true;
                        });
                        
                        if (replaced) {
                            window.mermaid.run({
                                nodes: document.querySelectorAll(".mermaid")
                            });
                        }
                    } catch (e) {
                        console.error("Mermaid error:", e);
                    }
                }
            }, [docContent, loading]);

            return (
                <div className="app-container">
                    {/* Left Sidebar */}
                    <div className={`sidebar ${isSidebarCollapsed ? 'collapsed' : ''} ${isResizing ? 'resizing' : ''}`} style={{ width: isSidebarCollapsed ? '0px' : `${sidebarWidth}px` }}>
                        <div className="sidebar-header">
                            <Icon name="book-open" size={22} className="text-blue-500" />
                            <h1 style={{ marginRight: '0.5rem' }}>Everops Wiki</h1>
                            <button 
                                className="generate-btn"
                                onClick={() => setIsModalOpen(true)}
                                title="Build/Generate New Wiki"
                                style={{ marginLeft: '0.5rem' }}
                            >
                                <Icon name="plus-circle" size={20} />
                            </button>
                            <button 
                                onClick={() => setIsSidebarCollapsed(true)} 
                                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', marginLeft: 'auto', display: 'flex', alignItems: 'center' }}
                                title="Collapse Sidebar"
                            >
                                <Icon name="chevron-left" size={18} />
                            </button>
                        </div>
                        
                        <div className="search-container">
                            <div className="search-input-wrapper">
                                <Icon name="search" size={16} className="search-icon" />
                                <input 
                                    type="text" 
                                    className="search-input" 
                                    placeholder="Filter documentation..."
                                    value={searchTerm}
                                    onChange={e => setSearchTerm(e.target.value)}
                                />
                            </div>
                        </div>

                        <div className="tree-container">
                            {tree.length === 0 ? (
                                <div className="text-center text-gray-500 mt-8">No documents found.</div>
                            ) : (
                                tree.map((node, idx) => (
                                    <TreeNode 
                                        key={idx} 
                                        node={node} 
                                        searchTerm={searchTerm} 
                                        selectedPath={selectedPath}
                                        onSelectFile={handleSelectFile}
                                    />
                                ))
                            )}
                        </div>
                    </div>

                    {/* Resize Handle */}
                    {!isSidebarCollapsed && (
                        <div 
                            className={`resize-handle ${isResizing ? 'active' : ''}`}
                            onMouseDown={startResizing}
                        />
                    )}

                    {/* Right Content Area */}
                    <div className="content-area">
                        {selectedPath ? (
                            <>
                                <div className="content-header">
                                    <div className="doc-title-container">
                                        {isSidebarCollapsed && (
                                            <button 
                                                onClick={() => setIsSidebarCollapsed(false)} 
                                                style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer', marginRight: '0.75rem', display: 'flex', alignItems: 'center' }}
                                                title="Expand Sidebar"
                                            >
                                                <Icon name="menu" size={20} />
                                            </button>
                                        )}
                                        <Icon name="file-text" size={20} className="text-blue-400" />
                                        <span style={{ fontWeight: 600 }}>
                                            {selectedPath.split("/").pop()}
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                        {/* 
                                        <button 
                                            onClick={handleDownloadPDF} 
                                            className="tech-badge"
                                            style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', background: 'rgba(59, 130, 246, 0.15)', border: '1px solid rgba(59, 130, 246, 0.35)', color: '#60a5fa', transition: 'all 0.2s' }}
                                            title="Download print-friendly PDF"
                                        >
                                            <Icon name="download" size={13} /> PDF
                                        </button>
                                        */}
                                        <span className="tech-badge">{tech}</span>
                                        <span className="date-badge">{comp}</span>
                                        {date && <span className="date-badge">{date}</span>}
                                    </div>
                                </div>
                                
                                <div className="doc-body">
                                    {loading ? (
                                        <div className="placeholder-view">
                                            <Icon name="loader" size={32} className="animate-spin text-blue-500" />
                                            <p>Rendering documentation...</p>
                                        </div>
                                    ) : (
                                        <div className="markdown-wrapper markdown-body">
                                            {/* Print-only Header */}
                                            <div className="pdf-only-header">
                                                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #2563eb', paddingBottom: '6px', marginBottom: '24px', fontSize: '10px', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
                                                    <span>Everops Code Wiki Explorer</span>
                                                    <span>{tech} / {comp}</span>
                                                </div>
                                            </div>
                                            
                                            <div dangerouslySetInnerHTML={{ __html: docContent }} />
                                            
                                            {/* Print-only Footer */}
                                            <div className="pdf-only-footer">
                                                <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '10px', marginTop: '40px', display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: '#64748b', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
                                                    <span>Confidential & Proprietary</span>
                                                    <span>Generated on {new Date().toLocaleDateString()}</span>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </>
                        ) : (
                            <div className="placeholder-view" style={{ position: 'relative' }}>
                                {isSidebarCollapsed && (
                                    <button 
                                        onClick={() => setIsSidebarCollapsed(false)} 
                                        style={{ position: 'absolute', top: '1.5rem', left: '2rem', background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                                        title="Expand Sidebar"
                                    >
                                        <Icon name="menu" size={22} />
                                    </button>
                                )}
                                <div className="placeholder-logo">📚</div>
                                <h2>Everops Wiki Document Viewer</h2>
                                <p>Select any document from the sidebar to start reading.</p>
                            </div>
                        )}
                    </div>

                    {isModalOpen && (
                        <div className="modal-overlay">
                            <div className="modal-content" style={{ width: '560px', maxWidth: '95%' }}>
                                <div className="modal-header">
                                    <h2>Build & Generate Wiki</h2>
                                    <button className="modal-close-btn" onClick={() => setIsModalOpen(false)}>
                                        <Icon name="x" size={20} />
                                    </button>
                                </div>
                                
                                {jobStatus === "running" ? (
                                    <div style={{ textAlign: 'center', padding: '2rem 0' }}>
                                        <Icon name="loader" size={40} className="animate-spin text-blue-500" style={{ margin: '0 auto 1rem auto' }} />
                                        <p style={{ fontWeight: 500, color: '#f3f4f6' }}>Building documentation wiki...</p>
                                        <p style={{ fontSize: '0.875rem', color: '#9ca3af', marginTop: '0.5rem' }}>
                                            Cloning repository, running structural parsing, generating architectural synthesis, and uploading docs to cloud storage.
                                        </p>
                                    </div>
                                ) : (
                                    <>
                                        {/* Mode Switcher Tabs */}
                                        <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid #374151', marginBottom: '1.25rem', paddingBottom: '0.5rem' }}>
                                            <button 
                                                style={{ background: 'none', border: 'none', borderBottom: activeTab === 'vault' ? '2px solid #3b82f6' : 'none', color: activeTab === 'vault' ? '#3b82f6' : '#9ca3af', cursor: 'pointer', paddingBottom: '0.25rem', fontWeight: 600, fontSize: '0.9rem' }}
                                                onClick={() => setActiveTab('vault')}
                                            >
                                                Vault (Enterprise)
                                            </button>
                                            <button 
                                                style={{ background: 'none', border: 'none', borderBottom: activeTab === 'local' ? '2px solid #3b82f6' : 'none', color: activeTab === 'local' ? '#3b82f6' : '#9ca3af', cursor: 'pointer', paddingBottom: '0.25rem', fontWeight: 600, fontSize: '0.9rem' }}
                                                onClick={() => setActiveTab('local')}
                                            >
                                                Local (Manual Dev)
                                            </button>
                                        </div>

                                        <div style={{ maxHeight: '55vh', overflowY: 'auto', paddingRight: '0.5rem' }}>
                                            <div className="form-group">
                                                <label className="form-label">GitHub Repository URL / Path</label>
                                                <input 
                                                    type="text" 
                                                    className="form-input" 
                                                    placeholder="e.g. AAInternal/Sequence_Builder or HTTPS URL"
                                                    value={githubUrl}
                                                    onChange={e => setGithubUrl(e.target.value)}
                                                />
                                            </div>
                                            
                                            <div className="form-group">
                                                <label className="form-label">Technology Category</label>
                                                <select 
                                                    className="form-select"
                                                    value={techSelect}
                                                    onChange={e => setTechSelect(e.target.value)}
                                                >
                                                    <option value="generic">generic</option>
                                                    <option value="solver">solver</option>
                                                    <option value="flink">flink</option>
                                                    <option value="api">api</option>
                                                </select>
                                            </div>
                                            
                                            <div className="form-group">
                                                <label className="form-label">Ignore Paths (Comma-separated)</label>
                                                <textarea 
                                                    className="form-textarea" 
                                                    rows="2"
                                                    value={ignorePathsInput}
                                                    onChange={e => setIgnorePathsInput(e.target.value)}
                                                />
                                            </div>

                                            {activeTab === "vault" ? (
                                                <div style={{ background: '#1e293b', borderLeft: '4px solid #3b82f6', padding: '0.75rem 1rem', borderRadius: '4px', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '1rem' }}>
                                                    🔒 All connection parameters, credentials, NATS endpoints, and storage targets will be dynamically resolved from the Open Bao (Vault) agent configuration context.
                                                </div>
                                            ) : (
                                                <div style={{ borderTop: '1px dashed #374151', paddingTop: '1rem', marginTop: '1rem' }}>
                                                    <h3 style={{ fontSize: '0.95rem', color: '#f3f4f6', marginBottom: '1rem', fontWeight: 600 }}>Local Developer Credentials overrides</h3>
                                                    
                                                    <div className="form-group">
                                                        <label className="form-label">GitHub PAT Override (Optional)</label>
                                                        <input 
                                                            type="password" 
                                                            className="form-input" 
                                                            placeholder="Personal Access Token for cloning private repos"
                                                            value={githubToken}
                                                            onChange={e => setGithubToken(e.target.value)}
                                                        />
                                                    </div>

                                                    <h4 style={{ fontSize: '0.85rem', color: '#3b82f6', margin: '1rem 0 0.5rem 0', fontWeight: 600 }}>NATS completions settings</h4>
                                                    <div className="form-group">
                                                        <label className="form-label">NATS Server URL</label>
                                                        <input 
                                                            type="text" 
                                                            className="form-input" 
                                                            placeholder="nats://localhost:4222"
                                                            value={localNatsUrl}
                                                            onChange={e => setLocalNatsUrl(e.target.value)}
                                                        />
                                                    </div>
                                                    <div style={{ display: 'flex', gap: '0.75rem' }}>
                                                        <div className="form-group" style={{ flex: 1 }}>
                                                            <label className="form-label">NATS Username</label>
                                                            <input 
                                                                type="text" 
                                                                className="form-input" 
                                                                value={localNatsUser}
                                                                onChange={e => setLocalNatsUser(e.target.value)}
                                                            />
                                                        </div>
                                                        <div className="form-group" style={{ flex: 1 }}>
                                                            <label className="form-label">NATS Password</label>
                                                            <input 
                                                                type="password" 
                                                                className="form-input" 
                                                                value={localNatsPass}
                                                                onChange={e => setLocalNatsPass(e.target.value)}
                                                            />
                                                        </div>
                                                    </div>

                                                    <h4 style={{ fontSize: '0.85rem', color: '#3b82f6', margin: '1rem 0 0.5rem 0', fontWeight: 600 }}>Local target storage Settings</h4>
                                                    <div className="form-group">
                                                        <label className="form-label">Storage Backend Type</label>
                                                        <select 
                                                            className="form-select"
                                                            value={localStorageType}
                                                            onChange={e => setLocalStorageType(e.target.value)}
                                                        >
                                                            <option value="efs">Local filesystem / EFS</option>
                                                            <option value="s3">AWS S3 Bucket</option>
                                                            <option value="azure">Azure Blob Storage</option>
                                                        </select>
                                                    </div>

                                                    {localStorageType === "s3" && (
                                                        <>
                                                            <div className="form-group">
                                                                <label className="form-label">S3 Bucket Name</label>
                                                                <input 
                                                                    type="text" 
                                                                    className="form-input" 
                                                                    placeholder="e.g. codewiki-bucket"
                                                                    value={localS3Bucket}
                                                                    onChange={e => setLocalS3Bucket(e.target.value)}
                                                                />
                                                            </div>
                                                            <div className="form-group">
                                                                <label className="form-label">S3 Region</label>
                                                                <input 
                                                                    type="text" 
                                                                    className="form-input" 
                                                                    placeholder="e.g. us-west-2"
                                                                    value={localS3Region}
                                                                    onChange={e => setLocalS3Region(e.target.value)}
                                                                />
                                                            </div>
                                                            <div style={{ display: 'flex', gap: '0.75rem' }}>
                                                                <div className="form-group" style={{ flex: 1 }}>
                                                                    <label className="form-label">AWS Access Key ID</label>
                                                                    <input 
                                                                        type="text" 
                                                                        className="form-input" 
                                                                        value={localS3AccessKey}
                                                                        onChange={e => setLocalS3AccessKey(e.target.value)}
                                                                    />
                                                                </div>
                                                                <div className="form-group" style={{ flex: 1 }}>
                                                                    <label className="form-label">AWS Secret Access Key</label>
                                                                    <input 
                                                                        type="password" 
                                                                        className="form-input" 
                                                                        value={localS3SecretKey}
                                                                        onChange={e => setLocalS3SecretKey(e.target.value)}
                                                                    />
                                                                </div>
                                                            </div>
                                                        </>
                                                    )}

                                                    {localStorageType === "azure" && (
                                                        <>
                                                            <div className="form-group">
                                                                <label className="form-label">Azure Container Name</label>
                                                                <input 
                                                                    type="text" 
                                                                    className="form-input" 
                                                                    placeholder="e.g. wikicontainer"
                                                                    value={localAzureContainer}
                                                                    onChange={e => setLocalAzureContainer(e.target.value)}
                                                                />
                                                            </div>
                                                            <div className="form-group">
                                                                <label className="form-label">Azure Storage Connection String</label>
                                                                <textarea 
                                                                    className="form-textarea" 
                                                                    rows="2"
                                                                    placeholder="DefaultEndpointsProtocol=https;..."
                                                                    value={localAzureConnStr}
                                                                    onChange={e => setLocalAzureConnStr(e.target.value)}
                                                                />
                                                            </div>
                                                        </>
                                                    )}

                                                    {localStorageType === "efs" && (
                                                        <div className="form-group">
                                                            <label className="form-label">EFS Base Directory Path</label>
                                                            <input 
                                                                type="text" 
                                                                className="form-input" 
                                                                placeholder="e.g. ."
                                                                value={localEfsBasePath}
                                                                onChange={e => setLocalEfsBasePath(e.target.value)}
                                                            />
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                        
                                        {jobError && (
                                            <div style={{ color: '#ef4444', fontSize: '0.875rem', marginTop: '0.75rem', marginBottom: '0.75rem' }}>
                                                Error: {jobError}
                                            </div>
                                        )}
                                        
                                        <div className="modal-footer" style={{ borderTop: '1px solid #374151', paddingTop: '1rem', marginTop: '1rem' }}>
                                            <button className="btn btn-secondary" onClick={() => setIsModalOpen(false)}>
                                                Cancel
                                            </button>
                                            <button 
                                                className="btn btn-primary" 
                                                onClick={handleStartGeneration}
                                                disabled={!githubUrl.trim()}
                                            >
                                                Build Wiki
                                            </button>
                                        </div>
                                    </>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            );
        };

        const root = ReactDOM.createRoot(document.getElementById("root"));
        root.render(<App />);
    </script>
</body>
</html>
"""
    return html_content

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8081)
