import ast
from typing import List
from app.schemas.project import FileModel, ClassModel, FunctionModel, ApiRouteModel

class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.classes: List[ClassModel] = []
        self.functions: List[FunctionModel] = []
        self.api_routes: List[ApiRouteModel] = []
        self.imports: List[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}" if module else alias.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        methods = []
        for body_item in node.body:
            if isinstance(body_item, ast.FunctionDef) or isinstance(body_item, ast.AsyncFunctionDef):
                methods.append(body_item.name)
        
        self.classes.append(ClassModel(name=node.name, methods=methods))
        # Do NOT call generic_visit here — we've already extracted methods manually.
        # Calling it would cause the walker to recurse into the class body and
        # re-invoke visit_FunctionDef for each method, leaking them into top-level functions.

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node)
        self.generic_visit(node)

    def _handle_function(self, node):
        args = [arg.arg for arg in node.args.args]
        decorators = []
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                # e.g. @app.get("/path")
                if isinstance(decorator.func, ast.Attribute):
                    if isinstance(decorator.func.value, ast.Name):
                        dec_name = f"{decorator.func.value.id}.{decorator.func.attr}"
                    else:
                        dec_name = decorator.func.attr
                    decorators.append(dec_name)
                    
                    # Detect FastAPI routes
                    if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app" and decorator.func.attr in ["get", "post", "put", "delete", "patch"]:
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            path = decorator.args[0].value
                            self.api_routes.append(ApiRouteModel(
                                method=decorator.func.attr.upper(),
                                path=path,
                                function_name=node.name
                            ))
            elif isinstance(decorator, ast.Attribute):
                if isinstance(decorator.value, ast.Name):
                    dec_name = f"{decorator.value.id}.{decorator.attr}"
                else:
                    dec_name = decorator.attr
                decorators.append(dec_name)
            elif isinstance(decorator, ast.Name):
                decorators.append(decorator.id)
                
        self.functions.append(FunctionModel(name=node.name, arguments=args, decorators=decorators))

def parse_python_code(code: str, filename: str = "unknown.py") -> FileModel:
    try:
        tree = ast.parse(code, filename=filename)
        visitor = PythonASTVisitor(filename)
        visitor.visit(tree)
        
        return FileModel(
            file=filename,
            language="python",
            classes=visitor.classes,
            functions=visitor.functions,
            api_routes=visitor.api_routes,
            imports=visitor.imports
        )
    except Exception as e:
        print(f"Error parsing python code in {filename}: {e}")
        return FileModel(
            file=filename,
            language="python",
            classes=[],
            functions=[],
            api_routes=[],
            imports=[]
        )
