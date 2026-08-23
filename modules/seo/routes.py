"""
modules/seo/routes.py
======================
CicSEO Intelligence — Blueprint SEO multiplataforma.
Endpoints para gestión de canales, optimización de contenido,
análisis de keywords, calendario y chat SEO con IA.

Plataformas: YouTube, Instagram, TikTok, WordPress, Blog/Web, X/Twitter
La IA aprende el nicho de cada canal automáticamente.
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from sqlalchemy import text
import logging

logger = logging.getLogger('cic_ia.seo')
logger.info('═══ [seo] routes.py iniciando carga ═══')

bp = Blueprint('seo', __name__, url_prefix='/api/seo')
logger.info('[seo] Blueprint creado con prefix=/api/seo')

# ── Auth helper (mismo patrón que image_generator) ──────────────────────────

def _get_current_user():
    """Verifica token contra BD — mismo mecanismo que token_required en el main."""
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

    db  = current_app.extensions['sqlalchemy']
    eng = db.engine

    with eng.connect() as conn:
        row = conn.execute(
            text("""
                SELECT us.user_id, us.expires_at, u.username, u.is_active, u.is_developer
                FROM user_session us
                JOIN "user" u ON u.id = us.user_id
                WHERE us.token = :token
            """),
            {'token': token}
        ).fetchone()

    if not row:
        raise PermissionError('Token inválido')
    if row.expires_at and row.expires_at < datetime.utcnow():
        raise PermissionError('Token expirado')
    if not row.is_active:
        raise PermissionError('Usuario inactivo')

    return {'id': row.user_id, 'username': row.username, 'is_developer': row.is_developer}


# ── DB helper ────────────────────────────────────────────────────────────────

def _db():
    return current_app.extensions['sqlalchemy'].engine


def _ensure_tables():
    """Crea las tablas SEO si no existen — safe, no toca tablas existentes."""
    with _db().connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS seo_channel (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                url        VARCHAR(500) NOT NULL,
                platform   VARCHAR(50),
                niche      VARCHAR(200),
                label      VARCHAR(200),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS seo_result (
                id          SERIAL PRIMARY KEY,
                channel_id  INTEGER NOT NULL,
                result_type VARCHAR(100),
                content_in  TEXT,
                result_out  TEXT,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()
    logger.info('[seo] Tablas verificadas/creadas OK')


# ── Platform helpers ─────────────────────────────────────────────────────────

def _detect_platform(url: str) -> str:
    if not url:
        return 'web'
    u = url.lower()
    if 'youtube.com' in u or 'youtu.be' in u:
        return 'youtube'
    if 'instagram.com' in u:
        return 'instagram'
    if 'tiktok.com' in u:
        return 'tiktok'
    if 'wordpress.com' in u or 'wp-content' in u:
        return 'wordpress'
    if 'twitter.com' in u or 'x.com' in u:
        return 'x'
    if u.startswith('@') and len(u) < 40:
        return 'instagram'
    return 'web'


def _platform_label(p: str) -> str:
    return {
        'youtube':   'YouTube',
        'instagram': 'Instagram',
        'tiktok':    'TikTok',
        'wordpress': 'WordPress',
        'x':         'X/Twitter',
        'web':       'Blog/Web',
    }.get(p, p)


# ── LLM helper ───────────────────────────────────────────────────────────────

SEO_SYSTEM = """Eres CicSEO Intelligence, experto en SEO y estrategia de contenido multiplataforma.
No tienes nicho fijo: aprendes y te adaptas automáticamente al canal y contexto de cada usuario.
Plataformas: YouTube, Instagram, TikTok, WordPress, blogs, X/Twitter, cualquier sitio web.
Responde SIEMPRE en español. Sé específico y usa datos concretos, no genérico.
Formato: usa ### para secciones principales, **negrita** para términos clave, listas con -.
Siempre termina con: 🎯 Acción inmediata: [la acción concreta más importante]."""


def _seo_llm(prompt: str, history: list = None, max_tokens: int = 2000) -> str:
    """
    Llama directamente a Groq o Anthropic con el system prompt de SEO.
    Cascada: Groq → Anthropic → error claro.
    """
    import os, requests as _requests

    messages = [{'role': 'system', 'content': SEO_SYSTEM}]
    for h in (history or [])[-10:]:
        role = h.get('role', 'user')
        content = h.get('content', '')
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': prompt})

    # ── Intento 1: Groq ──────────────────────────────────────────────────────
    groq_key = os.environ.get('GROQ_API_KEY', '')
    if groq_key:
        try:
            groq_model = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
            resp = _requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {groq_key}', 'Content-Type': 'application/json'},
                json={'model': groq_model, 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0.7},
                timeout=60
            )
            resp.raise_for_status()
            text = resp.json()['choices'][0]['message']['content']
            logger.info(f'[seo] Groq OK ({groq_model})')
            return text
        except Exception as e:
            logger.warning(f'[seo] Groq falló: {e} — intentando Anthropic')

    # ── Intento 2: Anthropic ─────────────────────────────────────────────────
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if anthropic_key:
        try:
            # Separar system del resto para Anthropic
            user_msgs = [m for m in messages if m['role'] != 'system']
            resp = _requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': anthropic_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                },
                json={
                    'model': 'claude-haiku-4-5-20251001',
                    'max_tokens': max_tokens,
                    'system': SEO_SYSTEM,
                    'messages': user_msgs
                },
                timeout=60
            )
            resp.raise_for_status()
            text = resp.json()['content'][0]['text']
            logger.info('[seo] Anthropic OK')
            return text
        except Exception as e:
            logger.warning(f'[seo] Anthropic falló: {e}')

    raise RuntimeError('Sin motor de IA disponible. Configura GROQ_API_KEY o ANTHROPIC_API_KEY en Render → Environment.')


# ── Prompts de optimización ──────────────────────────────────────────────────

def _opt_prompt(opt_type: str, content: str, platform: str, niche: str, url: str) -> str:
    plat = _platform_label(platform)
    base = f"Canal/sitio: {url}\nPlataforma: {plat}\nNicho: {niche}\n\nContenido del usuario:\n---\n{content}\n---\n\n"

    prompts = {
        # ── YouTube ──────────────────────────────────────────────────────────
        'yt_full': base + """Optimiza para YouTube. Entrega con estas etiquetas exactas:

