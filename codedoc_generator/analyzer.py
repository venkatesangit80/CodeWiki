import ast
import os
import logging
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger(__name__)

class SymbolRecord:
    def __init__(
        self,
        unit_id: str,
        repo_id: str,
        file_path: str,
        kind: str,
        name: str,
        parent: Optional[str],
        signature: str,
        start_line: int,
        end_line: int,
        imports: List[str],
        calls: List[str],
        docstring: str,
        is_entry_point: bool,
        code_content: str
    ):
        self.unit_id = unit_id
        self.repo_id = repo_id
        self.file_path = file_path
        self.kind = kind  # "class" | "function" | "method"
        self.name = name
        self.parent = parent
        self.signature = signature
        self.start_line = start_line
        self.end_line = end_line
        self.imports = imports
        self.calls = calls
        self.docstring = docstring
        self.is_entry_point = is_entry_point
        self.code_content = code_content

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "repo_id": self.repo_id,
            "file_path": self.file_path,
            "kind": self.kind,
            "name": self.name,
            "parent": self.parent,
            "signature": self.signature,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "imports": self.imports,
            "calls": self.calls,
            "docstring": self.docstring,
            "is_entry_point": self.is_entry_point,
            "code_content": self.code_content
        }

class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, repo_id: str, file_content: str):
        self.file_path = file_path
        self.repo_id = repo_id
        self.file_content = file_content
        self.lines = file_content.splitlines()
        
        self.symbols: List[SymbolRecord] = []
        self.imports: List[str] = []
        self.import_map: Dict[str, str] = {}  # local name -> imported module path
        
        self.scope_stack: List[str] = []  # Names of classes/functions we are inside
        self.current_class: Optional[str] = None
        self.class_bases: Dict[str, List[str]] = {}  # class name -> superclasses

        # Active function context
        self.current_function_calls: List[str] = []

    def get_line_range(self, node: ast.AST) -> Tuple[int, int]:
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        return start, end

    def get_source_segment(self, start: int, end: int) -> str:
        # 1-indexed lines
        return "\n".join(self.lines[start-1:end])

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            self.imports.append(name)
            self.import_map[asname] = name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        level = node.level
        # Handle relative imports (approximate module root if level > 0)
        if level > 0:
            parts = os.path.dirname(self.file_path).split(os.sep)
            # Remove components based on level
            if level <= len(parts):
                base = ".".join(parts[:-level+1] if level > 1 else parts)
                module = f"{base}.{module}" if module else base
        
        for alias in node.names:
            full_import = f"{module}.{alias.name}" if module else alias.name
            asname = alias.asname or alias.name
            self.imports.append(full_import)
            self.import_map[asname] = full_import
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_name = node.name
        outer_class = self.current_class
        if outer_class:
            class_name = f"{outer_class}.{class_name}"
            
        self.current_class = class_name
        self.scope_stack.append(class_name)

        # Extract bases
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                # E.g. module.BaseClass
                bases.append(self._get_attribute_name(base))
        self.class_bases[class_name] = bases

        start, end = self.get_line_range(node)
        docstring = ast.get_docstring(node) or ""
        code_segment = self.get_source_segment(start, end)
        
        # Build symbol
        unit_id = f"{self.repo_id}::{self.file_path}::{class_name}"
        record = SymbolRecord(
            unit_id=unit_id,
            repo_id=self.repo_id,
            file_path=self.file_path,
            kind="class",
            name=class_name,
            parent=outer_class,
            signature=f"class {node.name}({', '.join(bases)})",
            start_line=start,
            end_line=end,
            imports=list(self.imports),
            calls=[],
            docstring=docstring,
            is_entry_point=False,
            code_content=code_segment
        )
        self.symbols.append(record)

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_class = outer_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function(node)

    def _visit_function(self, node: ast.AST):
        func_name = node.name
        is_method = self.current_class is not None
        parent_name = self.current_class
        
        full_name = f"{parent_name}.{func_name}" if parent_name else func_name
        self.scope_stack.append(full_name)

        # Save active function calls accumulator
        prev_calls = self.current_function_calls
        self.current_function_calls = []

        # Find decorators to check entry points
        is_entry = False
        for dec in node.decorator_list:
            dec_name = ""
            if isinstance(dec, ast.Name):
                dec_name = dec.id
            elif isinstance(dec, ast.Attribute):
                dec_name = self._get_attribute_name(dec)
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    dec_name = dec.func.id
                elif isinstance(dec.func, ast.Attribute):
                    dec_name = self._get_attribute_name(dec.func)
            
            # Heuristics for Flask/FastAPI/cli decorators
            if any(term in dec_name.lower() for term in ["route", "get", "post", "put", "delete", "cli", "command", "task"]):
                is_entry = True

        start, end = self.get_line_range(node)
        docstring = ast.get_docstring(node) or ""
        code_segment = self.get_source_segment(start, end)

        # Reconstruct signature line
        args_list = []
        for arg in node.args.args:
            args_list.append(arg.arg)
        sig = f"def {node.name}({', '.join(args_list)})"

        # Visit function body to accumulate calls
        for item in node.body:
            self.visit(item)

        unit_id = f"{self.repo_id}::{self.file_path}::{full_name}"
        record = SymbolRecord(
            unit_id=unit_id,
            repo_id=self.repo_id,
            file_path=self.file_path,
            kind="method" if is_method else "function",
            name=full_name,
            parent=parent_name,
            signature=sig,
            start_line=start,
            end_line=end,
            imports=list(self.imports),
            calls=list(self.current_function_calls),
            docstring=docstring,
            is_entry_point=is_entry,
            code_content=code_segment
        )
        self.symbols.append(record)

        # Restore calls accumulator
        self.current_function_calls = prev_calls
        self.scope_stack.pop()

    def visit_Call(self, node: ast.Call):
        # Extract call targets
        call_target = ""
        if isinstance(node.func, ast.Name):
            call_target = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_target = self._get_attribute_name(node.func)
            
        if call_target:
            self.current_function_calls.append(call_target)
            
        self.generic_visit(node)

    def _get_attribute_name(self, node: ast.Attribute) -> str:
        parts = []
        curr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
        parts.reverse()
        return ".".join(parts)


