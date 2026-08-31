import pytest
import sys
import os

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.analyzer.code_analyzer.python_parser import parse_python_code
from app.analyzer.requirement_analyzer.requirement_parser import parse_requirements_text
from app.schemas.project import FileModel, RequirementModel

def test_python_parser():
    code = """
from fastapi import FastAPI
app = FastAPI()

class TestClass:
    def method_one(self): pass

@app.get("/api/test")
def read_test():
    return {"status": "ok"}
    """
    
    model = parse_python_code(code, "test.py")
    assert model.file == "test.py"
    assert "fastapi.FastAPI" in model.imports
    
    assert len(model.classes) == 1
    assert model.classes[0].name == "TestClass"
    assert "method_one" in model.classes[0].methods
    
    assert len(model.functions) == 2
    func_names = [f.name for f in model.functions]
    assert "method_one" in func_names
    assert "read_test" in func_names
    
    assert len(model.api_routes) == 1
    assert model.api_routes[0].method == "GET"
    assert model.api_routes[0].path == "/api/test"
    assert model.api_routes[0].function_name == "read_test"

def test_requirement_parser():
    reqs_text = """
REQ-101 Login Feature
The system must allow users to log in.
Acceptance Criteria:
- Should have a username field
- Should have a password field

REQ-102 Logout
Users can log out.
Acceptance Criteria:
- Clicking logout ends session
    """
    
    reqs = parse_requirements_text(reqs_text)
    assert len(reqs) == 2
    
    assert reqs[0].requirement_id == "REQ-101"
    assert reqs[0].title == "Login Feature"
    assert len(reqs[0].acceptance_criteria) == 2
    
    assert reqs[1].requirement_id == "REQ-102"
    assert reqs[1].title == "Logout"
    assert len(reqs[1].acceptance_criteria) == 1
