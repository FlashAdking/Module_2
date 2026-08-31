# backend/tests/test_module2_edge_cases.py

from app.analyzer.system_model.adapter import process_project


# ============================================================
# 1. Empty project
# ============================================================

def test_empty_project():
    profile = {
        "project_id": "empty_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    output = process_project(
        profile_json=profile,
        file_contents={},
        raw_requirements="",
    )

    assert output.project_id == "empty_project"
    assert output.files == []
    assert output.requirements == []


# ============================================================
# 2. Python async functions should be detected
# ============================================================

def test_python_async_function():
    profile = {
        "project_id": "async_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
async def list_users():
    return []
"""

    output = process_project(
        profile,
        {"app/main.py": code},
        "",
    )

    file = output.files[0]

    assert "list_users" in {
        function.name for function in file.functions
    }

    assert {
        (route.method, route.path, route.function_name)
        for route in file.api_routes
    } == {
        ("GET", "/users", "list_users")
    }


# ============================================================
# 3. Class methods must NOT become top-level functions
# ============================================================

def test_class_methods_not_top_level_functions():
    profile = {
        "project_id": "class_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
class UserService:

    def create_user(self, name):
        pass

    def delete_user(self, user_id):
        pass


def health_check():
    return {"status": "ok"}
"""

    output = process_project(
        profile,
        {"app/services/user.py": code},
        "",
    )

    file = output.files[0]

    class_model = next(
        cls for cls in file.classes
        if cls.name == "UserService"
    )

    assert set(class_model.methods) == {
        "create_user",
        "delete_user",
    }

    top_level_functions = {
        function.name for function in file.functions
    }

    assert "health_check" in top_level_functions
    assert "create_user" not in top_level_functions
    assert "delete_user" not in top_level_functions


# ============================================================
# 4. Multiple decorators should not create duplicate routes
# ============================================================

def test_route_detection_with_multiple_decorators():
    profile = {
        "project_id": "decorator_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
@app.get("/people")
def list_users():
    return []
"""

    output = process_project(
        profile,
        {"app/main.py": code},
        "",
    )

    file = output.files[0]

    routes = [
        (r.method, r.path, r.function_name)
        for r in file.api_routes
    ]

    assert ("GET", "/users", "list_users") in routes
    assert ("GET", "/people", "list_users") in routes

    # One function should still exist only once.
    functions = [
        f.name for f in file.functions
        if f.name == "list_users"
    ]

    assert len(functions) == 1


# ============================================================
# 5. Nested functions should not accidentally become
#    production top-level functions
# ============================================================

def test_nested_python_function():
    profile = {
        "project_id": "nested_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
def outer_function():

    def inner_function():
        return 123

    return inner_function()
"""

    output = process_project(
        profile,
        {"app/service.py": code},
        "",
    )

    file = output.files[0]

    functions = {
        function.name for function in file.functions
    }

    assert "outer_function" in functions

    # Inner implementation detail should not be represented
    # as an independent top-level system function.
    assert "inner_function" not in functions


# ============================================================
# 6. JavaScript arrow functions assigned to variables
# ============================================================

def test_javascript_arrow_functions():
    profile = {
        "project_id": "js_project",
        "project_type": "frontend",
        "languages": ["javascript"],
        "frameworks": ["react"],
    }

    code = """
import React from "react";

const UserList = () => {
    return [];
};

const fetchUsers = async () => {
    return [];
};

users.map(user => user.name);
"""

    output = process_project(
        profile,
        {"src/App.js": code},
        "",
    )

    file = output.files[0]

    functions = {
        function.name for function in file.functions
    }

    assert "UserList" in functions
    assert "fetchUsers" in functions

    # Inline callback should NOT become a fake system function.
    assert "AnonymousFunction" not in functions


# ============================================================
# 7. TypeScript function + interface should not create
#    fake classes
# ============================================================

def test_typescript_interface_is_not_class():
    profile = {
        "project_id": "typescript_project",
        "project_type": "frontend",
        "languages": ["typescript"],
        "frameworks": ["react"],
    }

    code = """
interface User {
    id: number;
    name: string;
}

class UserService {
    getUser() {
        return null;
    }
}

export function listUsers() {
    return [];
}
"""

    output = process_project(
        profile,
        {"src/users.ts": code},
        "",
    )

    file = output.files[0]

    class_names = {
        cls.name for cls in file.classes
    }

    assert "UserService" in class_names
    assert "User" not in class_names

    function_names = {
        function.name for function in file.functions
    }

    assert "listUsers" in function_names


# ============================================================
# 8. Requirements separated without blank line
# ============================================================

def test_requirements_without_blank_lines():
    profile = {
        "project_id": "requirements_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    requirements = """
User Listing
The system must list users.
Acceptance Criteria:
- Fetches from /users
- Displays users

User Creation
The system must create users.
Acceptance Criteria:
- Accepts name
- Accepts email
"""

    output = process_project(
        profile,
        {},
        requirements,
    )

    assert len(output.requirements) == 2

    assert output.requirements[0].requirement_id == "REQ-001"
    assert output.requirements[1].requirement_id == "REQ-002"


# ============================================================
# 9. Existing requirement IDs must never control generated IDs
# ============================================================

def test_requirement_ids_are_always_regenerated():
    profile = {
        "project_id": "id_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    requirements = """
REQ-999 User Listing
The system must list users.

REQ-123 Dashboard
The system must show dashboard.
"""

    output = process_project(
        profile,
        {},
        requirements,
    )

    ids = [
        requirement.requirement_id
        for requirement in output.requirements
    ]

    assert ids == [
        "REQ-001",
        "REQ-002",
    ]


# ============================================================
# 10. Test files must NOT participate in code → requirement
#     implementation links
# ============================================================

def test_test_files_excluded_from_requirement_links():
    profile = {
        "project_id": "test_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def create_user():
    pass
""",
        "tests/test_users.py": """
def test_create_user():
    pass
""",
    }

    requirements = """
User Creation
The system shall allow creating users.
"""

    output = process_project(
        profile,
        files,
        requirements,
    )

    test_links = [
        link
        for link in output.code_requirement_links
        if link.file.startswith("tests/")
    ]

    assert test_links == []


# ============================================================
# 11. Unrelated functions must not receive requirement links
# ============================================================

def test_unrelated_function_not_linked_to_requirement():
    profile = {
        "project_id": "false_positive_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
def create_user():
    pass

def calculate_tax():
    pass

def send_email():
    pass
"""

    requirements = """
User Creation
The system shall allow creating users.
"""

    output = process_project(
        profile,
        {"app/users.py": code},
        requirements,
    )

    req_links = [
        link
        for link in output.code_requirement_links
        if link.requirement_id == "REQ-001"
    ]

    symbols = {
        link.symbol
        for link in req_links
    }

    assert "create_user" in symbols

    assert "calculate_tax" not in symbols
    assert "send_email" not in symbols


# ============================================================
# 12. Requirement with no implementation should have
#     NO false-positive links
# ============================================================

def test_unimplemented_requirement_has_no_links():
    profile = {
        "project_id": "missing_feature_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
def create_user():
    pass

def list_users():
    pass
"""

    requirements = """
Dashboard
The system shall display active user statistics.
Acceptance Criteria:
- Show active user count
"""

    output = process_project(
        profile,
        {"app/users.py": code},
        requirements,
    )

    req_links = [
        link
        for link in output.code_requirement_links
        if link.requirement_id == "REQ-001"
    ]

    assert req_links == []


# ============================================================
# 13. API route must be associated with the correct function
# ============================================================

def test_multiple_http_methods_are_correctly_mapped():
    profile = {
        "project_id": "routes_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def list_users():
    pass

@app.post("/users")
def create_user():
    pass

@app.delete("/users/{user_id}")
def delete_user(user_id: int):
    pass
"""

    output = process_project(
        profile,
        {"app/main.py": code},
        "",
    )

    routes = {
        (route.method, route.path, route.function_name)
        for route in output.files[0].api_routes
    }

    assert ("GET", "/users", "list_users") in routes
    assert ("POST", "/users", "create_user") in routes
    assert ("DELETE", "/users/{user_id}", "delete_user") in routes


# ============================================================
# 14. Import resolution should distinguish internal modules
#     from external packages
# ============================================================

def test_internal_import_resolution():
    profile = {
        "project_id": "dependency_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.services.user import create_user
from fastapi import FastAPI
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(
        profile,
        files,
        "",
    )

    dependencies = output.dependencies

    internal = [
        dependency
        for dependency in dependencies
        if dependency.target_module == "app.services.user"
        or dependency.target_module == "app.services.user.create_user"
    ]

    assert internal

    # At least one internal dependency should resolve to
    # the actual source file.
    assert any(
        dependency.resolved_file == "app/services/user.py"
        for dependency in internal
    )


# ============================================================
# 15. Same function name in different files must remain
#     distinguishable
# ============================================================

def test_duplicate_function_names_across_files():
    profile = {
        "project_id": "duplicate_names_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def create():
    pass
""",
        "app/orders.py": """
def create():
    pass
""",
    }

    output = process_project(
        profile,
        files,
        "",
    )

    assert len(output.files) == 2

    for file in output.files:
        assert any(
            function.name == "create"
            for function in file.functions
        )


# ============================================================
# 16. Empty / malformed requirement input should be safe
# ============================================================

def test_whitespace_requirement_input():
    profile = {
        "project_id": "whitespace_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    output = process_project(
        profile,
        {},
        "   \n\n   \n",
    )

    assert output.requirements == []


# ============================================================
# 17. Python relative imports
# ============================================================

def test_python_relative_import_is_preserved():
    profile = {
        "project_id": "relative_import_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
from .services.user import UserService
from ..database import get_db
"""

    output = process_project(
        profile,
        {"app/main.py": code},
        "",
    )

    imports = output.files[0].imports

    assert ".services.user.UserService" in imports
    assert "..database.get_db" in imports


# ============================================================
# 18. Frontend API calls must not become API routes
# ============================================================

def test_frontend_fetch_is_not_server_route():
    profile = {
        "project_id": "frontend_api_project",
        "project_type": "frontend",
        "languages": ["typescript"],
        "frameworks": ["react"],
    }

    code = """
import axios from "axios";

export async function fetchUsers() {
    return axios.get("/users");
}

export async function createUser(user) {
    return axios.post("/users", user);
}
"""

    output = process_project(
        profile,
        {"src/api.ts": code},
        "",
    )

    file = output.files[0]

    assert file.api_routes == []

    assert "fetchUsers" in {
        function.name for function in file.functions
    }

    assert "createUser" in {
        function.name for function in file.functions
    }