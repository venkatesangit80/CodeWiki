import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import List, Dict, Any

app = FastAPI(title="CodeWiki Document Viewer")

WORKSPACE_DIR = Path(__file__).parent.resolve()
REPO_DOCS_DIR = WORKSPACE_DIR / "repo_docs"

# Serve the static files from repo_docs
if REPO_DOCS_DIR.exists():
    app.mount("/repo_docs", StaticFiles(directory=str(REPO_DOCS_DIR)), name="repo_docs")

def build_tree(path: Path, relative_to: Path) -> List[Dict[str, Any]]:
    tree = []
    try:
        # Sort directories first, then files
        for entry in sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith(".") or entry.name == "System Volume Information":
                continue
            
            rel_path = entry.relative_to(relative_to)
            
            if entry.is_dir():
                children = build_tree(entry, relative_to)
                if children: # Only add directory if it has children or files
                    tree.append({
                        "name": entry.name,
                        "type": "directory",
                        "path": str(rel_path),
                        "children": children
                    })
            else:
                if entry.suffix.lower() == ".md":
                    tree.append({
                        "name": entry.name,
                        "type": "file",
                        "path": str(rel_path)
                    })
    except Exception as e:
        pass
    return tree

@app.get("/api/tree")
def get_tree():
    if not REPO_DOCS_DIR.exists():
        return []
    return build_tree(REPO_DOCS_DIR, REPO_DOCS_DIR)

@app.get("/", response_class=HTMLResponse)
def get_index():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CodeWiki Interactive Viewer</title>
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
                    setComp("CodeWiki");
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
                    <div className="sidebar">
                        <div className="sidebar-header">
                            <Icon name="book-open" size={22} className="text-blue-500" />
                            <h1>CodeWiki Explorer</h1>
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

                    {/* Right Content Area */}
                    <div className="content-area">
                        {selectedPath ? (
                            <>
                                <div className="content-header">
                                    <div className="doc-title-container">
                                        <Icon name="file-text" size={20} className="text-blue-400" />
                                        <span style={{ fontWeight: 600 }}>
                                            {selectedPath.split("/").pop()}
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
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
                                        <div 
                                            className="markdown-wrapper markdown-body"
                                            dangerouslySetInnerHTML={{ __html: docContent }}
                                        />
                                    )}
                                </div>
                            </>
                        ) : (
                            <div className="placeholder-view">
                                <div className="placeholder-logo">📚</div>
                                <h2>CodeWiki Document Viewer</h2>
                                <p>Select any document from the sidebar to start reading.</p>
                            </div>
                        )}
                    </div>
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