[TÍTULO]
El mejor título (máx 70 chars, keyword principal, genera curiosidad)

[TÍTULO ALT 1]
Segunda opción con ángulo diferente

[TÍTULO ALT 2]
Tercera opción más directa

[DESCRIPCIÓN]
Descripción completa:
- Primeras 2 líneas con keyword principal (aparecen sin expandir)
- Cuerpo de 150-200 palabras con keywords integradas naturalmente
- Timestamps sugeridos si aplica
- CTA al final

[TAGS]
15 tags separados por coma (específicos + generales + variaciones)

[SCORE CTR]
Estimado: X/100 — razón en 1 línea

🎯 Acción inmediata: el elemento más importante para el alcance de este video.""",

        'yt_title': base + """Genera 5 títulos YouTube optimizados (máx 70 chars cada uno).

Para cada título:
**Título X:** [texto]
- Score CTR: X/100
- Keyword usada
- Por qué funciona (1 línea)

**Título recomendado:** el mejor y por qué.

🎯 Acción inmediata: el título exacto a usar.""",

        'yt_desc': base + """Escribe la descripción completa optimizada para YouTube.

**Primeras 2 líneas (críticas — aparecen sin expandir):**
[texto con keyword + gancho]

**Cuerpo principal (150-200 palabras):**
[contenido natural con keywords integradas]

**Hashtags de descripción:** #tag1 #tag2 #tag3

**CTA final:** [llamado a la acción]

Keywords usadas: [lista al final]

🎯 Acción inmediata: la frase más importante de las primeras 2 líneas.""",

        'yt_tags': base + """Genera estrategia completa de tags para YouTube.

**Tags principales (keyword exacta):** [5 tags]
**Tags de nicho:** [5 tags relacionados]
**Tags long-tail:** [5 frases completas]
**Tags de canal/marca:** [3 tags]

**Copia directa (15 tags separados por coma):**
[todos listos para pegar en YouTube]

🎯 Acción inmediata: el tag más importante para rankear.""",

        'yt_hook': base + """Escribe el hook de apertura del video (primeros 30-60 segundos).

**Hook visual:** [qué mostrar en pantalla]
**Script de apertura (3 oraciones exactas):** [texto]
**Promesa del video:** [qué gana el espectador si sigue viendo]
**Pattern interrupt:** [elemento sorpresa o contraintuitivo]
**Transición al contenido:** [cómo conectar con el desarrollo]

