from app.analyzer.system_model.adapter import process_project


def test_fastapi_apirouter_routes():
    profile = {
        "project_id": "apirouter_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    code = """
from fastapi import APIRouter

router = APIRouter()

@router.get("/users")
def list_users():
    return []

@router.post("/users")
def create_user():
    return []
"""

    output = process_project(
        profile,
        {"app/routes/users.py": code},
        "",
    )

    routes = output.files[0].api_routes

    assert {
        (route.method, route.path, route.function_name)
        for route in routes
    } == {
        ("GET", "/users", "list_users"),
        ("POST", "/users", "create_user"),
    }




def test_fastapi_async_routes():
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

@app.post("/users")
async def create_user():
    return []
"""

    output = process_project(
        profile,
        {"app/main.py": code},
        "",
    )

    app_file = output.files[0]

    # Async functions must be extracted.
    function_names = {
        function.name
        for function in app_file.functions
    }

    assert "list_users" in function_names
    assert "create_user" in function_names

    # Async FastAPI functions must still produce API routes.
    routes = {
        (route.method, route.path, route.function_name)
        for route in app_file.api_routes
    }

    assert routes == {
        ("GET", "/users", "list_users"),
        ("POST", "/users", "create_user"),
    }



def test_internal_import_resolves_to_file():
    profile = {
        "project_id": "import_resolution_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/main.py": """
from app.services.user import UserService

def main():
    service = UserService()
""",
        "app/services/user.py": """
class UserService:
    def create_user(self):
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
        if dependency.target_module in {
            "app.services.user",
            "app.services.user.UserService",
        }
    ]

    assert internal, "Internal import was not detected"

    # It must resolve to the actual project file.
    assert any(
        dependency.resolved_file == "app/services/user.py"
        for dependency in internal
    )

    # It must not be classified as external.
    assert all(
        dependency.kind == "INTERNAL"
        for dependency in internal
    )


def test_duplicate_function_names_keep_file_identity():
    profile = {
        "project_id": "symbol_identity_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def create_user():
    pass
""",
        "app/admin.py": """
def create_user():
    pass
""",
    }

    output = process_project(
        profile,
        files,
        "",
    )

    # Both functions must be represented.
    symbols = []

    for file in output.files:
        for function in file.functions:
            if function.name == "create_user":
                symbols.append(
                    (file.file, function.name)
                )

    assert len(symbols) == 2

    assert ("app/users.py", "create_user") in symbols
    assert ("app/admin.py", "create_user") in symbols




def test_duplicate_function_names_do_not_cross_link_requirements():
    profile = {
        "project_id": "symbol_identity_requirements",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def create_user():
    pass
""",
        "app/admin.py": """
def create_user():
    pass
""",
    }

    requirements = """
User Creation

The system must allow users to create accounts.

Acceptance Criteria:

- Accepts name and email

Admin Creation

The system must allow administrators to create admin accounts.

Acceptance Criteria:

- Requires administrator privileges
"""

    output = process_project(
        profile,
        files,
        requirements,
    )

    links = output.code_requirement_links

    create_links = [
        link
        for link in links
        if link.symbol == "create_user"
    ]

    # We should be able to distinguish the two
    # create_user implementations by their file.
    files_with_links = {
        link.file
        for link in create_links
    }

    assert "app/users.py" in files_with_links
    assert "app/admin.py" in files_with_links




def test_requirement_matching_avoids_similar_requirement_false_positives():
    profile = {
        "project_id": "requirement_matching_project",
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

    links = output.code_requirement_links

    def symbols_for(req_id):
        return {
            link.symbol
            for link in links
            if link.requirement_id == req_id
        }

    listing = symbols_for("REQ-001")
    search = symbols_for("REQ-002")
    deletion = symbols_for("REQ-003")

    # Strong positive matches.
    assert "list_users" in listing
    assert "search_users" in search
    assert "delete_user" in deletion

    # Prevent cross-requirement false positives.
    assert "search_users" not in listing
    assert "delete_user" not in listing

    assert "list_users" not in search
    assert "delete_user" not in search

    assert "list_users" not in deletion
    assert "search_users" not in deletion