class SemanticResolver:
    def __init__(self, repo_id: str, local_path: str):
        self.repo_id = repo_id
        self.local_path = local_path
        self.symbol_records: Dict[str, SymbolRecord] = {}
        self.file_symbols: Dict[str, List[SymbolRecord]] = {}
        self.class_hierarchy: Dict[str, List[str]] = {}  # subclass -> bases

    def add_symbols_from_file(self, file_path: str, visitor: PythonASTVisitor):
        self.file_symbols[file_path] = visitor.symbols
        for symbol in visitor.symbols:
            self.symbol_records[symbol.unit_id] = symbol
        for cls_name, bases in visitor.class_bases.items():
            self.class_hierarchy[cls_name] = bases

    def resolve_dependencies(self) -> List[Dict[str, Any]]:
        """
        Processes raw function call strings into concrete reference edges.
        Returns:
            A list of dependency edge dictionaries: {'from': unit_id, 'to': unit_id, 'type': 'calls'}
        """
        edges: List[Dict[str, Any]] = []
        
        # Build local index maps for fast lookup
        # Map: file_path -> list of (symbol name, symbol_id)
        local_symbols: Dict[str, List[Tuple[str, str]]] = {}
        for file_path, symbols in self.file_symbols.items():
            local_symbols[file_path] = [(s.name, s.unit_id) for s in symbols]

        for unit_id, symbol in self.symbol_records.items():
            if symbol.kind == "class":
                continue
                
            resolved_calls: Set[str] = set()
            for call in symbol.calls:
                resolved_id = self._resolve_call_target(symbol, call, local_symbols)
                if resolved_id and resolved_id != unit_id:
                    resolved_calls.add(resolved_id)
            
            # Map resolved calls to edges
            for target_id in resolved_calls:
                edges.append({
                    "from": unit_id,
                    "to": target_id,
                    "type": "calls"
                })
                
            # Also record cross-file imports as dependency edges at the module/file level
            # (which HLDD generation uses)
            for imp in symbol.imports:
                # E.g. imp = 'codewiki.src.be.backend'
                # Let's see if we can resolve this import to a file in our repo
                imported_file = self._resolve_import_to_file(imp)
                if imported_file:
                    edges.append({
                        "from": symbol.file_path,
                        "to": imported_file,
                        "type": "imports"
                    })
                    
        return edges

    def _resolve_call_target(self, caller: SymbolRecord, call: str, local_symbols: Dict[str, List[Tuple[str, str]]]) -> Optional[str]:
        # Case 1: call starts with "self." (e.g. self._verify_password)
        if call.startswith("self."):
            method_name = call[5:]
            if caller.parent:
                target_unit = f"{self.repo_id}::{caller.file_path}::{caller.parent}.{method_name}"
                if target_unit in self.symbol_records:
                    return target_unit
                # Check base classes
                for base in self.class_hierarchy.get(caller.parent, []):
                    target_unit = f"{self.repo_id}::{caller.file_path}::{base}.{method_name}"
                    if target_unit in self.symbol_records:
                        return target_unit
            return None

        # Case 2: Direct call to a function defined in the same file
        for name, unit_id in local_symbols.get(caller.file_path, []):
            if name == call:
                return unit_id

        # Case 3: Call to a class method (e.g. AuthService.login) where AuthService is in the same file
        if "." in call:
            parts = call.split(".")
            class_name = parts[0]
            method_name = ".".join(parts[1:])
            # Search same-file classes
            for name, unit_id in local_symbols.get(caller.file_path, []):
                if name == class_name:
                    target_unit = f"{self.repo_id}::{caller.file_path}::{class_name}.{method_name}"
                    if target_unit in self.symbol_records:
                        return target_unit

        # Case 4: Call matches an imported symbol (e.g. logger.info or backend.get_backend)
        # Check imports of the file
        for imp in caller.imports:
            # Check if import matches call prefix
            if "." in call:
                first_part = call.split(".")[0]
                if imp.endswith(f".{first_part}") or imp == first_part:
                    # Target resides in the imported module. Resolve the file.
                    target_file = self._resolve_import_to_file(imp)
                    if target_file:
                        # Attempt to match the remaining parts to a symbol in target_file
                        rem = ".".join(call.split(".")[1:])
                        # Look for class or function in target file symbols
                        for name, unit_id in local_symbols.get(target_file, []):
                            if name == rem or name.endswith(f".{rem}"):
                                return unit_id
            else:
                # E.g. call = "get_backend" and we did "from backend import get_backend"
                if imp.endswith(f".{call}"):
                    module_part = ".".join(imp.split(".")[:-1])
                    target_file = self._resolve_import_to_file(module_part)
                    if target_file:
                        for name, unit_id in local_symbols.get(target_file, []):
                            if name == call:
                                return unit_id
                                
        return None

    def _resolve_import_to_file(self, import_dotted_path: str) -> Optional[str]:
        # Walk relative paths matching the dotted notation.
        # E.g. codewiki.src.be.backend -> codewiki/src/be/backend.py
        path_parts = import_dotted_path.split(".")
        candidate_rel_path = os.path.join(*path_parts)
        
        # Test candidate file paths
        for ext in [".py", ".java", "/__init__.py"]:
            test_path = candidate_rel_path + ext
            full_test_path = os.path.join(self.local_path, test_path)
            if os.path.exists(full_test_path):
                return os.path.relpath(full_test_path, self.local_path)
                
        # Handle cases where the top-level folder is stripped in imports (like Java src/main/java)
        for root, dirs, files in os.walk(self.local_path):
            if any(ignore in root for ignore in [".git", "node_modules", "dist", "build", "venv", "__pycache__"]):
                continue
            for d in dirs:
                if d == path_parts[0] or d == "java" or d == "src":
                    # Try matching from subdirectories
                    test_rel = os.path.relpath(os.path.join(root, candidate_rel_path), self.local_path)
                    for ext in [".py", ".java", "/__init__.py"]:
                        test_path = test_rel + ext
                        full_test_path = os.path.join(self.local_path, test_path)
                        if os.path.exists(full_test_path):
                            return os.path.relpath(full_test_path, self.local_path)
                            
        return None


