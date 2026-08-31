from app.analyzer.system_model.adapter import process_project


def make_profile():
    return {
        "project_id": "critical_graph_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }


def find_edges(output, source_file, source_function):
    return [
        edge
        for edge in output.depends_edges
        if edge.source_file == source_file
        and edge.source_function == source_function
    ]


def test_critical_chained_import_resolves_each_real_file():
    """
    A -> B -> C must remain A -> B and B -> C.
    The analyzer must not collapse the chain or lose file identity.
    """
    files = {
        "app/main.py": """
from app.service import run

def endpoint():
    return run()
""",
        "app/service.py": """
from app.repository import fetch

def run():
    return fetch()
""",
        "app/repository.py": """
def fetch():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    assert any(
        edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
        and edge.target_file == "app/service.py"
        and edge.target_function == "run"
        for edge in output.depends_edges
    )

    assert any(
        edge.source_file == "app/service.py"
        and edge.source_function == "run"
        and edge.target_file == "app/repository.py"
        and edge.target_function == "fetch"
        for edge in output.depends_edges
    )


def test_critical_same_named_functions_never_cross_files():
    """
    Same function names are different graph nodes when they live
    in different files.
    """
    files = {
        "app/main.py": """
from app.a import process as process_a
from app.b import process as process_b

def endpoint():
    process_a()
    process_b()
""",
        "app/a.py": """
def process():
    pass
""",
        "app/b.py": """
def process():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    endpoint_edges = find_edges(output, "app/main.py", "endpoint")

    targets = {
        (edge.target_file, edge.target_function)
        for edge in endpoint_edges
    }

    assert ("app/a.py", "process") in targets
    assert ("app/b.py", "process") in targets

    # The analyzer must not invent a dependency to the wrong file.
    assert all(
        edge.target_function != "process"
        or edge.target_file in {"app/a.py", "app/b.py"}
        for edge in endpoint_edges
    )


def test_critical_alias_keeps_real_symbol_identity():
    """
    An imported alias must still resolve to the original function.
    """
    files = {
        "app/main.py": """
from app.user import create_user as register

def endpoint():
    return register()
""",
        "app/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    assert any(
        edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
        and edge.target_file == "app/user.py"
        and edge.target_function == "create_user"
        for edge in output.depends_edges
    )


def test_critical_unused_import_does_not_create_dependency():
    """
    Importing a symbol is not enough.
    A graph edge should represent an actual dependency.
    """
    files = {
        "app/main.py": """
from app.user import create_user

def endpoint():
    pass
""",
        "app/user.py": """
def create_user():
    pass
""",
    }

    output = process_project(make_profile(), files, "")

    assert not any(
        edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
        and edge.target_file == "app/user.py"
        and edge.target_function == "create_user"
        for edge in output.depends_edges
    )


def test_critical_missing_module_never_becomes_fake_internal_dependency():
    """
    If an imported project module does not exist, the analyzer must
    not invent a function/file node for it.
    """
    files = {
        "app/main.py": """
from app.missing import process

def endpoint():
    return process()
""",
    }

    output = process_project(make_profile(), files, "")

    assert not any(
        edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
        and edge.target_file == "app/missing.py"
        for edge in output.depends_edges
    )

    assert not any(
        edge.target_file == "app/missing.py"
        for edge in output.depends_edges
    )


def test_critical_class_method_identity_is_preserved():
    """
    Class.method must remain distinct from another class.method.
    """
    files = {
        "app/main.py": """
from app.services import UserService, AdminService

def endpoint():
    UserService.process()
    AdminService.process()
""",
        "app/services.py": """
class UserService:
    @staticmethod
    def process():
        pass


class AdminService:
    @staticmethod
    def process():
        pass
""",
    }

    output = process_project(make_profile(), files, "")

    symbols = {
        (edge.target_file, edge.target_function)
        for edge in output.depends_edges
        if edge.source_file == "app/main.py"
        and edge.source_function == "endpoint"
    }

    assert (
        "app/services.py",
        "UserService.process",
    ) in symbols

    assert (
        "app/services.py",
        "AdminService.process",
    ) in symbols


def test_critical_duplicate_edges_are_collapsed():
    """
    Different aliases pointing to the same target must produce
    exactly one graph edge.
    """
    files = {
        "app/main.py": """
from app.user import create_user
from app.user import create_user as register

def endpoint():
    create_user()
    register()
""",
        "app/user.py": """
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
        and edge.target_file == "app/user.py"
        and edge.target_function == "create_user"
    ]

    assert len(matching) == 1


def test_critical_circular_dependencies_remain_finite_and_identity_safe():
    """
    Circular imports must terminate and retain correct file identity.
    """
    files = {
        "app/a.py": """
from app.b import process_b

def process_a():
    return process_b()
""",
        "app/b.py": """
from app.a import process_a

def process_b():
    return process_a()
""",
    }

    output = process_project(make_profile(), files, "")

    edges = output.depends_edges

    assert any(
        edge.source_file == "app/a.py"
        and edge.source_function == "process_a"
        and edge.target_file == "app/b.py"
        and edge.target_function == "process_b"
        for edge in edges
    )

    assert any(
        edge.source_file == "app/b.py"
        and edge.source_function == "process_b"
        and edge.target_file == "app/a.py"
        and edge.target_function == "process_a"
        for edge in edges
    )

    # Most importantly: cycle handling must not explode into
    # duplicate/infinite edges.
    assert len(edges) <= 2