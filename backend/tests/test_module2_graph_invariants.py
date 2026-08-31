"""
Module 2 graph invariant tests.

These tests do not focus on one particular implementation technique.
They validate properties that must always be true in the system model.

Goal:
    Catch structurally invalid graphs before the model is persisted
    into Neo4j.
"""

from collections import Counter

from app.analyzer.system_model.adapter import process_project


def profile():
    return {
        "project_id": "graph_invariant_project",
        "project_type": "web_api",
        "languages": ["python", "tsx"],
        "frameworks": ["fastapi", "react"],
    }


def all_functions(output):
    """Return (file, symbol) pairs for all production functions."""
    result = set()

    for file_model in output.files:
        if "/tests/" in file_model.file or file_model.file.startswith("tests/"):
            continue

        for function in file_model.functions:
            result.add((file_model.file, function.name))

        for cls in file_model.classes:
            for method in cls.methods:
                result.add((file_model.file, f"{cls.name}.{method}"))

    return result


def all_production_files(output):
    return {
        file_model.file
        for file_model in output.files
        if "/tests/" not in file_model.file
        and not file_model.file.startswith("tests/")
    }


def test_internal_dependencies_resolve_to_existing_files():
    files = {
        "app/main.py": """
from app.services.user import create_user

def endpoint():
    return create_user()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile(), files, "")

    production_files = all_production_files(output)

    for dependency in output.dependencies:
        if dependency.kind == "INTERNAL":
            assert dependency.resolved_file is not None
            assert dependency.resolved_file in production_files


def test_dependency_edges_reference_existing_functions():
    files = {
        "app/main.py": """
from app.services.user import create_user

def endpoint():
    return create_user()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile(), files, "")

    functions = all_functions(output)

    for edge in output.depends_edges:
        assert (edge.source_file, edge.source_function) in functions
        assert (edge.target_file, edge.target_function) in functions


