"""
Archivo de entrada para Gunicorn
Importa la aplicación desde cic_ia_mejorado.py
"""

from cic_ia_mejorado import app, cic_ia, db

# Esto permite que Gunicorn encuentre 'app'
if __name__ == "__main__":
    app.run()