Duración recomendada del hook: X segundos

🎯 Acción inmediata: la primera oración exacta con la que abres el video.""",

        'yt_thumb': base + """Diseña el concepto de thumbnail.

**Concepto visual:** [descripción detallada]
**Texto en thumbnail (máx 4 palabras):** [texto + color + posición]
**Elementos:** [primer plano / fondo / expresión / color dominante]
**Referencias de thumbnails exitosos en este nicho:** [2-3 estilos]
**Score CTR estimado:** X/100

🎯 Acción inmediata: el elemento más importante del thumbnail para maximizar clics.""",

        # ── Instagram ─────────────────────────────────────────────────────────
        'ig_full': base + """Optimiza para Instagram. Entrega con etiquetas:

[HOOK]
Primera línea del caption (máx 125 chars — corta en "... más")

[CAPTION]
Caption completo con saltos de línea, emojis estratégicos y CTA

[HASHTAGS NICHO]
5 hashtags exactos (10k-200k posts)

[HASHTAGS MEDIOS]
10 hashtags intermedios (200k-1M posts)

[HASHTAGS ALCANCE]
5 hashtags de alto alcance (+1M posts)

[HORARIO]
Mejor día y hora para publicar en este nicho

[SCORE]
Engagement estimado: X/100 — razón

🎯 Acción inmediata: el cambio más importante para maximizar alcance.""",

        'ig_hook': base + """5 hooks para caption de Instagram (máx 125 chars cada uno).

Para cada hook:
**Hook X:** [texto exacto]
- Técnica: [curiosidad/controversia/utilidad/pregunta]
- Score stop-scrolling: X/10

**Hook recomendado:** el mejor y por qué.

🎯 Acción inmediata: el hook exacto a usar.""",

        'ig_hash': base + """Estrategia completa de hashtags Instagram.

**Nicho exacto (10k-200k):** [10 hashtags]
**Intermedios (200k-800k):** [10 hashtags]
**Alcance (800k-3M):** [5 hashtags]
**Comunidad:** [5 hashtags de grupos activos]

**Set de 30 hashtags para copiar:**
[todos juntos]

**Hashtags a EVITAR:** [3-5 saturados o shadowbanned]

🎯 Acción inmediata: los 5 hashtags de nicho más importantes.""",

        'ig_reel': base + """Script y estructura para Reel de Instagram.

**Hook visual (0-3s):** [qué mostrar]
**Texto en pantalla (0-3s):** [máx 5 palabras]

**Script:**
[00:00-00:03] Hook
[00:03-00:15] Punto 1
[00:15-00:30] Punto 2
[00:30-00:45] Punto 3 + CTA

**Audio recomendado:** [tipo/tendencia]
**Caption del Reel:** [texto completo]
**Hashtags:** [set optimizado]

🎯 Acción inmediata: el formato de Reel con mayor alcance esta semana en este nicho.""",

        # ── TikTok ────────────────────────────────────────────────────────────
        'tt_full': base + """Optimiza para TikTok. Entrega con etiquetas:

[CAPTION]
Caption (máx 150 chars — conciso, emoji, keyword, CTA)

[HASHTAGS]
#hashtag1 #hashtag2 ... (8-10 tags: nicho + trending + masivos)

[HOOK VISUAL]
Descripción exacta de los primeros 3 segundos en pantalla

[TEXTO EN PANTALLA]
Overlays de texto clave durante el video

[SONIDO]
Tipo de audio/sonido trending recomendado

[SCORE]
Potencial viral: X/100 — razón principal

🎯 Acción inmediata: el elemento más importante para el algoritmo de TikTok.""",

        'tt_script': base + """Script completo para TikTok.

**Duración recomendada:** X segundos

[00:00-00:03] HOOK — [texto exacto + acción visual]
[00:03-00:15] PUNTO 1 — [texto + acción]
[00:15-00:35] DESARROLLO — [texto + acción]
[00:35-00:50] GIRO/VALOR — [momento más compartible]
[00:50-00:60] CTA — [texto exacto del cierre]

**Textos en pantalla (overlays):** [lista]
**Audio recomendado:** [tipo]

