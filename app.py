# app.py - Punto de entrada para Render
# Importar directamente desde cic_ia_mejorado
from cic_ia_mejorado import app

# Esto permite que gunicorn app:app funcione
application = app

if __name__ == '__main__':
    port = int(__import__('os').environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
