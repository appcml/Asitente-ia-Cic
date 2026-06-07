# routes.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Define la ruta para la ejecución de código
router = APIRouter()

class CodeExecutionRequest(BaseModel):
    code: str
    language: str

@router.post("/execute")
async def execute_code(request: CodeExecutionRequest):
    # Lógica para ejecutar el código aquí
    return {"message": "Código ejecutado con éxito"}
