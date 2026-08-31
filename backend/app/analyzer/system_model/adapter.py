from pathlib import Path
from typing import Dict, Any, List

from app.schemas.project import ProjectProfile, SystemModelOutput, FileModel, RequirementModel
from app.analyzer.code_analyzer.python_parser import parse_python_code
from app.analyzer.code_analyzer.js_ts_parser import parse_js_ts_code
from app.analyzer.requirement_analyzer.requirement_parser import parse_requirements_text
from app.analyzer.dependency_analyzer.dependency_mapper import map_dependencies, map_depends_edges
from app.analyzer.dependency_analyzer.relationship_mapper import (
    map_code_to_requirements,
    map_code_to_tests,
)


def process_project(
    profile_json: Dict[str, Any],
    file_contents: Dict[str, str],
    raw_requirements: str,
) -> SystemModelOutput:
    """
    Main entry point for Module 2.

    Accepts:
        profile_json    – shallow JSON from Module 1 (Profiler).  Used only
                          for project_id; Module 2 re-derives everything else.
        file_contents   – {relative_path: source_code} for every file to analyse.
        raw_requirements – raw requirements text (any format).

    Returns a fully-populated SystemModelOutput ready for Module 3 ingestion.
    """
    profile = ProjectProfile(**profile_json)

    # ── 1. Parse every source file ─────────────────────────────────────────
    files: List[FileModel] = []
    for filepath, content in file_contents.items():
        ext = Path(filepath).suffix.lower()
        if ext == ".py":
            files.append(parse_python_code(content, filepath))
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            lang_map = {".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx", ".js": "javascript"}
            files.append(parse_js_ts_code(content, filepath, lang_map[ext]))

    # ── 2. Parse requirements ──────────────────────────────────────────────
    requirements: List[RequirementModel] = (
        parse_requirements_text(raw_requirements) if raw_requirements else []
    )

    # ── 3. Dependency / relationship mapping ───────────────────────────────
    dependencies  = map_dependencies(files)
    depends_edges = map_depends_edges(files)
    code_req_links = map_code_to_requirements(files, requirements)
    code_test_links = map_code_to_tests(files)

    return SystemModelOutput(
        project_id=profile.project_id,
        files=files,
        requirements=requirements,
        dependencies=dependencies,
        depends_edges=depends_edges,
        code_requirement_links=code_req_links,
        code_test_links=code_test_links,
    )


# ── Local smoke-test ────────────────────────────────────────────────────────

def test_local_adapter():
    """Mock end-to-end test for local development."""

    mock_profile = {
        "project_id": "test_project_123",
        "project_type": "web_api",
        "languages": ["python", "javascript"],
        "frameworks": ["fastapi", "react"],
    }

    mock_python = """\
from fastapi import FastAPI, Depends
from app.models.user import UserModel

app = FastAPI()

def get_db():
    pass

class UserService:
    def create_user(self): pass
    def list_users(self): pass

@app.get("/users")
def list_users(db=Depends(get_db)):
    return []

@app.post("/users")
def create_user(db=Depends(get_db)):
    return {}
"""

    mock_react = """\
import React, { useState } from 'react';
import axios from 'axios';
import { UserService } from '../services/user';

class ErrorBoundary extends React.Component {
    render() {}
}

const UserList = () => {
    const [users, setUsers] = useState([]);
    const fetchUsers = () => {
        axios.get('/users').then(res => setUsers(res.data));
    }
    return <div>List</div>
}
"""

    mock_test = """\
import pytest
from app.services.user import UserService

def test_create_user():
    svc = UserService()
    assert svc.create_user() is not None

def test_list_users():
    svc = UserService()
    assert isinstance(svc.list_users(), list)
"""

    mock_reqs = """\
User Listing
The system must list all users from the database.
Acceptance Criteria:
- Fetches from /users endpoint
- Displays a table of user records

User Creation
The system shall allow creating new users.
Acceptance Criteria:
- Must accept name and email
- Returns 201 on success

Dashboard
The system shall provide a dashboard with stats.
Acceptance Criteria:
- Must show active user count
"""

    file_contents = {
        "backend/app/main.py": mock_python,
        "frontend/src/App.tsx": mock_react,
        "backend/tests/test_users.py": mock_test,
    }

    output = process_project(mock_profile, file_contents, mock_reqs)
    print(output.model_dump_json(indent=2))


if __name__ == "__main__":
    test_local_adapter()
