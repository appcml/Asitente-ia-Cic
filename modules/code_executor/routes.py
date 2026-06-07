from flask import Blueprint, jsonify, request

from .main import CodeExecutor

code_executor_bp = Blueprint(
    "code_executor",
    __name__,
    url_prefix="/code-executor"
)

executor = CodeExecutor()


@code_executor_bp.route("/status", methods=["GET"])
def status():

    return jsonify(
        executor.status()
    )


@code_executor_bp.route("/projects", methods=["GET"])
def list_projects():

    return jsonify(
        executor.list_projects()
    )


@code_executor_bp.route("/knowledge", methods=["GET"])
def knowledge():

    return jsonify(
        executor.get_knowledge()
    )


@code_executor_bp.route("/analyze", methods=["POST"])
def analyze():

    data = request.get_json()

    repo_path = data.get("path")

    result = executor.analyze_repository(
        repo_path
    )

    return jsonify(result)


@code_executor_bp.route(
    "/project/save",
    methods=["POST"]
)
def save_project():

    data = request.get_json()

    result = executor.save_project(
        data["name"],
        data["data"]
    )

    return jsonify({
        "success": result
    })


@code_executor_bp.route(
    "/knowledge",
    methods=["POST"]
)
def save_knowledge():

    data = request.get_json()

    result = executor.remember_solution(
        data["problem"],
        data["solution"]
    )

    return jsonify(result)
