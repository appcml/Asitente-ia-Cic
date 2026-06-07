from fastapi import APIRouter
from pydantic import BaseModel

from .main import CodeExecutor

router = APIRouter(
    prefix="/code-executor",
    tags=["Code Executor"]
)

executor = CodeExecutor()


class RepositoryRequest(BaseModel):
    path: str


class ProjectRequest(BaseModel):
    name: str
    data: dict


class KnowledgeRequest(BaseModel):
    problem: str
    solution: str


@router.get("/status")
async def status():

    return executor.status()


@router.post("/analyze")
async def analyze_repository(
    request: RepositoryRequest
):

    return executor.analyze_repository(
        request.path
    )


@router.post("/project/save")
async def save_project(
    request: ProjectRequest
):

    return executor.save_project(
        request.name,
        request.data
    )


@router.get("/projects")
async def list_projects():

    return executor.list_projects()


@router.post("/knowledge")
async def save_knowledge(
    request: KnowledgeRequest
):

    return executor.remember_solution(
        request.problem,
        request.solution
    )


@router.get("/knowledge")
async def get_knowledge():

    return executor.get_knowledge()
