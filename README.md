# CodeSentinel — Module 2: System Model

Module 2 analyzes a project's source code and requirements to produce a structured system model.

The main entry point is located at:
`backend/app/analyzer/system_model/adapter.py`

Consumers only need to interact with the `process_project()` function.

---

##  Module Structure

```bash
codesentinel/
├── backend
│   ├── app
│   │   ├── analyzer
│   │   │   ├── code_analyzer
│   │   │   │   ├── custom_ast_parser.py
│   │   │   │   ├── __init__.py
│   │   │   │   ├── js_ts_parser.py
│   │   │   │   ├── python_ast.py
│   │   │   │   ├── python_parser.py
│   │   │   │   └── tests
│   │   │   ├── dependency_analyzer
│   │   │   │   ├── dependency_mapper.py
│   │   │   │   └── relationship_mapper.py
│   │   │   ├── requirement_analyzer
│   │   │   │   └── requirement_parser.py
│   │   │   └── system_model
│   │   │       └── adapter.py  # (entry point for module 2 )
│   │   └── schemas
│   │       └── project.py  # (all pydentic models i have used)
│   └── tests
│       ├── test_analyzers.py
│       ├── test_module2_acceptance.py
│       ├── test_module2_critical_graph.py
│       ├── test_module2_dependencies.py
│       ├── test_module2_dependency_real_world.py
│       ├── test_module2_dependency_semantics.py
│       ├── test_module2_edge_cases.py
│       ├── test_module2_graph_invariants.py
│       ├── test_module2_import_edge_cases.py
│       ├── test_module2_integration.py
│       ├── test_module2_real_world.py
│       ├── test_module2_requirement_semantics.py
│       ├── test_module2_stress.py
│       └── test_module2_symbol_identity.py
├── .env
├── README.md
└── req.txt

11 directories, 26 files
```

---

## Input

To generate the system model, call `process_project()` with three inputs:

```python
from app.analyzer.system_model.adapter import process_project

process_project(
    profile_json,
    file_contents,
    raw_requirements
)
```

### 1. `profile_json`
Contains the core project metadata.

```json
{
    "project_id": "P001",
    "project_type": "web_api",
    "languages": ["Python", "TypeScript"],
    "frameworks": ["FastAPI", "React"],
    "dependencies": [],
    "apis": [],
    "tests": [],
    "docker": true,
    "ci_cd": false
}
```

### 2. `file_contents`
A dictionary mapping file paths to their respective raw source code.

```python
file_contents = {
    "app/main.py": """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def list_users():
    return []
""",

    "src/App.tsx": """
import React from "react";

export const UserList = () => {
    return <div>List</div>;
};
"""
}
```

### 3. `raw_requirements`
Raw requirements text. Module 2 will automatically parse this and generate the `REQ-*` identifiers.

```text
User Listing
The system must list all users.
Acceptance Criteria:
- Fetches from /users
- Displays a table

Dashboard
The system shall provide a dashboard.
Acceptance Criteria:
- Must show stats
```

---

##  Output

`process_project()` returns a `SystemModelOutput` containing everything needed to map the system, including files, classes, methods, API routes, dependencies, and code-to-requirement mappings.

**Example Output:**