🎯 Acción inmediata: el segundo del video más crítico para la retención.""",

        # ── WordPress / Blog ──────────────────────────────────────────────────
        'wp_full': base + """Optimiza para WordPress/SEO. Entrega con etiquetas:

[META TÍTULO]
Título SEO (máx 60 chars — keyword + modificador)

[META DESCRIPCIÓN]
Meta desc (máx 155 chars — keyword + propuesta de valor + CTA implícito)

[SLUG]
/slug-url-optimizado

[H1]
Título principal del post

[ESTRUCTURA]
H2: Sección 1
  H3: Subsección
H2: Sección 2
  H3: Subsección
[estructura completa]

[KEYWORD PRINCIPAL]
Keyword + densidad recomendada

[KEYWORDS SECUNDARIAS]
5-8 LSI keywords

[EXCERPT]
Extracto (máx 160 chars)

[SCHEMA]
Tipo de Schema markup recomendado

🎯 Acción inmediata: el elemento SEO más importante para rankear este post.""",

        'wp_struct': base + """Estructura de contenido para post WordPress.

**H1:** [título optimizado]

**Introducción:** [keyword en primeras 100 palabras]

**Estructura H2/H3 completa:**
H2: [sección 1]
  H3: [subsección]
H2: [sección 2]
  H3: [subsección]
[continuar]

H2: FAQ
  - Pregunta / Respuesta
  - Pregunta / Respuesta

**Longitud recomendada:** X palabras
**Imágenes:** [dónde y qué mostrar]

🎯 Acción inmediata: la sección más importante para el posicionamiento.""",

        'wp_meta': base + """Meta tags completos para WordPress.

**Meta título:** [máx 60 chars]
**Meta descripción:** [máx 155 chars]
**Slug:** /url
**Focus keyword:** [keyword]
**Keywords secundarias:** [lista]

**Open Graph:**
og:title: [título para redes]
og:description: [descripción para redes]
og:image alt: [descripción de imagen]

**Checklist Yoast/RankMath:**
✅/❌ [cada punto SEO]

🎯 Acción inmediata: el meta dato más crítico para el CTR en Google.""",

        # ── Web general ───────────────────────────────────────────────────────
        'web_full': base + """SEO on-page completo para esta página web.

[META TÍTULO] (máx 60 chars)
[META DESCRIPCIÓN] (máx 155 chars)
[SLUG] /url-recomendada
[H1] Título principal
[ESTRUCTURA] H2/H3 completa
[KEYWORDS] Principal + 5 secundarias
[SCHEMA] Tipo de markup recomendado
[SCORE] Estimado: X/100 con las optimizaciones

🎯 Acción inmediata: el cambio más impactante para rankear en Google.""",

        # ── X / Twitter ───────────────────────────────────────────────────────
        'x_thread': base + """Thread de X/Twitter optimizado.

**Tweet 1 (hook):** [gancho — máx 280 chars]
**Tweet 2:** [punto clave 1]
**Tweet 3:** [punto clave 2]
**Tweet 4:** [dato sorprendente]
**Tweet 5:** [acción práctica]
**Tweet 6 (cierre):** [resumen + CTA]

**Hashtags:** [máx 2-3 al final del último tweet]
**Mejor hora:** [cuándo publicar]

🎯 Acción inmediata: el tweet de apertura exacto.""",

        'x_tweet': base + """5 tweets virales sobre este contenido (máx 280 chars cada uno).

Para cada tweet:
**Tweet X:** [texto exacto]
- Técnica: [gancho/utilidad/controversia/dato]
- Score viral: X/10

**Tweet recomendado:** el mejor y por qué.

🎯 Acción inmediata: el tweet exacto a publicar hoy.""",
    }

    return prompts.get(
        opt_type,
        base + f"""Optimiza este contenido para {plat} con las mejores prácticas SEO actuales.
Incluye todos los metadatos, textos y recomendaciones necesarias para maximizar alcance y posicionamiento.

🎯 Acción inmediata: el cambio más importante."""
    )


# ── Prompts de análisis ──────────────────────────────────────────────────────

def _analysis_prompt(analysis_type: str, url: str, platform: str, niche: str) -> str:
    plat = _platform_label(platform)

    prompts = {
        'full': f"""Haz un análisis SEO completo del canal/sitio:
URL: {url} | Plataforma: {plat} | Nicho: {niche}

### 1. Detección de nicho y audiencia
Detecta el nicho exacto, subnicho y perfil de audiencia ideal.

