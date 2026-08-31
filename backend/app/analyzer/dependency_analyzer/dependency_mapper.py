from typing import List, Dict, Any
from app.schemas.project import FileModel

def map_dependencies(files: List[FileModel]) -> List[Dict[str, Any]]:
    """
    Maps cross-file dependencies and internal function calls/injections.
    Returns a list of dependency relationships as dicts for generic use.
    """
    dependencies = []
    
    for file in files:
        for imp in file.imports:
            dependencies.append({
                "source": file.file,
                "target": imp,
                "type": "IMPORTS"
            })
            
    for file in files:
        for func in file.functions:
            for decorator in func.decorators:
                if "Depends" in decorator:
                    target = decorator.replace('Depends(', '').replace(')', '')
                    dependencies.append({
                        "source_function": func.name,
                        "target_dependency": target,
                        "type": "DEPENDS_ON"
                    })
                    
    return dependencies
