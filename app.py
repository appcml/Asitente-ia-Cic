"""
Cic_IA v7.0 - Wrapper para Render
Este archivo es el punto de entrada para gunicorn
"""

import sys
import os

# Añadir directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importar todo desde el archivo principal
from cic_ia_mejorado import app, cic_ia, db

# Exportar para gunicorn
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
