"""
modules/image_generator/routes.py
===================================
Blueprint del módulo de generación de imágenes.
Incluye rutas de feedback para CicDream.

FIXES v2.1:
- BUG #1: /training/analyze leía 'image_base64' pero frontend envía 'image_b64' → corregido
- BUG #2: /training/manual ignoraba 'image_b64' del frontend → ahora lo acepta opcionalmente
- NUEVO: /cicdream/top — ruta que el frontend llama en loadCDTopGens()
- NUEVO: /dataset/export acepta ?min_rating y ?limit correctamente
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


def _is_developer(user_id, engine):
    """Verifica si el usuario es desarrollador."""
    from sqlalchemy import text
    with engine.connect() as conn:
        row = conn.execute(
            text('SELECT is_developer FROM "user" WHERE id = :uid LIMIT 1'),
            {'uid': user_id}
        ).fetchone()
    return bool(row and row[0])


# ══════════════════════════════════════════════════════════════════════════
# RUTAS PRINCIPALES
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

    FIX v2.3: SQL directo en cicdream_feedback como fallback robusto.
    Si cicdream.cicdream_feedback() falla, igual se guarda en BD.
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
    details = (data.get('details') or '').strip()[:500]
    tags    = data.get('tags', [])

    if not generation_id:
        return jsonify({'success': False, 'error': 'generation_id requerido'}), 400

    # Clamp rating 1.0 - 5.0
    rating = max(1.0, min(5.0, rating))

    # Intentar primero con cicdream.cicdream_feedback (preferido)
    cicdream_ok = False
    cicdream_msg = ''
    try:
        if _cicdream_ok:
            result = cicdream_feedback(
                generation_id = generation_id,
                rating        = rating,
                details       = details,
                tags          = tags,
                user_id       = user.id,
            )
            if result and result.get('success'):
                cicdream_ok = True
                cicdream_msg = result.get('message', '')
    except Exception as e:
        logger.warning(f'[feedback] cicdream_feedback falló, usando SQL directo: {e}')

    # SIEMPRE guardar en BD con SQL directo - así nunca se pierde el feedback
    try:
        from flask import current_app
        from sqlalchemy import text
        import json as _json
        db = current_app.extensions['sqlalchemy'].engine

        # Asegurar tabla
        with db.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cicdream_feedback (
                    id              SERIAL PRIMARY KEY,
                    generation_id   INTEGER NOT NULL,
                    user_id         INTEGER NOT NULL,
                    rating          REAL NOT NULL,
                    details         TEXT,
                    tags            TEXT,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        tags_str = _json.dumps(tags) if isinstance(tags, list) else str(tags)

        with db.begin() as conn:
            conn.execute(text("""
                INSERT INTO cicdream_feedback (generation_id, user_id, rating, details, tags, created_at)
                VALUES (:gid, :uid, :r, :det, :tags, CURRENT_TIMESTAMP)
            """), {
                'gid': generation_id, 'uid': user.id,
                'r': rating, 'det': details[:500], 'tags': tags_str[:1000],
            })

        logger.info(f'[feedback] ✅ gen_id={generation_id} rating={rating} user={user.username} via_cicdream={cicdream_ok}')

        return jsonify({
            'success': True,
            'message': cicdream_msg or '✅ CicDream aprendió de tu feedback',
            'generation_id': generation_id,
            'rating': rating,
        })

    except Exception as e:
        logger.error(f'[feedback] Error guardando: {e}', exc_info=True)
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


@bp.route('/cicdream/top', methods=['GET'])
def cicdream_top():
    """
    Devuelve las mejores generaciones de CicDream (mayor rating).
    Usado por el panel CicDream Studio para mostrar 'Mejores generaciones'.
    """
    try:
        _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    try:
        limit = min(int(request.args.get('limit', 6)), 20)
    except (TypeError, ValueError):
        limit = 6

    try:
        from flask import current_app
        from sqlalchemy import text
        db = current_app.extensions['sqlalchemy'].engine

        with db.connect() as conn:
            rows = conn.execute(text("""
                SELECT
                    g.id,
                    g.prompt,
                    g.style,
                    g.created_at,
                    COALESCE(AVG(f.rating), 0) as avg_rating,
                    COUNT(f.id) as feedback_count
                FROM cicdream_generation g
                LEFT JOIN cicdream_feedback f ON f.generation_id = g.id
                GROUP BY g.id, g.prompt, g.style, g.created_at
                HAVING COALESCE(AVG(f.rating), 0) >= 3.5
                ORDER BY avg_rating DESC, g.created_at DESC
                LIMIT :lim
            """), {'lim': limit}).fetchall()

        top = []
        for row in rows:
            top.append({
                'id':             row[0],
                'prompt':         (row[1] or '')[:120],
                'style':          row[2],
                'created_at':     str(row[3]),
                'rating':         round(float(row[4]), 2),
                'feedback_count': int(row[5]),
            })

        return jsonify({'success': True, 'top': top, 'total': len(top)})

    except Exception as e:
        logger.error(f'[cicdream/top] Error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e), 'top': []}), 500


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
        'version':    '2.1',
        'engine_ok':  _ok,
        'cicdream':   _cicdream_ok,
        'routes': [
            'POST /api/image/generate',
            'POST /api/image/feedback',
            'GET  /api/image/history',
            'GET  /api/image/models',
            'GET  /api/image/cicdream/status',
            'GET  /api/image/cicdream/stats',
            'GET  /api/image/cicdream/top',
            'POST /api/image/training/manual',
            'POST /api/image/training/analyze',
            'GET  /api/image/dataset/export',
        ]
    })


# ══════════════════════════════════════════════════════════════════════════
# RUTAS DE ENTRENAMIENTO CICDREAM
# ══════════════════════════════════════════════════════════════════════════

@bp.route('/training/manual', methods=['POST'])
def manual_training():
    """
    Permite al desarrollador enseñar a CicDream manualmente.
    Recibe imagen + descripción + metadatos y los guarda como
    dato de entrenamiento en la BD.

    FIX v2.1: Ahora acepta 'image_b64' (clave que envía el frontend)
    además de 'image_base64' para compatibilidad total.
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    # Solo desarrolladores
    try:
        from flask import current_app
        from sqlalchemy import text
        db = current_app.extensions['sqlalchemy'].engine
        if not _is_developer(user.id, db):
            return jsonify({'success': False, 'error': 'Solo desarrolladores'}), 403
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    data   = request.get_json(force=True, silent=True) or {}
    prompt = data.get('prompt', '').strip()
    style  = data.get('style', 'realistic')
    notes  = data.get('notes', '').strip()
    tags   = data.get('tags', [])
    # FIX: aceptar 'image_b64' O 'image_base64' (el frontend envía 'image_b64')
    b64    = data.get('image_b64', '') or data.get('image_base64', '')
    try:
        rating = float(data.get('rating', 5.0))
    except (ValueError, TypeError):
        rating = 5.0

    if not prompt:
        return jsonify({'success': False, 'error': 'El prompt es obligatorio'}), 400

    # Si viene imagen pero sin prompt detallado, aceptar igual
    full_prompt = prompt
    if notes:
        full_prompt = f"{prompt}. Notas técnicas: {notes}"

    try:
        from flask import current_app
        from .cicdream import get_feedback
        db = current_app.extensions['sqlalchemy'].engine
        fb = get_feedback(db)

        gen_result = {
            'provider': 'Manual Training',
            'engine':   'manual',
            'seed':     0,
            'steps':    0,
            'guidance': 7.5,
            'time_ms':  0,
        }

        # Añadir info de imagen si vino
        if b64:
            gen_result['has_image'] = True
            gen_result['image_size_kb'] = round(len(b64) * 3 / 4 / 1024, 1)

        gen_id = fb.save_generation(
            user_id           = user.id,
            prompt            = full_prompt,
            style             = style,
            size              = 'square',
            quality           = 'standard',
            generation_result = gen_result,
        )

        if gen_id:
            fb.submit(
                generation_id = gen_id,
                user_id       = user.id,
                rating        = rating,
                details       = notes,
                tags          = tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(',') if t.strip()],
            )
            logger.info(f'[training/manual] gen_id={gen_id} prompt={prompt[:50]!r} rating={rating} has_img={bool(b64)}')
            return jsonify({
                'success':       True,
                'generation_id': gen_id,
                'message':       f'CicDream aprendió: "{prompt[:60]}"',
            })
        else:
            return jsonify({'success': False, 'error': 'No se pudo guardar en la BD'}), 500

    except Exception as e:
        logger.error(f'[training/manual] Error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/training/analyze', methods=['POST'])
