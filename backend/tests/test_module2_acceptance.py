import pytest

from app.analyzer.system_model.adapter import process_project


@pytest.fixture
def realistic_project():
    profile = {
        "project_id": "GRADE-001",
        "project_type": "web_api",
        "languages": ["Python", "TypeScript"],
        "frameworks": ["FastAPI", "React"],
    }

    files = {
        "app/main.py": """
from fastapi import FastAPI, Depends
from app.services.user import UserService

app = FastAPI()


def get_db():
    pass


@app.get("/users")
def list_users(db=Depends(get_db)):
    return []


@app.post("/users")
def create_user(db=Depends(get_db)):
    return {}
""",

        "app/services/user.py": """
class UserService:

    def list_users(self):
        pass

    def create_user(self, name, email):
        pass
""",

        "app/models/user.py": """
class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
""",

        "frontend/src/App.tsx": """
import React from "react";
import axios from "axios";

export const UserList = () => {
    return <div>Users</div>;
};

export const fetchUsers = () => {
    return axios.get("/users");
};
""",

        "tests/test_users.py": """
from app.services.user import UserService


def test_create_user():
    service = UserService()
    assert service.create_user("Aditya", "a@test.com") is not None


def test_list_users():
    service = UserService()
    assert service.list_users() is not None
""",
    }

    requirements = """
User Listing
The system must list all users from the database.
Acceptance Criteria:
- Fetches from /users endpoint
- Displays a table of user records

User Creation
The system shall allow creating new users.
Acceptance Criteria:
- Must accept name and email
- Returns 201 on success

Dashboard
The system shall provide a dashboard with statistics.
Acceptance Criteria:
- Must show active user count
"""

    return profile, files, requirements


def test_module2_end_to_end_contract(realistic_project):
    """
    High-level acceptance test for the complete Module 2 pipeline.

    This test intentionally checks the final SystemModelOutput rather
    than implementation details of individual analyzers.
    """

    profile, files, requirements = realistic_project

    output = process_project(
        profile,
        files,
        requirements,
    )

    # ---------------------------------------------------------
    # 1. Project identity
    # ---------------------------------------------------------

    assert output.project_id == "GRADE-001"

    # ---------------------------------------------------------
    # 2. Requirements
    # ---------------------------------------------------------

    assert len(output.requirements) == 3

    requirement_ids = {
        requirement.requirement_id
        for requirement in output.requirements
    }

    assert requirement_ids == {
        "REQ-001",
        "REQ-002",
        "REQ-003",
    }

    # ---------------------------------------------------------
    # 3. File discovery
    # ---------------------------------------------------------

    analyzed_files = {
        file.file
        for file in output.files
    }

    assert analyzed_files == {
        "app/main.py",
        "app/services/user.py",
        "app/models/user.py",
        "frontend/src/App.tsx",
        "tests/test_users.py",
    }

    # ---------------------------------------------------------
    # 4. Python API analysis
    # ---------------------------------------------------------

    main_file = next(
        file for file in output.files
        if file.file == "app/main.py"
    )

    routes = {
        (route.method, route.path, route.function_name)
        for route in main_file.api_routes
    }

    assert routes == {
        ("GET", "/users", "list_users"),
        ("POST", "/users", "create_user"),
    }

    # ---------------------------------------------------------
    # 5. FastAPI dependency analysis
    # ---------------------------------------------------------

    depends_edges = {
        (
            edge.source_function,
            edge.target_function,
        )
        for edge in output.depends_edges
    }

    assert (
        "list_users",
        "get_db",
    ) in depends_edges

    assert (
        "create_user",
        "get_db",
    ) in depends_edges

    # ---------------------------------------------------------
    # 6. Internal dependency resolution
    # ---------------------------------------------------------

    internal_dependencies = {
        (
            dependency.source_file,
            dependency.target_module,
            dependency.resolved_file,
        )
        for dependency in output.dependencies
        if dependency.kind == "INTERNAL"
    }

    assert (
        "app/main.py",
        "app.services.user",
        "app/services/user.py",
    ) in internal_dependencies

    # ---------------------------------------------------------
    # 7. External dependency detection
    # ---------------------------------------------------------

    external_dependencies = {
        dependency.target_module
        for dependency in output.dependencies
        if dependency.kind == "EXTERNAL"
    }

    assert "fastapi.FastAPI" in external_dependencies

    # ---------------------------------------------------------
    # 8. JavaScript / TypeScript analysis
    # ---------------------------------------------------------

    app_file = next(
        file for file in output.files
        if file.file == "frontend/src/App.tsx"
    )

    function_names = {
        function.name
        for function in app_file.functions
    }

    assert "UserList" in function_names
    assert "fetchUsers" in function_names

    assert "react" in app_file.imports
    assert "axios" in app_file.imports

    # Frontend must NOT incorrectly create server API routes.
    assert app_file.api_routes == []

    # ---------------------------------------------------------
    # 9. Code → requirement mapping
    # ---------------------------------------------------------

    links = output.code_requirement_links

    def links_for(requirement_id):
        return {
            link.symbol
            for link in links
            if link.requirement_id == requirement_id
        }

    req_001_symbols = links_for("REQ-001")
    req_002_symbols = links_for("REQ-002")
    req_003_symbols = links_for("REQ-003")

    # Positive relationships.
    assert "list_users" in req_001_symbols
    assert "UserList" in req_001_symbols
    assert "fetchUsers" in req_001_symbols

    assert "create_user" in req_002_symbols

    # Dashboard has no implementation in this fixture.
    assert req_003_symbols == set()

    # ---------------------------------------------------------
    # 10. Prevent major false-positive relationships
    # ---------------------------------------------------------

    assert "create_user" not in req_001_symbols
    assert "list_users" not in req_002_symbols

    # Test functions should not be treated as production
    # requirement implementations.
    test_symbols = {
        link.symbol
        for link in links
        if link.file.startswith("tests/")
    }

    assert test_symbols == set()

    # ---------------------------------------------------------
    # 11. Code → test mapping
    # ---------------------------------------------------------

    test_links = {
        (
            link.test_function,
            link.target_symbol,
        )
        for link in output.code_test_links
    }

    assert (
        "test_create_user",
        "create_user",
    ) in test_links

    assert (
        "test_list_users",
        "list_users",
    ) in test_links

    # ---------------------------------------------------------
    # 12. No unexpected test relationships
    # ---------------------------------------------------------

    assert all(
        link.target_symbol in {
            "create_user",
            "list_users",
        }
        for link in output.code_test_links
    )