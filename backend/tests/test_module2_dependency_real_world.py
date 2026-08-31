"""
Real-world dependency graph tests for Module 2.

Focus:
- chained cross-file dependencies
- re-exported symbols
- package __init__.py imports
- wildcard imports
- unresolved internal-looking imports
- external vs internal classification
- dependency direction
- transitive dependency representation
- alias chains
"""

from app.analyzer.system_model.adapter import process_project


def make_profile():
    return {
        "project_id": "dependency_real_world_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }


def test_chained_cross_file_dependencies():
    files = {
        "app/main.py": """
from app.services.user import create_user

def endpoint():
    return create_user()
""",
        "app/services/user.py": """
from app.repositories.user import save_user

def create_user():
    return save_user()
""",
        "app/repositories/user.py": """
def save_user():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    edges = output.depends_edges

    assert any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        for edge in edges
    )

    assert any(
        edge.source_function == "create_user"
        and edge.target_function == "save_user"
        for edge in edges
    )


def test_dependency_edges_preserve_file_identity_for_chained_dependencies():
    files = {
        "app/main.py": """
from app.a import process

def run():
    return process()
""",
        "app/a.py": """
from app.b import process as b_process

def process():
    return b_process()
""",
        "app/b.py": """
def process():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    edges = output.depends_edges

    assert any(
        edge.source_file == "app/main.py"
        and edge.source_function == "run"
        and edge.target_file == "app/a.py"
        and edge.target_function == "process"
        for edge in edges
    )

    assert any(
        edge.source_file == "app/a.py"
        and edge.source_function == "process"
        and edge.target_file == "app/b.py"
        and edge.target_function == "process"
        for edge in edges
    )


def test_package_init_reexport_resolves_to_real_module():
    files = {
        "app/main.py": """
from app.services import create_user

def endpoint():
    return create_user()
""",
        "app/services/__init__.py": """
from .user import create_user
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    edges = output.depends_edges

    assert any(
        edge.source_function == "endpoint"
        and edge.target_function == "create_user"
        for edge in edges
    )

    dependency = next(
        (
            d
            for d in output.dependencies
            if d.source_file == "app/main.py"
        ),
        None,
    )

    assert dependency is not None


def test_reexported_symbol_does_not_create_fake_function():
    files = {
        "app/main.py": """
from app.services import create_user

def endpoint():
    return create_user()
""",
        "app/services/__init__.py": """
from .user import create_user
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    symbols = [
        (f.file, fn.name)
        for f in output.files
        for fn in f.functions
    ]

    # create_user should belong to the actual implementation file.
    assert ("app/services/user.py", "create_user") in symbols

    # The import/re-export file must not fabricate another implementation.
    assert symbols.count(("app/services/__init__.py", "create_user")) == 0


def test_wildcard_import_does_not_create_fake_internal_dependency():
    files = {
        "app/main.py": """
from app.services.user import *

def endpoint():
    return create_user()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    # This test intentionally defines the desired contract:
    # wildcard imports should either resolve correctly or remain unresolved,
    # but must never point at an unrelated symbol.
    edges = output.depends_edges

    for edge in edges:
        if edge.source_function == "endpoint":
            assert edge.target_function == "create_user"


def test_unresolved_internal_import_is_not_marked_external_when_file_exists():
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

    output = process_project(make_profile(), files, "")

    deps = [
        d
        for d in output.dependencies
        if d.source_file == "app/main.py"
    ]

    matching = [
        d
        for d in deps
        if "app.services.user" in d.target_module
    ]

    assert matching

    # A project-local module should resolve as INTERNAL.
    assert any(d.kind == "INTERNAL" for d in matching)


def test_missing_project_module_is_external():
    files = {
        "app/main.py": """
from third_party.client import Client

def endpoint():
    return Client()
""",
    }

    output = process_project(make_profile(), files, "")

    deps = [
        d
        for d in output.dependencies
        if d.source_file == "app/main.py"
    ]

    matching = [
        d
        for d in deps
        if "third_party.client" in d.target_module
    ]

    assert matching
    assert all(d.kind == "EXTERNAL" for d in matching)


def test_imported_alias_keeps_real_target_identity():
    files = {
        "app/main.py": """
from app.services.user import create_user as make_user

def endpoint():
    return make_user()
""",
        "app/services/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    edges = output.depends_edges

    assert any(
        edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
        and edge.target_file == "app/services/user.py"
        and edge.target_function == "create_user"
        for edge in edges
    )


def test_two_aliases_to_same_function_do_not_duplicate_dependency_edges():
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

    output = process_project(make_profile(), files, "")

    matching = [
        edge
        for edge in output.depends_edges
        if edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
        and edge.target_file == "app/services/user.py"
        and edge.target_function == "create_user"
    ]

    # Multiple references to the same target should represent one graph edge.
    assert len(matching) == 1


def test_dependency_direction_is_caller_to_callee():
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

    output = process_project(make_profile(), files, "")

    edges = output.depends_edges

    assert any(
        edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
        and edge.target_file == "app/services/user.py"
        and edge.target_function == "create_user"
        for edge in edges
    )

    assert not any(
        edge.source_file == "app/services/user.py"
        and edge.source_function == "create_user"
        and edge.target_file == "app/main.py"
        and edge.target_function == "endpoint"
        for edge in edges
    )


def test_same_module_local_call_is_not_confused_with_imported_symbol():
    files = {
        "app/main.py": """
from app.other import process

def process():
    pass

def endpoint():
    return process()
""",
        "app/other.py": """
def process():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    edges = output.depends_edges

    endpoint_edges = [
        edge
        for edge in edges
        if edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
    ]

    assert any(
        edge.target_file == "app/main.py"
        and edge.target_function == "process"
        for edge in endpoint_edges
    )

    assert not any(
        edge.target_file == "app/other.py"
        and edge.target_function == "process"
        for edge in endpoint_edges
    )


def test_circular_dependency_graph_remains_finite():
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

    output = process_project(make_profile(), files, "")

    edges = output.depends_edges

    assert any(
        edge.source_file == "app/a.py"
        and edge.target_file == "app/b.py"
        for edge in edges
    )

    assert any(
        edge.source_file == "app/b.py"
        and edge.target_file == "app/a.py"
        for edge in edges
    )

    # Most importantly, processing must terminate and produce a finite graph.
    assert len(edges) < 10