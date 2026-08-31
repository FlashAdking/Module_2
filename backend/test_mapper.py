from app.analyzer.dependency_analyzer.relationship_mapper import map_code_to_requirements, _overlap, _symbol_tokens, _tokenise
from app.schemas.project import FileModel, RequirementModel, FunctionModel

files = [
    FileModel(
        file="app/users.py", language="python",
        classes=[], api_routes=[], imports=[],
        functions=[
            FunctionModel(name="list_users", arguments=[], decorators=[], depends_on=[]),
            FunctionModel(name="search_users", arguments=[], decorators=[], depends_on=[]),
            FunctionModel(name="delete_user", arguments=[], decorators=[], depends_on=[]),
        ]
    )
]

reqs = [
    RequirementModel(
        requirement_id="REQ-001",
        title="User Listing",
        description="The system must list all users.",
        acceptance_criteria=["Fetches the users list"]
    ),
    RequirementModel(
        requirement_id="REQ-002",
        title="User Search",
        description="The system must allow searching for users.",
        acceptance_criteria=["Searches users by name"]
    ),
]

links = map_code_to_requirements(files, reqs)
for l in links:
    print(f"Req: {l.requirement_id}, Symbol: {l.symbol}, Score: {l.match_score}")

print("Debug search_users vs REQ-002:")
sym_toks = _symbol_tokens("search_users")
req2 = reqs[1]
req_text = f"{req2.title} {req2.description} {' '.join(req2.acceptance_criteria)}"
req_toks = _tokenise(req_text)
print(f"sym_toks: {sym_toks}")
print(f"req_toks: {req_toks}")
print(f"overlap: {_overlap(sym_toks, req_toks)}")
