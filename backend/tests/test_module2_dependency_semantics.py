from app.analyzer.system_model.adapter import process_project


def _dependency_edges(output):
    return [
        (
            edge.source_file,
            edge.source_function,
            edge.target_file,
            edge.target_function,
        )
        for edge in output.depends_edges
    ]


def test_imported_function_called_through_alias_creates_dependency():
    profile = {
        "project_id": "alias_call_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.services.user import create_user as create

def handler():
    create()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = _dependency_edges(output)

    assert (
        "app/main.py",
        "handler",
        "app/services/user.py",
        "create_user",
    ) in edges


def test_imported_function_not_called_does_not_create_dependency():
    profile = {
        "project_id": "unused_import_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.services.user import create_user

def handler():
    pass
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = _dependency_edges(output)

    assert not any(
        edge[0] == "app/main.py"
        and edge[1] == "handler"
        and edge[3] == "create_user"
        for edge in edges
    )


def test_two_functions_call_different_imported_functions():
    profile = {
        "project_id": "multiple_calls_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.services.user import create_user
from app.services.audit import write_audit

def handler():
    create_user()
    write_audit()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
        "app/services/audit.py": """
def write_audit():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = _dependency_edges(output)

    assert (
        "app/main.py",
        "handler",
        "app/services/user.py",
        "create_user",
    ) in edges

    assert (
        "app/main.py",
        "handler",
        "app/services/audit.py",
        "write_audit",
    ) in edges


def test_same_name_from_two_modules_keeps_import_identity():
    profile = {
        "project_id": "same_name_imports",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.users import get_user
from app.admin import get_user as get_admin

def handler():
    get_user()
    get_admin()
""",
        "app/users.py": """
def get_user():
    pass
""",
        "app/admin.py": """
def get_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = _dependency_edges(output)

    assert (
        "app/main.py",
        "handler",
        "app/users.py",
        "get_user",
    ) in edges

    assert (
        "app/main.py",
        "handler",
        "app/admin.py",
        "get_user",
    ) in edges


def test_class_method_call_preserves_class_identity():
    profile = {
        "project_id": "class_method_dependency",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.services.user import UserService

def handler():
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

    edges = _dependency_edges(output)

    assert any(
        edge[0] == "app/main.py"
        and edge[1] == "handler"
        and edge[2] == "app/services/user.py"
        and edge[3] in {
            "UserService.create_user",
            "create_user",
        }
        for edge in edges
    )


def test_calling_local_function_creates_dependency():
    profile = {
        "project_id": "local_call_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
def get_db():
    pass

def handler():
    get_db()
""",
    }

    output = process_project(profile, files, "")

    edges = _dependency_edges(output)

    assert any(
        edge[0] == "app/main.py"
        and edge[1] == "handler"
        and edge[2] == "app/main.py"
        and edge[3] == "get_db"
        for edge in edges
    )


def test_call_to_unknown_function_does_not_create_fake_internal_dependency():
    profile = {
        "project_id": "unknown_call_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
def handler():
    something_from_unknown_library()
""",
    }

    output = process_project(profile, files, "")

    edges = _dependency_edges(output)

    assert not any(
        edge[0] == "app/main.py"
        and edge[1] == "handler"
        and edge[3] == "something_from_unknown_library"
        for edge in edges
    )


def test_dependency_edges_are_not_duplicated():
    profile = {
        "project_id": "duplicate_edge_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.services.user import create_user

def handler():
    create_user()
    create_user()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(profile, files, "")

    edges = _dependency_edges(output)

    matching = [
        edge
        for edge in edges
        if edge == (
            "app/main.py",
            "handler",
            "app/services/user.py",
            "create_user",
        )
    ]

    assert len(matching) == 1


def test_dependency_graph_handles_circular_imports_without_crashing():
    profile = {
        "project_id": "circular_import_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/a.py": """
from app.b import function_b

def function_a():
    function_b()
""",
        "app/b.py": """
from app.a import function_a

def function_b():
    function_a()
""",
    }

    output = process_project(profile, files, "")

    edges = _dependency_edges(output)

    assert (
        "app/a.py",
        "function_a",
        "app/b.py",
        "function_b",
    ) in edges

    assert (
        "app/b.py",
        "function_b",
        "app/a.py",
        "function_a",
    ) in edges