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

import ast

def parse_python_code(code: str, filename: str = "unknown.py") -> FileModel:
    """
    Parse Python source into a ``FileModel``.

    Internally uses ``custom_ast_parser.parse_code()`` for the full AST walk,
    then flattens the result to the schema contract.
    """
    try:
        module_node = parse_code(code)
        classes, functions, api_routes, imports = _walk_module(module_node)

        # Enhance functions with actual function call dependencies
        try:
            tree = ast.parse(code)
            
            func_calls = {}
            class CallVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.current_func = None
                    self.calls = []
                    self.class_stack = []
                    
                def visit_ClassDef(self, node):
                    self.class_stack.append(node.name)
                    self.generic_visit(node)
                    self.class_stack.pop()
                    
                def visit_FunctionDef(self, node):
                    old_func = self.current_func
                    old_calls = self.calls
                    
                    func_name = f"{self.class_stack[-1]}.{node.name}" if self.class_stack else node.name
                    self.current_func = func_name
                    self.calls = []
                    self.generic_visit(node)
                    
                    for arg in node.args.defaults + node.args.kw_defaults:
                        if isinstance(arg, ast.Call) and getattr(arg.func, "id", "") == "Depends":
                            if arg.args and isinstance(arg.args[0], ast.Name):
                                self.calls.append(arg.args[0].id)
                                
                    func_calls[func_name] = list(set(self.calls))
                    
                    self.current_func = old_func
                    self.calls = old_calls
                    
                def visit_AsyncFunctionDef(self, node):
                    self.visit_FunctionDef(node)
                    
                def visit_Call(self, node):
                    if self.current_func:
                        if isinstance(node.func, ast.Name):
                            self.calls.append(node.func.id)
                        elif isinstance(node.func, ast.Attribute):
                            # If the receiver is a plain Name that starts with an
                            # uppercase letter, it's almost certainly a class name
                            # (e.g. UserService.process), so record the fully-qualified
                            # form to disambiguate same-named methods across classes.
                            # Lowercase receivers are instance variables (e.g.
                            # service.create_user) — record just the method name so
                            # the mapper can still find it via the suffix search.
                            if (
                                isinstance(node.func.value, ast.Name)
                                and node.func.value.id[:1].isupper()
                            ):
                                self.calls.append(f"{node.func.value.id}.{node.func.attr}")
                            else:
                                self.calls.append(node.func.attr)
                    self.generic_visit(node)
                    
            CallVisitor().visit(tree)
            
            for func in functions:
                if func.name in func_calls:
                    func.depends_on = list(set(func.depends_on + func_calls[func.name]))
                    
        except SyntaxError:
            pass

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
