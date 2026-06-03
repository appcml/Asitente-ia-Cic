"""
modules/image_generator/routes.py
===================================
Blueprint del módulo de generación de imágenes.
Incluye rutas de feedback para CicDream.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

logger = logging.getLogger('cic_ia.image_generator')

bp = Blueprint('image_generator', __name__, url_prefix='/api/image')

# ── Cargar motores ────────────────────────────────────────────────────────
try:
    from .main import generar
    _ok = True
    logger.info('Motor de imágenes cargado')
except Exception as e:
    _ok = False
    _motor_err_msg = str(e)
    logger.warning(f'Motor no disponible: {_motor_err_msg}')
    def generar(**kw):
        return {'success': False, 'error': f'Motor no disponible: {_motor_err_msg}'}

# ── Cargar CicDream para feedback ─────────────────────────────────────────
try:
    from .cicdream import cicdream_feedback, cicdream_status, CicDream
    _cicdream_ok = True
except Exception as e:
    _cicdream_ok = False
    def cicdream_feedback(**kw): return {'success': False, 'error': 'CicDream no disponible'}
    def cicdream_status(**kw):   return {'ready': False}

VALID_STYLES  = {'realistic','artistic','anime','sketch','3d','minimalist',
                 'fantasy','cyberpunk','cartoon','abstract','space','fractal','landscape'}
VALID_SIZES   = {'square','landscape','portrait','512'}
VALID_QUALITY = {'standard','hd'}
VALID_MODELS  = {
    'auto','svg','pil','fractal','cicdream',
    'pollinations_flux','pollinations_turbo','pollinations_sd',
    'hf_flux','hf_sdxl','hf_sd21',
    'fal_flux_schnell','fal_flux_dev',
    'stability_core','stability_sd3',
    'gemini_flash',
}


def _get_current_user():
    """Verifica token contra BD — mismo mecanismo que token_required."""
    from flask import current_app
    from sqlalchemy import text

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

    db = current_app.extensions['sqlalchemy']
    engine = db.engine

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, user_id, expires_at FROM user_session WHERE token = :t LIMIT 1"),
            {'t': token}
        ).fetchone()

    if not row:
        raise PermissionError('Token inválido')

    session_id, user_id, expires_at = row[0], row[1], row[2]

    if expires_at and datetime.utcnow() > expires_at:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM user_session WHERE id = :id"), {'id': session_id})
            conn.commit()
        raise PermissionError('Token expirado')

    with engine.connect() as conn:
        conn.execute(
            text("UPDATE user_session SET last_access = :now WHERE id = :id"),
            {'now': datetime.utcnow(), 'id': session_id}
        )
        conn.commit()

    with engine.connect() as conn:
        user_row = conn.execute(
            text('SELECT id, username, is_active FROM "user" WHERE id = :uid LIMIT 1'),
            {'uid': user_id}
        ).fetchone()

    if not user_row or not user_row[2]:
        raise PermissionError('Usuario inactivo')

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
    """Genera imágenes con el motor seleccionado."""
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401
    except Exception as e:
        logger.error(f'[auth] Error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': 'Error de autenticación'}), 500

    data    = request.json or {}
    prompt  = data.get('prompt', '').strip()
    style   = data.get('style',   'realistic')
    size    = data.get('size',    'square')
    quality = data.get('quality', 'standard')
    try:
        count = int(data.get('count', data.get('n', 1)))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'count debe ser un entero'}), 400
    model   = data.get('model',   'auto')

    if not prompt:
        return jsonify({'success': False, 'error': 'El prompt es requerido'}), 400
    if len(prompt) > 4000:
        return jsonify({'success': False, 'error': 'Prompt muy largo (máx 4000)'}), 400

    if style   not in VALID_STYLES:   style   = 'realistic'
    if size    not in VALID_SIZES:    size    = 'square'
    if quality not in VALID_QUALITY:  quality = 'standard'
    if model   not in VALID_MODELS:   model   = 'auto'
    count = max(1, min(4, count))

    logger.info(f"[generate] user={user.username} prompt={prompt[:50]!r} model={model}")

    try:
        result = generar(
            prompt=prompt, style=style, size=size,
            quality=quality, count=count, model=model,
            user_id=user.id,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f'[generate] Error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'Error generando imagen: {str(e)}'}), 500


@bp.route('/feedback', methods=['POST'])
def image_feedback():
    """
    Recibe feedback del usuario sobre una imagen generada.
    Ajusta CicDream en tiempo real.

    Body JSON:
        generation_id  (int)   — ID retornado por /generate
        rating         (float) — 1.0 a 5.0
        details        (str)   — "más oscuro", "más detalle", etc.
        tags           (list)  — ["buena composición", "colores incorrectos"]
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    data = request.json or {}
    try:
        generation_id = int(data.get('generation_id', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'generation_id debe ser un entero'}), 400
    try:
        rating = float(data.get('rating', 3.0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'rating debe ser numerico'}), 400
    details = data.get('details', '').strip()[:500]
    tags    = data.get('tags', [])

    if not generation_id:
        return jsonify({'success': False, 'error': 'generation_id requerido'}), 400

    import numpy as np
    rating = float(np.clip(rating, 1.0, 5.0))

    try:
        result = cicdream_feedback(
            generation_id = generation_id,
            rating        = rating,
            details       = details,
            tags          = tags,
            user_id       = user.id,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f'[feedback] Error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/history', methods=['GET'])
