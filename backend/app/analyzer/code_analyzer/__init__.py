"""Code Analyzer package.

Provides a self‑contained FastAPI‑aware Python AST parser.
"""

from .custom_ast_parser import parse_code, Node, ModuleNode

__all__ = ["parse_code", "Node", "ModuleNode"]