### 2. Score SEO actual (0-100)
Evalúa: optimización de títulos, consistencia de contenido, potencial de crecimiento, competencia.

### 3. Top 10 keywords de oportunidad
Formato: [keyword] | vol:alto/medio/bajo | comp:alta/media/baja | score:X/100

### 4. Análisis de competencia
3-5 competidores directos con puntos fuertes y débiles.

### 5. Gaps de contenido detectados
Temas que la competencia NO cubre bien y este canal puede dominar.

### 6. 5 acciones prioritarias ordenadas por impacto

🎯 Acción inmediata: la UNA cosa que cambia más el algoritmo en los próximos 7 días.""",

        'keywords': f"""Investiga keywords para:
URL: {url} | Plataforma: {plat} | Nicho: {niche}

### Keywords principales (alta oportunidad — 15 keywords)
[keyword] | vol:X | comp:X | score:X/100 | por qué sirve

### Keywords long-tail (10 keywords)
Muy específicas, fácil de rankear, intención clara.

### Keywords en tendencia AHORA (5 keywords)
Términos que están subiendo esta semana en {plat}.

### Keywords a EVITAR (3-5)
Saturadas o irrelevantes para este canal.

### Estrategia de distribución
Cómo usar estas keywords en el próximo mes.

🎯 Acción inmediata: el tema con mayor potencial para publicar esta semana.""",

        'calendar': f"""Crea un calendario de contenido de 30 días para:
URL: {url} | Plataforma: {plat} | Nicho: {niche}

### Semana 1 — Establecer autoridad
Lun / Mié / Vie: [tema] | [keyword] | [formato] | [hora ideal]

### Semana 2 — Superar a la competencia
Contenido que supere a los competidores en sus temas más fuertes.

### Semana 3 — Tendencia
Temas en alza esta semana con oportunidad de posicionamiento rápido.

### Semana 4 — Consolidación
Reforzar los temas de mayor rendimiento.

### Reglas del algoritmo de {plat} ahora mismo
Qué está priorizando el algoritmo y cómo aprovecharlo.

🎯 Acción inmediata: el contenido que deberías publicar HOY.""",

        'algo': f"""Analiza el estado actual del algoritmo de {plat} para el nicho "{niche}".

### Estado actual del algoritmo
Cambios recientes y qué tipo de contenido está priorizando HOY.

### Señales de alerta para este nicho
Cambios que afectan directamente al nicho "{niche}".

### Oportunidades detectadas ahora mismo
Temas, formatos o keywords que están subiendo esta semana.

### Comparación con hace 3 meses
Qué funcionaba antes y ya no. Qué es nuevo.

### Métricas clave a monitorear
Las 5 métricas más importantes para este canal en {plat}.

### Predicción próximas 4 semanas
Qué se espera basado en el patrón histórico del algoritmo.

