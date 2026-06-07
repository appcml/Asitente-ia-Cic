from pathlib import Path
import json
from datetime import datetime


class ProjectMemory:

    def __init__(self):

        self.memory_dir = (
            Path("data")
            / "code_executor"
            / "projects"
        )

        self.memory_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def save_project(
        self,
        project_name: str,
        data: dict
    ):

        file_path = (
            self.memory_dir
            / f"{project_name}.json"
        )

        payload = {
            "updated_at": datetime.utcnow().isoformat(),
            "data": data
        }

        with open(
            file_path,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                payload,
                f,
                indent=4,
                ensure_ascii=False
            )

        return True

    def load_project(
        self,
        project_name: str
    ):

        file_path = (
            self.memory_dir
            / f"{project_name}.json"
        )

        if not file_path.exists():
            return None

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    def list_projects(self):

        return [
            file.stem
            for file in self.memory_dir.glob("*.json")
        ]
