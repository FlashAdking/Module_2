"""Custom AST parser for full Python syntax with FastAPI detection.

The parser walks Python's built‑in ``ast`` tree and produces a hierarchy
of lightweight ``Node`` objects. Each node knows its type, a dictionary of
attributes, and a list of child nodes. The hierarchy can be turned into a plain
JSON structure via ``Node.to_dict()`` which downstream tools (e.g. graph
builders) can consume.

FastAPI support:
- Detects route decorators such as ``@app.get('/path')`` and records the
  HTTP method, path, function name, and any ``Depends`` dependencies.
- Detects middleware registration ``app.add_middleware`` and exception
  handler registration ``app.add_exception_handler``.

All functionality lives in the standard library – no external dependencies.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# ---------------------------------------------------------------------------
# Node hierarchy
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """Base class for all custom AST nodes.

    Subclasses should set ``node_type`` in ``__post_init__`` and implement
    ``_attributes`` to expose their own fields.
    """

    node_type: str = field(init=False)
    children: List[Node] = field(default_factory=list)

    def __post_init__(self) -> None:
        # By default, use the class name without the ``Node`` suffix.
        if not hasattr(self, "node_type") or self.node_type == "":
            self.node_type = self.__class__.__name__.replace("Node", "")

    def _attributes(self) -> Dict[str, Any]:  # pragma: no cover
        """Return a dict of node‑specific attributes.

        Sub‑classes should override this method. The base implementation returns
        an empty dict.
        """

        return {}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the node to a JSON‑compatible dictionary.

        The output has three keys:
        * ``type`` – the ``node_type`` string.
        * ``attributes`` – the subclass‑specific dict from ``_attributes``.
        * ``children`` – a list of child node dictionaries.
        """

        return {
            "type": self.node_type,
            "attributes": self._attributes(),
            "children": [child.to_dict() for child in self.children],
        }

# ---------------------------------------------------------------------------
# Concrete node definitions – language constructs
# ---------------------------------------------------------------------------

@dataclass
class ModuleNode(Node):
    def __post_init__(self) -> None:
        self.node_type = "Module"

    def _attributes(self) -> Dict[str, Any]:
        return {}

# Import statements

@dataclass
class ImportNode(Node):
    names: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.node_type = "Import"

    def _attributes(self) -> Dict[str, Any]:
        return {"names": self.names}


@dataclass
class ImportFromNode(Node):
    module: Optional[str] = None
    names: List[str] = field(default_factory=list)
    level: int = 0

    def __post_init__(self) -> None:
        self.node_type = "ImportFrom"

    def _attributes(self) -> Dict[str, Any]:
        return {"module": self.module, "names": self.names, "level": self.level}

# Class definitions

@dataclass
class ClassDefNode(Node):
    name: str = ""
    bases: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.node_type = "ClassDef"

    def _attributes(self) -> Dict[str, Any]:
        return {"name": self.name, "bases": self.bases, "decorators": self.decorators}

# Function / method definitions

@dataclass
class ArgumentNode(Node):
    arg: str = ""
    annotation: Optional[str] = None
    default: Optional[str] = None

    def __post_init__(self) -> None:
        self.node_type = "Argument"

    def _attributes(self) -> Dict[str, Any]:
        return {"arg": self.arg, "annotation": self.annotation, "default": self.default}


@dataclass
class FunctionDefNode(Node):
    name: str = ""
    args: List[ArgumentNode] = field(default_factory=list)
    returns: Optional[str] = None
    decorators: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.node_type = "FunctionDef"

    def _attributes(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "args": [arg._attributes() for arg in self.args],
            "returns": self.returns,
            "decorators": self.decorators,
        }

# Assignment

@dataclass
class AssignNode(Node):
    targets: List[str] = field(default_factory=list)
    value: Optional[str] = None

    def __post_init__(self) -> None:
        self.node_type = "Assign"

    def _attributes(self) -> Dict[str, Any]:
        return {"targets": self.targets, "value": self.value}


