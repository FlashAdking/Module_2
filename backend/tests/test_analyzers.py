import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analyzer.code_analyzer.python_parser import parse_python_code
from app.analyzer.requirement_analyzer.requirement_parser import parse_requirements_text
from app.analyzer.dependency_analyzer.dependency_mapper import map_dependencies, map_depends_edges
from app.analyzer.dependency_analyzer.relationship_mapper import map_code_to_requirements, map_code_to_tests
from app.schemas.project import FileModel, RequirementModel


# ── Python parser ────────────────────────────────────────────────────────────

def test_python_parser_basic():
    code = """\
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

    # Functions: only module-level (method_one is a method, NOT in top-level functions)
    func_names = [f.name for f in model.functions]
    assert "read_test" in func_names
    assert "method_one" not in func_names  # methods must NOT leak into functions

    assert len(model.api_routes) == 1
    assert model.api_routes[0].method == "GET"
    assert model.api_routes[0].path == "/api/test"
    assert model.api_routes[0].function_name == "read_test"


def test_python_parser_depends():
    code = """\
from fastapi import FastAPI, Depends
app = FastAPI()

def get_db(): pass

@app.get("/items")
def list_items(db=Depends(get_db)):
    return []
"""
    model = parse_python_code(code, "main.py")
    route_func = next(f for f in model.functions if f.name == "list_items")
    assert "get_db" in route_func.depends_on


def test_python_parser_multiple_routes():
    code = """\
from fastapi import FastAPI, Depends
app = FastAPI()

def get_db(): pass

@app.get("/users")
def list_users(db=Depends(get_db)): return []

@app.post("/users")
def create_user(db=Depends(get_db)): return {}

@app.delete("/users/{id}")
def delete_user(id: int, db=Depends(get_db)): return {}
"""
    model = parse_python_code(code, "routes.py")
    assert len(model.api_routes) == 3
    methods = {r.method for r in model.api_routes}
    assert methods == {"GET", "POST", "DELETE"}
    for f in model.functions:
        if f.name in ("list_users", "create_user", "delete_user"):
            assert "get_db" in f.depends_on


# ── Requirement parser ────────────────────────────────────────────────────────

def test_requirement_parser_sequential_ids():
    """Default mode: Module 2 assigns fresh sequential IDs."""
    reqs_text = """\
Login Feature
The system must allow users to log in.
Acceptance Criteria:
- Should have a username field
- Should have a password field

Logout
Users can log out.
Acceptance Criteria:
- Clicking logout ends session
"""
    reqs = parse_requirements_text(reqs_text)
    assert len(reqs) == 2

    assert reqs[0].requirement_id == "REQ-001"
    assert reqs[0].title == "Login Feature"
    assert len(reqs[0].acceptance_criteria) == 2

    assert reqs[1].requirement_id == "REQ-002"
    assert reqs[1].title == "Logout"
    assert len(reqs[1].acceptance_criteria) == 1


def test_requirement_parser_strips_upstream_ids_by_default():
    """Upstream REQ-XXX tokens in titles must be stripped in default mode."""
    reqs_text = """\
REQ-101 Login Feature
The system must allow users to log in.
Acceptance Criteria:
- Should have a username field

REQ-102 Logout
Users can log out.
"""
    reqs = parse_requirements_text(reqs_text)
    assert reqs[0].requirement_id == "REQ-001"   # re-assigned
    assert reqs[0].title == "Login Feature"       # token stripped from title
    assert reqs[1].requirement_id == "REQ-002"
    assert reqs[1].title == "Logout"


def test_requirement_parser_preserve_upstream_ids():
    """preserve_upstream_ids=True should keep the upstream REQ-XXX values."""
    reqs_text = """\
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
    reqs = parse_requirements_text(reqs_text, preserve_upstream_ids=True)
    assert len(reqs) == 2

    assert reqs[0].requirement_id == "REQ-101"
    assert reqs[0].title == "Login Feature"
    assert len(reqs[0].acceptance_criteria) == 2

    assert reqs[1].requirement_id == "REQ-102"
    assert reqs[1].title == "Logout"
    assert len(reqs[1].acceptance_criteria) == 1


