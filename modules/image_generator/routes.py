"""
modules/image_generator/routes.py
===================================
Blueprint del módulo de generación de imágenes.
Usa el mismo sistema de autenticación que cic_ia_mejorado.py
(tokens en BD, no JWT).
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

logger = logging.getLogger('cic_ia.image_generator')

bp = Blueprint('image_generator', __name__, url_prefix='/api/image')

# ── Cargar motor ──────────────────────────────────────────────────────────
try:
    from .main import generar
    _ok = True
    logger.info('Motor de imágenes cargado (SVG + PIL + Fractal)')
except Exception as e:
    _ok = False
    logger.warning(f'Motor no disponible: {e}')
    def generar(**kw):
        return {'success': False, 'error': f'Motor no disponible: {e}'}

VALID_STYLES  = {'realistic','artistic','anime','sketch','3d','minimalist',
                 'fantasy','cyberpunk','cartoon','abstract','space','fractal','landscape'}
VALID_SIZES   = {'square','landscape','portrait','512'}
VALID_QUALITY = {'standard','hd'}
VALID_MODELS  = {'auto','svg','pil','fractal','pollinations'}


def _get_current_user():
    """
    Verifica el token usando el mismo sistema que token_required en cic_ia_mejorado.py:
    busca el token en la tabla UserSession de la base de datos.
    """
    from cic_ia_mejorado import db, UserSession, User

    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth[7:]
    else:
        parts = auth.split()
        token = parts[1] if len(parts) == 2 else None

    if not token:
        token = request.args.get('token')

    if not token:
        raise PermissionError('Token requerido')

    session = UserSession.query.filter_by(token=token).first()
    if not session:
        raise PermissionError('Token inválido')

    if session.expires_at and session.expires_at < datetime.utcnow():
        db.session.delete(session)
        db.session.commit()
        raise PermissionError('Token expirado')

    session.last_access = datetime.utcnow()
    db.session.commit()

    user = User.query.get(session.user_id)
    if not user or not user.is_active:
        raise PermissionError('Usuario inactivo')

    return user


# ══════════════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════════════

@bp.route('/generate', methods=['POST'])
def generate_image():
    """
    Genera imágenes con el motor propio de Cic_IA.

    Body JSON:
        prompt   (str, requerido)
        style    (str)  realistic|artistic|anime|sketch|3d|minimalist|
                        fantasy|cyberpunk|cartoon|abstract|space|fractal|landscape
        size     (str)  square|landscape|portrait|512
        quality  (str)  standard|hd
        count    (int)  1-4
        model    (str)  auto|svg|pil|fractal|pollinations
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    data    = request.json or {}
    prompt  = data.get('prompt', '').strip()
    style   = data.get('style',   'realistic')
    size    = data.get('size',    'square')
    quality = data.get('quality', 'standard')
    count   = int(data.get('count', data.get('n', 1)))
    model   = data.get('model',   'auto')

    if not prompt:
        return jsonify({'success': False, 'error': 'El prompt es requerido'}), 400
    if len(prompt) > 4000:
        return jsonify({'success': False, 'error': 'Prompt muy largo (máx 4000 chars)'}), 400

    if style   not in VALID_STYLES:   style   = 'realistic'
    if size    not in VALID_SIZES:    size    = 'square'
    if quality not in VALID_QUALITY:  quality = 'standard'
    if model   not in VALID_MODELS:   model   = 'auto'
    count = max(1, min(4, count))

    logger.info(
        f"[generate] user={user.username} "
        f"prompt={prompt[:50]!r} style={style} size={size} "
        f"quality={quality} count={count} model={model}"
    )

    result = generar(
        prompt=prompt, style=style, size=size,
        quality=quality, count=count, model=model,
    )
    return jsonify(result)


@bp.route('/models', methods=['GET'])
def list_models():
    """Lista los motores disponibles."""
    return jsonify({
        'engine_ok': _ok,
        'motors': [
            {'id': 'auto',         'name': 'Auto (recomendado)', 'free': True, 'available': True},
            {'id': 'svg',          'name': 'SVG vectorial',      'free': True, 'available': _ok},
            {'id': 'pil',          'name': 'PIL / píxeles',      'free': True, 'available': _ok},
            {'id': 'fractal',      'name': 'Fractal matemático', 'free': True, 'available': _ok},
            {'id': 'pollinations', 'name': 'Pollinations.ai',    'free': True, 'available': True},
        ]
    })


@bp.route('/status', methods=['GET'])
def status():
    """Estado del módulo."""
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


def register(app):
    """Registra el Blueprint. Llamado desde modules/__init__.py"""
    app.register_blueprint(bp)
    logger.info('Rutas /api/image/* registradas')
