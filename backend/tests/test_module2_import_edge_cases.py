from app.analyzer.system_model.adapter import process_project


def _process(files):
    profile = {
        "project_id": "import_edge_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }
    return process_project(profile, files, "")


def test_package_init_re_export_resolves_correct_file():
    files = {
        "app/main.py": """
from app.services import create_user

def endpoint():
    return create_user()
""",
        "app/services/__init__.py": """
from app.services.users import create_user
""",
        "app/services/users.py": """
def create_user():
    return "created"
""",
    }

    output = _process(files)

    edges = output.depends_edges

    assert any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        and edge.target_file == "app/services/users.py"
        for edge in edges
    )


def test_from_module_import_alias_preserves_identity():
    files = {
        "app/main.py": """
from app.users import create_user as make_user

def endpoint():
    return make_user()
""",
        "app/users.py": """
def create_user():
    return "created"
""",
    }

    output = _process(files)

    assert any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        and edge.target_file == "app/users.py"
        for edge in output.depends_edges
    )


def test_module_import_then_attribute_call_resolves():
    files = {
        "app/main.py": """
import app.users

def endpoint():
    return app.users.create_user()
""",
        "app/users.py": """
def create_user():
    return "created"
""",
    }

    output = _process(files)

    assert any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        and edge.target_file == "app/users.py"
        for edge in output.depends_edges
    )


def test_relative_import_from_package_resolves():
    files = {
        "app/api/routes.py": """
from ..services.users import create_user

def endpoint():
    return create_user()
""",
        "app/services/users.py": """
def create_user():
    return "created"
""",
    }

    output = _process(files)

    assert any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        and edge.target_file == "app/services/users.py"
        for edge in output.depends_edges
    )


def test_missing_internal_module_does_not_become_fake_internal_edge():
    files = {
        "app/main.py": """
from app.missing import create_user

def endpoint():
    return create_user()
""",
    }

    output = _process(files)

    # There is no real target file, so the analyzer must not invent
    # an internal dependency.
    assert not any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        for edge in output.depends_edges
    )


def test_same_function_name_in_three_packages_keeps_file_identity():
    files = {
        "app/main.py": """
from app.admin.users import get_user as admin_user
from app.public.users import get_user as public_user
from app.internal.users import get_user as internal_user

def endpoint():
    admin_user()
    public_user()
    internal_user()
""",
        "app/admin/users.py": """
def get_user():
    return "admin"
""",
        "app/public/users.py": """
def get_user():
    return "public"
""",
        "app/internal/users.py": """
def get_user():
    return "internal"
""",
    }

    output = _process(files)

    edges = [
        edge
        for edge in output.depends_edges
        if edge.source_function == "endpoint"
    ]

    target_files = {
        edge.target_file
        for edge in edges
        if edge.target_function == "get_user"
    }

    assert target_files == {
        "app/admin/users.py",
        "app/public/users.py",
        "app/internal/users.py",
    }


def test_unused_import_does_not_create_dependency():
    files = {
        "app/main.py": """
from app.users import create_user

def endpoint():
    return "hello"
""",
        "app/users.py": """
def create_user():
    return "created"
""",
    }

    output = _process(files)

    assert not any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        for edge in output.depends_edges
    )