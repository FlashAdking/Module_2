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
            
        if resolved_path in module_index:
            return "INTERNAL", module_index[resolved_path], imp
        if f"{resolved_path}/__init__" in module_index:
            return "INTERNAL", module_index[f"{resolved_path}/__init__"], imp
        if f"{resolved_path}/index" in module_index:
            return "INTERNAL", module_index[f"{resolved_path}/index"], imp
            
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
                
                # 1. Check if the dependency is defined in the same file
                if any(fn.name == dep for fn in f.functions):
                    target_file = f.file
                else:
                    # 2. Check if the dependency is imported
                    for imp in f.imports:
                        if imp.endswith(f".{dep}") or imp == dep:
                            kind, resolved, target_mod = _resolve_import(imp, f.file, module_index)
                            if kind == "INTERNAL" and resolved:
                                target_file = resolved
                                break
                    
                    # 3. Fallback: Check if it's defined globally somewhere else
                    if not target_file and dep in all_funcs_map:
                        target_file = all_funcs_map[dep]

                edges.append(DependsEdge(
                    source_file=f.file,
                    source_function=func.name,
                    target_file=target_file,
                    target_function=dep,
                ))

    return edges
