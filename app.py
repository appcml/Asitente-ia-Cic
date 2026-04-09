# app.py - Punto de entrada para Render
from cic_ia_mejorado import app

# Esto permite que gunicorn app:app funcione
application = app

if __name__ == '__main__':
    app.run()