🎯 Acción inmediata: el cambio de estrategia más urgente para mantener/mejorar el alcance.""",
    }

    return prompts.get(analysis_type, prompts['full'])


# ============================================================
# ENDPOINTS
# ============================================================

@bp.route('/channels', methods=['GET'])
def seo_get_channels():
    """Lista los canales SEO del usuario autenticado."""
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'error': str(e)}), 401

    with _db().connect() as conn:
        rows = conn.execute(
            text("SELECT id, url, platform, niche, label, created_at FROM seo_channel WHERE user_id = :uid ORDER BY created_at DESC"),
            {'uid': user['id']}
        ).fetchall()

    return jsonify({'channels': [{
        'id':       r.id,
        'url':      r.url,
        'platform': r.platform,
        'niche':    r.niche,
        'label':    r.label,
        'created':  r.created_at.isoformat() if r.created_at else ''
    } for r in rows]})


@bp.route('/channels', methods=['POST'])
def seo_add_channel():
    """Agrega un canal/sitio SEO al usuario."""
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'error': str(e)}), 401

    data  = request.json or {}
    url   = data.get('url', '').strip()
    niche = data.get('niche', '').strip() or 'Auto-detectar'

    if not url:
        return jsonify({'error': 'URL es requerida'}), 400

    platform = _detect_platform(url)
    label    = url.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]

    with _db().connect() as conn:
        row = conn.execute(
            text("""
                INSERT INTO seo_channel (user_id, url, platform, niche, label, created_at)
                VALUES (:uid, :url, :plat, :niche, :label, NOW())
                RETURNING id
            """),
            {'uid': user['id'], 'url': url, 'plat': platform, 'niche': niche, 'label': label}
        ).fetchone()
        conn.commit()

    return jsonify({
        'success': True,
        'channel': {
            'id': row.id, 'url': url, 'platform': platform,
            'niche': niche, 'label': label
        }
    })


@bp.route('/channels/<int:cid>', methods=['DELETE'])
def seo_delete_channel(cid):
    """Elimina un canal SEO del usuario."""
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'error': str(e)}), 401

    with _db().connect() as conn:
        result = conn.execute(
            text("DELETE FROM seo_channel WHERE id = :id AND user_id = :uid"),
            {'id': cid, 'uid': user['id']}
        )
        conn.commit()

    if result.rowcount == 0:
        return jsonify({'error': 'Canal no encontrado'}), 404

    return jsonify({'success': True})


@bp.route('/optimize', methods=['POST'])
def seo_optimize():
    """
    Optimiza contenido para una plataforma específica.
    El usuario pega su texto + elige el tipo de optimización.
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'error': str(e)}), 401

    data       = request.json or {}
    channel_id = data.get('channel_id')
    opt_type   = data.get('opt_type', 'web_full')
    content    = data.get('content', '').strip()
    extra      = data.get('extra', '').strip()

    if not content:
        return jsonify({'error': 'content es requerido'}), 400

    # Obtener canal
    platform = 'web'
    niche    = 'general'
    url      = 'sin canal definido'

    if channel_id:
        with _db().connect() as conn:
            ch = conn.execute(
                text("SELECT url, platform, niche FROM seo_channel WHERE id = :id AND user_id = :uid"),
                {'id': channel_id, 'uid': user['id']}
            ).fetchone()
            if ch:
                url      = ch.url
                platform = ch.platform
                niche    = ch.niche

    prompt = _opt_prompt(opt_type, content, platform, niche, url)
    if extra:
        prompt += f"\n\nInstrucción adicional del usuario: {extra}"

    try:
        result = _seo_llm(prompt, max_tokens=2000)

        # Guardar resultado
        if channel_id:
            with _db().connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO seo_result (channel_id, result_type, content_in, result_out, created_at)
                        VALUES (:cid, :rtype, :cin, :cout, NOW())
                    """),
                    {'cid': channel_id, 'rtype': opt_type,
                     'cin': content[:1000], 'cout': result[:5000]}
                )
                conn.commit()

        return jsonify({'success': True, 'result': result, 'opt_type': opt_type})

    except Exception as e:
        logger.error(f'[seo] optimize error: {e}')
        return jsonify({'error': str(e)}), 500


@bp.route('/analyze', methods=['POST'])
def seo_analyze():
    """
    Análisis completo del canal: keywords, competencia, calendario, algoritmo.
    type: full | keywords | calendar | algo
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'error': str(e)}), 401

    data          = request.json or {}
    channel_id    = data.get('channel_id')
    analysis_type = data.get('type', 'full')
    history       = data.get('history', [])

    if not channel_id:
        return jsonify({'error': 'channel_id es requerido'}), 400

    with _db().connect() as conn:
        ch = conn.execute(
            text("SELECT url, platform, niche FROM seo_channel WHERE id = :id AND user_id = :uid"),
            {'id': channel_id, 'uid': user['id']}
        ).fetchone()

    if not ch:
        return jsonify({'error': 'Canal no encontrado'}), 404

    prompt = _analysis_prompt(analysis_type, ch.url, ch.platform, ch.niche)

    try:
        result = _seo_llm(prompt, history=history, max_tokens=2000)

        with _db().connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO seo_result (channel_id, result_type, content_in, result_out, created_at)
                    VALUES (:cid, :rtype, '', :cout, NOW())
                """),
                {'cid': channel_id, 'rtype': f'analyze_{analysis_type}', 'cout': result[:5000]}
            )
            conn.commit()

        return jsonify({'success': True, 'result': result})

    except Exception as e:
        logger.error(f'[seo] analyze error: {e}')
        return jsonify({'error': str(e)}), 500


@bp.route('/chat', methods=['POST'])
def seo_chat():
    """Chat SEO libre con contexto del canal activo."""
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'error': str(e)}), 401

    data       = request.json or {}
    message    = data.get('message', '').strip()
    channel_id = data.get('channel_id')
    history    = data.get('history', [])

    if not message:
        return jsonify({'error': 'message es requerido'}), 400

    # Contexto del canal
    ctx = ''
    if channel_id:
        with _db().connect() as conn:
            ch = conn.execute(
                text("SELECT url, platform, niche FROM seo_channel WHERE id = :id AND user_id = :uid"),
                {'id': channel_id, 'uid': user['id']}
            ).fetchone()
            if ch:
                ctx = f"\n[Contexto activo: canal '{ch.url}', plataforma {_platform_label(ch.platform)}, nicho: {ch.niche}]"

    try:
        result = _seo_llm(message + ctx, history=history, max_tokens=1500)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        logger.error(f'[seo] chat error: {e}')
        return jsonify({'error': str(e)}), 500


@bp.route('/history/<int:cid>', methods=['GET'])
def seo_history(cid):
    """Historial de resultados de un canal."""
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'error': str(e)}), 401

    # Verificar que el canal pertenece al usuario
    with _db().connect() as conn:
        ch = conn.execute(
            text("SELECT id FROM seo_channel WHERE id = :id AND user_id = :uid"),
            {'id': cid, 'uid': user['id']}
        ).fetchone()

        if not ch:
            return jsonify({'error': 'Canal no encontrado'}), 404

        rows = conn.execute(
            text("""
                SELECT id, result_type, content_in, result_out, created_at
                FROM seo_result
                WHERE channel_id = :cid
                ORDER BY created_at DESC
                LIMIT 20
            """),
            {'cid': cid}
        ).fetchall()

    return jsonify({'history': [{
        'id':         r.id,
        'type':       r.result_type,
        'content_in': (r.content_in or '')[:200],
        'preview':    (r.result_out or '')[:300],
        'created':    r.created_at.isoformat() if r.created_at else ''
    } for r in rows]})


# ── Inicialización del blueprint ─────────────────────────────────────────────

@bp.record_once
def _on_register(state):
    """Se ejecuta una vez cuando el blueprint se registra en la app."""
    with state.app.app_context():
        try:
            _ensure_tables()
            logger.info('✅ [seo] Tablas SEO inicializadas correctamente')
        except Exception as e:
            logger.warning(f'⚠️ [seo] Error inicializando tablas: {e}')


logger.info('═══ [seo] routes.py cargado OK ═══')

# ── Prompts de competencia (agregar al dict de _analysis_prompt) ─────────────
# Estos tipos se agregan como casos en _analysis_prompt:

_COMPETE_PROMPTS = {
    'compete_auto': """Detecta automáticamente los 5 principales competidores de este canal/sitio:
