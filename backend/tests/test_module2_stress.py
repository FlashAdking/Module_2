"""
Module 2 stress / real-world tests.

These tests intentionally exercise behavior that is easy to get subtly wrong:
- FastAPI APIRouter + prefixes
- async routes
- relative and nested imports
- duplicate symbols
- class methods vs top-level functions
- JavaScript / TypeScript symbols
- requirement matching using acceptance criteria
- requirement false positives
- unimplemented requirements
- test-file exclusion
- dependency resolution
"""

from app.analyzer.system_model.adapter import process_project


def _links_for(output, requirement_id):
    return {
        link.symbol
        for link in output.code_requirement_links
        if link.requirement_id == requirement_id
    }


# ---------------------------------------------------------------------------
# 1. FastAPI APIRouter + prefix + async routes
# ---------------------------------------------------------------------------

def test_router_prefix_and_async_routes():
    profile = {
        "project_id": "router_stress",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from fastapi import APIRouter

router = APIRouter(prefix="/api/users")


@router.get("/")
async def list_users():
    pass


@router.post("/")
async def create_user():
    pass


@router.delete("/{user_id}")
async def delete_user(user_id: int):
    pass
"""
    }

    output = process_project(profile, files, "")

    routes = output.files[0].api_routes

    assert {
        (route.method, route.path, route.function_name)
        for route in routes
    } == {
        ("GET", "/api/users/", "list_users"),
        ("POST", "/api/users/", "create_user"),
        ("DELETE", "/api/users/{user_id}", "delete_user"),
    }


# ---------------------------------------------------------------------------
# 2. Multiple routers in different files must retain file identity
# ---------------------------------------------------------------------------

def test_same_route_symbols_in_different_files_keep_identity():
    profile = {
        "project_id": "duplicate_router_symbols",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
from fastapi import APIRouter

router = APIRouter()

@router.get("/users")
def list_items():
    pass
""",
        "app/admin.py": """
from fastapi import APIRouter

router = APIRouter()

@router.get("/admin/users")
def list_items():
    pass
""",
    }

    output = process_project(profile, files, "")

    user_file = next(
        f for f in output.files
        if f.file == "app/users.py"
    )

    admin_file = next(
        f for f in output.files
        if f.file == "app/admin.py"
    )

    assert "list_items" in {
        function.name for function in user_file.functions
    }

    assert "list_items" in {
        function.name for function in admin_file.functions
    }

    routes = {
        (route.path, route.function_name)
        for f in output.files
        for route in f.api_routes
    }

    assert ("/users", "list_items") in routes
    assert ("/admin/users", "list_items") in routes


# ---------------------------------------------------------------------------
# 3. Internal imports must resolve to actual files
# ---------------------------------------------------------------------------

def test_nested_internal_import_resolution():
    profile = {
        "project_id": "nested_imports",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.services.users.service import UserService
from app.database.session import get_db
""",
        "app/services/users/service.py": """
class UserService:
    pass
""",
        "app/database/session.py": """
def get_db():
    pass
""",
    }

    output = process_project(profile, files, "")

    internal = [
        dependency
        for dependency in output.dependencies
        if dependency.kind == "INTERNAL"
    ]

    assert any(
        dependency.resolved_file == "app/services/users/service.py"
        for dependency in internal
    )

    assert any(
        dependency.resolved_file == "app/database/session.py"
        for dependency in internal
    )


# ---------------------------------------------------------------------------
# 4. Relative imports should preserve semantic information
# ---------------------------------------------------------------------------

def test_relative_import_resolution_preserves_module_identity():
    profile = {
        "project_id": "relative_imports",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from ..services.user import UserService
from ...database import get_db
""",
        "app/services/user.py": """
class UserService:
    pass
""",
        "database.py": """
def get_db():
    pass
""",
    }

    output = process_project(profile, files, "")

    imports = next(
        f.imports
        for f in output.files
        if f.file == "app/api/users.py"
    )

    assert any("UserService" in item for item in imports)
    assert any("get_db" in item for item in imports)


# ---------------------------------------------------------------------------
# 5. Class methods must not become unrelated top-level symbols
# ---------------------------------------------------------------------------

def test_class_methods_have_correct_symbol_identity():
    profile = {
        "project_id": "class_identity",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
class UserService:

    def create_user(self):
        pass

    def list_users(self):
        pass


def list_users():
    pass
"""
    }

    output = process_project(profile, files, "")

    file = output.files[0]

    # Exactly one top-level list_users function.
    top_level = [
        function.name
        for function in file.functions
        if function.name == "list_users"
    ]

    assert top_level == ["list_users"]

    service = next(
        cls for cls in file.classes
        if cls.name == "UserService"
    )

    assert "create_user" in service.methods
    assert "list_users" in service.methods


# ---------------------------------------------------------------------------
# 6. Requirement matching should use acceptance criteria
# ---------------------------------------------------------------------------

def test_requirement_matching_uses_acceptance_criteria():
    profile = {
        "project_id": "acceptance_criteria",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
from fastapi import APIRouter

router = APIRouter()


@router.get("/users")
def fetch_all():
    pass


@router.delete("/users/{user_id}")
def remove():
    pass
"""
    }

    requirements = """
User Management
The application shall provide user management.
Acceptance Criteria:
- GET /users returns all users
- Users are displayed in a table

User Administration
The application shall provide administrative user operations.
Acceptance Criteria:
- DELETE /users/{user_id} removes a selected user
"""

    output = process_project(
        profile,
        files,
        requirements,
    )

    management = _links_for(output, "REQ-001")
    administration = _links_for(output, "REQ-002")

    assert "fetch_all" in management
    assert "remove" in administration

    assert "remove" not in management
    assert "fetch_all" not in administration


