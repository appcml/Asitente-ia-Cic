"""
modules/__init__.py
===================
Registro central de Cic_IA.

Para agregar un módulo nuevo en el futuro:
  1. Crea modules/tu_modulo/__init__.py, main.py, routes.py
  2. Agrega una línea aquí: _reg(app, 'tu_modulo', 'Nombre del módulo')
  3. NO toques cic_ia_mejorado.py
"""
import logging
logger = logging.getLogger('cic_ia.modules')


def register_all(app):
    """
    Registra todos los módulos en la app Flask.
    Cada módulo gestiona sus propias rutas con Blueprint.
    """
    _reg(app, 'image_generator', 'Generador de imágenes')
    _reg(app, 'file_analyzer',   'Analizador de archivos')
    _reg(app, 'tts',             'Texto a voz')
    _reg(app, 'music_gen',       'Generador de música')
    _reg(app, 'code_executor',   'Ejecutor de código')
    _reg(app, 'video_gen',       'Generador de video')


def _reg(app, module_name, label):
    """Carga y registra un módulo de forma segura."""
    try:
        mod = __import__(f'modules.{module_name}', fromlist=['register'])
        if hasattr(mod, 'register'):
            mod.register(app)
            logger.info(f'✅ {label} ({module_name}) registrado')
        else:
            logger.warning(f'⚠️  {module_name} no tiene register(app) — saltando')
    except ImportError as e:
        logger.warning(f'⚠️  {module_name} no disponible: {e}')
    except Exception as e:
        logger.error(f'❌ Error en {module_name}: {e}', exc_info=True)
