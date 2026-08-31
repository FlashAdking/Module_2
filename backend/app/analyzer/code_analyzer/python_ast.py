import ast
from app.schemas.project import FileModel, ClassModel

import ast
from app.schemas.project import FileModel, ClassModel, FunctionModel, ApiRouteModel

class CodeVisitor(ast.NodeVisitor):
    def __init__(self):
        self.classes = []
        self.imports = []
        self.functions = []
        self.api_routes = []
        self.current_class = None # Track if we are inside a class

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # Keep track of class methods vs standalone functions
        self.current_class = node.name
        methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
        self.classes.append(ClassModel(name=node.name, methods=methods))
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node):
        # 1. Check for API route decorators (e.g., @app.get("/users"))
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                method = decorator.func.attr.upper()
                if method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    path = ""
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        path = decorator.args[0].value
                    
                    self.api_routes.append(ApiRouteModel(
                        path=path,
                        method=method,
                        function_name=node.name
                    ))

        # 2. If it is not inside a class, it is a standalone function
        if not self.current_class:
            self.functions.append(FunctionModel(name=node.name))
            
        self.generic_visit(node)



def parse_python_file(filepath: str, file_content: str) -> FileModel:
    """Parses raw Python code and returns a structured FileModel."""
    try:
        tree = ast.parse(file_content)
        visitor = CodeVisitor()
        visitor.visit(tree)
        
        return FileModel(
            file=filepath,
            language="python",
            classes=visitor.classes,
            imports=visitor.imports
        )
    except SyntaxError as e:
        # Failsafe for invalid Python files
        return FileModel(
            file=filepath,
            language="python",
            classes=[],
            imports=[f"ERROR: {str(e)}"]
        )