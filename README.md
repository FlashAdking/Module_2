

## Module Structure

```text
codesentinel/
.
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
│   │   │       └── adapter.py
│   │   └── schemas
│   │       └── project.py
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
├── README.md
└── req.txt

11 directories, 26 file
```

### Sample Input
```json
// we have to just call this function with required inputs and file paths
// process_project(profile_json: Dict[str, Any], file_contents: Dict[str, str], raw_requirements: str) -> SystemModelOutput:

// path : /codesentinel/backend/app/analyzer/system_model/adapter.py

profile_json = {
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

file_contents = {
    "app/main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/users')\ndef list_users():\n    return []\n",
    "src/App.tsx": "import React from 'react';\n\nexport const UserList = () => {\n  return <div>List</div>;\n};\n"
}


// module 2 is responsible for generating REQ-ID
raw_requirements = """User Listing
The system must list all users.
Acceptance Criteria:
- Fetches from /users
- Displays a table

Dashboard
The system shall provide a dashboard.
Acceptance Criteria:
- Must show stats"""
```


### Sample Output
```json
 "project_id": "test_project_123",
 "files": [
   {
     "file": "main.py",
     "language": "python",
     "classes": [
       {
         "name": "User",
         "methods": [
           "get_name"
         ]
       }
     ],
     "functions": [
       {
         "name": "get_db",
         "arguments": [],
         "decorators": []
       },
       {
         "name": "list_users",
         "arguments": [
           "db"
         ],
         "decorators": [
           "app.get"
         ]
       }
     ],
     "api_routes": [
       {
         "method": "GET",
         "path": "/users",
         "function_name": "list_users"
       }
     ],
     "imports": [
       "fastapi.FastAPI",
       "fastapi.Depends"
     ]
   },
   {
     "file": "App.tsx",
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
         "name": "UserList",
         "arguments": [],
         "decorators": []
       },
       {
         "name": "fetchUsers",
         "arguments": [],
         "decorators": []
       }
     ],
     "api_routes": [],
     "imports": [
       "react",
       "axios"
     ]
   }
 ],
 "requirements": [
   {
     "requirement_id": "REQ-001",
     "title": "User Listing",
     "description": "The system must list all users.",
     "acceptance_criteria": [
       "Fetches from /users",
       "Displays a table"
     ]
   },
   {
     "requirement_id": "REQ-002",
     "title": "Dashboard",
     "description": "The system shall provide a dashboard.",
     "acceptance_criteria": [
       "Must show stats"
     ]
   }
 ]
}

```


## local testing

```bash
## run this command inside codesentinel/backend/
python3 -m app.analyzer.system_model.adapter
```