class JavaSimpleParser:
    def __init__(self, file_path: str, repo_id: str, content: str):
        self.file_path = file_path
        self.repo_id = repo_id
        self.content = content
        self.lines = content.splitlines()
        self.symbols: List[SymbolRecord] = []
        self.imports: List[str] = []
        self.class_bases: Dict[str, List[str]] = {}
        self.class_methods: Dict[str, Set[str]] = {}
        
        self._parse()

    def _parse(self):
        import re
        # Extract imports
        import_matches = re.findall(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", self.content, re.MULTILINE)
        self.imports = list(import_matches)
        
        # Extract class/interface declarations
        class_regex = r"(?:public\s+)?(?:abstract\s+)?(?:class|interface)\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w\s,]+))?"
        class_matches = list(re.finditer(class_regex, self.content))
        current_class = None
        for match in class_matches:
            class_name = match.group(1)
            current_class = class_name
            bases = []
            if match.group(2):
                bases.append(match.group(2))
            if match.group(3):
                bases.extend([b.strip() for b in match.group(3).split(",")])
            self.class_bases[class_name] = bases
            
            # Add class symbol
            unit_id = f"{self.repo_id}::{self.file_path}::{class_name}"
            docstring = self._find_javadoc_above(match.start())
            record = SymbolRecord(
                unit_id=unit_id,
                repo_id=self.repo_id,
                file_path=self.file_path,
                kind="class",
                name=class_name,
                parent=None,
                signature=f"class {class_name}",
                start_line=self._pos_to_line(match.start()),
                end_line=self._pos_to_line(match.end()),
                imports=list(self.imports),
                calls=[],
                docstring=docstring,
                is_entry_point=False,
                code_content=match.group(0)
            )
            self.symbols.append(record)
            
        # Parse methods
        # Standard method: modifier return_type name(args) {
        method_regex = r"(?:@\w+(?:\([^)]*\))?\s*)*?(?:public|private|protected|package)?\s*(?:static\s+)?(?:final\s+)?(?:[\w<>\s\[\]]+)\s+(\w+)\(([^)]*)\)\s*(?:throws\s+[\w\s,]+)?\s*\{"
        method_matches = list(re.finditer(method_regex, self.content))
        for match in method_matches:
            method_name = match.group(1)
            # Skip control flow keywords
            if method_name in ["if", "for", "while", "switch", "catch", "synchronized", "class", "interface", "return"]:
                continue
                
            args = match.group(2)
            start_pos = match.start()
            start_line = self._pos_to_line(start_pos)
            
            end_pos = self._find_matching_brace(match.end() - 1)
            end_line = self._pos_to_line(end_pos) if end_pos != -1 else len(self.lines)
            
            docstring = self._find_javadoc_above(start_pos)
            
            body = self.content[match.end():end_pos] if end_pos != -1 else ""
            calls = self._extract_calls_from_body(body)
            
            # Entry point heuristics
            is_entry = False
            context_above = self.content[max(0, start_pos-200):start_pos]
            combined_context = context_above + match.group(0)
            if any(term in combined_context for term in ["@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@RequestMapping", "@Scheduled", "@KafkaListener", "@EventListener"]):
                is_entry = True
            if method_name == "main" and "public static void main" in match.group(0):
                is_entry = True
                
            full_name = f"{current_class}.{method_name}" if current_class else method_name
            unit_id = f"{self.repo_id}::{self.file_path}::{full_name}"
            
            sig = f"{method_name}({args})"
            code_content = self.content[start_pos:end_pos+1] if end_pos != -1 else match.group(0)
            
            record = SymbolRecord(
                unit_id=unit_id,
                repo_id=self.repo_id,
                file_path=self.file_path,
                kind="method" if current_class else "function",
                name=full_name,
                parent=current_class,
                signature=sig,
                start_line=start_line,
                end_line=end_line,
                imports=list(self.imports),
                calls=calls,
                docstring=docstring,
                is_entry_point=is_entry,
                code_content=code_content
            )
            self.symbols.append(record)

    def _pos_to_line(self, pos: int) -> int:
        return self.content[:pos].count("\n") + 1

    def _find_javadoc_above(self, pos: int) -> str:
        import re
        text_before = self.content[:pos]
        matches = list(re.finditer(r"/\*\*(.*?)\*/", text_before, re.DOTALL))
        if matches:
            last_match = matches[-1]
            match_end_line = self._pos_to_line(last_match.end())
            symbol_line = self._pos_to_line(pos)
            if symbol_line - match_end_line <= 3:
                doc_lines = []
                for line in last_match.group(1).splitlines():
                    line = line.strip().lstrip("*").strip()
                    if line:
                        doc_lines.append(line)
                return "\n".join(doc_lines)
        return ""

    def _find_matching_brace(self, start_pos: int) -> int:
        brace_count = 0
        in_string = False
        in_char = False
        escape = False
        
        for i in range(start_pos, len(self.content)):
            char = self.content[i]
            
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"' and not in_char:
                in_string = not in_string
                continue
            if char == "'" and not in_string:
                in_char = not in_char
                continue
            if in_string or in_char:
                continue
                
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    return i
        return -1

    def _extract_calls_from_body(self, body: str) -> List[str]:
        import re
        calls = re.findall(r"\b([\w.]+)\s*\(", body)
        return list(set(calls))
