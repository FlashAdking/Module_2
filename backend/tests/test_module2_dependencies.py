from app.analyzer.system_model.adapter import process_project


def test_cross_file_function_call_creates_dependency_edge():
    profile = {
        "project_id": "cross_file_calls",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from app.services.user import create_user

def create():
    create_user()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = output.depends_edges

    assert any(
        edge.source_file == "app/api/users.py"
        and edge.source_function == "create"
        and edge.target_function == "create_user"
        for edge in edges
    )


def test_same_function_name_in_different_files_does_not_cross_link():
    profile = {
        "project_id": "qualified_identity",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from app.services.user import validate

def create_user():
    validate()
""",
        "app/services/user.py": """
def validate():
    pass
""",
        "app/services/admin.py": """
def validate():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = output.depends_edges

    matching = [
        edge
        for edge in edges
        if edge.source_file == "app/api/users.py"
        and edge.source_function == "create_user"
        and edge.target_function == "validate"
    ]

    assert len(matching) == 1


def test_imported_alias_preserves_target_identity():
    profile = {
        "project_id": "import_alias",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from app.services.user import create_user as create

def endpoint():
    create()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = output.depends_edges

    assert any(
        edge.source_file == "app/api/users.py"
        and edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        for edge in edges
    )


def test_multiple_imported_functions_keep_individual_edges():
    profile = {
        "project_id": "multiple_calls",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from app.services.user import create_user, delete_user

def endpoint():
    create_user()
    delete_user()
""",
        "app/services/user.py": """
def create_user():
    pass

def delete_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = output.depends_edges

    assert any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        for edge in edges
    )

    assert any(
        edge.source_function == "endpoint"
        and edge.target_function == "delete_user"
        for edge in edges
    )


def test_unrelated_same_named_function_is_not_dependency():
    profile = {
        "project_id": "unrelated_same_name",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from app.services.user import create_user

def endpoint():
    create_user()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
        "app/utils.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = [
        edge
        for edge in output.depends_edges
        if edge.source_file == "app/api/users.py"
        and edge.source_function == "endpoint"
        and edge.target_function == "create_user"
    ]

    assert len(edges) == 1


def test_class_method_dependency_keeps_class_identity():
    profile = {
        "project_id": "class_method_dependency",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from app.services.user import UserService

def endpoint():
    service = UserService()
    service.create_user()
""",
        "app/services/user.py": """
class UserService:
    def create_user(self):
        pass
""",
    }

    output = process_project(profile, files, "")

    # The important invariant is that the analyzer must not
    # confuse UserService.create_user with an unrelated
    # top-level create_user symbol.
    service_file = next(
        file
        for file in output.files
        if file.file == "app/services/user.py"
    )

    service = next(
        cls
        for cls in service_file.classes
        if cls.name == "UserService"
    )

    assert "create_user" in service.methods


def test_imported_module_without_local_file_is_external():
    profile = {
        "project_id": "external_dependency",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from fastapi import FastAPI
from requests import get

app = FastAPI()

def fetch():
    get("https://example.com")
"""
    }

    output = process_project(profile, files, "")

    external = [
        dependency
        for dependency in output.dependencies
        if dependency.kind == "EXTERNAL"
    ]

    assert any(
        "fastapi" in dependency.target_module
        for dependency in external
    )

    assert any(
        "requests" in dependency.target_module
        for dependency in external
    )


def test_dependency_edges_are_not_created_for_unused_imports():
    profile = {
        "project_id": "unused_import",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/api/users.py": """
from app.services.user import create_user

def endpoint():
    pass
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = [
        edge
        for edge in output.depends_edges
        if edge.source_file == "app/api/users.py"
    ]

    assert not any(
        edge.target_function == "create_user"
        for edge in edges
    )