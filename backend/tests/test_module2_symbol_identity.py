"""
High-level symbol identity tests.

These tests verify that Module 2 keeps symbols unique and correctly scoped
before the model is persisted into Neo4j.

Run:

    python -m pytest tests/test_module2_symbol_identity.py -v
"""

from app.analyzer.system_model.adapter import process_project


def _process(files, requirements=""):
    profile = {
        "project_id": "symbol_identity_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    return process_project(profile, files, requirements)


def _edges(output):
    return output.depends_edges


# ---------------------------------------------------------------------------
# 1. Same method name in different classes.
# ---------------------------------------------------------------------------

def test_same_method_name_in_different_classes_keeps_class_identity():
    files = {
        "app/services.py": """
class UserService:
    def create(self):
        pass


class AdminService:
    def create(self):
        pass


def endpoint():
    user = UserService()
    admin = AdminService()

    user.create()
    admin.create()
"""
    }

    output = _process(files)

    functions = [
        function
        for file in output.files
        for function in file.functions
    ]

    # Top-level endpoint should exist.
    assert any(
        function.name == "endpoint"
        for function in functions
    )

    # Class methods must not collapse into one generic "create".
    service_file = next(
        file for file in output.files
        if file.file == "app/services.py"
    )

    assert any(
        cls.name == "UserService"
        and "create" in cls.methods
        for cls in service_file.classes
    )

    assert any(
        cls.name == "AdminService"
        and "create" in cls.methods
        for cls in service_file.classes
    )


# ---------------------------------------------------------------------------
# 2. Same method name in different files.
# ---------------------------------------------------------------------------

def test_same_method_name_in_different_files_keeps_file_identity():
    files = {
        "app/users.py": """
class UserService:
    def create(self):
        pass
""",
        "app/orders.py": """
class OrderService:
    def create(self):
        pass
""",
        "app/main.py": """
from app.users import UserService
from app.orders import OrderService

def endpoint():
    UserService().create()
    OrderService().create()
""",
    }

    output = _process(files)

    service_files = {
        file.file
        for file in output.files
        if any(
            cls.name in {"UserService", "OrderService"}
            for cls in file.classes
        )
    }

    assert service_files == {
        "app/users.py",
        "app/orders.py",
    }


# ---------------------------------------------------------------------------
# 3. Class methods should use fully qualified identity where required.
# ---------------------------------------------------------------------------

def test_class_method_symbol_identity_is_fully_qualified():
    files = {
        "app/users.py": """
class UserService:
    def create(self):
        pass

    def delete(self):
        pass
"""
    }

    requirements = """
User Creation

The system must create users.

Acceptance Criteria:

- Creates a new user


User Deletion

The system must delete users.

Acceptance Criteria:

- Deletes a user
"""

    output = _process(files, requirements)

    links = output.code_requirement_links

    symbols = {
        link.symbol
        for link in links
    }

    # If class identity is represented in links, it must remain distinct.
    assert any(
        symbol.endswith("create")
        and "UserService" in symbol
        for symbol in symbols
    )

    assert any(
        symbol.endswith("delete")
        and "UserService" in symbol
        for symbol in symbols
    )


# ---------------------------------------------------------------------------
# 4. Two classes with identical method names must not cross-link requirements.
# ---------------------------------------------------------------------------

def test_identical_class_methods_do_not_cross_link_requirements():
    files = {
        "app/services.py": """
class UserService:
    def create(self):
        pass


class ProductService:
    def create(self):
        pass
"""
    }

    requirements = """
User Creation

The system must create a user.

Acceptance Criteria:

- Creates a user account


Product Creation

The system must create a product.

Acceptance Criteria:

- Creates a product
"""

    output = _process(files, requirements)

    user_links = {
        link.symbol
        for link in output.code_requirement_links
        if link.requirement_id == "REQ-001"
    }

    product_links = {
        link.symbol
        for link in output.code_requirement_links
        if link.requirement_id == "REQ-002"
    }

    # At least the semantically relevant implementation should be present.
    # More importantly, an implementation must not be represented only by
    # an ambiguous generic "create" identity.
    assert "create" not in user_links
    assert "create" not in product_links


# ---------------------------------------------------------------------------
# 5. Route -> service class method dependency.
# ---------------------------------------------------------------------------

def test_route_to_class_method_dependency_preserves_identity():
    files = {
        "app/main.py": """
from app.services import UserService

def get_users():
    service = UserService()
    return service.list_users()
""",
        "app/services.py": """
class UserService:
    def list_users(self):
        return []
""",
    }

    output = _process(files)

    edges = _edges(output)

    matching = [
        edge
        for edge in edges
        if edge.source_function == "get_users"
    ]

    assert matching

    assert any(
        edge.target_function == "UserService.list_users"
        or (
            edge.target_function == "list_users"
            and edge.target_file == "app/services.py"
        )
        for edge in matching
    )


# ---------------------------------------------------------------------------
# 6. Class method -> repository method.
# ---------------------------------------------------------------------------

def test_class_method_dependency_chain_preserves_both_symbols():
    files = {
        "app/services.py": """
from app.repositories import UserRepository


class UserService:
    def create(self):
        repository = UserRepository()
        return repository.save()
""",
        "app/repositories.py": """
class UserRepository:
    def save(self):
        return True
""",
    }

    output = _process(files)

    edges = _edges(output)

    assert any(
        edge.target_function in {
            "UserRepository.save",
            "save",
        }
        and edge.target_file == "app/repositories.py"
        for edge in edges
    )


# ---------------------------------------------------------------------------
# 7. Static methods should retain class identity.
# ---------------------------------------------------------------------------

def test_static_method_keeps_class_identity():
    files = {
        "app/users.py": """
class UserService:
    @staticmethod
    def normalize_email(email):
        return email.lower()
"""
    }

    output = _process(files)

    service_file = next(
        file for file in output.files
        if file.file == "app/users.py"
    )

    user_service = next(
        cls
        for cls in service_file.classes
        if cls.name == "UserService"
    )

    assert "normalize_email" in user_service.methods


# ---------------------------------------------------------------------------
# 8. Classmethod should retain class identity.
# ---------------------------------------------------------------------------

def test_classmethod_keeps_class_identity():
    files = {
        "app/users.py": """
class UserService:
    @classmethod
    def from_email(cls, email):
        return cls()
"""
    }

    output = _process(files)

    service_file = next(
        file for file in output.files
        if file.file == "app/users.py"
    )

    user_service = next(
        cls
        for cls in service_file.classes
        if cls.name == "UserService"
    )

    assert "from_email" in user_service.methods


# ---------------------------------------------------------------------------
# 9. Nested classes should not collide with outer class methods.
# ---------------------------------------------------------------------------

def test_nested_class_methods_do_not_collide():
    files = {
        "app/services.py": """
class OuterService:
    def process(self):
        pass

    class InnerService:
        def process(self):
            pass
"""
    }

    output = _process(files)

    service_file = next(
        file for file in output.files
        if file.file == "app/services.py"
    )

    outer = next(
        cls
        for cls in service_file.classes
        if cls.name == "OuterService"
    )

    assert "process" in outer.methods

    # The analyzer should not create a duplicate top-level function.
    top_level_names = {
        function.name
        for function in service_file.functions
    }

    assert "process" not in top_level_names


# ---------------------------------------------------------------------------
# 10. Same function name + different files must produce independent nodes.
# ---------------------------------------------------------------------------

def test_duplicate_functions_have_unique_graph_identity():
    files = {
        "app/a.py": """
def process():
    pass
""",
        "app/b.py": """
def process():
    pass
""",
    }

    output = _process(files)

    process_locations = [
        file.file
        for file in output.files
        for function in file.functions
        if function.name == "process"
    ]

    assert process_locations == [
        "app/a.py",
        "app/b.py",
    ]


# ---------------------------------------------------------------------------
# 11. Requirement links must not depend only on generic method names.
# ---------------------------------------------------------------------------

def test_generic_method_names_do_not_create_requirement_collision():
    files = {
        "app/services.py": """
class UserService:
    def process(self):
        pass


class PaymentService:
    def process(self):
        pass
"""
    }

    requirements = """
User Processing

The system must process user registration.

Acceptance Criteria:

- Validates and registers users


Payment Processing

The system must process customer payments.

Acceptance Criteria:

- Charges the customer's payment method
"""

    output = _process(files, requirements)

    user_links = {
        link.symbol
        for link in output.code_requirement_links
        if link.requirement_id == "REQ-001"
    }

    payment_links = {
        link.symbol
        for link in output.code_requirement_links
        if link.requirement_id == "REQ-002"
    }

    # Generic "process" alone is not enough evidence.
    assert "process" not in user_links
    assert "process" not in payment_links


# ---------------------------------------------------------------------------
# 12. Analysis must be deterministic for graph persistence.
# ---------------------------------------------------------------------------

def test_symbol_identity_is_deterministic():
    files = {
        "app/a.py": """
class UserService:
    def create(self):
        pass

def list_users():
    pass
""",
        "app/b.py": """
class AdminService:
    def create(self):
        pass

def list_users():
    pass
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