```json
// detailed AST ( functions , imports , apis , logix , etc)
{
  "project_id": "test_project_123",
  "files": [
    {
      "file": "backend/app/main.py",
      "language": "python",
      "classes": [
        {
          "name": "UserService",
          "methods": [
            "create_user",
            "list_users"
          ]
        }
      ],
      "functions": [
        {
          "name": "get_db",
          "arguments": [],
          "decorators": [],
          "depends_on": []
        },
        {
          "name": "UserService.create_user",
          "arguments": [
            "self"
          ],
          "decorators": [],
          "depends_on": []
        },
        {
          "name": "UserService.list_users",
          "arguments": [
            "self"
          ],
          "decorators": [],
          "depends_on": []
        },
        {
          "name": "list_users",
          "arguments": [
            "db"
          ],
          "decorators": [
            "app.get('/users')"
          ],
          "depends_on": [
            "get",
            "Depends",
            "get_db"
          ]
        },
        {
          "name": "create_user",
          "arguments": [
            "db"
          ],
          "decorators": [
            "app.post('/users')"
          ],
          "depends_on": [
            "Depends",
            "post",
            "get_db"
          ]
        }
      ],
      "api_routes": [
        {
          "method": "GET",
          "path": "/users",
          "function_name": "list_users"
        },
        {
          "method": "POST",
          "path": "/users",
          "function_name": "create_user"
        }
      ],
      "imports": [
        "fastapi.FastAPI",
        "fastapi.Depends",
        "app.models.user.UserModel"
      ]
    },
    {
      "file": "frontend/src/App.tsx",
      "language": "tsx",
      "classes": [
        {
          "name": "ErrorBoundary",
          "methods": [
            "render"
          ]
        }
      ],
      "functions": [
        {
          "name": "ErrorBoundary.render",
          "arguments": [],
          "decorators": [],
          "depends_on": []
        },
        {
          "name": "UserList",
          "arguments": [],
          "decorators": [],
          "depends_on": []
        },
        {
          "name": "fetchUsers",
          "arguments": [],
          "decorators": [],
          "depends_on": []
        }
      ],
      "api_routes": [],
      "imports": [
        "react",
        "axios",
        "../services/user"
      ]
    },
    {
      "file": "backend/tests/test_users.py",
      "language": "python",
      "classes": [],
      "functions": [
        {
          "name": "test_create_user",
          "arguments": [],
          "decorators": [],
          "depends_on": [
            "create_user",
            "UserService"
          ]
        },
        {
          "name": "test_list_users",
          "arguments": [],
          "decorators": [],
          "depends_on": [
            "isinstance",
            "list_users",
            "UserService"
          ]
        }
      ],
      "api_routes": [],
      "imports": [
        "pytest",
        "app.services.user.UserService"
      ]
    }
  ],
  "requirements": [
    {
      "requirement_id": "REQ-001",
      "title": "User Listing",
      "description": "The system must list all users from the database.",
      "acceptance_criteria": [
        "Fetches from /users endpoint",
        "Displays a table of user records"
      ]
    },
    {
      "requirement_id": "REQ-002",
      "title": "User Creation",
      "description": "The system shall allow creating new users.",
      "acceptance_criteria": [
        "Must accept name and email",
        "Returns 201 on success"
      ]
    },
    {
      "requirement_id": "REQ-003",
      "title": "Dashboard",
      "description": "The system shall provide a dashboard with stats.",
      "acceptance_criteria": [
        "Must show active user count"
      ]
    }
  ],
  "dependencies": [  
    {
      "source_file": "backend/app/main.py",
      "target_module": "fastapi.FastAPI",
      "kind": "EXTERNAL",
      "resolved_file": null
    },
    {
      "source_file": "backend/app/main.py",
      "target_module": "fastapi.Depends",
      "kind": "EXTERNAL",
      "resolved_file": null
    },
    {
      "source_file": "backend/app/main.py",
      "target_module": "app.models.user.UserModel",
      "kind": "EXTERNAL",
      "resolved_file": null
    },
    {
      "source_file": "frontend/src/App.tsx",
      "target_module": "react",
      "kind": "EXTERNAL",
      "resolved_file": null
    },
    {
      "source_file": "frontend/src/App.tsx",
      "target_module": "axios",
      "kind": "EXTERNAL",
      "resolved_file": null
    },
    {
      "source_file": "frontend/src/App.tsx",
      "target_module": "../services/user",
      "kind": "EXTERNAL",
      "resolved_file": null
    },
    {
      "source_file": "backend/tests/test_users.py",
      "target_module": "pytest",
      "kind": "EXTERNAL",
      "resolved_file": null
    },
    {
      "source_file": "backend/tests/test_users.py",
      "target_module": "app.services.user.UserService",
      "kind": "EXTERNAL",
      "resolved_file": null
    }
  ],
  "depends_edges": [
    {
      "source_file": "backend/app/main.py",
      "source_function": "list_users",
      "target_file": "backend/app/main.py",
      "target_function": "get_db"
    },
    {
      "source_file": "backend/app/main.py",
      "source_function": "create_user",
      "target_file": "backend/app/main.py",
      "target_function": "get_db"
    },
    {
      "source_file": "backend/tests/test_users.py",
      "source_function": "test_create_user",
      "target_file": "backend/app/main.py",
      "target_function": "create_user"
    },
    {
      "source_file": "backend/tests/test_users.py",
      "source_function": "test_list_users",
      "target_file": "backend/app/main.py",
      "target_function": "list_users"
    }
  ],
  "code_requirement_links": [
    {
      "file": "backend/app/main.py",
      "symbol": "UserService.create_user",
      "symbol_type": "function",
      "requirement_id": "REQ-002",
      "match_score": 0.533,
      "evidence": [
        "Symbol 'UserService.create_user' shares 2 token(s) with requirement title",
        "Symbol 'UserService.create_user' shares 2 token(s) with requirement text"
      ]
    },
    {
      "file": "backend/app/main.py",
      "symbol": "UserService.list_users",
      "symbol_type": "function",
      "requirement_id": "REQ-001",
      "match_score": 0.533,
      "evidence": [
        "Symbol 'UserService.list_users' shares 2 token(s) with requirement title",
        "Symbol 'UserService.list_users' shares 2 token(s) with requirement text"
      ]
    },
    {
      "file": "backend/app/main.py",
      "symbol": "list_users",
      "symbol_type": "function",
      "requirement_id": "REQ-001",
      "match_score": 1.0,
      "evidence": [
        "API path '/users' matches requirement text",
        "HTTP GET aligns with listing/fetching intent",
        "Symbol 'list_users' shares 2 token(s) with requirement title",
        "Symbol 'list_users' shares 2 token(s) with requirement text"
      ]
    },
    {
      "file": "backend/app/main.py",
      "symbol": "create_user",
      "symbol_type": "function",
      "requirement_id": "REQ-002",
      "match_score": 1.0,
      "evidence": [
        "API path '/users' matches requirement text",
        "HTTP POST aligns with creation/update intent",
        "Symbol 'create_user' shares 2 token(s) with requirement title",
        "Symbol 'create_user' shares 2 token(s) with requirement text"
      ]
    },
    {
      "file": "frontend/src/App.tsx",
      "symbol": "UserList",
      "symbol_type": "function",
      "requirement_id": "REQ-001",
      "match_score": 0.8,
      "evidence": [
        "Symbol 'UserList' shares 2 token(s) with requirement title",
        "Symbol 'UserList' shares 2 token(s) with requirement text"
      ]
    },
    {
      "file": "frontend/src/App.tsx",
      "symbol": "fetchUsers",
      "symbol_type": "function",
      "requirement_id": "REQ-001",
      "match_score": 0.6,
      "evidence": [
        "Symbol 'fetchUsers' shares 1 token(s) with requirement title",
        "Symbol 'fetchUsers' shares 2 token(s) with requirement text"
      ]
    }
  ],
  "code_test_links": [
    {
      "test_file": "backend/tests/test_users.py",
      "test_function": "test_create_user",
      "target_file": "backend/app/main.py",
      "target_symbol": "create_user",
      "target_type": "function",
      "evidence": [
        "Semantic match between 'test_create_user' and 'create_user'",
        "Exact naming convention match"
      ]
    },
    {
      "test_file": "backend/tests/test_users.py",
      "test_function": "test_list_users",
      "target_file": "backend/app/main.py",
      "target_symbol": "list_users",
      "target_type": "function",
      "evidence": [
        "Semantic match between 'test_list_users' and 'list_users'",
        "Exact naming convention match"
      ]
    }
  ]
}
```

---

##  Processing Flow

The adapter acts as the entry point. Callers do not need to know how the individual sub-analyzers work internally.

```text
  [profile_json] + [file_contents] + [raw_requirements]
                            │
                            ▼
                    process_project()
                            │
                            ├── Code analysis
                            │     ├── Python
                            │     └── JavaScript / TypeScript
                            │
                            ├── Requirement parsing
                            │
                            ├── Import / dependency resolution
                            │
                            ├── Dependency relationships
                            │
                            └── Code ↔ Requirement / Test mapping
                            │
                            ▼
                   SystemModelOutput
```

---

##  Local Testing

Navigate to the backend directory:
```bash
cd codesentinel/backend/
```

Run the complete Module 2 test suite:
```bash
python3 -m pytest -v
```

Run the adapter directly (if configured with a main block):
```bash
python3 -m app.analyzer.system_model.adapter
```