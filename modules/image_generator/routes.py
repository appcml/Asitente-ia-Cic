"""
modules/image_generator/routes.py
===================================
Blueprint del módulo de generación de imágenes.
Sin import circular — usa flask.current_app y db directamente.
"""
from flask import Blueprint, request, jsonify, current_app, g
from datetime import datetime
import logging

logger = logging.getLogger('cic_ia.image_generator')

bp = Blueprint('image_generator', __name__, url_prefix='/api/image')

# ── Cargar motor ──────────────────────────────────────────────────────────
try:
    from .main import generar
    _ok = True
    logger.info('Motor de imágenes cargado (SVG + PIL + Fractal)')
except Exception as _motor_err:
    _ok = False
    _motor_err_msg = str(_motor_err)
    logger.warning(f'Motor no disponible: {_motor_err_msg}')
    def generar(**kw):
        return {'success': False, 'error': f'Motor no disponible: {_motor_err_msg}'}

VALID_STYLES  = {'realistic','artistic','anime','sketch','3d','minimalist',
                 'fantasy','cyberpunk','cartoon','abstract','space','fractal','landscape'}
VALID_SIZES   = {'square','landscape','portrait','512'}
VALID_QUALITY = {'standard','hd'}
VALID_MODELS  = {'auto','svg','pil','fractal','pollinations'}


def _get_current_user():
    """
    Verifica el token contra la BD usando el mismo mecanismo que
    token_required en cic_ia_mejorado.py.
    Evita import circular usando db y modelos desde el contexto de la app.
    """
    # Extraer token del header
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

    # Acceder a db y modelos desde el contexto Flask (sin import circular)
    from flask_sqlalchemy import SQLAlchemy
    db    = current_app.extensions['sqlalchemy']

    # Usar SQL directo para evitar referencias a clases del módulo principal
    from sqlalchemy import text
    engine = db.engine

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, user_id, expires_at FROM user_session WHERE token = :token LIMIT 1"),
            {'token': token}
        ).fetchone()

    if not row:
        raise PermissionError('Token inválido')

    session_id, user_id, expires_at = row[0], row[1], row[2]

    if expires_at and datetime.utcnow() > expires_at:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM user_session WHERE id = :sid"), {'sid': session_id})
            conn.commit()
        raise PermissionError('Token expirado')

    # Actualizar last_access
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE user_session SET last_access = :now WHERE id = :sid"),
            {'now': datetime.utcnow(), 'sid': session_id}
        )
        conn.commit()

    # Obtener usuario
    with engine.connect() as conn:
        user_row = conn.execute(
            text("SELECT id, username, is_active FROM \"user\" WHERE id = :uid LIMIT 1"),
            {'uid': user_id}
        ).fetchone()

    if not user_row or not user_row[2]:
        raise PermissionError('Usuario inactivo')

    # Retornar objeto simple con los datos necesarios
    class SimpleUser:
        def __init__(self, id, username):
            self.id       = id
            self.username = username

    return SimpleUser(user_row[0], user_row[1])


# ══════════════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════════════

@bp.route('/generate', methods=['POST'])
def generate_image():
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401
    except Exception as e:
        logger.error(f'[auth] Error inesperado: {e}', exc_info=True)
        return jsonify({'success': False, 'error': 'Error de autenticación'}), 500

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

    logger.info(f"[generate] user={user.username} prompt={prompt[:50]!r} "
                f"style={style} size={size} quality={quality} count={count} model={model}")

    try:
        result = generar(prompt=prompt, style=style, size=size,
                         quality=quality, count=count, model=model)

        # Comprimir respuesta si es grande (base64 puede ser pesado)
        import json, gzip
        payload = json.dumps(result).encode('utf-8')

        if len(payload) > 500_000:  # > 500KB → comprimir
            from flask import Response
            compressed = gzip.compress(payload, compresslevel=6)
            logger.info(f"[generate] Respuesta comprimida: {len(payload)//1024}KB → {len(compressed)//1024}KB")
            return Response(
                compressed,
                status=200,
                mimetype='application/json',
                headers={'Content-Encoding': 'gzip', 'Content-Type': 'application/json'}
            )

        return jsonify(result)
    except Exception as e:
        logger.error(f'[generate] Error motor: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'Error generando imagen: {str(e)}'}), 500


@bp.route('/models', methods=['GET'])
def list_models():
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
    return jsonify({
        'module': 'image_generator', 'version': '1.0', 'engine_ok': _ok,
        'routes': ['POST /api/image/generate', 'GET /api/image/models', 'GET /api/image/status']
    })


def register(app):
    app.register_blueprint(bp)
    logger.info('Rutas /api/image/* registradas')
