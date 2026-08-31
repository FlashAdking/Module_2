import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser
from app.schemas.project import FileModel, ClassModel, FunctionModel, ApiRouteModel
from typing import List

try:
    JS_LANGUAGE = Language(tsjavascript.language())
    TS_LANGUAGE = Language(tstypescript.language_typescript())
    TSX_LANGUAGE = Language(tstypescript.language_tsx())
except Exception as e:
    print(f"Warning: tree-sitter languages could not be loaded: {e}")
    JS_LANGUAGE = None
    TS_LANGUAGE = None
    TSX_LANGUAGE = None

def get_parser(language_str: str) -> Parser:
    parser = Parser()
    if language_str in ['javascript', 'jsx'] and JS_LANGUAGE:
        parser.language = JS_LANGUAGE
    elif language_str == 'typescript' and TS_LANGUAGE:
        parser.language = TS_LANGUAGE
    elif language_str == 'tsx' and TSX_LANGUAGE:
        parser.language = TSX_LANGUAGE
    elif JS_LANGUAGE:
        parser.language = JS_LANGUAGE
    return parser

def extract_node_text(node, source_code: bytes) -> str:
    return source_code[node.start_byte:node.end_byte].decode('utf-8')

def parse_js_ts_code(code: str, filename: str, language_str: str = 'javascript') -> FileModel:
    if not JS_LANGUAGE:
        print("tree-sitter languages not available, returning empty model.")
        return FileModel(file=filename, language=language_str, classes=[], functions=[], api_routes=[], imports=[])

    parser = get_parser(language_str)
    source_bytes = code.encode('utf-8')
    tree = parser.parse(source_bytes)
    
    classes: List[ClassModel] = []
    functions: List[FunctionModel] = []
    api_routes: List[ApiRouteModel] = []
    imports: List[str] = []

    def traverse(node):
        if node.type == 'import_statement':
            # Extract only the module specifier (the string after 'from'), not the full raw line.
            # e.g. "import React from 'react'" → "react"
            source_node = node.child_by_field_name('source')
            if source_node:
                # Strip surrounding quotes from the string literal
                module_name = extract_node_text(source_node, source_bytes).strip("'\"`")
                imports.append(module_name)
            else:
                # Fallback: store raw text if no source field found
                imports.append(extract_node_text(node, source_bytes))
        
        elif node.type == 'class_declaration':
            name_node = node.child_by_field_name('name')
            class_name = extract_node_text(name_node, source_bytes) if name_node else "AnonymousClass"
            
            methods = []
            body = node.child_by_field_name('body')
            if body:
                for child in body.children:
                    if child.type == 'method_definition':
                        method_name_node = child.child_by_field_name('name')
                        if method_name_node:
                            methods.append(extract_node_text(method_name_node, source_bytes))
            classes.append(ClassModel(name=class_name, methods=methods))
            
        elif node.type in ['function_declaration', 'arrow_function']:
            name = "AnonymousFunction"
            if node.type == 'function_declaration':
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = extract_node_text(name_node, source_bytes)
            elif node.type == 'arrow_function':
                # Only capture arrow functions directly assigned to a variable:
                # const Foo = () => {}  → parent is variable_declarator
                # Inline callbacks like .then(res => ...) have a different parent type
                # and should NOT be treated as top-level functions.
                if node.parent and node.parent.type == 'variable_declarator':
                    name_node = node.parent.child_by_field_name('name')
                    if name_node:
                        name = extract_node_text(name_node, source_bytes)
                else:
                    # Skip inline/callback arrow functions entirely
                    for child in node.children:
                        traverse(child)
                    return
            # Extract arguments
            arguments = []
            
            if node.type == 'arrow_function':
                # Check for parameter without parens: e.g. name => {}
                for child in node.children:
                    if child.type == 'identifier':
                        arguments.append(extract_node_text(child, source_bytes))
                        break
            
            params_node = node.child_by_field_name('parameters')
            if params_node and params_node.type == 'formal_parameters':
                for child in params_node.children:
                    if child.type == 'identifier':
                        arguments.append(extract_node_text(child, source_bytes))
                    elif child.type in ['required_parameter', 'optional_parameter']:
                        # Try to find the identifier child (usually the parameter name)
                        ident = next((c for c in child.children if c.type == 'identifier'), None)
                        if ident:
                            arguments.append(extract_node_text(ident, source_bytes))
                    elif child.type in ['array_pattern', 'object_pattern']:
                        arguments.append("<pattern>")
            
            functions.append(FunctionModel(name=name, arguments=arguments, decorators=[]))

        # NOTE: Frontend JS/TS files CONSUME APIs — they do not define server routes.
        # axios/fetch calls are intentionally NOT added to api_routes.
        # api_routes remains empty for all JS/TS files.
        
        for child in node.children:
            traverse(child)

    try:
        traverse(tree.root_node)
    except Exception as e:
        print(f"Error parsing JS/TS code in {filename}: {e}")

    return FileModel(
        file=filename,
        language=language_str,
        classes=classes,
        functions=functions,
        api_routes=api_routes,
        imports=imports
    )
