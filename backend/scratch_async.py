import ast
from app.analyzer.code_analyzer.custom_ast_parser import parse_code
from app.analyzer.code_analyzer.python_parser import parse_python_code

code = """
from fastapi import FastAPI, Depends

app = FastAPI()

async def get_db():
    pass

@app.get("/users")
async def list_users(db=Depends(get_db)):
    pass
"""

file_model = parse_python_code(code, "test.py")
print(file_model.model_dump_json(indent=2))
