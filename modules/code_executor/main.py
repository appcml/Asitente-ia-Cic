# main.py

from flask import Flask
from codex.routes import codex_blueprint

app = Flask(__name__)
app.register_blueprint(codex_blueprint)

if __name__ == '__main__':
    app.run(debug=True)