def test_requirement_parser_ac_no_blank_line():
    """AC items should parse even when there's no blank line before the bullets."""
    reqs_text = """\
Dashboard
The system shall provide a dashboard.
Acceptance Criteria:
- Must show stats
- Must show active user count
"""
    reqs = parse_requirements_text(reqs_text)
    assert len(reqs) == 1
    assert len(reqs[0].acceptance_criteria) == 2
    assert "Must show stats" in reqs[0].acceptance_criteria


# ── Dependency mapper ─────────────────────────────────────────────────────────

def test_map_dependencies_internal():
    """Imports that match a project file path should be tagged INTERNAL."""
    files = [
        FileModel(
            file="app/main.py", language="python",
            classes=[], functions=[], api_routes=[],
            # "app.models.user.SomeClass" → resolves to module "app.models.user"
            imports=["app.models.user.SomeClass", "fastapi.FastAPI"],
        ),
        FileModel(
            file="app/models/user.py", language="python",
            classes=[], functions=[], api_routes=[], imports=[],
        ),
    ]
    edges = map_dependencies(files)
    internal = [e for e in edges if e.kind == "INTERNAL"]
    external = [e for e in edges if e.kind == "EXTERNAL"]

    # INTERNAL: target_module is the matched module path, not the full symbol
    assert any(e.target_module == "app.models.user" for e in internal)
    # EXTERNAL: target_module is the full import string as-is
    assert any(e.target_module == "fastapi.FastAPI" for e in external)


def test_map_depends_edges():
    from app.schemas.project import FunctionModel
    files = [
        FileModel(
            file="app/routes/users.py", language="python",
            classes=[],
            functions=[
                FunctionModel(
                    name="list_users", arguments=["db"],
                    decorators=["app.get"],
                    depends_on=["get_db"],
                )
            ],
            api_routes=[], imports=[],
        )
    ]
    edges = map_depends_edges(files)
    assert len(edges) == 1
    assert edges[0].source_function == "list_users"
    assert edges[0].target_function == "get_db"


# ── Relationship mapper ───────────────────────────────────────────────────────

def test_code_to_requirements_link():
    from app.schemas.project import FunctionModel
    files = [
        FileModel(
            file="app/services/user.py", language="python",
            classes=[],
            functions=[
                FunctionModel(name="create_user", arguments=[], decorators=[], depends_on=[]),
                FunctionModel(name="delete_item", arguments=[], decorators=[], depends_on=[]),
            ],
            api_routes=[], imports=[],
        )
    ]
    reqs = [
        RequirementModel(
            requirement_id="REQ-001",
            title="User Creation",
            description="The system must allow creating new users.",
            acceptance_criteria=[],
        )
    ]
    links = map_code_to_requirements(files, reqs)
    matched_funcs = {l.symbol for l in links}
    assert "create_user" in matched_funcs   # "create", "user" both appear in req text
    assert "delete_item" not in matched_funcs  # no overlap


def test_code_to_tests_link():
    from app.schemas.project import FunctionModel
    prod = FileModel(
        file="app/services/user.py", language="python",
        classes=[],
        functions=[
            FunctionModel(name="create_user", arguments=[], decorators=[], depends_on=[]),
            FunctionModel(name="list_users",  arguments=[], decorators=[], depends_on=[]),
        ],
        api_routes=[], imports=[],
    )
    test_f = FileModel(
        file="tests/test_user.py", language="python",
        classes=[],
        functions=[
            FunctionModel(name="test_create_user", arguments=[], decorators=[], depends_on=[]),
            FunctionModel(name="test_list_users",  arguments=[], decorators=[], depends_on=[]),
        ],
        api_routes=[], imports=[],
    )
    links = map_code_to_tests([prod, test_f])
    target_symbols = {l.target_symbol for l in links}
    assert "create_user" in target_symbols
    assert "list_users" in target_symbols
