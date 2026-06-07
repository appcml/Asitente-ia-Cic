from .routes import code_executor_bp


def register(app):

    app.register_blueprint(
        code_executor_bp
    )
