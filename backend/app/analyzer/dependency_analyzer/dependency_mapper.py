from typing import List, Dict, Set
import os
from app.schemas.project import FileModel, DependencyEdge, DependsEdge


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_module_index(files: List[FileModel]) -> Dict[str, str]:
    """
    Build a lookup for resolving imports to project files.

    Provides:
      - Dotted lookup for Python (e.g. 'app.models.user')
      - Path lookup for JS/TS (e.g. 'frontend/services/user')
    """
    index: Dict[str, str] = {}
    for f in files:
        path = f.file.replace("\\", "/")
        # Strip leading "./" if present
        if path.startswith("./"):
            path = path[2:]
        # Strip extension
        without_ext = path.rsplit(".", 1)[0]
        
        # 1. Path-based lookup (JS/TS relative imports)
        index[without_ext] = f.file
        # Map frontend/services/user/index to frontend/services/user
        if without_ext.endswith("/index"):
            index[without_ext[:-6]] = f.file

        # 2. Dotted lookup (Python)
        # Register all suffix paths to handle cases where the project root (e.g. 'backend')
        # is not part of the import string (e.g. 'app.services.user').
        parts = without_ext.split("/")
        for i in range(len(parts)):
            suffix_dotted = ".".join(parts[i:])
            if suffix_dotted not in index:
                index[suffix_dotted] = f.file
            # Map app.services.__init__ to app.services
            if suffix_dotted.endswith(".__init__"):
                index[suffix_dotted[:-9]] = f.file

    return index


def _resolve_import(imp: str, source_file: str, module_index: Dict[str, str]) -> tuple[str, str, str]:
    """
    Returns (kind, resolved_file, target_module).
    kind = "INTERNAL" if the import matches a project file, "EXTERNAL" otherwise.
    """
    imp = imp.split(" as ")[0].strip()
    # 1. Relative imports (Python and JS/TS)
    if imp.startswith("."):
        # Count leading dots
        dots = 0
        for c in imp:
            if c == ".":
                dots += 1
            else:
                break
        
        # Calculate parent directory based on dots
        # '.' means current dir, '..' means parent dir, etc.
        # But wait! If the file is `backend/app/services/order.py`:
        # dirname is `backend/app/services`.
        # '.' -> backend/app/services
        # '..' -> backend/app
        source_dir = os.path.dirname(source_file).replace("\\", "/")
        dir_parts = source_dir.split("/")
        
        # JS/TS relative imports use slashes: "../services/user"
        # Python relative imports use dots: "..services.user"
        if "/" in imp:
            # JS/TS style
            resolved_path = os.path.normpath(os.path.join(source_dir, imp)).replace("\\", "/")
            resolved_path = resolved_path.rstrip("/")
        else:
            # Python style
            # pop directories for dots > 1
            if dots > 1:
                pops = dots - 1
                if pops <= len(dir_parts):
                    dir_parts = dir_parts[:-pops]
                else:
                    dir_parts = []
                    
            base_dir = "/".join(dir_parts)
            remainder = imp[dots:].replace(".", "/")
            resolved_path = os.path.normpath(f"{base_dir}/{remainder}").replace("\\", "/") if remainder else base_dir
            
        # Try to match the resolved path. If it contains symbols at the end, pop them off.
        path_parts = resolved_path.split("/")
        for length in range(len(path_parts), 0, -1):
            candidate_path = "/".join(path_parts[:length])
            if candidate_path in module_index:
                return "INTERNAL", module_index[candidate_path], imp
            if f"{candidate_path}/__init__" in module_index:
                return "INTERNAL", module_index[f"{candidate_path}/__init__"], imp
            if f"{candidate_path}/index" in module_index:
                return "INTERNAL", module_index[f"{candidate_path}/index"], imp
            
        return "EXTERNAL", "", imp

    # 3. Python dotted imports
    parts = imp.split(".")
    for length in range(len(parts), 0, -1):
        candidate = ".".join(parts[:length])
        if candidate in module_index:
            # Return imp as target_module so we don't truncate the class name
            return "INTERNAL", module_index[candidate], imp
            
    return "EXTERNAL", "", imp


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_dependencies(files: List[FileModel]) -> List[DependencyEdge]:
    """
    Produce cross-file import dependency edges.

    Each entry in ``files`` is inspected for its imports.  Imports that
    resolve to another file in the project are tagged ``kind="INTERNAL"``;
    third-party / stdlib imports are ``kind="EXTERNAL"``.
    """
    module_index = _build_module_index(files)
    edges: List[DependencyEdge] = []
    seen: Set[tuple] = set()

    for f in files:
        for imp in f.imports:
            kind, resolved, target_mod = _resolve_import(imp, f.file, module_index)
            key = (f.file, imp)
            if key in seen:
                continue
            seen.add(key)

            # Skip self-references (a file importing itself via a relative path)
            if kind == "INTERNAL" and resolved == f.file:
                continue

            edges.append(DependencyEdge(
                source_file=f.file,
                # INTERNAL: use matched module path ("app.services.user")
                # EXTERNAL: use full import string ("fastapi.FastAPI") — the symbol IS the identifier
                target_module=target_mod,
                kind=kind,
                resolved_file=resolved if resolved else None,
            ))

    return edges