URL: {url} | Plataforma: {plat} | Nicho: {niche}

### Competidores detectados
Para cada competidor:
**Competidor X:** [nombre/URL]
- Fortalezas: [qué hace bien]
- Debilidades: [dónde falla]
- Keywords principales: [3-5 keywords que dominan]
- Frecuencia de publicación: [estimado]
- Score de amenaza: X/10

### Resumen de la competencia
Nivel general de competencia en este nicho: [alto/medio/bajo]
El competidor más peligroso y por qué.

🎯 Acción inmediata: el cambio más urgente para diferenciarte de la competencia.""",

    'compete_gaps': """Encuentra los gaps de contenido que la competencia NO cubre para:
URL: {url} | Plataforma: {plat} | Nicho: {niche}

### Gaps de contenido detectados (oportunidades reales)
Para cada gap:
**Gap X:** [tema o tipo de contenido]
- Por qué la competencia lo ignora
- Potencial de audiencia: alto/medio/bajo
- Dificultad para crear: alta/media/baja
- Urgencia: [publicar esta semana / este mes / a largo plazo]

### Top 3 gaps prioritarios
Los 3 temas con mayor potencial de posicionamiento inmediato.

### Formato recomendado para cada gap
Qué tipo de contenido funciona mejor para cada oportunidad.

🎯 Acción inmediata: el gap que deberías cubrir HOY para ganar terreno rápido.""",

    'compete_keywords': """Analiza las keywords que usa la competencia en este nicho:
URL: {url} | Plataforma: {plat} | Nicho: {niche}

### Keywords que la competencia domina (pero tú puedes robarles)
[keyword] | quién la domina | vol:X | dificultad:X | estrategia para superarlos