@dataclass
class AnnAssignNode(Node):
    target: str = ""
    annotation: str = ""
    value: Optional[str] = None
    simple: bool = False

    def __post_init__(self) -> None:
        self.node_type = "AnnAssign"

    def _attributes(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "annotation": self.annotation,
            "value": self.value,
            "simple": self.simple,
        }

# Expression statement

@dataclass
class ExprNode(Node):
    value: str = ""

    def __post_init__(self) -> None:
        self.node_type = "Expr"

    def _attributes(self) -> Dict[str, Any]:
        return {"value": self.value}


@dataclass
class ReturnNode(Node):
    value: Optional[str] = None

    def __post_init__(self) -> None:
        self.node_type = "Return"

    def _attributes(self) -> Dict[str, Any]:
        return {"value": self.value}

# Control‑flow constructs

@dataclass
class IfNode(Node):
    test: str = ""

    def __post_init__(self) -> None:
        self.node_type = "If"

    def _attributes(self) -> Dict[str, Any]:
        return {"test": self.test}


@dataclass
class ForNode(Node):
    target: str = ""
    iter: str = ""
    is_async: bool = False

    def __post_init__(self) -> None:
        self.node_type = "For"

    def _attributes(self) -> Dict[str, Any]:
        return {"target": self.target, "iter": self.iter, "is_async": self.is_async}


@dataclass
class WhileNode(Node):
    test: str = ""

    def __post_init__(self) -> None:
        self.node_type = "While"

    def _attributes(self) -> Dict[str, Any]:
        return {"test": self.test}


@dataclass
class TryNode(Node):
    def __post_init__(self) -> None:
        self.node_type = "Try"

    def _attributes(self) -> Dict[str, Any]:
        return {}


@dataclass
class ExceptHandlerNode(Node):
    type: Optional[str] = None
    name: Optional[str] = None

    def __post_init__(self) -> None:
        self.node_type = "ExceptHandler"

    def _attributes(self) -> Dict[str, Any]:
        return {"type": self.type, "name": self.name}


@dataclass
class WithNode(Node):
    is_async: bool = False

    def __post_init__(self) -> None:
        self.node_type = "With"

    def _attributes(self) -> Dict[str, Any]:
        return {"is_async": self.is_async}


@dataclass
class WithItemNode(Node):
    context_expr: str = ""
    optional_vars: Optional[str] = None

    def __post_init__(self) -> None:
        self.node_type = "WithItem"

    def _attributes(self) -> Dict[str, Any]:
        return {"context_expr": self.context_expr, "optional_vars": self.optional_vars}

# Comprehensions

@dataclass
class ListCompNode(Node):
    elt: str = ""

    def __post_init__(self) -> None:
        self.node_type = "ListComp"

    def _attributes(self) -> Dict[str, Any]:
        return {"elt": self.elt}


@dataclass
class DictCompNode(Node):
    key: str = ""
    value: str = ""

    def __post_init__(self) -> None:
        self.node_type = "DictComp"

    def _attributes(self) -> Dict[str, Any]:
        return {"key": self.key, "value": self.value}


@dataclass
class SetCompNode(Node):
    elt: str = ""

    def __post_init__(self) -> None:
        self.node_type = "SetComp"

    def _attributes(self) -> Dict[str, Any]:
        return {"elt": self.elt}


@dataclass
class GeneratorExpNode(Node):
    elt: str = ""

    def __post_init__(self) -> None:
        self.node_type = "GeneratorExp"

    def _attributes(self) -> Dict[str, Any]:
        return {"elt": self.elt}


@dataclass
class ComprehensionNode(Node):
    target: str = ""
    iter: str = ""
    ifs: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.node_type = "Comprehension"

    def _attributes(self) -> Dict[str, Any]:
        return {"target": self.target, "iter": self.iter, "ifs": self.ifs}

# FastAPI specific nodes

@dataclass
class FastAPIRouteNode(Node):
    path: str = ""
    method: str = ""
    function_name: str = ""
    dependencies: List[str] = field(default_factory=list)
    response_model: Optional[str] = None

    def __post_init__(self) -> None:
        self.node_type = "FastAPIRoute"

    def _attributes(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "method": self.method,
            "function_name": self.function_name,
            "dependencies": self.dependencies,
            "response_model": self.response_model,
        }