def _resolve_through_init(
    symbol: str,
    resolved_file: str,
    files: List[FileModel],
    module_index: Dict[str, str],
    _visited: set = None,
) -> str:
    """
    If `resolved_file` is an __init__.py that re-exports `symbol`,
    follow the chain until we find the actual definition file.
    Returns the deepest resolved file path.
    """
    if _visited is None:
        _visited = set()

    if resolved_file in _visited:
        return resolved_file
    _visited.add(resolved_file)

    if not resolved_file.endswith("__init__.py"):
        return resolved_file

    # Find the __init__.py FileModel
    init_file = next((f for f in files if f.file == resolved_file), None)
    if init_file is None:
        return resolved_file

    # Search its imports for the symbol
    for imp in init_file.imports:
        parts = imp.split(" as ")
        alias = parts[1].strip() if len(parts) > 1 else parts[0].split(".")[-1]
        real_imp = parts[0].strip()
        if alias == symbol:
            kind, next_resolved, _ = _resolve_import(real_imp, resolved_file, module_index)
            if kind == "INTERNAL" and next_resolved and next_resolved != resolved_file:
                return _resolve_through_init(symbol, next_resolved, files, module_index, _visited)

    return resolved_file


def map_depends_edges(files: List[FileModel]) -> List[DependsEdge]:
    """
    Produce FastAPI ``Depends()`` injection edges.

    Reads ``FunctionModel.depends_on`` (populated by the Python AST parser)
    and returns one edge per (caller_function → injected_function) pair.
    """
    edges: List[DependsEdge] = []
    seen: Set[tuple] = set()

    # Pre-build a map of all functions to their source file
    all_funcs_map: Dict[str, str] = {}
    for file_model in files:
        for func in file_model.functions:
            all_funcs_map[func.name] = file_model.file

    module_index = _build_module_index(files)

    for f in files:
        for func in f.functions:
            for dep in func.depends_on:
                key = (f.file, func.name, dep)
                if key in seen:
                    continue
                seen.add(key)
                
                target_file = None
                target_func_name = dep
                
                # 1. Check if the dependency is defined in the same file
                if any(fn.name == dep for fn in f.functions):
                    target_file = f.file
                else:
                    # 2. Check if the dependency is imported
                    for imp in f.imports:
                        parts = imp.split(" as ")
                        alias = parts[1].strip() if len(parts) > 1 else parts[0].split(".")[-1]
                        real_imp = parts[0].strip()
                        if alias == dep:
                            kind, resolved, target_mod = _resolve_import(real_imp, f.file, module_index)
                            if kind == "INTERNAL" and resolved:
                                # Follow re-export chains through __init__.py
                                resolved = _resolve_through_init(dep, resolved, files, module_index)
                                target_file = resolved
                                target_func_name = real_imp.split(".")[-1]
                                break
                    
                    # 3. Fallback: Check if it's defined globally somewhere else
                    if not target_file:
                        if dep in all_funcs_map:
                            target_file = all_funcs_map[dep]
                        else:
                            for class_method, file_path in all_funcs_map.items():
                                if class_method.endswith(f".{dep}"):
                                    target_file = file_path
                                    target_func_name = class_method
                                    break

                # Ignore external builtins or unknown functions that we cannot resolve internally
                if not target_file:
                    continue

                edges.append(DependsEdge(
                    source_file=f.file,
                    source_function=func.name,
                    target_file=target_file,
                    target_function=target_func_name,
                ))

    return edges