### Keywords que la competencia ignora
[keyword] | vol:X | por qué es una oportunidad | cómo posicionarte primero

### Keywords donde ya puedes competir ahora
[keyword] | competencia actual débil | cómo atacar esta semana

### Mapa de keywords de la competencia
Visión general de cómo están distribuidas las keywords entre los competidores.

🎯 Acción inmediata: la keyword exacta que puedes rankear antes que la competencia.""",

    'compete_strategy': """Crea un plan estratégico completo para superar a la competencia:
URL: {url} | Plataforma: {plat} | Nicho: {niche}

### Análisis de posición actual
Dónde estás vs la competencia en este momento.

### Estrategia de diferenciación
Qué hace único a este canal y cómo potenciarlo.

### Plan de ataque — 90 días
**Mes 1:** [acciones concretas para establecer presencia]
**Mes 2:** [acciones para ganar terreno]
**Mes 3:** [acciones para superar a los rivales]

### Tácticas específicas por plataforma
Qué hace {plat} que puedes usar para adelantar a la competencia ahora.

### Métricas para medir el progreso
Las 5 métricas que confirmarán que estás superando a la competencia.

🎯 Acción inmediata: la UNA acción esta semana que más daño hace a la competencia.""",

    'compete_specific': """Analiza este competidor específico vs mi canal:
Mi canal: {url} | Plataforma: {plat} | Nicho: {niche}
Competidor a analizar: {competitor_url}

### Perfil del competidor
- Tipo de contenido que publica
- Frecuencia y consistencia
- Audiencia estimada y perfil
- Fortalezas principales
- Debilidades explotables

### Comparación directa: mi canal vs competidor
| Aspecto | Mi canal | Competidor |
|---------|----------|------------|
[tabla comparativa en los aspectos más importantes]

### Sus keywords más exitosas
[lista de keywords donde está ganando y cómo superarlas]

### Sus contenidos más populares
[tipos de contenido que le funcionan — para aprender o superar]

### Plan para superarlo específicamente
Pasos concretos para superar a ESTE competidor en los próximos 60 días.

🎯 Acción inmediata: el punto débil de este competidor que puedes atacar esta semana."""
}

# Monkey-patch para agregar los prompts de competencia a _analysis_prompt
_orig_analysis_prompt = _analysis_prompt

def _analysis_prompt(analysis_type: str, url: str, platform: str, niche: str, competitor_url: str = '') -> str:
    plat = _platform_label(platform)
    if analysis_type in _COMPETE_PROMPTS:
        return _COMPETE_PROMPTS[analysis_type].format(
            url=url, plat=plat, niche=niche,
            competitor_url=competitor_url or 'no especificado'
        )
    return _orig_analysis_prompt(analysis_type, url, platform, niche)


# Override del endpoint analyze para soportar competitor_url
@bp.route('/analyze', methods=['POST'])
def seo_analyze():
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'error': str(e)}), 401

    data             = request.json or {}
    channel_id       = data.get('channel_id')
    analysis_type    = data.get('type', 'full')
    history          = data.get('history', [])
    competitor_url   = data.get('competitor_url', '')

    if not channel_id:
        return jsonify({'error': 'channel_id es requerido'}), 400

    with _db().connect() as conn:
        ch = conn.execute(
            text("SELECT url, platform, niche FROM seo_channel WHERE id = :id AND user_id = :uid"),
            {'id': channel_id, 'uid': user['id']}
        ).fetchone()

    if not ch:
        return jsonify({'error': 'Canal no encontrado'}), 404

    prompt = _analysis_prompt(analysis_type, ch.url, ch.platform, ch.niche, competitor_url)

    try:
        result = _seo_llm(prompt, history=history, max_tokens=2000)

        with _db().connect() as conn:
            conn.execute(
                text("""INSERT INTO seo_result (channel_id, result_type, content_in, result_out, created_at)
                        VALUES (:cid, :rtype, :cin, :cout, NOW())"""),
                {'cid': channel_id, 'rtype': analysis_type,
                 'cin': competitor_url[:500] if competitor_url else '',
                 'cout': result[:5000]}
            )
            conn.commit()

        return jsonify({'success': True, 'result': result})
    except Exception as e:
        logger.error(f'[seo] analyze error: {e}')
        return jsonify({'error': str(e)}), 500
