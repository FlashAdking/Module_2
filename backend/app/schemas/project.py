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

# --- OUTPUT FOR MODULE 3 (Knowledge Graph) ---
class SystemModelOutput(BaseModel):
    project_id: str
    files: List[FileModel]
    requirements: List[RequirementModel]