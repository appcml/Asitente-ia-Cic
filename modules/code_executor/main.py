from .memory import ProjectMemory
from .repository import RepositoryAnalyzer
from .knowledge import KnowledgeBase


class CodeExecutor:

    VERSION = "1.0.0"

    def __init__(self):

        self.memory = ProjectMemory()
        self.repository = RepositoryAnalyzer()
        self.knowledge = KnowledgeBase()

    def status(self):

        return {
            "module": "CodeExecutor",
            "version": self.VERSION,
            "memory": True,
            "repository_analyzer": True,
            "knowledge_base": True
        }

    def analyze_repository(
        self,
        repo_path: str
    ):

        return self.repository.analyze(repo_path)

    def save_project(
        self,
        project_name: str,
        project_data: dict
    ):

        return self.memory.save_project(
            project_name,
            project_data
        )

    def load_project(
        self,
        project_name: str
    ):

        return self.memory.load_project(
            project_name
        )

    def list_projects(self):

        return self.memory.list_projects()

    def remember_solution(
        self,
        problem: str,
        solution: str
    ):

        self.knowledge.add_solution(
            problem,
            solution
        )

        return {
            "success": True
        }

    def get_knowledge(self):

        return self.knowledge.get_all()
