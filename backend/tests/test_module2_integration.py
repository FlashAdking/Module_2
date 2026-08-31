"""
High-level integration tests for Module 2.

These tests intentionally model a small realistic application rather than
isolated parser cases.

Goal:
    Verify that Module 2 produces a coherent semantic model that is safe
    to later persist as a Neo4j graph.

Run:
    python -m pytest tests/test_module2_integration.py -v
"""

from app.analyzer.system_model.adapter import process_project


def _process(files, requirements):
    profile = {
        "project_id": "integration_project",
        "project_type": "web_api",
        "languages": ["python", "tsx"],
        "frameworks": ["fastapi", "react"],
    }

    return process_project(profile, files, requirements)


def _links_for(output, requirement_id):
    return {
        link.symbol
        for link in output.code_requirement_links
        if link.requirement_id == requirement_id
    }


# ---------------------------------------------------------------------------
# 1. Realistic backend dependency chain
#
# API route -> service -> repository -> database
#
# This is one of the most important graph structures Module 2 must preserve.
# ---------------------------------------------------------------------------

def test_realistic_backend_dependency_chain():
    files = {
        "app/main.py": """
from fastapi import FastAPI
from app.api.users import router

app = FastAPI()
app.include_router(router, prefix="/api")
""",
        "app/api/users.py": """
from fastapi import APIRouter
from app.services.users import list_users

router = APIRouter()

@router.get("/users")
async def get_users():
    return await list_users()
""",
        "app/services/users.py": """
from app.repositories.users import fetch_users

async def list_users():
    return await fetch_users()
""",
        "app/repositories/users.py": """
from app.database import get_db

async def fetch_users():
    db = get_db()
    return db.query("users")
""",
        "app/database.py": """
def get_db():
    return object()
""",
    }

    requirements = """
User Listing
The system must allow users to list all users.
Acceptance Criteria:
- GET /api/users returns the users
- Users are fetched from the database
"""

    output = _process(files, requirements)

    # Route must be discovered.
    routes = output.files

    api_file = next(
        file for file in routes
        if file.file == "app/api/users.py"
    )

    assert any(
        route.method == "GET"
        and route.path == "/users"
        and route.function_name == "get_users"
        for route in api_file.api_routes
    )

    # Requirement must identify the implementation.
    links = _links_for(output, "REQ-001")

    assert "get_users" in links

    # Dependency graph must contain the chain.
    edges = output.depends_edges

    edge_pairs = {
        (
            edge.source_function,
            edge.target_function,
        )
        for edge in edges
    }

    assert ("list_users", "fetch_users") in edge_pairs
    assert ("fetch_users", "get_db") in edge_pairs


# ---------------------------------------------------------------------------
# 2. Frontend + backend must remain semantically separate.
#
# Frontend fetchUsers may implement a requirement, but it must NOT become
# a server API route merely because it contains "fetch".
# ---------------------------------------------------------------------------

def test_fullstack_frontend_does_not_become_server_route():
    files = {
        "app/main.py": """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
async def list_users():
    return []
""",
        "frontend/src/App.tsx": """
import React from "react";
import axios from "axios";

async function fetchUsers() {
    const response = await axios.get("/users");
    return response.data;
}

export function UserList() {
    return <div>Users</div>;
}
""",
    }

    requirements = """
User Listing
The system must list all users.
Acceptance Criteria:
- Fetches users from /users
- Displays users in the frontend
"""

    output = _process(files, requirements)

    frontend = next(
        file for file in output.files
        if file.file == "frontend/src/App.tsx"
    )

    # Critical architectural invariant:
    # frontend functions must never become server routes.
    assert frontend.api_routes == []

    links = _links_for(output, "REQ-001")

    assert "list_users" in links
    assert "fetchUsers" in links
    assert "UserList" in links


# ---------------------------------------------------------------------------
# 3. Same symbols in different packages must remain independent.
#
# This is critical for Neo4j node identity.
# ---------------------------------------------------------------------------

def test_same_symbol_in_different_packages_keeps_identity():
    files = {
        "app/admin/users.py": """
def list_users():
    return ["admin"]
""",
        "app/public/users.py": """
def list_users():
    return ["public"]
""",
        "app/admin/routes.py": """
from app.admin.users import list_users

def admin_users():
    return list_users()
""",
        "app/public/routes.py": """
from app.public.users import list_users

def public_users():
    return list_users()
""",
    }

    requirements = """
Admin User Listing
The system must allow administrators to list users.
Acceptance Criteria:
- Returns administrative users

Public User Listing
The system must allow public users to list users.
Acceptance Criteria:
- Returns public users
"""

    output = _process(files, requirements)

    # Every implementation must retain file identity.
    symbols = [
        (
            file.file,
            function.name,
        )
        for file in output.files
        for function in file.functions
    ]

    assert (
        "app/admin/users.py",
        "list_users",
    ) in symbols

    assert (
        "app/public/users.py",
        "list_users",
    ) in symbols

    # Dependency edges must not collapse both list_users functions.
    edges = output.depends_edges

    admin_edges = [
        edge for edge in edges
        if edge.source_function == "admin_users"
    ]

    public_edges = [
        edge for edge in edges
        if edge.source_function == "public_users"
    ]

    assert admin_edges
    assert public_edges

    assert any(
        "admin" in edge.target_file
        for edge in admin_edges
    )

    assert any(
        "public" in edge.target_file
        for edge in public_edges
    )