# ---------------------------------------------------------------------------
# 7. Similar requirements must not cross-link
# ---------------------------------------------------------------------------

def test_similar_requirements_do_not_cross_link():
    profile = {
        "project_id": "similar_requirements",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def list_users():
    pass

def search_users():
    pass

def delete_user():
    pass
"""
    }

    requirements = """
User Listing
The system must list all users.
Acceptance Criteria:
- Fetches the users list

User Search
The system must allow searching for users.
Acceptance Criteria:
- Searches users by name

User Deletion
The system must allow administrators to delete users.
Acceptance Criteria:
- Deletes a selected user
"""

    output = process_project(
        profile,
        files,
        requirements,
    )

    listing = _links_for(output, "REQ-001")
    search = _links_for(output, "REQ-002")
    deletion = _links_for(output, "REQ-003")

    assert "list_users" in listing
    assert "search_users" in search
    assert "delete_user" in deletion

    assert "search_users" not in listing
    assert "delete_user" not in listing

    assert "list_users" not in search
    assert "delete_user" not in search

    assert "list_users" not in deletion
    assert "search_users" not in deletion


# ---------------------------------------------------------------------------
# 8. Unimplemented requirement must remain empty
# ---------------------------------------------------------------------------

def test_unimplemented_requirement_has_no_code_links():
    profile = {
        "project_id": "unimplemented",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def list_users():
    pass
"""
    }

    requirements = """
User Listing
The system must list users.

Analytics Dashboard
The system must display revenue analytics.
Acceptance Criteria:
- Shows monthly revenue
- Shows yearly revenue
"""

    output = process_project(
        profile,
        files,
        requirements,
    )

    analytics = _links_for(output, "REQ-002")

    assert analytics == set()


# ---------------------------------------------------------------------------
# 9. Test code must not become production requirement implementation
# ---------------------------------------------------------------------------

def test_test_files_are_not_requirement_implementations():
    profile = {
        "project_id": "test_exclusion",
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

Acceptance Criteria:
- Accepts name and email
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


# ---------------------------------------------------------------------------
# 10. Frontend functions must not become backend API routes
# ---------------------------------------------------------------------------

def test_frontend_functions_do_not_create_server_routes():
    profile = {
        "project_id": "frontend_routes",
        "project_type": "web_app",
        "languages": ["typescript"],
        "frameworks": ["react"],
    }

    files = {
        "frontend/src/users.tsx": """
import axios from "axios";

export function UserList() {
    return null;
}

export async function fetchUsers() {
    return axios.get("/users");
}
"""
    }

    output = process_project(profile, files, "")

    file = output.files[0]

    assert file.api_routes == []

    symbols = {
        function.name
        for function in file.functions
    }

    assert "UserList" in symbols
    assert "fetchUsers" in symbols


# ---------------------------------------------------------------------------
# 11. JavaScript / TypeScript arrow functions
# ---------------------------------------------------------------------------

def test_typescript_arrow_function_identity():
    profile = {
        "project_id": "typescript_symbols",
        "project_type": "web_app",
        "languages": ["typescript"],
        "frameworks": ["react"],
    }

    files = {
        "src/users.ts": """
export const fetchUsers = async () => {
    return [];
};

const deleteUser = (id: string) => {
    return id;
};
"""
    }

    output = process_project(profile, files, "")

    symbols = {
        function.name
        for function in output.files[0].functions
    }

    assert "fetchUsers" in symbols
    assert "deleteUser" in symbols


# ---------------------------------------------------------------------------
# 12. HTTP method semantics must influence matching
# ---------------------------------------------------------------------------

def test_http_method_semantics_help_requirement_matching():
    profile = {
        "project_id": "http_semantics",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
from fastapi import APIRouter

router = APIRouter()

@router.get("/users")
def fetch_users():
    pass

@router.post("/users")
def create_user():
    pass

@router.delete("/users/{user_id}")
def remove_user():
    pass
"""
    }

    requirements = """
User Listing
The system must list users.
Acceptance Criteria:
- GET /users returns all users

User Creation
The system must create users.
Acceptance Criteria:
- POST /users creates a user

User Deletion
The system must delete users.
Acceptance Criteria:
- DELETE /users/{user_id} removes a user
"""

    output = process_project(
        profile,
        files,
        requirements,
    )

    listing = _links_for(output, "REQ-001")
    creation = _links_for(output, "REQ-002")
    deletion = _links_for(output, "REQ-003")

    assert "fetch_users" in listing
    assert "create_user" in creation
    assert "remove_user" in deletion

    assert "create_user" not in listing
    assert "remove_user" not in listing

    assert "fetch_users" not in creation
    assert "remove_user" not in creation

    assert "fetch_users" not in deletion
    assert "create_user" not in deletion