def image_history():
    """Historial de imágenes generadas por el usuario."""
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    limit = min(int(request.args.get('limit', 20)), 50)

    try:
        if _cicdream_ok:
            from flask import current_app
            db = current_app.extensions['sqlalchemy'].engine
            from .cicdream import get_feedback
            fb = get_feedback(db)
            history = fb.get_history(user.id, limit)
        else:
            history = []
        return jsonify({'success': True, 'history': history, 'count': len(history)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/cicdream/status', methods=['GET'])
def cicdream_engine_status():
    """Estado del motor CicDream."""
    try:
        _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    try:
        status = cicdream_status()
        return jsonify({'success': True, 'cicdream': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/cicdream/stats', methods=['GET'])
def cicdream_stats():
    """Estadísticas de aprendizaje de CicDream."""
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    try:
        if _cicdream_ok:
            from flask import current_app
            db = current_app.extensions['sqlalchemy'].engine
            from .cicdream import get_feedback
            fb    = get_feedback(db)
            stats = fb.get_stats(user.id)
        else:
            stats = {}
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/models', methods=['GET'])
def list_models():
    """Lista todos los motores disponibles."""
    try:
        _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    from flask import current_app
    try:
        from .main import EXTERNAL_MOTORS, _CICDREAM_OK, _HF_TOKEN, _FAL_KEY, _STABILITY_KEY, _GEMINI_KEY
    except Exception:
        return jsonify({'success': True, 'motors': []})

    motors = []
    for mid, info in EXTERNAL_MOTORS.items():
        name, key_req, desc = info
        available = (key_req is None) or bool({
            'HF_TOKEN':      _HF_TOKEN,
            'FAL_KEY':       _FAL_KEY,
            'STABILITY_KEY': _STABILITY_KEY,
            'GEMINI_KEY':    _GEMINI_KEY,
        }.get(key_req, False))
        motors.append({
            'id': mid, 'name': name, 'desc': desc,
            'available': available, 'key_req': key_req,
        })

    return jsonify({'success': True, 'motors': motors, 'total': len(motors)})


@bp.route('/status', methods=['GET'])
def status():
    """Estado del módulo."""
    return jsonify({
        'module':     'image_generator',
        'version':    '2.0',
        'engine_ok':  _ok,
        'cicdream':   _cicdream_ok,
        'routes': [
            'POST /api/image/generate',
            'POST /api/image/feedback',
            'GET  /api/image/history',
            'GET  /api/image/models',
            'GET  /api/image/cicdream/status',
            'GET  /api/image/cicdream/stats',
        ]
    })


def register(app):
    app.register_blueprint(bp)
    logger.info('Rutas /api/image/* registradas (v2 con CicDream)')