# ---------------------------------------------------------------------------
# 4. Requirement with overlapping vocabulary.
#
# Listing and searching both contain "users".
# The analyzer must use operation semantics rather than keyword overlap.
# ---------------------------------------------------------------------------

def test_realistic_requirements_do_not_cross_link():
    files = {
        "app/users.py": """
def list_users():
    return []

def search_users(query):
    return []

def delete_user(user_id):
    return None
""",
    }

    requirements = """
User Listing
The system must list users.
Acceptance Criteria:
- Returns all users

User Search
The system must search users.
Acceptance Criteria:
- Searches users by name

User Deletion
The system must delete a user.
Acceptance Criteria:
- Removes the selected user
"""

    output = _process(files, requirements)

    listing = _links_for(output, "REQ-001")
    search = _links_for(output, "REQ-002")
    deletion = _links_for(output, "REQ-003")

    assert "list_users" in listing
    assert "search_users" in search
    assert "delete_user" in deletion

    # Prevent semantic cross-linking.
    assert "search_users" not in listing
    assert "delete_user" not in listing

    assert "list_users" not in search
    assert "delete_user" not in search

    assert "list_users" not in deletion
    assert "search_users" not in deletion


# ---------------------------------------------------------------------------
# 5. Diamond dependency graph.
#
#             route
#             /   \
#            A     B
#             \   /
#               C
#
# The graph must retain both paths and must not duplicate C unnecessarily.
# ---------------------------------------------------------------------------

def test_diamond_dependency_graph_is_preserved():
    files = {
        "app/routes.py": """
from app.service_a import service_a
from app.service_b import service_b

def endpoint():
    service_a()
    service_b()
""",
        "app/service_a.py": """
from app.common import common

def service_a():
    common()
""",
        "app/service_b.py": """
from app.common import common

def service_b():
    common()
""",
        "app/common.py": """
def common():
    pass
""",
    }

    output = _process(files, "")

    edges = {
        (
            edge.source_function,
            edge.target_function,
            edge.source_file,
            edge.target_file,
        )
        for edge in output.depends_edges
    }

    assert any(
        source == "endpoint"
        and target == "service_a"
        for source, target, _, _ in edges
    )

    assert any(
        source == "endpoint"
        and target == "service_b"
        for source, target, _, _ in edges
    )

    assert any(
        source == "service_a"
        and target == "common"
        for source, target, _, _ in edges
    )

    assert any(
        source == "service_b"
        and target == "common"
        for source, target, _, _ in edges
    )

    # No exact duplicate graph edges.
    assert len(edges) == len(output.depends_edges)


# ---------------------------------------------------------------------------
# 6. Unimplemented requirement must stay unimplemented.
#
# The analyzer must not "helpfully" attach an unrelated function merely
# because the requirement shares common words with the codebase.
# ---------------------------------------------------------------------------

def test_realistic_unimplemented_requirement_stays_unlinked():
    files = {
        "app/users.py": """
def list_users():
    return []

def create_user(name, email):
    return {
        "name": name,
        "email": email,
    }
""",
        "app/reports.py": """
def generate_sales_report():
    return []
""",
    }

    requirements = """
User Listing
The system must list users.
Acceptance Criteria:
- Returns all users

User Analytics Dashboard
The system must provide an analytics dashboard showing
monthly revenue, conversion rate, and active subscriptions.
Acceptance Criteria:
- Displays monthly revenue
- Displays conversion rate
- Displays active subscriptions
"""

    output = _process(files, requirements)

    dashboard_links = _links_for(output, "REQ-002")

    assert dashboard_links == set()


# ---------------------------------------------------------------------------
# 7. Deterministic output.
#
# This is important before Neo4j persistence:
# analyzing the same project twice should produce the same semantic model.
# ---------------------------------------------------------------------------

def test_analysis_is_deterministic():
    files = {
        "app/users.py": """
def list_users():
    return []

def create_user(name):
    return {"name": name}
""",
        "app/main.py": """
from app.users import list_users

def users():
    return list_users()
""",
    }

    requirements = """
User Listing
The system must list users.
Acceptance Criteria:
- Returns users
"""

    first = _process(files, requirements)
    second = _process(files, requirements)

    assert first == second