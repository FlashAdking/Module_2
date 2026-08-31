from typing import List, Dict, Set
from app.schemas.project import FileModel, DependencyEdge, DependsEdge


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_module_index(files: List[FileModel]) -> Dict[str, str]:
    """
    Build a lookup: dotted-module-path → project-relative file path.

    Example:
        "app/models/user.py"  →  {"app.models.user": "app/models/user.py",
                                   "app.models":       "app/models/user.py"}

    This lets us resolve import strings like ``"app.models.user"`` back to
    real files inside the project.
    """
    index: Dict[str, str] = {}
    for f in files:
        path = f.file.replace("\\", "/")
        # Strip leading "./" if present
        if path.startswith("./"):
            path = path[2:]
        # Strip extension
        without_ext = path.rsplit(".", 1)[0]
        # Convert slashes → dots  (app/models/user → app.models.user)
        dotted = without_ext.replace("/", ".")
        index[dotted] = f.file
        # Also register parent packages so "from app.models import user" hits
        parts = dotted.split(".")
        for i in range(1, len(parts)):
            partial = ".".join(parts[:i])
            if partial not in index:
                index[partial] = f.file

    return index


def _resolve_import(imp: str, module_index: Dict[str, str]) -> tuple[str, str]:
    """
    Returns (kind, resolved_file).
    kind = "INTERNAL" if the import matches a project file, "EXTERNAL" otherwise.
    """
    # Try the full import path first, then progressively shorter prefixes
    parts = imp.split(".")
    for length in range(len(parts), 0, -1):
        candidate = ".".join(parts[:length])
        if candidate in module_index:
            return "INTERNAL", module_index[candidate]
    return "EXTERNAL", ""


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
            kind, resolved = _resolve_import(imp, module_index)
            key = (f.file, imp)
            if key in seen:
                continue
            seen.add(key)

            # Skip self-references (a file importing itself via a relative path)
            if kind == "INTERNAL" and resolved == f.file:
                continue

            edges.append(DependencyEdge(
                source_file=f.file,
                target_module=imp,
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

    for f in files:
        for func in f.functions:
            for dep in func.depends_on:
                key = (f.file, func.name, dep)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(DependsEdge(
                    source_file=f.file,
                    source_function=func.name,
                    target_function=dep,
                ))

    return edges
