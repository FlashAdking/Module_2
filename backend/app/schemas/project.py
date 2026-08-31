from pydantic import BaseModel
from typing import List, Optional

# --- INPUT FROM MODULE 1 (Profiler) ---
class ProjectProfile(BaseModel):
    project_id: str
    project_type: str
    languages: List[str]
    frameworks: List[str]

# --- INTERNAL MODULE 2 MODELS ---
class ClassModel(BaseModel):
    name: str
    methods: List[str]

class FunctionModel(BaseModel):
    name: str
    arguments: List[str]
    decorators: List[str]
    # FastAPI Depends() injections extracted from function arguments
    depends_on: List[str] = []

class ApiRouteModel(BaseModel):
    method: str
    path: str
    function_name: str

class FileModel(BaseModel):
    file: str
    language: str
    classes: List[ClassModel]
    functions: List[FunctionModel]
    api_routes: List[ApiRouteModel]
    imports: List[str]

class RequirementModel(BaseModel):
    requirement_id: str
    title: str
    description: str
    acceptance_criteria: List[str]

# --- RELATIONSHIP MODELS (consumed by Module 3 / Neo4j) ---

class DependencyEdge(BaseModel):
    """An import/dependency relationship between two files or modules."""
    source_file: str
    target_module: str
    # "INTERNAL" if target resolves to a project file, "EXTERNAL" otherwise
    kind: str = "EXTERNAL"
    # Resolved project-relative path when kind == "INTERNAL"
    resolved_file: Optional[str] = None

class DependsEdge(BaseModel):
    """A FastAPI Depends() injection relationship between two functions."""
    source_file: str
    source_function: str
    target_function: str

class CodeRequirementLink(BaseModel):
    """Associates a source function/class with a requirement via keyword match."""
    file: str
    symbol: str          # function name or class name
    symbol_type: str     # "function" | "class"
    requirement_id: str
    match_score: float   # 0.0–1.0, ratio of matched keywords

class CodeTestLink(BaseModel):
    """Associates a test function with the production symbol it tests."""
    test_file: str
    test_function: str
    target_file: str
    target_symbol: str
    target_type: str     # "function" | "class"

# --- OUTPUT FOR MODULE 3 (Knowledge Graph) ---
class SystemModelOutput(BaseModel):
    project_id: str
    files: List[FileModel]
    requirements: List[RequirementModel]
    # Relationship layers — empty lists when nothing is detected
    dependencies: List[DependencyEdge] = []
    depends_edges: List[DependsEdge] = []
    code_requirement_links: List[CodeRequirementLink] = []
    code_test_links: List[CodeTestLink] = []