def analyze_training_image():
    """
    Analiza automáticamente una imagen con visión IA y extrae:
    - Prompt descriptivo
    - Colores dominantes
    - Composición y estructura
    - Parámetros técnicos
    Luego guarda todo como dato de entrenamiento para CicDream.

    FIX v2.1: El frontend envía 'image_b64' pero antes se leía 'image_base64'.
    Ahora acepta ambas claves correctamente.
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    # Solo desarrolladores
    try:
        from flask import current_app
        from sqlalchemy import text
        db = current_app.extensions['sqlalchemy'].engine
        if not _is_developer(user.id, db):
            return jsonify({'success': False, 'error': 'Solo desarrolladores'}), 403
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    data     = request.json or {}
    filename = data.get('filename', 'imagen')
    style    = data.get('style', 'realistic')
    try:
        rating = float(data.get('rating', 4.0))
    except (ValueError, TypeError):
        rating = 4.0

    # FIX CRÍTICO: el frontend envía 'image_b64', antes se leía 'image_base64' → siempre vacío
    b64 = data.get('image_b64', '') or data.get('image_base64', '')

    if not b64:
        return jsonify({
            'success': False,
            'error':   'imagen requerida — enviar campo "image_b64" con base64 de la imagen'
        }), 400

    # Analizar imagen con visión IA (Groq Vision)
    try:
        from flask import current_app as _app
        prompt_generado = None
        notas_tecnicas  = None
        tags_ia         = []

        import os
        import requests as _req
        groq_key = os.environ.get('GROQ_API_KEY', '')

        if groq_key:
            try:
                r = _req.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {groq_key}',
                        'Content-Type':  'application/json'
                    },
                    json={
                        'model': 'meta-llama/llama-4-scout-17b-16e-instruct',
                        'messages': [{
                            'role': 'user',
                            'content': [
                                {
                                    'type': 'text',
                                    'text': (
                                        'Analiza esta imagen en detalle para entrenamiento de IA generativa.\n'
                                        'Responde SOLO en JSON con este formato exacto (sin markdown, sin texto extra):\n'
                                        '{\n'
                                        '  "prompt": "descripción detallada en inglés para generar algo similar",\n'
                                        '  "tags": ["tag1", "tag2", "tag3"],\n'
                                        '  "colores": ["color1", "color2"],\n'
                                        '  "composicion": "descripción de la composición visual",\n'
                                        '  "notas_tecnicas": "parámetros matemáticos, gradientes, texturas, iluminación"\n'
                                        '}'
                                    )
                                },
                                {
                                    'type':      'image_url',
                                    'image_url': {'url': f'data:image/jpeg;base64,{b64}'}
                                }
                            ]
                        }],
                        'max_tokens': 700,
                    },
                    timeout=30
                )
                if r.status_code == 200:
                    import json as _json
                    content = r.json()['choices'][0]['message']['content']
                    start = content.find('{')
                    end   = content.rfind('}') + 1
                    if start >= 0 and end > start:
                        parsed          = _json.loads(content[start:end])
                        prompt_generado = parsed.get('prompt', '').strip()
                        tags_ia         = parsed.get('tags', [])
                        colores         = parsed.get('colores', [])
                        composicion     = parsed.get('composicion', '')
                        notas_tecnicas  = f"Colores: {', '.join(colores)}. Composición: {composicion}. {parsed.get('notas_tecnicas', '')}"
                else:
                    logger.warning(f'[training/analyze] Groq Vision HTTP {r.status_code}: {r.text[:200]}')
            except Exception as ve:
                logger.warning(f'[training/analyze] Groq Vision error: {ve}')

        # Si no se pudo analizar con IA, usar nombre de archivo como fallback
        if not prompt_generado:
            prompt_generado = filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ')
            notas_tecnicas  = f'Imagen subida manualmente sin análisis IA: {filename}'
            tags_ia         = []
            logger.info(f'[training/analyze] Fallback a nombre de archivo: {prompt_generado!r}')

        # Guardar en BD
        from .cicdream import get_feedback
        from flask import current_app
        db = current_app.extensions['sqlalchemy'].engine
        fb = get_feedback(db)

        full_prompt = prompt_generado
        if notas_tecnicas:
            full_prompt = f"{prompt_generado}. Notas: {notas_tecnicas[:300]}"

        gen_id = fb.save_generation(
            user_id  = user.id,
            prompt   = full_prompt,
            style    = style,
            size     = 'square',
            quality  = 'standard',
            generation_result = {
                'provider': 'Mass Training',
                'engine':   'manual_analyze',
                'seed': 0, 'steps': 0, 'guidance': 7.5, 'time_ms': 0,
                'filename': filename,
            },
        )

        if gen_id:
            fb.submit(
                generation_id = gen_id,
                user_id       = user.id,
                rating        = rating,
                details       = notas_tecnicas or '',
                tags          = tags_ia,
            )
            logger.info(f'[training/analyze] Guardado gen_id={gen_id} file={filename!r} prompt={prompt_generado[:60]!r}')

        return jsonify({
            'success':         True,
            'generation_id':   gen_id,
            'prompt_extraido': prompt_generado,
            'tags':            tags_ia,
            'filename':        filename,
            'analyzed_by_ai':  bool(groq_key and prompt_generado and 'Imagen subida' not in prompt_generado),
        })

    except Exception as e:
        logger.error(f'[training/analyze] Error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# DATASET EXPORT
# ══════════════════════════════════════════════════════════════════════════

@bp.route('/dataset/export', methods=['GET'])
def dataset_export():
    """
    Exporta el dataset de imágenes con feedback para entrenar CicDream.
    Usado por el notebook de Colab y el panel de CicDream Studio.

    Query params:
        min_rating  (float) — rating mínimo para filtrar (default: 0)
        limit       (int)   — máximo de registros (default: 2000)
    """
    try:
        user = _get_current_user()

        from flask import current_app
        from sqlalchemy import text
        db = current_app.extensions['sqlalchemy'].engine

        if not _is_developer(user.id, db):
            return jsonify({'error': 'Solo desarrolladores pueden exportar el dataset'}), 403

        # Parámetros de filtrado
        try:
            min_rating = float(request.args.get('min_rating', 0))
        except (ValueError, TypeError):
            min_rating = 0.0
        try:
            limit = min(int(request.args.get('limit', 2000)), 5000)
        except (ValueError, TypeError):
            limit = 2000

        from .cicdream import get_feedback
        fb = get_feedback(db)

        with db.connect() as conn:
            rows = conn.execute(text("""
                SELECT
                    g.id, g.prompt, g.style, g.size, g.quality,
                    g.created_at,
                    COALESCE(AVG(f.rating), 0) as rating,
                    STRING_AGG(COALESCE(f.details, ''), ' | ') as details
                FROM cicdream_generation g
                LEFT JOIN cicdream_feedback f ON f.generation_id = g.id
                GROUP BY g.id, g.prompt, g.style, g.size, g.quality, g.created_at
                HAVING COALESCE(AVG(f.rating), 0) >= :min_r
                ORDER BY rating DESC, g.created_at DESC
                LIMIT :lim
            """), {'min_r': min_rating, 'lim': limit}).fetchall()

        dataset = []
        for row in rows:
            dataset.append({
                'id':         row[0],
                'prompt':     row[1],
                'style':      row[2],
                'size':       row[3],
                'quality':    row[4],
                'created_at': str(row[5]),
                'rating':     round(float(row[6]) if row[6] else 0.0, 2),
                'details':    row[7] or '',
                'tags':       [],
            })

        total = len(dataset)
        good  = [d for d in dataset if d['rating'] >= 3.5]
        ready = len(good) >= 10

        return jsonify({
            'success':            True,
            'total':              total,
            'ready_for_training': ready,
            'min_rating_filter':  min_rating,
            'dataset':            dataset,
            'message':            f'{total} registros encontrados, {len(good)} con rating ≥ 3.5',
        })

    except PermissionError as e:
        return jsonify({'error': str(e)}), 401
    except Exception as e:
        logger.error(f'[dataset/export] Error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@bp.route('/register-external', methods=['POST'])
def register_external():
    """
    Registra en la BD una imagen generada en el navegador (ej. Pollinations
    llamado browser-side por las restricciones de Render free tier).

    Esto permite que el feedback funcione SIEMPRE, incluso cuando el motor
    no pasa por el backend: devuelve un generation_id que el frontend usa
    para enviar el rating y que CicDream pueda aprender.

    FIX v2.3: usa SQL directo en vez de cicdream.save_generation()
    para evitar dependencias frágiles. Inserta directo en cicdream_generation.
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    data    = request.get_json(force=True, silent=True) or {}
    prompt  = (data.get('prompt') or '').strip()
    style   = data.get('style',   'realistic')
    size    = data.get('size',    'square')
    quality = data.get('quality', 'standard')
    engine  = data.get('engine',  'pollinations_browser')
    provider= data.get('provider', engine)

    if not prompt:
        return jsonify({'success': False, 'error': 'prompt requerido'}), 400

    try:
        from flask import current_app
        from sqlalchemy import text
        db = current_app.extensions['sqlalchemy'].engine

        # Asegurar que la tabla existe (idempotente, no falla si ya existe)
        with db.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cicdream_generation (
                    id          SERIAL PRIMARY KEY,
                    user_id     INTEGER NOT NULL,
                    prompt      TEXT NOT NULL,
                    style       VARCHAR(50),
                    size        VARCHAR(50),
                    quality     VARCHAR(50),
                    provider    VARCHAR(100),
                    engine      VARCHAR(100),
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        # INSERT directo - sin pasar por cicdream.py
        with db.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO cicdream_generation (user_id, prompt, style, size, quality, provider, engine, created_at)
                VALUES (:uid, :prompt, :style, :size, :quality, :provider, :engine, CURRENT_TIMESTAMP)
                RETURNING id
            """), {
                'uid': user.id, 'prompt': prompt[:2000],
                'style': style[:50], 'size': size[:50], 'quality': quality[:50],
                'provider': provider[:100], 'engine': engine[:100],
            }).fetchone()

        gen_id = row[0] if row else None

        if gen_id:
            logger.info(f'[register-external] ✅ gen_id={gen_id} engine={engine} user={user.username} prompt={prompt[:50]!r}')
            return jsonify({'success': True, 'generation_id': gen_id})
        else:
            logger.error(f'[register-external] INSERT no retornó ID')
            return jsonify({'success': False, 'error': 'INSERT no retornó ID'}), 500

    except Exception as e:
        logger.error(f'[register-external] Error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


def register(app):
    app.register_blueprint(bp)
    logger.info('Rutas /api/image/* registradas (v2.2 — CicDream dataset + external register)')
