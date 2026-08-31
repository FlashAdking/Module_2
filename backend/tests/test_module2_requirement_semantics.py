from app.analyzer.system_model.adapter import process_project


def _links_for(output, requirement_id):
    return {
        link.symbol
        for link in output.code_requirement_links
        if link.requirement_id == requirement_id
    }


def test_generic_function_names_do_not_create_false_positive_links():
    profile = {
        "project_id": "generic_names_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def process():
    pass

def handle():
    pass

def create():
    pass

def delete_user():
    pass
""",
    }

    requirements = """
User Deletion
The system must allow administrators to delete users.
Acceptance Criteria:
- Deletes a selected user
"""

    output = process_project(profile, files, requirements)

    deletion = _links_for(output, "REQ-001")

    assert "delete_user" in deletion

    assert "process" not in deletion
    assert "handle" not in deletion
    assert "create" not in deletion


def test_create_user_does_not_match_user_deletion():
    profile = {
        "project_id": "create_delete_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def create_user():
    pass

def delete_user():
    pass
""",
    }

    requirements = """
User Creation
The system shall allow creating new users.
Acceptance Criteria:
- Must accept name and email

User Deletion
The system shall allow administrators to delete users.
Acceptance Criteria:
- Deletes a selected user
"""

    output = process_project(profile, files, requirements)

    creation = _links_for(output, "REQ-001")
    deletion = _links_for(output, "REQ-002")

    assert "create_user" in creation
    assert "delete_user" not in creation

    assert "delete_user" in deletion
    assert "create_user" not in deletion


def test_update_and_delete_are_not_treated_as_same_operation():
    profile = {
        "project_id": "update_delete_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def update_user():
    pass

def delete_user():
    pass
""",
    }

    requirements = """
User Update
The system shall allow users to update their profile.
Acceptance Criteria:
- Changes the user's email address

User Deletion
The system shall allow administrators to delete users.
Acceptance Criteria:
- Permanently removes the selected user
"""

    output = process_project(profile, files, requirements)

    update = _links_for(output, "REQ-001")
    deletion = _links_for(output, "REQ-002")

    assert "update_user" in update
    assert "delete_user" not in update

    assert "delete_user" in deletion
    assert "update_user" not in deletion


def test_acceptance_criteria_can_identify_implementation():
    profile = {
        "project_id": "acceptance_criteria_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def export_users_csv():
    pass

def unrelated_function():
    pass
""",
    }

    requirements = """
User Export
The system shall allow exporting users.
Acceptance Criteria:
- Exports all user records as CSV
"""

    output = process_project(profile, files, requirements)

    links = _links_for(output, "REQ-001")

    assert "export_users_csv" in links
    assert "unrelated_function" not in links


def test_unrelated_generic_function_is_not_linked_when_requirement_is_specific():
    profile = {
        "project_id": "specific_requirement_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/orders.py": """
def process():
    pass

def handle():
    pass

def calculate_order_total():
    pass
""",
    }

    requirements = """
Order Total Calculation
The system must calculate the total price of an order.
Acceptance Criteria:
- Includes item prices
- Includes applicable tax
"""

    output = process_project(profile, files, requirements)

    links = _links_for(output, "REQ-001")

    assert "calculate_order_total" in links
    assert "process" not in links
    assert "handle" not in links


def test_one_function_can_match_multiple_genuinely_related_requirements():
    profile = {
        "project_id": "multi_requirement_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def list_users():
    pass
""",
    }

    requirements = """
User Listing
The system must list all users.
Acceptance Criteria:
- Returns all users

User Search
The system must allow searching the user database.
Acceptance Criteria:
- Searches users by name
"""

    output = process_project(profile, files, requirements)

    listing = _links_for(output, "REQ-001")
    search = _links_for(output, "REQ-002")

    assert "list_users" in listing

    # Listing and searching are semantically different.
    # A function should not be linked to Search merely because
    # both requirements contain the word "users".
    assert "list_users" not in search


def test_implementation_without_requirement_is_not_forced_into_a_link():
    profile = {
        "project_id": "unmatched_implementation_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def list_users():
    pass

def export_users():
    pass
""",
    }

    requirements = """
User Listing
The system must list all users.
Acceptance Criteria:
- Returns all users
"""

    output = process_project(profile, files, requirements)

    listing = _links_for(output, "REQ-001")

    assert "list_users" in listing
    assert "export_users" not in listing


def test_requirement_without_implementation_has_no_links():
    profile = {
        "project_id": "missing_implementation_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def list_users():
    pass
""",
    }

    requirements = """
User Listing
The system must list all users.
Acceptance Criteria:
- Returns all users

User Analytics Dashboard
The system must show active users and monthly growth.
Acceptance Criteria:
- Displays active user count
- Displays monthly growth
"""

    output = process_project(profile, files, requirements)

    dashboard = _links_for(output, "REQ-002")

    assert dashboard == set()


def test_similar_requirement_words_do_not_override_operation_semantics():
    profile = {
        "project_id": "operation_semantics_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def create_user():
    pass

def update_user():
    pass

def delete_user():
    pass
""",
    }

    requirements = """
Create User
The system must create a new user.
Acceptance Criteria:
- Accepts name and email

Update User
The system must update an existing user.
Acceptance Criteria:
- Changes user information

Delete User
The system must delete an existing user.
Acceptance Criteria:
- Removes the user permanently
"""

    output = process_project(profile, files, requirements)

    create_links = _links_for(output, "REQ-001")
    update_links = _links_for(output, "REQ-002")
    delete_links = _links_for(output, "REQ-003")

    assert "create_user" in create_links
    assert "update_user" not in create_links
    assert "delete_user" not in create_links

    assert "update_user" in update_links
    assert "create_user" not in update_links
    assert "delete_user" not in update_links

    assert "delete_user" in delete_links
    assert "create_user" not in delete_links
    assert "update_user" not in delete_links


def test_test_functions_do_not_match_specific_requirements():
    profile = {
        "project_id": "test_symbol_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
def delete_user():
    pass
""",
        "tests/test_users.py": """
def test_delete_user():
    pass
""",
    }

    requirements = """
User Deletion
The system shall allow deleting users.
Acceptance Criteria:
- Removes the selected user
"""

    output = process_project(profile, files, requirements)

    links = output.code_requirement_links

    production_symbols = {
        link.symbol
        for link in links
        if not link.file.startswith("tests/")
    }

    test_symbols = {
        link.symbol
        for link in links
        if link.file.startswith("tests/")
    }

    assert "delete_user" in production_symbols
    assert test_symbols == set()


def test_class_method_identity_is_used_for_requirement_matching():
    profile = {
        "project_id": "class_identity_project",
        "project_type": "web_api",
        "languages": ["python"],
        "frameworks": ["fastapi"],
    }

    files = {
        "app/users.py": """
class UserService:
    def create_user(self):
        pass

    def delete_user(self):
        pass
""",
    }

    requirements = """
User Creation
The system shall allow creating users.
Acceptance Criteria:
- Creates a new user

User Deletion
The system shall allow deleting users.
Acceptance Criteria:
- Removes an existing user
"""

    output = process_project(profile, files, requirements)

    creation = _links_for(output, "REQ-001")
    deletion = _links_for(output, "REQ-002")

    assert (
        "UserService.create_user" in creation
        or "create_user" in creation
    )

    assert (
        "UserService.delete_user" in deletion
        or "delete_user" in deletion
    )

    assert "UserService.delete_user" not in creation
    assert "UserService.create_user" not in deletion