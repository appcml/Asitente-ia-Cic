"""
modules/image_generator/routes.py
===================================
Blueprint del módulo de generación de imágenes.

Rutas:
  POST /api/image/generate   — genera 1-4 imágenes
  GET  /api/image/models     — lista motores disponibles
  GET  /api/image/status     — estado del módulo

cic_ia_mejorado.py NO contiene ninguna de estas rutas.
Toda la lógica vive en main.py (motores SVG, PIL, Fractal).
"""
from flask import Blueprint, request, jsonify, current_app
import logging
import jwt

logger = logging.getLogger('cic_ia.image_generator')

bp = Blueprint('image_generator', __name__, url_prefix='/api/image')

# ── Cargar motor al iniciar el módulo ─────────────────────────────────────
try:
    from .main import generar
    _ok = True
    logger.info('Motor de imágenes cargado (SVG + PIL + Fractal)')
except Exception as e:
    _ok = False
    logger.warning(f'Motor no disponible: {e}')
    def generar(**kw):
        return {'success': False, 'error': f'Motor no disponible: {e}'}

# ── Constantes de validación ──────────────────────────────────────────────
VALID_STYLES  = {'realistic','artistic','anime','sketch','3d','minimalist',
                 'fantasy','cyberpunk','cartoon','abstract','space','fractal','landscape'}
VALID_SIZES   = {'square','landscape','portrait','512'}
VALID_QUALITY = {'standard','hd'}
VALID_MODELS  = {'auto','svg','pil','fractal','pollinations'}


# ── Helper: verificar JWT ─────────────────────────────────────────────────
def _get_user(req):
    """
    Extrae y verifica el JWT del header Authorization.
    Retorna el payload o lanza excepción.
    Compatible con el sistema de tokens de cic_ia_mejorado.py.
    """
    token = req.headers.get('Authorization', '').replace('Bearer ', '').strip()
    if not token:
        raise PermissionError('Token requerido')
    try:
        secret = current_app.config.get('SECRET_KEY', '')
        return jwt.decode(token, secret, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise PermissionError('Token expirado')
    except Exception:
        raise PermissionError('Token inválido')


# ══════════════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════════════

@bp.route('/generate', methods=['POST'])
def generate_image():
    """
    Genera imágenes con el motor propio de Cic_IA.

    Body JSON:
        prompt   (str, requerido)  descripción de la imagen
        style    (str)  realistic|artistic|anime|sketch|3d|minimalist|
                        fantasy|cyberpunk|cartoon|abstract|space|fractal|landscape
        size     (str)  square|landscape|portrait|512
        quality  (str)  standard|hd
        count    (int)  1-4 variantes
        model    (str)  auto|svg|pil|fractal|pollinations

    Respuesta exitosa:
        {
          "success": true,
          "images":  [{"url": "data:image/png;base64,...", "provider": "..."}],
          "count":   N,
          "provider": "Cic_IA — Motor PIL",
          "engine":  "pil"
        }
    """
    # Auth
    try:
        user = _get_user(request)
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    # Datos
    data    = request.json or {}
    prompt  = data.get('prompt', '').strip()
    style   = data.get('style',   'realistic')
    size    = data.get('size',    'square')
    quality = data.get('quality', 'standard')
    count   = int(data.get('count', data.get('n', 1)))
    model   = data.get('model',   'auto')

    # Validar prompt
    if not prompt:
        return jsonify({'success': False, 'error': 'El prompt es requerido'}), 400
    if len(prompt) > 4000:
        return jsonify({'success': False, 'error': 'Prompt muy largo (máx 4000 chars)'}), 400

    # Sanitizar parámetros
    if style   not in VALID_STYLES:   style   = 'realistic'
    if size    not in VALID_SIZES:    size    = 'square'
    if quality not in VALID_QUALITY:  quality = 'standard'
    if model   not in VALID_MODELS:   model   = 'auto'
    count = max(1, min(4, count))

    logger.info(
        f"[generate] user={user.get('username','?')} "
        f"prompt={prompt[:50]!r} style={style} size={size} "
        f"quality={quality} count={count} model={model}"
    )

    result = generar(
        prompt  = prompt,
        style   = style,
        size    = size,
        quality = quality,
        count   = count,
        model   = model,
    )
    return jsonify(result)


@bp.route('/models', methods=['GET'])
def list_models():
    """Lista los motores disponibles y su estado."""
    return jsonify({
        'engine_ok': _ok,
        'motors': [
            {
                'id':        'auto',
                'name':      'Auto (recomendado)',
                'free':      True,
                'available': True,
                'note':      'Elige el mejor motor automáticamente',
            },
            {
                'id':        'svg',
                'name':      'SVG vectorial',
                'free':      True,
                'available': _ok,
                'note':      'Paisajes, cyberpunk, abstracto, cartoon',
            },
            {
                'id':        'pil',
                'name':      'PIL / píxeles reales',
                'free':      True,
                'available': _ok,
                'note':      'Fotorrealista, anime, sketch, 3D, espacio',
            },
            {
                'id':        'fractal',
                'name':      'Fractal matemático',
                'free':      True,
                'available': _ok,
                'note':      'Mandelbrot, Julia sets — arte matemático',
            },
            {
                'id':        'pollinations',
                'name':      'Pollinations.ai',
                'free':      True,
                'available': True,
                'note':      'Fallback gratuito — requiere internet',
            },
        ]
    })


@bp.route('/status', methods=['GET'])
def status():
    """Estado del módulo — útil para debug en Render."""
    return jsonify({
        'module':    'image_generator',
        'version':   '1.0',
        'engine_ok': _ok,
        'routes': [
            'POST /api/image/generate',
            'GET  /api/image/models',
            'GET  /api/image/status',
        ]
    })


# ── Registro del Blueprint ────────────────────────────────────────────────
def register(app):
    """
    Punto de entrada del módulo.
    Llamado UNA VEZ desde modules/__init__.py → register_all(app).
    """
    app.register_blueprint(bp)
    logger.info('Rutas /api/image/* registradas')
