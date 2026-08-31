from pathlib import Path
from typing import Dict, Any, List
from app.schemas.project import ProjectProfile, SystemModelOutput, FileModel, RequirementModel
from app.analyzer.code_analyzer.python_parser import parse_python_code
from app.analyzer.code_analyzer.js_ts_parser import parse_js_ts_code
from app.analyzer.requirement_analyzer.requirement_parser import parse_requirements_text

def process_project(profile_json: Dict[str, Any], file_contents: Dict[str, str], raw_requirements: str) -> SystemModelOutput:
    """
    Main entry point for Module 2.
    """
    profile = ProjectProfile(**profile_json)
    
    files: List[FileModel] = []
    
    # Process files — path can be relative, absolute, or deeply nested.
    # Path(filename).suffix extracts the extension correctly for any format.
    for filepath, content in file_contents.items():
        ext = Path(filepath).suffix.lower()
        if ext == '.py':
            files.append(parse_python_code(content, filepath))
        elif ext in ('.js', '.jsx', '.ts', '.tsx'):
            lang_map = {'.ts': 'typescript', '.tsx': 'tsx', '.jsx': 'jsx', '.js': 'javascript'}
            lang = lang_map[ext]
            files.append(parse_js_ts_code(content, filepath, lang))
            
    # Process requirements
    requirements = parse_requirements_text(raw_requirements) if raw_requirements else []

    output = SystemModelOutput(
        project_id=profile.project_id,
        files=files,
        requirements=requirements
    )

    return output

def test_local_adapter():
    """Mock testing for local development."""
    mock_profile = {
        "project_id": "test_project_123",
        "project_type": "web_api",
        "languages": ["python", "javascript"],
        "frameworks": ["fastapi", "react"]
    }
    
    mock_python = """
from fastapi import FastAPI, Depends
app = FastAPI()

def get_db(): pass

class User:
    def get_name(self): pass

@app.get("/users")
def list_users(db = Depends(get_db)):
    return []
"""
    
    mock_react = """
import React, { useState } from 'react';
import axios from 'axios';

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

    # Module 2 always generates REQ-XXX IDs regardless of document format
    mock_reqs = """
User Listing
The system must list all users.
Acceptance Criteria:
- Fetches from /users
- Displays a table

Dashboard
The system shall provide a dashboard.
Acceptance Criteria:
- Must show stats
"""

    file_contents = {
        "backend/app/main.py": mock_python,
        "frontend/src/App.tsx": mock_react
    }

    output = process_project(mock_profile, file_contents, mock_reqs)
    print(output.model_dump_json(indent=2))

if __name__ == "__main__":
    test_local_adapter()