@dataclass
class FastAPIMiddlewareNode(Node):
    middleware_class: str = ""
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.node_type = "FastAPIMiddleware"

    def _attributes(self) -> Dict[str, Any]:
        return {"middleware_class": self.middleware_class, "options": self.options}


@dataclass
class FastAPIExceptionHandlerNode(Node):
    exception_class: str = ""
    handler_name: str = ""

    def __post_init__(self) -> None:
        self.node_type = "FastAPIExceptionHandler"

    def _attributes(self) -> Dict[str, Any]:
        return {"exception_class": self.exception_class, "handler_name": self.handler_name}

# ---------------------------------------------------------------------------
# Visitor – converts stdlib ast to custom nodes
# ---------------------------------------------------------------------------

class CustomASTVisitor(ast.NodeVisitor):
    """Walks a Python ``ast`` tree and builds the custom node hierarchy.

    FastAPI‑specific nodes are collected in ``self.fastapi_nodes`` and attached
    to the top‑level ``ModuleNode`` after the module body is processed.
    """

    def __init__(self) -> None:
        self.fastapi_nodes: List[Node] = []
        super().__init__()

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------
    def _expr_to_str(self, expr: Optional[ast.AST]) -> Optional[str]:
        if expr is None:
            return None
        try:
            return ast.unparse(expr)  # type: ignore[attr-defined]
        except Exception:
            return ast.dump(expr)

    def _parse_arguments(self, args: ast.arguments) -> List[ArgumentNode]:
        arg_nodes: List[ArgumentNode] = []

        def add(arg_obj: ast.arg, default_val: Optional[ast.AST] = None):
            annotation = self._expr_to_str(arg_obj.annotation)
            default = self._expr_to_str(default_val) if default_val else None
            arg_nodes.append(ArgumentNode(arg=arg_obj.arg, annotation=annotation, default=default))

        # Positional only (Python 3.8+)
        for i, a in enumerate(args.posonlyargs):
            default = args.defaults[i] if i < len(args.defaults) else None
            add(a, default)

        # Regular args
        offset = len(args.posonlyargs)
        for i, a in enumerate(args.args):
            default_index = offset + i - (len(args.args) - len(args.defaults))
            default = args.defaults[default_index] if default_index >= 0 else None
            add(a, default)

        # *args
        if args.vararg:
            add(args.vararg)

        # Keyword‑only args
        for i, a in enumerate(args.kwonlyargs):
            default = args.kw_defaults[i]
            add(a, default)

        # **kwargs
        if args.kwarg:
            add(args.kwarg)

        return arg_nodes

    # -------------------------------------------------------------------
    # Node visitors – each returns a custom ``Node`` instance
    # -------------------------------------------------------------------
    def visit_Module(self, node: ast.Module) -> ModuleNode:
        body_nodes = [self.visit(stmt) for stmt in node.body]
        module_node = ModuleNode(children=body_nodes + self.fastapi_nodes)
        return module_node

    def visit_Import(self, node: ast.Import) -> ImportNode:
        names = [alias.name for alias in node.names]
        return ImportNode(names=names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ImportFromNode:
        module = node.module
        names = [alias.name for alias in node.names]
        level = node.level
        return ImportFromNode(module=module, names=names, level=level)

    def visit_ClassDef(self, node: ast.ClassDef) -> ClassDefNode:
        bases = [self._expr_to_str(b) or "" for b in node.bases]
        decorators = [self._expr_to_str(d) or "" for d in node.decorator_list]
        body = [self.visit(stmt) for stmt in node.body]
        return ClassDefNode(name=node.name, bases=bases, decorators=decorators, children=body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> FunctionDefNode:
        # FastAPI route detection
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                method = decorator.func.attr.upper()
                if method in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                    path = ""
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        path = decorator.args[0].value
                    # Determine dependencies via argument annotations containing ``Depends``
                    args_list = self._parse_arguments(node.args)
                    deps = []
                    for a in args_list:
                        if a.annotation and "Depends" in a.annotation:
                            deps.append(a.annotation)
                    route_node = FastAPIRouteNode(
                        path=path,
                        method=method,
                        function_name=node.name,
                        dependencies=deps,
                    )
                    self.fastapi_nodes.append(route_node)
        args_list = self._parse_arguments(node.args)
        returns = self._expr_to_str(node.returns)
        decorators = [self._expr_to_str(d) or "" for d in node.decorator_list]
        body = [self.visit(stmt) for stmt in node.body]
        return FunctionDefNode(
            name=node.name,
            args=args_list,
            returns=returns,
            decorators=decorators,
            children=body,
        )

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> FunctionDefNode:
        # Re‑use the same logic as ``visit_FunctionDef`` – FastAPI routes work the same way
        return self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Assign(self, node: ast.Assign) -> AssignNode:
        targets = [self._expr_to_str(t) or "" for t in node.targets]
        value = self._expr_to_str(node.value)
        return AssignNode(targets=targets, value=value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> AnnAssignNode:
        target = self._expr_to_str(node.target) or ""
        annotation = self._expr_to_str(node.annotation) or ""
        value = self._expr_to_str(node.value) if node.value else None
        return AnnAssignNode(target=target, annotation=annotation, value=value, simple=node.simple)

    def visit_Expr(self, node: ast.Expr) -> ExprNode:
        # Ensure inner Call nodes (e.g., app.add_middleware) are visited so FastAPI
        # specific nodes are captured via ``visit_Call``.
        self.generic_visit(node)
        value = self._expr_to_str(node.value) or ""
        return ExprNode(value=value)

    def visit_Return(self, node: ast.Return) -> ReturnNode:
        value = self._expr_to_str(node.value) if node.value else None
        return ReturnNode(value=value)

    # Control‑flow
    def visit_If(self, node: ast.If) -> IfNode:
        test = self._expr_to_str(node.test) or ""
        body = [self.visit(stmt) for stmt in node.body]
        orelse = [self.visit(stmt) for stmt in node.orelse]
        return IfNode(test=test, children=body + orelse)

    def visit_For(self, node: ast.For) -> ForNode:
        target = self._expr_to_str(node.target) or ""
        iter_ = self._expr_to_str(node.iter) or ""
        body = [self.visit(stmt) for stmt in node.body]
        orelse = [self.visit(stmt) for stmt in node.orelse]
        return ForNode(target=target, iter=iter_, is_async=False, children=body + orelse)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ForNode:
        target = self._expr_to_str(node.target) or ""
        iter_ = self._expr_to_str(node.iter) or ""
        body = [self.visit(stmt) for stmt in node.body]
        orelse = [self.visit(stmt) for stmt in node.orelse]
        return ForNode(target=target, iter=iter_, is_async=True, children=body + orelse)

    def visit_While(self, node: ast.While) -> WhileNode:
        test = self._expr_to_str(node.test) or ""
        body = [self.visit(stmt) for stmt in node.body]
        orelse = [self.visit(stmt) for stmt in node.orelse]
        return WhileNode(test=test, children=body + orelse)

    def visit_Try(self, node: ast.Try) -> TryNode:
        body = [self.visit(stmt) for stmt in node.body]
        handlers = [self.visit(h) for h in node.handlers]
        orelse = [self.visit(stmt) for stmt in node.orelse]
        finalbody = [self.visit(stmt) for stmt in node.finalbody]
        return TryNode(children=body + handlers + orelse + finalbody)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ExceptHandlerNode:
        type_ = self._expr_to_str(node.type) if node.type else None
        name = node.name if isinstance(node.name, str) else None
        body = [self.visit(stmt) for stmt in node.body]
        return ExceptHandlerNode(type=type_, name=name, children=body)

    def visit_With(self, node: ast.With) -> WithNode:
        items = [self._visit_withitem(item) for item in node.items]
        body = [self.visit(stmt) for stmt in node.body]
        with_node = WithNode(is_async=False, children=body)
        # Attach WithItemNode objects as children of the WithNode for full detail
        with_node.children = items + body
        return with_node

    def visit_AsyncWith(self, node: ast.AsyncWith) -> WithNode:
        items = [self._visit_withitem(item) for item in node.items]
        body = [self.visit(stmt) for stmt in node.body]
        with_node = WithNode(is_async=True, children=body)
        with_node.children = items + body
        return with_node

    def _visit_withitem(self, item: ast.withitem) -> WithItemNode:
        ctx = self._expr_to_str(item.context_expr) or ""
        opt = self._expr_to_str(item.optional_vars) if item.optional_vars else None
        return WithItemNode(context_expr=ctx, optional_vars=opt)

    # Comprehensions
    def visit_ListComp(self, node: ast.ListComp) -> ListCompNode:
        elt = self._expr_to_str(node.elt) or ""
        comps = [self._visit_comprehension(gen) for gen in node.generators]
        return ListCompNode(elt=elt, children=comps)

    def visit_DictComp(self, node: ast.DictComp) -> DictCompNode:
        key = self._expr_to_str(node.key) or ""
        value = self._expr_to_str(node.value) or ""
        comps = [self._visit_comprehension(gen) for gen in node.generators]
        return DictCompNode(key=key, value=value, children=comps)

    def visit_SetComp(self, node: ast.SetComp) -> SetCompNode:
        elt = self._expr_to_str(node.elt) or ""
        comps = [self._visit_comprehension(gen) for gen in node.generators]
        return SetCompNode(elt=elt, children=comps)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> GeneratorExpNode:
        elt = self._expr_to_str(node.elt) or ""
        comps = [self._visit_comprehension(gen) for gen in node.generators]
        return GeneratorExpNode(elt=elt, children=comps)

    def _visit_comprehension(self, comp: ast.comprehension) -> ComprehensionNode:
        target = self._expr_to_str(comp.target) or ""
        iter_ = self._expr_to_str(comp.iter) or ""
        ifs = [self._expr_to_str(cond) or "" for cond in comp.ifs]
        return ComprehensionNode(target=target, iter=iter_, ifs=ifs)

    # FastAPI middleware / exception handler detection via generic Call handling
    def visit_Call(self, node: ast.Call) -> Any:  # return type is ignored for Call nodes
        # Detect ``app.add_middleware``
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr == "add_middleware" and node.args:
                middleware_class = self._expr_to_str(node.args[0]) or ""
                options: Dict[str, Any] = {}
                for kw in node.keywords:
                    options[kw.arg] = self._expr_to_str(kw.value)
                self.fastapi_nodes.append(FastAPIMiddlewareNode(middleware_class=middleware_class, options=options))
            elif attr == "add_exception_handler" and len(node.args) >= 2:
                exc_class = self._expr_to_str(node.args[0]) or ""
                handler = self._expr_to_str(node.args[1]) or ""
                self.fastapi_nodes.append(FastAPIExceptionHandlerNode(exception_class=exc_class, handler_name=handler))
        # Continue normal traversal for the call's arguments / sub‑expressions
        self.generic_visit(node)
        return None

    # Fallback for anything we did not explicitly handle
    def generic_visit(self, node: ast.AST) -> ExprNode:
        try:
            src = ast.unparse(node)  # type: ignore[attr-defined]
        except Exception:
            src = ast.dump(node)
        return ExprNode(value=src)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_code(source: str) -> ModuleNode:
    """Parse Python source into the custom AST.

    The function returns the root ``ModuleNode`` which contains language nodes
    and any FastAPI‑specific nodes discovered.
    """
    tree = ast.parse(source)
    visitor = CustomASTVisitor()
    return visitor.visit(tree)  # type: ignore[no-any-return]

# ---------------------------------------------------------------------------
# Command‑line interface for debugging
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parse Python source into a custom JSON‑serialisable AST.")
    parser.add_argument("path", nargs="?", help="Path to a .py file. If omitted, source is read from stdin.")
    args = parser.parse_args()

    if args.path:
        with open(args.path, "r", encoding="utf-8") as f:
            src = f.read()
    else:
        src = sys.stdin.read()

    root = parse_code(src)
    print(json.dumps(root.to_dict(), indent=2))
