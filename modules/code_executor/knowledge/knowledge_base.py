from pathlib import Path
import json


class KnowledgeBase:

    def __init__(self):

        self.db_path = (
            Path("data")
            / "code_executor"
            / "knowledge.json"
        )

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if not self.db_path.exists():

            with open(
                self.db_path,
                "w",
                encoding="utf-8"
            ) as f:
                json.dump([], f)

    def add_solution(
        self,
        problem: str,
        solution: str
    ):

        data = self.get_all()

        data.append({
            "problem": problem,
            "solution": solution
        })

        with open(
            self.db_path,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

    def get_all(self):

        with open(
            self.db_path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)
