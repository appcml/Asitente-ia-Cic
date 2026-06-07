from pathlib import Path


class RepositoryAnalyzer:

    def analyze(self, repo_path: str):

        repo = Path(repo_path)

        result = {
            "folders": [],
            "files": [],
            "python_files": 0,
            "javascript_files": 0,
            "typescript_files": 0,
        }

        for item in repo.rglob("*"):

            if item.is_dir():
                result["folders"].append(
                    str(item.relative_to(repo))
                )

            elif item.is_file():

                result["files"].append(
                    str(item.relative_to(repo))
                )

                suffix = item.suffix.lower()

                if suffix == ".py":
                    result["python_files"] += 1

                elif suffix == ".js":
                    result["javascript_files"] += 1

                elif suffix == ".ts":
                    result["typescript_files"] += 1

        return result