def test_dependency_edges_are_unique():
    files = {
        "app/main.py": """
from app.services.user import create_user
from app.services.user import create_user as make_user

def endpoint():
    create_user()
    make_user()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile(), files, "")

    keys = [
        (
            edge.source_file,
            edge.source_function,
            edge.target_file,
            edge.target_function,
        )
        for edge in output.depends_edges
    ]

    assert len(keys) == len(set(keys))


def test_genuine_self_call_is_allowed_but_fake_self_dependency_is_not():
    files = {
        "app/main.py": """
def recursive_function(n):
    if n <= 0:
        return 0
    return recursive_function(n - 1)
""",
        "app/other.py": """
def helper():
    pass
""",
    }

    output = process_project(profile(), files, "")

    self_edges = [
        edge
        for edge in output.depends_edges
        if edge.source_file == edge.target_file
        and edge.source_function == edge.target_function
    ]

    # A genuine recursive function may legitimately have a self-edge.
    assert all(
        edge.source_function == "recursive_function"
        for edge in self_edges
    )


def test_same_named_functions_remain_distinct_graph_nodes():
    files = {
        "app/users.py": """
def process():
    pass
""",
        "app/orders.py": """
def process():
    pass
""",
    }

    output = process_project(profile(), files, "")

    functions = all_functions(output)

    assert ("app/users.py", "process") in functions
    assert ("app/orders.py", "process") in functions


def test_class_method_identity_is_preserved():
    files = {
        "app/services.py": """
class UserService:
    def create(self):
        pass

class AdminService:
    def create(self):
        pass
""",
    }

    output = process_project(profile(), files, "")

    functions = all_functions(output)

    assert ("app/services.py", "UserService.create") in functions
    assert ("app/services.py", "AdminService.create") in functions

    assert (
        "UserService.create" != "AdminService.create"
    )


def test_external_dependencies_do_not_become_internal_graph_nodes():
    files = {
        "app/main.py": """
from fastapi import FastAPI
from sqlalchemy import create_engine

def endpoint():
    pass
""",
    }

    output = process_project(profile(), files, "")

    for dependency in output.dependencies:
        if dependency.kind == "EXTERNAL":
            assert dependency.resolved_file is None


def test_test_files_are_not_production_graph_nodes():
    files = {
        "app/main.py": """
def create_user():
    pass
""",
        "tests/test_users.py": """
def test_create_user():
    pass
""",
    }

    output = process_project(profile(), files, "")

    for edge in output.depends_edges:
        assert not edge.source_file.startswith("tests/")
        assert not edge.target_file.startswith("tests/")


def test_api_routes_reference_existing_functions():
    files = {
        "app/main.py": """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def list_users():
    pass

@app.post("/users")
async def create_user():
    pass
""",
    }

    output = process_project(profile(), files, "")

    functions = all_functions(output)

    for file_model in output.files:
        for route in file_model.api_routes:
            assert (
                file_model.file,
                route.function_name,
            ) in functions


def test_frontend_files_do_not_create_backend_routes():
    files = {
        "frontend/src/App.tsx": """
import axios from "axios";

export function UserList() {
    return null;
}

export const fetchUsers = () => axios.get("/users");
""",
    }

    output = process_project(profile(), files, "")

    frontend_routes = [
        route
        for file_model in output.files
        if file_model.file.endswith(".tsx")
        for route in file_model.api_routes
    ]

    assert frontend_routes == []


def test_requirement_links_reference_existing_production_symbols():
    files = {
        "app/users.py": """
def list_users():
    pass

def create_user():
    pass
""",
        "tests/test_users.py": """
def test_list_users():
    pass
""",
    }

    requirements = """
User Listing

The system must list all users.

Acceptance Criteria:

- Fetches the users list


User Creation

The system must create users.

Acceptance Criteria:

- Creates a new user
"""

    output = process_project(
        profile(),
        files,
        requirements,
    )

    functions = all_functions(output)

    for link in output.code_requirement_links:
        assert link.file in all_production_files(output)
        assert (link.file, link.symbol) in functions


def test_requirement_links_never_target_test_functions():
    files = {
        "app/users.py": """
def list_users():
    pass
""",
        "tests/test_users.py": """
def test_list_users():
    pass
""",
    }

    requirements = """
User Listing

The system must list all users.

Acceptance Criteria:

- Fetches the users list
"""

    output = process_project(
        profile(),
        files,
        requirements,
    )

    for link in output.code_requirement_links:
        assert not link.file.startswith("tests/")
        assert not link.symbol.startswith("test_")


def test_unresolved_dependency_does_not_point_to_random_same_named_function():
    files = {
        "app/main.py": """
from missing.module import process

def endpoint():
    return process()
""",
        "app/unrelated.py": """
def process():
    pass
""",
    }

    output = process_project(profile(), files, "")

    edges = [
        edge
        for edge in output.depends_edges
        if edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
    ]

    assert not any(
        edge.target_file == "app/unrelated.py"
        and edge.target_function == "process"
        for edge in edges
    )


def test_circular_dependencies_are_represented_without_duplicate_edges():
    files = {
        "app/a.py": """
from app.b import function_b

def function_a():
    return function_b()
""",
        "app/b.py": """
from app.a import function_a

def function_b():
    return function_a()
""",
    }

    output = process_project(profile(), files, "")

    keys = [
        (
            edge.source_file,
            edge.source_function,
            edge.target_file,
            edge.target_function,
        )
        for edge in output.depends_edges
    ]

    assert len(keys) == len(set(keys))

    assert any(
        edge.source_file == "app/a.py"
        and edge.target_file == "app/b.py"
        for edge in output.depends_edges
    )

    assert any(
        edge.source_file == "app/b.py"
        and edge.target_file == "app/a.py"
        for edge in output.depends_edges
    )


def test_multiple_paths_to_same_target_converge_on_same_node():
    files = {
        "app/main.py": """
from app.service import create_user
from app.other import audit

def endpoint():
    create_user()
    audit()
""",
        "app/service.py": """
from app.repository import save_user

def create_user():
    return save_user()
""",
        "app/other.py": """
from app.repository import save_user

def audit():
    return save_user()
""",
        "app/repository.py": """
def save_user():
    pass
""",
    }

    output = process_project(profile(), files, "")

    repository_edges = [
        edge
        for edge in output.depends_edges
        if edge.target_file == "app/repository.py"
        and edge.target_function == "save_user"
    ]

    sources = {
        (
            edge.source_file,
            edge.source_function,
        )
        for edge in repository_edges
    }

    assert ("app/service.py", "create_user") in sources
    assert ("app/other.py", "audit") in sources


def test_analysis_is_deterministic_for_same_input():
    files = {
        "app/main.py": """
from app.service import create_user

def endpoint():
    return create_user()
""",
        "app/service.py": """
def create_user():
    pass
""",
    }

    output1 = process_project(profile(), files, "")
    output2 = process_project(profile(), files, "")

    assert output1.model_dump() == output2.model_dump()


def test_requirement_link_identity_preserves_file_boundary():
    files = {
        "app/users.py": """
def create_user():
    pass
""",
        "app/orders.py": """
def create_user():
    pass
""",
    }

    requirements = """
User Creation

The system shall create a user.

Acceptance Criteria:

- Creates a new user account
"""

    output = process_project(
        profile(),
        files,
        requirements,
    )

    links = [
        link
        for link in output.code_requirement_links
        if link.requirement_id == "REQ-001"
    ]

    assert all(link.symbol == "create_user" for link in links)

    # The important invariant is that file identity is retained.
    linked_files = {link.file for link in links}

    assert linked_files <= {
        "app/users.py",
        "app/orders.py",
    }


def test_empty_project_produces_empty_graph():
    output = process_project(
        profile(),
        {},
        "",
    )

    assert output.files == []
    assert output.dependencies == []
    assert output.depends_edges == []
    assert output.code_requirement_links == []
    assert output.code_test_links == []


def test_requirement_ids_are_unique():
    requirements = """
User Listing

The system must list users.

Acceptance Criteria:

- Displays users


User Creation

The system must create users.

Acceptance Criteria:

- Creates users


User Deletion

The system must delete users.

Acceptance Criteria:

- Deletes users
"""

    output = process_project(
        profile(),
        {},
        requirements,
    )

    ids = [
        requirement.requirement_id
        for requirement in output.requirements
    ]

    assert len(ids) == len(set(ids))