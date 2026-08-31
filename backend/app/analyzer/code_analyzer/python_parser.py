"""
python_parser.py
────────────────
Thin adapter that drives ``custom_ast_parser.py`` (the full-featured Python
AST walker) and flattens its rich node tree into the ``FileModel`` Pydantic
schema consumed by the rest of Module 2.

Why this two-layer design?
──────────────────────────
* ``custom_ast_parser.py`` produces a full, JSON-serialisable tree that
  preserves every construct (base classes, return annotations, middleware,
  exception handlers, comprehensions …).  That tree is the right input for
  future graph-traversal or LLM-context features.
* ``FileModel`` is a deliberately shallow contract agreed with Module 3
  (Neo4j).  This adapter bridges the gap — no other file needs to know about
  the internal tree format.
"""

import ast
from typing import List

from app.schemas.project import FileModel, ClassModel, FunctionModel, ApiRouteModel
from app.analyzer.code_analyzer.custom_ast_parser import (
    parse_code,
    ModuleNode,
    ImportNode,
    ImportFromNode,
    ClassDefNode,
    FunctionDefNode,
    FastAPIRouteNode,
    ArgumentNode,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _depends_from_args(args: List[ArgumentNode]) -> List[str]:
    """
    Extract the injected function names from ``Depends(...)`` default values.

    ``custom_ast_parser`` stores the default as an unparsed string, e.g.
    ``"Depends(get_db)"``.  We pull the inner symbol out with a simple parse.
    """
    deps: List[str] = []
    for arg in args:
        default = arg.default or ""
        # Match Depends(<symbol>)  — handles both name and dotted attr forms
        if default.startswith("Depends(") and default.endswith(")"):
            inner = default[len("Depends("):-1].strip()
            if inner:
                deps.append(inner)
    return deps


def _walk_module(module_node: ModuleNode):
    """
    Walk the custom AST module node and extract the four categories needed
    for FileModel.  Returns (classes, functions, api_routes, imports).
    """
    classes: List[ClassModel] = []
    functions: List[FunctionModel] = []
    api_routes: List[ApiRouteModel] = []
    imports: List[str] = []

    # FastAPI route nodes are attached directly as children of ModuleNode
    # by custom_ast_parser (not nested under their FunctionDefNode).
    fastapi_routes_by_func: dict = {}
    for child in module_node.children:
        if isinstance(child, FastAPIRouteNode):
            fastapi_routes_by_func[child.function_name] = child

    for child in module_node.children:

        # ── Imports ──────────────────────────────────────────────────────
        if isinstance(child, ImportNode):
            imports.extend(child.names)

        elif isinstance(child, ImportFromNode):
            module = child.module or ""
            prefix = "." * (child.level or 0)
            for name in child.names:
                if module:
                    imports.append(f"{prefix}{module}.{name}")
                else:
                    imports.append(f"{prefix}{name}")

        # ── Classes ───────────────────────────────────────────────────────
        elif isinstance(child, ClassDefNode):
            methods: List[str] = []
            for body_child in child.children:
                if isinstance(body_child, FunctionDefNode):
                    methods.append(body_child.name)
                    # Emit class method as a canonical top-level function to capture metadata
                    functions.append(FunctionModel(
                        name=f"{child.name}.{body_child.name}",
                        arguments=[a.arg for a in body_child.args],
                        decorators=body_child.decorators,
                        depends_on=_depends_from_args(body_child.args),
                    ))
            classes.append(ClassModel(name=child.name, methods=methods))

        # ── Top-level functions ───────────────────────────────────────────
        elif isinstance(child, FunctionDefNode):
            depends_on = _depends_from_args(child.args)

            functions.append(FunctionModel(
                name=child.name,
                arguments=[a.arg for a in child.args],
                decorators=child.decorators,
                depends_on=depends_on,
            ))

        # ── FastAPI routes (add to api_routes list) ───────────────────────
        elif isinstance(child, FastAPIRouteNode):
            api_routes.append(ApiRouteModel(
                method=child.method,
                path=child.path,
                function_name=child.function_name,
            ))

    return classes, functions, api_routes, imports


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_python_code(code: str, filename: str = "unknown.py") -> FileModel:
    """
    Parse Python source into a ``FileModel``.

    Internally uses ``custom_ast_parser.parse_code()`` for the full AST walk,
    then flattens the result to the schema contract.
    """
    try:
        module_node = parse_code(code)
        classes, functions, api_routes, imports = _walk_module(module_node)

        return FileModel(
            file=filename,
            language="python",
            classes=classes,
            functions=functions,
            api_routes=api_routes,
            imports=imports,
        )

    except Exception as e:
        print(f"Error parsing python code in {filename}: {e}")
        return FileModel(
            file=filename,
            language="python",
            classes=[],
            functions=[],
            api_routes=[],
            imports=[],
        )
