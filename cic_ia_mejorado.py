"""
Cic_IA - Asistente Inteligente EVOLUTIVO
Archivo principal - Versión 9.0
Mejoras v9: Streaming SSE real, Query Expansion, Compaction de contexto,
            System prompt con personalidad, Sesión en RAM thread-safe,
            Filtro de calidad en auto-learning, Ruta /api/chat/stream
"""

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os
import json
import re
import random
import threading
import time
import hashlib
import requests
import secrets
import logging
import pickle
import numpy as np
from functools import wraps
from sqlalchemy import text, inspect

# ========== CONFIGURACIÓN ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('cic_ia')

app = Flask(__name__)

_secret = os.environ.get('SECRET_KEY')
if not _secret:
    _secret = secrets.token_hex(32)
    logger.warning("SECRET_KEY no configurada. Generando aleatoria (sesiones no persistirán entre reinicios).")
app.config['SECRET_KEY'] = _secret

database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
_is_postgres = database_url and 'postgresql' in database_url
if _is_postgres and 'sslmode' not in database_url:
    sep = '&' if '?' in database_url else '?'
    database_url = database_url + sep + 'sslmode=require'
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///cic_ia.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
_engine_opts = {'pool_pre_ping': True, 'pool_recycle': 300}
if _is_postgres:
    _engine_opts['connect_args'] = {'sslmode': 'require'}
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = _engine_opts

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
OPENAI_API_KEY    = os.environ.get('OPENAI_API_KEY', '')

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt','pdf','png','jpg','jpeg','gif','doc','docx','py','js','html','css','json','csv','xlsx','xls','db','sqlite','md'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('models', exist_ok=True)

db = SQLAlchemy(app)

# ========== SESIÓN EN RAM — thread-safe ==========
# Guarda el historial de conversación activa por usuario.
# Más rápido que BD y evita mezclar historial de sesiones distintas.
_session_history: dict = {}   # {user_id: [{'role': str, 'content': str}]}
_session_lock = threading.Lock()

def get_session_history(user_id: int) -> list:
    with _session_lock:
        return list(_session_history.get(user_id, []))

def append_session(user_id: int, role: str, content: str):
    with _session_lock:
        if user_id not in _session_history:
            _session_history[user_id] = []
        _session_history[user_id].append({'role': role, 'content': content})
        # Mantener máximo 20 mensajes (10 turnos) para no saturar tokens
        if len(_session_history[user_id]) > 20:
            _session_history[user_id] = _session_history[user_id][-20:]

def clear_session(user_id: int):
    with _session_lock:
        _session_history.pop(user_id, None)

# ========== QUERY EXPANSION — Stop Words ==========
# Inspirado en xai-grok-memory/src/query_expansion.rs
# Filtra palabras vacías antes de buscar en memoria para mejorar precisión.

STOP_WORDS_ES = {
    # Artículos y determinantes
    "el","la","los","las","un","una","unos","unas","lo",
    # Pronombres
    "yo","me","mi","tú","te","tu","él","ella","nos","vos","se","su","sus",
    "esto","eso","aquello","este","ese","aquel","esta","esa","aquella",
    # Verbos comunes vacíos
    "es","son","fue","era","ser","estar","hay","tiene","tengo","tiene",
    "hacer","hago","hice","puedo","puede","quiero","quiere","soy","eres",
    "saber","ver","ir","voy","vas","va","van","vamos","dar","doy",
    # Preposiciones y conjunciones
    "de","en","con","por","para","sin","sobre","como","qué","que",
    "si","y","o","pero","porque","cuando","donde","aunque","mientras",
    "desde","hasta","entre","según","tras","hacia","ante","bajo",
    # Adverbios vacíos
    "muy","más","menos","bien","mal","ya","así","también","tampoco",
    "siempre","nunca","antes","después","ahora","hoy","ayer","mañana",
    "aquí","allí","allá","cerca","lejos","solo","sólo","tan","tanto",
    # Palabras de conversación — clave para búsqueda en memoria
    "recuerdas","dijiste","hablamos","conversamos","mencionaste","dije",
    "comentaste","explicaste","me","nos","les","les","decir","dices",
    # Inglés mezclado frecuente
    "the","a","an","is","are","was","how","what","can","do","i","my",
    "you","your","we","they","it","this","that","for","with","in","on",
}

def extract_keywords(query: str) -> list:
    """
    Extrae keywords significativas de una consulta conversacional.
    Pipeline: lowercase → split en no-alfanuméricos → filtrar stop words → dedup
    """
    lowered = query.lower()
    tokens = re.split(r'[^a-záéíóúüña-z0-9_]', lowered)
    seen = set()
    result = []
    for w in tokens:
        if (len(w) >= 3
                and w not in STOP_WORDS_ES
                and not w.isdigit()
                and w not in seen):
            seen.add(w)
            result.append(w)
    return result

# ========== COMPACTION DE CONTEXTO ==========
# Inspirado en CompactionPolicy de xai-grok-agent/src/compaction.rs
# Cuando el historial supera el umbral seguro, resume los mensajes antiguos
# y conserva intactos los últimos 4 turnos (la "tail" reciente).

COMPACTION_THRESHOLD = 0.80   # 80% del límite → activar compaction
MAX_SAFE_TOKENS      = 4000   # Límite conservador para Groq free tier

def _estimate_tokens(messages: list) -> int:
    """Estimación rápida: ~4 caracteres por token (misma métrica que Grok)"""
    return sum(len(m.get('content', '')) // 4 for m in messages)

def compact_history(messages: list, max_tokens: int = MAX_SAFE_TOKENS) -> list:
    """
    Compacta el historial de conversación cuando supera el umbral seguro.
    Conserva la "tail" reciente intacta (últimos 4 turnos = 8 mensajes).
    """
    if not messages:
        return messages

    if _estimate_tokens(messages) <= int(max_tokens * COMPACTION_THRESHOLD):
        return messages  # No necesita compactar

    # Conservar cola reciente intacta
    tail_size = 8
    tail = messages[-tail_size:] if len(messages) > tail_size else messages
    head = messages[:-tail_size] if len(messages) > tail_size else []

    if not head:
        return messages

    # Resumir head en un solo mensaje de sistema
    lines = []
    for m in head:
        role = "Usuario" if m['role'] == 'user' else "Asistente"
        lines.append(f"{role}: {m['content'][:150]}")

    summary = {
        "role": "system",
        "content": "[Resumen de conversación anterior]\n" + "\n".join(lines[:12])
    }

    tokens_freed = _estimate_tokens(head)
    logger.info(f"Compaction: {len(head)} msgs → 1 resumen. ~{tokens_freed} tokens liberados.")
    return [summary] + tail

# ========== MODELOS ==========

class User(db.Model):
    __tablename__ = 'user'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    is_active     = db.Column(db.Boolean, default=True)
    is_developer  = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class UserSession(db.Model):
    __tablename__ = 'user_session'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token       = db.Column(db.String(256), unique=True, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at  = db.Column(db.DateTime)
    last_access = db.Column(db.DateTime, default=datetime.utcnow)

class Memory(db.Model):
    __tablename__   = 'memory'
    id              = db.Column(db.Integer, primary_key=True)
    content         = db.Column(db.Text, nullable=False)
    source          = db.Column(db.String(50), default='local')
    topic           = db.Column(db.String(200), index=True)
    file_path       = db.Column(db.String(500))
    file_type       = db.Column(db.String(50))
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    access_count    = db.Column(db.Integer, default=0)
    relevance_score = db.Column(db.Float, default=0.5)
    tags            = db.Column(db.JSON, default=list)

class Conversation(db.Model):
    __tablename__   = 'conversation'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    user_message    = db.Column(db.Text, nullable=False)
    bot_response    = db.Column(db.Text, nullable=False)
    has_attachment  = db.Column(db.Boolean, default=False)
    attachment_path = db.Column(db.String(500))
    sources_used    = db.Column(db.JSON)
    timestamp       = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    mode_used       = db.Column(db.String(50), default='chat')
    tokens_used     = db.Column(db.Integer, default=0)

class LearningLog(db.Model):
    __tablename__ = 'learning_log'
    id           = db.Column(db.Integer, primary_key=True)
    date         = db.Column(db.Date, default=date.today, unique=True)
    count        = db.Column(db.Integer, default=0)
    web_searches = db.Column(db.Integer, default=0)
    auto_learned = db.Column(db.Integer, default=0)

class ManualKnowledge(db.Model):
    __tablename__ = 'manual_knowledge'
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), nullable=False)
    content     = db.Column(db.Text, nullable=False)
    category    = db.Column(db.String(100), index=True)
    tags        = db.Column(db.JSON, default=list)
    priority    = db.Column(db.Integer, default=1)
    added_by    = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active      = db.Column(db.Boolean, default=True)

class WebSearchCache(db.Model):
    __tablename__ = 'web_search_cache'
    id         = db.Column(db.Integer, primary_key=True)
    query      = db.Column(db.String(500), unique=True, index=True)
    results    = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    id         = db.Column(db.Integer, primary_key=True)
    key        = db.Column(db.String(100), unique=True, nullable=False)
    value      = db.Column(db.Text)
    type       = db.Column(db.String(20), default='string')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========== MIGRACIÓN ==========

def _safe_count(model):
    try:
        return model.query.count()
    except Exception:
        return 0

def run_migration():
    try:
        with app.app_context():
            db.create_all()
            inspector = inspect(db.engine)
            tables    = inspector.get_table_names()

            def add_column_if_missing(table, column, definition):
                try:
                    cols = {col['name'] for col in inspector.get_columns(table)}
                    if column not in cols:
                        with db.engine.connect() as conn:
                            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                            conn.commit()
                        logger.info(f"Migración: {table}.{column} agregada")
                except Exception as e:
                    logger.warning(f"No se pudo agregar {table}.{column}: {e}")

            if 'memory' in tables:
                add_column_if_missing('memory', 'tags', "JSON DEFAULT '[]'")
            if 'conversation' in tables:
                add_column_if_missing('conversation', 'tokens_used', 'INTEGER DEFAULT 0')
                add_column_if_missing('conversation', 'user_id',   'INTEGER')
                add_column_if_missing('conversation', 'mode_used', "VARCHAR(50) DEFAULT 'chat'")

            # System prompt con personalidad — v9
            SYSTEM_PROMPT_V9 = """Eres Cic_IA, asistente inteligente creado por Cic, desarrollador independiente chileno.

PERSONALIDAD:
- Responde siempre en español, excepto si el usuario escribe en otro idioma
- Tono: profesional, directo y cercano — sin rodeos innecesarios
- NO empieces respuestas con "¡Claro!", "¡Por supuesto!" o frases genéricas
- Si no sabes algo, dilo directamente en vez de inventar
- Para código: usa bloques ```lenguaje``` correctamente formateados

CAPACIDADES:
- Análisis de archivos, código y documentos
- Generación de código en cualquier lenguaje
- Búsqueda web para información actual
- Memoria de conversaciones anteriores

REGLAS CRÍTICAS:
- Razona internamente paso a paso antes de responder
- Si el usuario referencia algo anterior, búscalo en el contexto dado
- Nunca digas que eres ChatGPT, Claude, Grok u otro asistente
- Eres Cic_IA — identidad única e irremplazable"""

            defaults = [
                ('ai_provider',                  'groq',            'string'),
                ('ai_model',                     'claude-haiku-4-5-20251001', 'string'),
                ('system_prompt',                SYSTEM_PROMPT_V9,  'string'),
                ('max_tokens',                   '1200',            'int'),
                ('auto_learning_enabled',        'true',            'bool'),
                ('auto_learning_interval_hours', '4',               'int'),
                ('max_memory_results',           '5',               'int'),
                ('web_search_enabled',           'true',            'bool'),
                ('stream_enabled',               'true',            'bool'),
            ]
            for key, val, typ in defaults:
                try:
                    if not SystemConfig.query.filter_by(key=key).first():
                        db.session.add(SystemConfig(key=key, value=val, type=typ))
                except Exception:
                    pass
            db.session.commit()

            # Actualizar system_prompt solo si sigue siendo el default antiguo
            try:
                cfg = SystemConfig.query.filter_by(key='system_prompt').first()
                if cfg and cfg.value and 'Eres Cic_IA, un asistente inteligente en español.' in cfg.value:
                    cfg.value = SYSTEM_PROMPT_V9
                    db.session.commit()
                    logger.info("Migración: system_prompt actualizado a v9")
            except Exception:
                pass

            logger.info("✅ Migración v9 completada")
    except Exception as e:
        logger.error(f"Error migración: {e}")
        import traceback
        logger.error(traceback.format_exc())

run_migration()

# ========== HELPERS DE CONFIG ==========

def get_config(key, default=None):
    try:
        cfg = SystemConfig.query.filter_by(key=key).first()
        if not cfg:
            return default
        if cfg.type == 'int':
            return int(cfg.value)
        if cfg.type == 'bool':
            return cfg.value.lower() == 'true'
        if cfg.type == 'json':
            return json.loads(cfg.value)
        return cfg.value
    except Exception:
        return default

def set_config(key, value):
    cfg = SystemConfig.query.filter_by(key=key).first()
    if cfg:
        cfg.value = str(value)
        cfg.updated_at = datetime.utcnow()
    else:
        cfg = SystemConfig(key=key, value=str(value))
        db.session.add(cfg)
    db.session.commit()

# ========== DECORADORES AUTH ==========

def _get_token_from_request():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    if auth:
        parts = auth.split()
        if len(parts) == 2:
            return parts[1]
    return request.args.get('token') or (request.json.get('token') if request.is_json else None)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token_from_request()
        if not token:
            return jsonify({'error': 'Token requerido'}), 401
        session = UserSession.query.filter_by(token=token).first()
        if not session:
            return jsonify({'error': 'Token inválido'}), 401
        if session.expires_at and session.expires_at < datetime.utcnow():
            db.session.delete(session)
            db.session.commit()
            return jsonify({'error': 'Token expirado, por favor inicia sesión de nuevo'}), 401
        session.last_access = datetime.utcnow()
        db.session.commit()
        current_user = User.query.get(session.user_id)
        if not current_user or not current_user.is_active:
            return jsonify({'error': 'Usuario inactivo'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def dev_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token_from_request()
        if not token:
            return jsonify({'error': 'No autorizado'}), 401
        session = UserSession.query.filter_by(token=token).first()
        if not session:
            return jsonify({'error': 'Token inválido'}), 401
        user = User.query.get(session.user_id)
        if not user or not user.is_developer:
            return jsonify({'error': 'Se requieren privilegios de desarrollador'}), 403
        return f(*args, **kwargs)
    return decorated

# ========== MOTOR DE BÚSQUEDA WEB ==========

class WebSearchEngine:
    @staticmethod
    def search(query: str, max_results: int = 5) -> list:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = []
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        'title':   r.get('title', ''),
                        'url':     r.get('href', ''),
                        'snippet': r.get('body', ''),
                        'source':  'duckduckgo'
                    })
                return results
        except Exception as e:
            logger.warning(f"DuckDuckGo falló: {e}. Intentando fallback.")
            return WebSearchEngine._search_fallback(query, max_results)

    @staticmethod
    def _search_fallback(query: str, max_results: int = 3) -> list:
        try:
            import urllib.request
            import urllib.parse
            encoded = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            for result in soup.select('.result')[:max_results]:
                title_el   = result.select_one('.result__title')
                snippet_el = result.select_one('.result__snippet')
                link_el    = result.select_one('.result__url')
                if title_el:
                    results.append({
                        'title':   title_el.get_text(strip=True),
                        'url':     link_el.get_text(strip=True) if link_el else '',
                        'snippet': snippet_el.get_text(strip=True) if snippet_el else '',
                        'source':  'duckduckgo_html'
                    })
            return results
        except Exception as e:
            logger.error(f"Fallback búsqueda falló: {e}")
            return []

# ========== MOTOR LLM ==========

class LLMEngine:
    """
    Motor de IA multi-proveedor con fallback automático.
    Orden de prioridad: Groq → Ollama → Anthropic → OpenAI → fallback
    """

    def __init__(self):
        self.anthropic_key = ANTHROPIC_API_KEY
        self.openai_key    = OPENAI_API_KEY
        self.groq_key      = os.environ.get('GROQ_API_KEY', '')
        self.ollama_url    = os.environ.get('OLLAMA_URL', '')
        self.groq_model    = os.environ.get('GROQ_MODEL', 'qwen/qwen3.6-27b')
        self.ollama_model  = os.environ.get('OLLAMA_MODEL', 'llama3.2')

    def chat(self, user_message: str, system_prompt: str, context: str = '',
             conversation_history: list = None, max_tokens: int = 1200) -> dict:
        """Intenta cada proveedor en orden hasta obtener respuesta exitosa."""

        full_system = system_prompt
        if context:
            full_system += f'\n\n{context}'

        provider = get_config('ai_provider', 'auto')
        providers = ['groq', 'ollama', 'anthropic', 'openai'] if provider == 'auto' else [provider]

        for p in providers:
            result = self._try_provider(p, user_message, full_system, conversation_history, max_tokens)
            if result.get('success'):
                logger.info(f"✅ Respuesta via {p}")
                return result
            else:
                logger.warning(f"⚠️ {p} falló: {result.get('error', 'desconocido')}")

        return self._fallback_response(user_message)

    def stream_groq(self, messages: list, max_tokens: int = 1200):
        """
        Genera tokens en tiempo real desde Groq vía streaming HTTP.
        Retorna un generator que yields strings de texto.
        """
        if not self.groq_key:
            yield '__ERROR__: Sin GROQ_API_KEY configurada'
            return

        try:
            resp = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.groq_key}',
                    'Content-Type':  'application/json'
                },
                json={
                    'model':       self.groq_model,
                    'messages':    messages,
                    'max_tokens':  max_tokens,
                    'temperature': 0.7,
                    'stream':      True
                },
                stream=True,
                timeout=60
            )
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue
                chunk_str = line[6:]
                if chunk_str == '[DONE]':
                    break
                try:
                    chunk_data = json.loads(chunk_str)
                    token = chunk_data['choices'][0]['delta'].get('content', '')
                    if token:
                        yield token
                except Exception:
                    continue

        except requests.exceptions.Timeout:
            yield '\n\n⚠️ Tiempo de espera agotado. Intenta de nuevo.'
        except requests.exceptions.HTTPError as e:
            yield f'\n\n⚠️ Error de API ({e.response.status_code}). Intenta de nuevo.'
        except Exception as e:
            logger.error(f"Error streaming Groq: {e}")
            yield f'\n\n⚠️ Error de conexión. Intenta de nuevo.'

    def _try_provider(self, provider: str, user_message: str, system: str,
                      history: list, max_tokens: int) -> dict:
        try:
            if provider == 'groq':
                return self._call_groq(user_message, system, history, max_tokens)
            elif provider == 'ollama':
                return self._call_ollama(user_message, system, history, max_tokens)
            elif provider == 'anthropic':
                return self._call_anthropic(user_message, system, history, max_tokens)
            elif provider == 'openai':
                return self._call_openai(user_message, system, history, max_tokens)
            return {'success': False, 'error': f'Proveedor {provider} desconocido'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _call_groq(self, user_message: str, system: str,
                   history: list = None, max_tokens: int = 1200) -> dict:
        if not self.groq_key:
            return {'success': False, 'error': 'Sin GROQ_API_KEY'}

        messages = [{'role': 'system', 'content': system}]
        if history:
            for h in history[-10:]:
                messages.append({'role': h['role'], 'content': h['content']})
        messages.append({'role': 'user', 'content': user_message})

        resp = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {self.groq_key}',
                'Content-Type':  'application/json'
            },
            json={
                'model':       self.groq_model,
                'messages':    messages,
                'max_tokens':  max_tokens,
                'temperature': 0.7
            },
            timeout=30
        )
        resp.raise_for_status()
        data   = resp.json()
        text   = data['choices'][0]['message']['content']
        tokens = data.get('usage', {}).get('completion_tokens', 0)
        return {'success': True, 'response': text, 'tokens': tokens,
                'provider': 'groq', 'model': self.groq_model}

    def _call_ollama(self, user_message: str, system: str,
                     history: list = None, max_tokens: int = 1200) -> dict:
        if not self.ollama_url:
            return {'success': False, 'error': 'Sin OLLAMA_URL'}

        messages = [{'role': 'system', 'content': system}]
        if history:
            for h in history[-10:]:
                messages.append({'role': h['role'], 'content': h['content']})
        messages.append({'role': 'user', 'content': user_message})

        base_url = self.ollama_url.rstrip('/')
        resp = requests.post(
            f'{base_url}/api/chat',
            json={
                'model':    self.ollama_model,
                'messages': messages,
                'stream':   False,
                'options':  {'num_predict': max_tokens, 'temperature': 0.7}
            },
            timeout=120
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get('message', {}).get('content', '')
        if not text:
            return {'success': False, 'error': 'Ollama retornó respuesta vacía'}
        return {'success': True, 'response': text, 'tokens': data.get('eval_count', 0),
                'provider': 'ollama', 'model': self.ollama_model}

    def _call_anthropic(self, user_message: str, system: str,
                        history: list = None, max_tokens: int = 1200) -> dict:
        if not self.anthropic_key:
            return {'success': False, 'error': 'Sin ANTHROPIC_API_KEY'}

        model    = get_config('ai_model', 'claude-haiku-4-5-20251001')
        messages = []
        if history:
            for h in history[-10:]:
                messages.append({'role': h['role'], 'content': h['content']})
        messages.append({'role': 'user', 'content': user_message})

        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key':         self.anthropic_key,
                'anthropic-version': '2023-06-01',
                'content-type':      'application/json'
            },
            json={'model': model, 'max_tokens': max_tokens, 'system': system, 'messages': messages},
            timeout=30
        )
        resp.raise_for_status()
        data   = resp.json()
        text   = data['content'][0]['text']
        tokens = data.get('usage', {}).get('output_tokens', 0)
        return {'success': True, 'response': text, 'tokens': tokens,
                'provider': 'anthropic', 'model': model}

    def _call_openai(self, user_message: str, system: str,
                     history: list = None, max_tokens: int = 1200) -> dict:
        if not self.openai_key:
            return {'success': False, 'error': 'Sin OPENAI_API_KEY'}

        model    = get_config('ai_model', 'gpt-3.5-turbo')
        messages = [{'role': 'system', 'content': system}]
        if history:
            for h in history[-10:]:
                messages.append({'role': h['role'], 'content': h['content']})
        messages.append({'role': 'user', 'content': user_message})

        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {self.openai_key}', 'Content-Type': 'application/json'},
            json={'model': model, 'messages': messages, 'max_tokens': max_tokens},
            timeout=30
        )
        resp.raise_for_status()
        data   = resp.json()
        text   = data['choices'][0]['message']['content']
        tokens = data.get('usage', {}).get('completion_tokens', 0)
        return {'success': True, 'response': text, 'tokens': tokens,
                'provider': 'openai', 'model': model}

    def _fallback_response(self, user_message: str) -> dict:
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ['hola', 'buenas', 'hey', 'saludos']):
            r = ("Hola. Soy Cic_IA. Actualmente no tengo ningún motor de IA conectado. "
                 "Configura GROQ_API_KEY (gratis en console.groq.com) en las variables de entorno de Render.")
        elif any(w in msg_lower for w in ['qué hora', 'qué día', 'fecha', 'hoy']):
            now   = datetime.now()
            dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
            meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
                     'septiembre','octubre','noviembre','diciembre']
            r = f"Hoy es {dias[now.weekday()]}, {now.day} de {meses[now.month-1]} de {now.year} — {now.strftime('%H:%M')}"
        else:
            r = (f"Recibí tu mensaje. "
                 "⚠️ Sin motor de IA activo. Configura GROQ_API_KEY en las variables de entorno de Render.")
        return {'success': False, 'response': r, 'provider': 'fallback', 'tokens': 0}

# ========== MOTOR DE MEMORIA CON QUERY EXPANSION ==========

class MemoryEngine:

    @staticmethod
    def search(query: str, limit: int = 5) -> list:
        """
        Búsqueda con keyword expansion.
        Extrae palabras significativas antes de buscar para mayor precisión.
        """
        keywords = extract_keywords(query)

        # Sin keywords útiles → retornar memorias más relevantes recientes
        if not keywords:
            return Memory.query.order_by(
                Memory.relevance_score.desc(),
                Memory.created_at.desc()
            ).limit(limit).all()

        try:
            from sqlalchemy import or_
            result_ids = set()

            # Prioridad 1: buscar en topic (campo indexado — más rápido)
            for kw in keywords[:6]:
                mems = Memory.query.filter(
                    Memory.topic.ilike(f'%{kw}%')
                ).order_by(Memory.relevance_score.desc()).limit(8).all()
                result_ids.update(m.id for m in mems)

            # Prioridad 2: buscar en contenido si hay pocas coincidencias
            if len(result_ids) < 3:
                for kw in keywords[:4]:
                    mems = Memory.query.filter(
                        Memory.content.ilike(f'%{kw}%')
                    ).order_by(Memory.relevance_score.desc()).limit(6).all()
                    result_ids.update(m.id for m in mems)

            if not result_ids:
                return []

            memories = Memory.query.filter(
                Memory.id.in_(list(result_ids))
            ).order_by(
                Memory.relevance_score.desc(),
                Memory.access_count.desc()
            ).limit(limit).all()

            # Actualizar acceso en batch (eficiente)
            if memories:
                Memory.query.filter(
                    Memory.id.in_([m.id for m in memories])
                ).update({'access_count': Memory.access_count + 1}, synchronize_session=False)
                db.session.commit()

            return memories

        except Exception as e:
            logger.error(f"Error MemoryEngine.search: {e}")
            return []

    @staticmethod
    def search_manual_knowledge(query: str, limit: int = 5) -> list:
        """Busca en el conocimiento manual del desarrollador con keyword expansion."""
        keywords = extract_keywords(query)

        if not keywords:
            return ManualKnowledge.query.filter_by(active=True).order_by(
                ManualKnowledge.priority.desc()
            ).limit(limit).all()

        try:
            result_ids = set()
            for kw in keywords[:5]:
                items = ManualKnowledge.query.filter(
                    ManualKnowledge.active == True,
                    db.or_(
                        ManualKnowledge.content.ilike(f'%{kw}%'),
                        ManualKnowledge.title.ilike(f'%{kw}%'),
                        ManualKnowledge.category.ilike(f'%{kw}%')
                    )
                ).order_by(ManualKnowledge.priority.desc()).limit(10).all()
                result_ids.update(m.id for m in items)

            if not result_ids:
                return []

            return ManualKnowledge.query.filter(
                ManualKnowledge.id.in_(list(result_ids))
            ).order_by(ManualKnowledge.priority.desc()).limit(limit).all()

        except Exception as e:
            logger.error(f"Error search_manual_knowledge: {e}")
            return []

# ========== CLASE PRINCIPAL CIC_IA ==========

class CicIA:
    def __init__(self):
        self.search_engine = WebSearchEngine()
        self.llm           = LLMEngine()
        self.memory_engine = MemoryEngine()
        self._start_background_tasks()

        with app.app_context():
            logger.info("=" * 55)
            logger.info("🤖 CIC_IA v9.0 INICIADA")
            logger.info(f"   Memorias:        {Memory.query.count()}")
            logger.info(f"   Conversaciones:  {Conversation.query.count()}")
            logger.info(f"   Conocimiento:    {ManualKnowledge.query.count()}")
            has_key = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY or os.environ.get('GROQ_API_KEY'))
            logger.info(f"   API Keys:        {'✅ OK' if has_key else '⚠️ Sin API Key'}")
            logger.info(f"   Streaming:       ✅ Activo")
            logger.info("=" * 55)

    def _start_background_tasks(self):
        threading.Thread(target=self._auto_learning_loop, daemon=True).start()
        threading.Thread(target=self._keepalive_loop, daemon=True).start()

    def _keepalive_loop(self):
        import urllib.request
        time.sleep(30)
        app_url = os.environ.get('RENDER_EXTERNAL_URL', '')
        if not app_url:
            logger.info("ℹ️ RENDER_EXTERNAL_URL no configurada — keepalive desactivado")
            return
        logger.info(f"💓 Keepalive activo → {app_url}/health cada 10 min")
        while True:
            try:
                req = urllib.request.Request(f"{app_url}/health",
                                             headers={'User-Agent': 'CicIA-Keepalive/1.0'})
                urllib.request.urlopen(req, timeout=10)
                logger.info("💓 Keepalive OK")
            except Exception as e:
                logger.warning(f"💓 Keepalive error: {e}")
            time.sleep(600)

    def _auto_learning_loop(self):
        time.sleep(60)
        while True:
            try:
                with app.app_context():
                    if get_config('auto_learning_enabled', True):
                        self._perform_auto_learning()
            except Exception as e:
                logger.error(f"Error auto-learning: {e}")
            interval = get_config('auto_learning_interval_hours', 4)
            time.sleep(interval * 3600)

    def _quality_filter(self, content: str) -> bool:
        """
        Filtra contenido de baja calidad antes de guardarlo en memoria.
        Evita llenar la BD con basura que luego contamina el contexto del LLM.
        """
        if not content or len(content.strip()) < 80:
            return False

        content_lower = content.lower()
        junk_signals = [
            '404', 'not found', 'page not found', 'access denied',
            'subscribe to read', 'sign in to', 'enable javascript',
            'cookies', 'javascript is required', 'paywall',
            'create an account', 'log in to', 'register to',
        ]
        if any(s in content_lower for s in junk_signals):
            return False

        words = content_lower.split()
        if len(words) < 15:
            return False

        return True

    def _dedup_check(self, content: str) -> bool:
        """True = no existe duplicado, es seguro guardar."""
        fingerprint = content[:60].strip().lower()
        exists = Memory.query.filter(
            Memory.content.ilike(f'%{fingerprint[:40]}%')
        ).first()
        return exists is None

    def _perform_auto_learning(self, topic: str = None) -> dict:
        """Aprendizaje automático desde web con filtro de calidad."""
        default_topics = [
            'inteligencia artificial 2025', 'machine learning avances',
            'python novedades desarrollo', 'desarrollo web moderno',
            'tecnología Chile 2025'
        ]
        query = topic or random.choice(default_topics)
        logger.info(f"🔍 Auto-aprendiendo: '{query}'")

        results = self.search_engine.search(query, max_results=5)
        if not results:
            return {'learned': 0, 'topic': query, 'error': 'Sin resultados web'}

        learned = 0
        for r in results:
            try:
                snippet = r.get('snippet', '').strip()
                title   = r.get('title', '').strip()
                if not snippet:
                    continue

                content = f"{title}\n\n{snippet}\n\nFuente: {r.get('url', '')}"

                # Filtro de calidad — evitar guardar basura
                if not self._quality_filter(content):
                    continue

                # Deduplicación
                if not self._dedup_check(content):
                    continue

                mem = Memory(
                    content=content,
                    source='auto_learning',
                    topic=query,
                    relevance_score=0.5
                )
                db.session.add(mem)
                learned += 1
            except Exception:
                continue

        if learned > 0:
            db.session.commit()
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            if not log:
                log = LearningLog(date=today, count=0, web_searches=0, auto_learned=0)
                db.session.add(log)
            log.auto_learned += learned
            db.session.commit()

        logger.info(f"✅ Guardados {learned} memorias sobre '{query}'")
        return {'learned': learned, 'topic': query}

    def force_learn(self, topic: str, content: str = None, user_id: int = None) -> dict:
        with app.app_context():
            learned_items = []
            if content:
                mk = ManualKnowledge(
                    title=topic, content=content,
                    category='forzado', priority=2,
                    added_by=user_id, tags=['forced_learning']
                )
                db.session.add(mk)
                mem = Memory(
                    content=content, source='manual_dev',
                    topic=topic, relevance_score=0.95,
                    tags=['priority', 'manual']
                )
                db.session.add(mem)
                db.session.commit()
                learned_items.append({'type': 'manual', 'title': topic})

            web_result = self._perform_auto_learning(topic)
            if web_result.get('learned', 0) > 0:
                learned_items.append({'type': 'web', 'count': web_result['learned']})

            return {
                'success': True, 'topic': topic,
                'manual_saved': bool(content),
                'web_learned': web_result.get('learned', 0),
                'total': len(learned_items)
            }

    def _get_db_history(self, user_id: int, limit: int = 6) -> list:
        """Recupera historial reciente desde BD como contexto base."""
        if not user_id:
            return []
        try:
            recent = Conversation.query.filter_by(user_id=user_id).order_by(
                Conversation.timestamp.desc()
            ).limit(limit).all()
            history = []
            for conv in reversed(recent):
                history.append({'role': 'user',      'content': conv.user_message[:400]})
                history.append({'role': 'assistant',  'content': conv.bot_response[:400]})
            return history
        except Exception as e:
            logger.error(f"Error recuperando historial BD: {e}")
            return []

    def _build_system_prompt(self, memories: list, manual_knowledge: list,
                              db_history: list) -> str:
        """Construye el system prompt enriquecido con contexto relevante."""
        base = get_config('system_prompt',
                          'Eres Cic_IA, un asistente inteligente en español.')
        parts = [base, '']

        parts.append("""=== INSTRUCCIONES DE RAZONAMIENTO ===
Antes de responder, analiza internamente:
1. ¿Qué pide exactamente el usuario?
2. ¿Tengo información relevante en el conocimiento base?
3. ¿El historial da contexto adicional útil?
4. ¿Cuál es la respuesta más precisa y útil?
Responde directamente sin mostrar este proceso.""")
        parts.append('')

        if manual_knowledge:
            parts.append('=== CONOCIMIENTO BASE (fuente prioritaria) ===')
            for mk in manual_knowledge[:5]:
                parts.append(f"[{mk.category or 'General'}] {mk.title}:\n{mk.content[:600]}")
            parts.append('')

        if memories:
            parts.append('=== CONOCIMIENTO APRENDIDO ===')
            for mem in memories[:4]:
                parts.append(f"Tema: {mem.topic or 'general'}\n{mem.content[:350]}")
            parts.append('')

        if db_history and len(db_history) >= 4:
            parts.append('=== CONTEXTO DE CONVERSACIONES ANTERIORES ===')
            for i in range(0, min(4, len(db_history)), 2):
                if i + 1 < len(db_history):
                    u = db_history[i]['content'][:100]
                    a = db_history[i + 1]['content'][:100]
                    parts.append(f"- Usuario: '{u}...' → Respondiste: '{a}...'")
            parts.append('')

        return '\n'.join(parts)

    def build_messages_for_stream(self, user_message: str, user_id: int,
                                   mode: str = 'balanced') -> tuple:
        """
        Construye la lista de mensajes lista para enviar al LLM vía streaming.
        Retorna (messages_list, metadata_dict)
        """
        # Historial de sesión en RAM (conversación actual)
        session_hist = get_session_history(user_id)

        # Si la sesión está vacía, cargar últimas conversaciones de BD como base
        if not session_hist:
            session_hist = self._get_db_history(user_id, limit=6)

        # Compactar si supera límite de tokens
        session_hist = compact_history(session_hist)

        # Buscar contexto relevante con keyword expansion
        memories         = self.memory_engine.search(user_message, limit=get_config('max_memory_results', 5))
        manual_knowledge = self.memory_engine.search_manual_knowledge(user_message, limit=5)

        # Construir system prompt enriquecido
        db_hist_for_prompt = self._get_db_history(user_id, limit=4)
        system_prompt = self._build_system_prompt(memories, manual_knowledge, db_hist_for_prompt)

        # Armar lista de mensajes
        messages = [{'role': 'system', 'content': system_prompt}]
        messages.extend(session_hist)
        messages.append({'role': 'user', 'content': user_message})

        tokens_map = {'fast': 600, 'balanced': 1200, 'complete': 2000}
        max_tokens = tokens_map.get(mode, 1200)

        meta = {
            'memories_used':   len(memories),
            'manual_kb_used':  len(manual_knowledge),
            'history_used':    len(session_hist),
            'max_tokens':      max_tokens,
        }

        return messages, meta

    def chat(self, user_message: str, user_id: int = None,
             conversation_history: list = None, mode: str = 'balanced') -> dict:
        """
        Chat clásico (sin streaming) — mantiene compatibilidad con frontend actual.
        """
        if len(user_message) > 100000:
            user_message = user_message[:100000]

        messages, meta = self.build_messages_for_stream(user_message, user_id, mode)

        # Quitar el system message de messages para LLMEngine (lo maneja internamente)
        system = messages[0]['content'] if messages and messages[0]['role'] == 'system' else ''
        conv_msgs = [m for m in messages if m['role'] != 'system']
        # El último mensaje es el user actual — extraerlo
        hist_msgs = conv_msgs[:-1] if len(conv_msgs) > 1 else []

        llm_result = self.llm.chat(
            user_message=user_message,
            system_prompt=system,
            conversation_history=hist_msgs,
            max_tokens=meta['max_tokens']
        )

        response_text = llm_result['response']

        # Búsqueda web si el LLM falla
        if not llm_result.get('success') and get_config('web_search_enabled', True):
            web_data = self._search_and_cache(user_message)
            if web_data:
                response_text += f"\n\n📖 Información web:\n{web_data}"

        # Actualizar sesión en RAM
        if user_id:
            append_session(user_id, 'user', user_message)
            append_session(user_id, 'assistant', response_text)

        # Guardar en BD
        self._save_conversation(
            user_msg=user_message,
            bot_resp=response_text,
            user_id=user_id,
            tokens=llm_result.get('tokens', 0),
            sources=['llm', llm_result.get('provider', 'unknown')]
        )

        return {
            'response':       response_text,
            'provider':       llm_result.get('provider', 'unknown'),
            'model':          llm_result.get('model', 'unknown'),
            'tokens_used':    llm_result.get('tokens', 0),
            'memories_used':  meta['memories_used'],
            'manual_kb_used': meta['manual_kb_used'],
            'history_used':   meta['history_used'],
            'success':        llm_result.get('success', False)
        }

    def _search_and_cache(self, query: str) -> str:
        try:
            cached = WebSearchCache.query.filter_by(query=query).first()
            if cached and cached.expires_at and cached.expires_at > datetime.utcnow():
                return cached.results.get('summary', '')

            results = self.search_engine.search(query, max_results=3)
            if not results:
                return ''

            summary = '\n'.join(
                f"• {r['title']}: {r['snippet'][:200]}" for r in results
            )

            cache = WebSearchCache(
                query=query,
                results={'summary': summary},
                expires_at=datetime.utcnow() + timedelta(hours=6)
            )
            db.session.merge(cache)
            db.session.commit()
            return summary
        except Exception as e:
            logger.error(f"Error web search cache: {e}")
            return ''

    def _save_conversation(self, user_msg: str, bot_resp: str,
                           user_id: int = None, tokens: int = 0, sources: list = None):
        try:
            conv = Conversation(
                user_id=user_id,
                user_message=user_msg[:50000],
                bot_response=bot_resp[:20000],
                sources_used={'providers': sources or []},
                tokens_used=tokens,
                mode_used='chat'
            )
            db.session.add(conv)

            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            if not log:
                log = LearningLog(date=today, count=1, web_searches=0, auto_learned=0)
                db.session.add(log)
            else:
                log.count += 1
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error guardando conversación: {e}")

    def get_stats(self) -> dict:
        with app.app_context():
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            return {
                'total_memories':      Memory.query.count(),
                'total_conversations': Conversation.query.count(),
                'manual_knowledge':    ManualKnowledge.query.filter_by(active=True).count(),
                'today_conversations': log.count if log else 0,
                'today_auto_learned':  log.auto_learned if log else 0,
                'ai_provider':         get_config('ai_provider', 'groq'),
                'ai_model':            get_config('ai_model', 'unknown'),
                'has_api_key':         bool(ANTHROPIC_API_KEY or OPENAI_API_KEY or os.environ.get('GROQ_API_KEY')),
                'web_search_enabled':  get_config('web_search_enabled', True),
                'stream_enabled':      True,
                'version':             '9.0',
            }


# Instancia global
cic_ia = CicIA()

# ========== RUTAS PÚBLICAS ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    stats = cic_ia.get_stats()
    return jsonify({
        'status':    'healthy',
        'version':   '9.0',
        'timestamp': datetime.utcnow().isoformat(),
        **stats
    })

# ========== AUTENTICACIÓN ==========

@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data     = request.json or {}
        username = data.get('username', '').strip()
        email    = data.get('email', '').strip()
        password = data.get('password', '')

        if not username or len(username) < 3:
            return jsonify({'success': False, 'error': 'Usuario debe tener al menos 3 caracteres'}), 400
        if not password or len(password) < 6:
            return jsonify({'success': False, 'error': 'Contraseña debe tener al menos 6 caracteres'}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'error': 'Nombre de usuario ya existe'}), 409
        if email and User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'error': 'Email ya registrado'}), 409

        user = User(username=username, email=email or f"{username}@cic.local")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        token   = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(days=30)
        sess    = UserSession(user_id=user.id, token=token, expires_at=expires)
        db.session.add(sess)
        db.session.commit()

        return jsonify({
            'success': True, 'token': token,
            'user': {'id': user.id, 'username': user.username, 'is_developer': user.is_developer}
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data     = request.json or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return jsonify({'success': False, 'error': 'Credenciales inválidas'}), 401
        if not user.is_active:
            return jsonify({'success': False, 'error': 'Cuenta desactivada'}), 403

        token   = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(days=30)
        sess    = UserSession(user_id=user.id, token=token, expires_at=expires)
        db.session.add(sess)
        db.session.commit()

        return jsonify({
            'success': True, 'token': token,
            'user': {'id': user.id, 'username': user.username, 'is_developer': user.is_developer}
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/verify', methods=['GET'])
@token_required
def verify_token(current_user):
    return jsonify({
        'success': True,
        'user': {'id': current_user.id, 'username': current_user.username, 'is_developer': current_user.is_developer}
    })

@app.route('/api/auth/logout', methods=['POST'])
@token_required
def logout(current_user):
    token = _get_token_from_request()
    UserSession.query.filter_by(token=token).delete()
    db.session.commit()
    # Limpiar sesión en RAM
    clear_session(current_user.id)
    return jsonify({'success': True, 'message': 'Sesión cerrada'})

# ========== CHAT — CLÁSICO ==========

@app.route('/api/chat', methods=['POST'])
@token_required
def chat(current_user):
    try:
        data    = request.json or {}
        message = data.get('message', '').strip()
        mode    = data.get('mode', 'balanced')

        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        if len(message) > 100000:
            return jsonify({'error': 'Mensaje demasiado largo (máx 100,000 caracteres)'}), 400

        result = cic_ia.chat(
            user_message=message,
            user_id=current_user.id,
            mode=mode
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error chat: {e}")
        return jsonify({'error': str(e)}), 500

# ========== CHAT — STREAMING SSE ==========
# Nueva ruta. El frontend la llama con EventSource o fetch + ReadableStream.
# Envía tokens a medida que el LLM los genera → el usuario ve la respuesta crecer.

@app.route('/api/chat/stream', methods=['POST'])
@token_required
def chat_stream(current_user):
    try:
        data    = request.json or {}
        message = data.get('message', '').strip()
        mode    = data.get('mode', 'balanced')

        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        if len(message) > 100000:
            return jsonify({'error': 'Mensaje demasiado largo'}), 400

        # Preparar mensajes (incluye system prompt + historial + keywords)
        messages, meta = cic_ia.build_messages_for_stream(message, current_user.id, mode)

        def generate():
            full_response = []

            # Enviar metadata inicial
            yield f"data: {json.dumps({'type': 'meta', 'memories': meta['memories_used'], 'history': meta['history_used']})}\n\n"

            # Streaming de tokens desde Groq
            for token in cic_ia.llm.stream_groq(messages, max_tokens=meta['max_tokens']):
                if token.startswith('__ERROR__'):
                    err_msg = token.replace('__ERROR__: ', '')
                    yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                    return
                full_response.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # Respuesta completa
            complete = ''.join(full_response)

            if not complete.strip():
                # Groq no respondió → fallback a modo clásico
                fallback = cic_ia.llm._fallback_response(message)
                complete = fallback['response']
                yield f"data: {json.dumps({'type': 'token', 'content': complete})}\n\n"

            # Guardar en BD y sesión RAM
            with app.app_context():
                append_session(current_user.id, 'user', message)
                append_session(current_user.id, 'assistant', complete)
                cic_ia._save_conversation(
                    user_msg=message,
                    bot_resp=complete,
                    user_id=current_user.id,
                    tokens=len(complete) // 4,
                    sources=['groq_stream']
                )

            yield f"data: {json.dumps({'type': 'done', 'response': complete})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control':    'no-cache',
                'X-Accel-Buffering': 'no',       # Crítico para nginx en Render
                'Connection':       'keep-alive',
            }
        )

    except Exception as e:
        logger.error(f"Error chat/stream: {e}")
        return jsonify({'error': str(e)}), 500

# ========== LIMPIAR SESIÓN ==========

@app.route('/api/chat/session/clear', methods=['POST'])
@token_required
def clear_chat_session(current_user):
    """Limpia el historial de sesión en RAM para el usuario actual."""
    clear_session(current_user.id)
    return jsonify({'success': True, 'message': 'Sesión limpiada'})

# ========== HISTORIAL ==========

@app.route('/api/chat/history', methods=['GET'])
@token_required
def chat_history(current_user):
    page     = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    pagination = Conversation.query.filter_by(
        user_id=current_user.id
    ).order_by(Conversation.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'conversations': [{
            'id':           c.id,
            'user_message': c.user_message,
            'bot_response': c.bot_response,
            'timestamp':    c.timestamp.isoformat(),
            'tokens_used':  c.tokens_used
        } for c in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })

@app.route('/api/user/stats', methods=['GET'])
@token_required
def user_stats(current_user):
    conv_count   = Conversation.query.filter_by(user_id=current_user.id).count()
    total_tokens = db.session.query(
        db.func.sum(Conversation.tokens_used)
    ).filter_by(user_id=current_user.id).scalar() or 0

    return jsonify({
        'success':            True,
        'user_id':            current_user.id,
        'username':           current_user.username,
        'conversation_count': conv_count,
        'total_tokens_used':  total_tokens,
        'is_developer':       current_user.is_developer,
        'member_since':       current_user.created_at.isoformat()
    })

@app.route('/api/status')
def status():
    return jsonify(cic_ia.get_stats())

# ========== LECTOR DE GITHUB Y ARCHIVOS ==========

@app.route('/api/chat/read-github', methods=['POST'])
@token_required
def read_github(current_user):
    try:
        data = request.json or {}
        url  = data.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL requerida'}), 400

        raw_url = url
        if 'github.com' in url and '/blob/' in url:
            raw_url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')

        import urllib.request
        req_obj = urllib.request.Request(raw_url, headers={'User-Agent': 'CicIA/1.0'})
        with urllib.request.urlopen(req_obj, timeout=15) as resp:
            code_content = resp.read().decode('utf-8', errors='ignore')

        if len(code_content) > 80000:
            code_content = code_content[:80000] + "\n... [truncado por tamaño]"

        lang = 'plaintext'
        for ext, l in [('.py','python'),('.js','javascript'),('.ts','typescript'),
                       ('.html','html'),('.css','css'),('.json','json'),('.md','markdown'),
                       ('.rs','rust'),('.go','go'),('.java','java'),('.php','php')]:
            if ext in url:
                lang = l
                break

        return jsonify({
            'success':  True,
            'content':  code_content,
            'language': lang,
            'url':      raw_url,
            'lines':    code_content.count('\n') + 1,
            'chars':    len(code_content)
        })
    except Exception as e:
        return jsonify({'error': f'No se pudo leer el archivo: {str(e)}'}), 400

@app.route('/api/chat/analyze-image', methods=['POST'])
@token_required
def analyze_image(current_user):
    try:
        data      = request.json or {}
        image_b64 = data.get('image_b64', '')
        message   = data.get('message', 'Describe esta imagen en detalle en español')
        mime_type = data.get('mime_type', 'image/jpeg')

        if not image_b64:
            return jsonify({'error': 'imagen requerida'}), 400

        groq_key = os.environ.get('GROQ_API_KEY', '')
        system   = get_config('system_prompt', 'Eres Cic_IA, un asistente inteligente en español.')

        if groq_key:
            try:
                data_url = f"data:{mime_type};base64,{image_b64}"
                resp = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': f'Bearer {groq_key}', 'Content-Type': 'application/json'},
                    json={
                        'model':      'llama-3.2-11b-vision-preview',
                        'max_tokens': 1500,
                        'messages': [
                            {'role': 'system', 'content': system},
                            {'role': 'user', 'content': [
                                {'type': 'image_url', 'image_url': {'url': data_url}},
                                {'type': 'text', 'text': message}
                            ]}
                        ]
                    },
                    timeout=30
                )
                resp.raise_for_status()
                result_text = resp.json()['choices'][0]['message']['content']
                tokens      = resp.json().get('usage', {}).get('completion_tokens', 0)
                cic_ia._save_conversation(
                    user_msg=f'[IMAGEN] {message}', bot_resp=result_text,
                    user_id=current_user.id, tokens=tokens, sources=['groq_vision']
                )
                return jsonify({'success': True, 'response': result_text,
                                'provider': 'groq_vision', 'tokens': tokens})
            except Exception as e:
                logger.warning(f"Groq Vision falló: {e}")

        if ANTHROPIC_API_KEY:
            try:
                resp = requests.post(
                    'https://api.anthropic.com/v1/messages',
                    headers={
                        'x-api-key': ANTHROPIC_API_KEY,
                        'anthropic-version': '2023-06-01',
                        'content-type': 'application/json'
                    },
                    json={
                        'model': 'claude-haiku-4-5-20251001',
                        'max_tokens': 1500,
                        'system': system,
                        'messages': [{'role': 'user', 'content': [
                            {'type': 'image', 'source': {'type': 'base64', 'media_type': mime_type, 'data': image_b64}},
                            {'type': 'text', 'text': message}
                        ]}]
                    },
                    timeout=30
                )
                resp.raise_for_status()
                result_text = resp.json()['content'][0]['text']
                tokens      = resp.json().get('usage', {}).get('output_tokens', 0)
                cic_ia._save_conversation(
                    user_msg=f'[IMAGEN] {message}', bot_resp=result_text,
                    user_id=current_user.id, tokens=tokens, sources=['anthropic_vision']
                )
                return jsonify({'success': True, 'response': result_text,
                                'provider': 'anthropic_vision', 'tokens': tokens})
            except Exception as e:
                logger.error(f"Anthropic Vision falló: {e}")

        return jsonify({
            'success':  False,
            'response': '⚠️ No hay proveedor de visión disponible. Configura GROQ_API_KEY.',
            'provider': 'fallback'
        })

    except Exception as e:
        logger.error(f"Error análisis imagen: {e}")
        return jsonify({'error': str(e)}), 500

# ========== MÓDULOS ==========

@app.route('/api/modules/list', methods=['GET'])
def list_modules():
    return jsonify({'modules': [
        {'id': 'chat',           'name': 'Chat IA',           'icon': '🤖', 'status': 'active'},
        {'id': 'web_search',     'name': 'Búsqueda Web',      'icon': '🔍', 'status': 'active'},
        {'id': 'memory',         'name': 'Memoria',           'icon': '🧠', 'status': 'active'},
        {'id': 'imggen',         'name': 'Crear Imagen',      'icon': '🎨', 'status': 'active'},
        {'id': 'vidgen',         'name': 'CicVideo',          'icon': '🎬', 'status': 'active'},
        {'id': 'data_analysis',  'name': 'Análisis de Datos', 'icon': '📊', 'status': 'available'},
        {'id': 'code_assistant', 'name': 'Ejecutor Código',   'icon': '⚙️', 'status': 'available'},
        {'id': 'tts',            'name': 'Voz / TTS',         'icon': '🎙️', 'status': 'available'},
        {'id': 'docsgen',        'name': 'Análisis Docs',     'icon': '📄', 'status': 'available'},
    ]})

# ── Registro de módulos externos ─────────────────────────────────────────────
try:
    from modules.video_gen.routes import register_video_routes
    register_video_routes(app, db, token_required, dev_required)
    logger.info('✅ CicVideo registrado')
except Exception as _ve:
    logger.warning(f'CicVideo no cargado: {_ve}')

try:
    from modules.image_generator.routes import register as register_image_routes
    register_image_routes(app)
    logger.info('✅ CicImage registrado')
except Exception as _ie:
    logger.warning(f'CicImage no cargado: {_ie}')

try:
    from modules.code_executor.routes import bp as ciccode_bp
    app.register_blueprint(ciccode_bp)
    logger.info('✅ CicCode IDE registrado')
except Exception as _ce:
    logger.warning(f'CicCode no cargado: {_ce}')

try:
    from modules.audio_studio.routes import register as register_audio_routes
    register_audio_routes(app)
    logger.info('✅ Audio Studio registrado')
except Exception as _as:
    logger.warning(f'Audio Studio no cargado: {_as}')

try:
    from modules.seo.routes import bp as cicseo_bp
    app.register_blueprint(cicseo_bp)
    logger.info('✅ CicSEO registrado')
except Exception as _se:
    logger.warning(f'CicSEO no cargado: {_se}')

# ========== PANEL DESARROLLADOR ==========

@app.route('/developer')
def developer_panel():
    try:
        return render_template('developer.html')
    except Exception:
        return jsonify({'message': 'Panel desarrollador activo. Usa /api/dev/*'})

@app.route('/api/dev/stats', methods=['GET'])
@dev_required
def dev_stats():
    try:
        today = date.today()
        log   = LearningLog.query.filter_by(date=today).first()
        week_logs = LearningLog.query.filter(
            LearningLog.date >= today - timedelta(days=7)
        ).order_by(LearningLog.date.desc()).all()
        last_convs = Conversation.query.order_by(Conversation.timestamp.desc()).limit(5).all()

        return jsonify({
            'system': {
                'total_memories':      Memory.query.count(),
                'total_conversations': Conversation.query.count(),
                'total_users':         User.query.count(),
                'active_sessions':     UserSession.query.count(),
                'manual_knowledge':    ManualKnowledge.query.filter_by(active=True).count(),
                'cached_searches':     _safe_count(WebSearchCache),
                'active_ram_sessions': len(_session_history),
            },
            'today': {
                'conversations': log.count if log else 0,
                'auto_learned':  log.auto_learned if log else 0,
                'web_searches':  log.web_searches if log else 0,
            },
            'week_activity': [{
                'date':          l.date.isoformat(),
                'conversations': l.count,
                'auto_learned':  l.auto_learned,
            } for l in week_logs],
            'recent_conversations': [{
                'user':   c.user_message[:80],
                'bot':    c.bot_response[:80],
                'time':   c.timestamp.isoformat(),
                'tokens': c.tokens_used,
            } for c in last_convs],
            'ai_config': {
                'provider':      get_config('ai_provider', 'groq'),
                'model':         get_config('ai_model'),
                'has_anthropic': bool(ANTHROPIC_API_KEY),
                'has_openai':    bool(OPENAI_API_KEY),
                'has_groq':      bool(os.environ.get('GROQ_API_KEY', '')),
                'system_prompt': get_config('system_prompt'),
                'max_tokens':    get_config('max_tokens'),
                'auto_learning': get_config('auto_learning_enabled'),
                'web_search':    get_config('web_search_enabled'),
                'streaming':     True,
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/knowledge', methods=['GET'])
@dev_required
def dev_get_knowledge():
    page     = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    query    = ManualKnowledge.query.filter_by(active=True)
    if category:
        query = query.filter_by(category=category)
    pagination = query.order_by(
        ManualKnowledge.priority.desc(), ManualKnowledge.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    return jsonify({
        'knowledge': [{
            'id': k.id, 'title': k.title, 'category': k.category,
            'content': k.content[:300], 'priority': k.priority,
            'tags': k.tags, 'created': k.created_at.isoformat()
        } for k in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages
    })

@app.route('/api/dev/knowledge', methods=['POST'])
@dev_required
def dev_add_knowledge():
    try:
        data    = request.json or {}
        title   = data.get('title', '').strip()
        content = data.get('content', '').strip()
        if not title or not content:
            return jsonify({'error': 'title y content son requeridos'}), 400

        token   = _get_token_from_request()
        session = UserSession.query.filter_by(token=token).first()
        user_id = session.user_id if session else None

        mk = ManualKnowledge(
            title=title, content=content,
            category=data.get('category', 'general'),
            tags=data.get('tags', []),
            priority=data.get('priority', 1),
            added_by=user_id
        )
        db.session.add(mk)

        mem = Memory(
            content=f"{title}\n\n{content}",
            source='manual_dev', topic=title,
            relevance_score=0.9 + (data.get('priority', 1) * 0.03),
            tags=data.get('tags', [])
        )
        db.session.add(mem)
        db.session.commit()

        return jsonify({'success': True, 'id': mk.id,
                        'message': f'Conocimiento "{title}" agregado', 'memory_id': mem.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/knowledge/<int:kid>', methods=['PUT'])
@dev_required
def dev_update_knowledge(kid):
    try:
        mk = ManualKnowledge.query.get_or_404(kid)
        data = request.json or {}
        for field in ['title', 'content', 'category', 'tags', 'priority', 'active']:
            if field in data:
                setattr(mk, field, data[field])
        mk.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Actualizado correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/knowledge/<int:kid>', methods=['DELETE'])
@dev_required
def dev_delete_knowledge(kid):
    mk = ManualKnowledge.query.get_or_404(kid)
    mk.active = False
    db.session.commit()
    return jsonify({'success': True, 'message': 'Conocimiento desactivado'})

@app.route('/api/dev/learn', methods=['POST'])
@dev_required
def dev_force_learn():
    try:
        data    = request.json or {}
        topic   = data.get('topic', '').strip()
        content = data.get('content', '').strip()
        if not topic:
            return jsonify({'error': 'topic es requerido'}), 400

        token   = _get_token_from_request()
        session = UserSession.query.filter_by(token=token).first()
        user_id = session.user_id if session else None

        result = cic_ia.force_learn(topic=topic, content=content or None, user_id=user_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/learn/bulk', methods=['POST'])
@dev_required
def dev_bulk_learn():
    try:
        data  = request.json or {}
        items = data.get('items', [])
        if not items:
            return jsonify({'error': 'items es requerido'}), 400
        if len(items) > 50:
            return jsonify({'error': 'Máximo 50 items por lote'}), 400

        results = []
        for item in items:
            if isinstance(item, str):
                item = {'topic': item}
            r = cic_ia.force_learn(
                topic=item.get('topic', ''),
                content=item.get('content', '') or None
            )
            results.append(r)
            time.sleep(0.5)

        total_learned = sum(r.get('web_learned', 0) for r in results)
        return jsonify({'success': True, 'processed': len(results),
                        'total_learned': total_learned, 'results': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/config', methods=['GET'])
@dev_required
def dev_get_config():
    configs = SystemConfig.query.all()
    return jsonify({
        'config': {c.key: {'value': c.value, 'type': c.type,
                            'updated': c.updated_at.isoformat()} for c in configs}
    })

@app.route('/api/dev/config', methods=['PUT'])
@dev_required
def dev_update_config():
    try:
        data    = request.json or {}
        updates = data.get('updates', {})
        if not updates:
            return jsonify({'error': 'updates es requerido'}), 400

        protected = {'SECRET_KEY', 'DATABASE_URL'}
        updated = []
        for key, value in updates.items():
            if key in protected:
                continue
            set_config(key, value)
            updated.append(key)

        return jsonify({'success': True, 'updated': updated,
                        'message': f'{len(updated)} configuraciones actualizadas'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/config/prompt', methods=['PUT'])
@dev_required
def dev_update_prompt():
    try:
        data   = request.json or {}
        prompt = data.get('prompt', '').strip()
        if not prompt:
            return jsonify({'error': 'prompt es requerido'}), 400
        if len(prompt) > 3000:
            return jsonify({'error': 'Prompt muy largo (máx 3000 caracteres)'}), 400
        set_config('system_prompt', prompt)
        return jsonify({'success': True, 'message': 'System prompt actualizado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/memories', methods=['GET'])
@dev_required
def dev_get_memories():
    page     = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 30, type=int), 100)
    source   = request.args.get('source', '')
    topic    = request.args.get('topic', '')

    query = Memory.query
    if source: query = query.filter_by(source=source)
    if topic:  query = query.filter(Memory.topic.ilike(f'%{topic}%'))

    sort_by = request.args.get('sort', 'recent')
    if sort_by == 'score':
        query = query.order_by(Memory.relevance_score.desc(), Memory.created_at.desc())
    elif sort_by == 'accesses':
        query = query.order_by(Memory.access_count.desc(), Memory.created_at.desc())
    else:
        query = query.order_by(Memory.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'memories': [{
            'id': m.id, 'topic': m.topic, 'content': m.content[:400],
            'source': m.source, 'score': m.relevance_score,
            'accesses': m.access_count, 'created': m.created_at.isoformat()
        } for m in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages
    })

@app.route('/api/dev/memories/<int:mid>', methods=['DELETE'])
@dev_required
def dev_delete_memory(mid):
    mem = Memory.query.get_or_404(mid)
    db.session.delete(mem)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/dev/memories/clear', methods=['POST'])
@dev_required
def dev_clear_memories():
    data    = request.json or {}
    source  = data.get('source', '')
    confirm = data.get('confirm', '')

    if confirm != 'CONFIRMAR':
        return jsonify({'error': 'Agrega confirm: "CONFIRMAR" para proceder'}), 400

    if source:
        count = Memory.query.filter_by(source=source).count()
        Memory.query.filter_by(source=source).delete()
    else:
        count = Memory.query.count()
        Memory.query.delete()

    db.session.commit()
    return jsonify({'success': True, 'deleted': count})

@app.route('/api/dev/users', methods=['GET'])
@dev_required
def dev_list_users():
    users = User.query.all()
    return jsonify({'users': [{
        'id': u.id, 'username': u.username, 'email': u.email,
        'is_developer': u.is_developer, 'is_active': u.is_active,
        'created_at': u.created_at.isoformat(),
        'conversations': Conversation.query.filter_by(user_id=u.id).count()
    } for u in users]})

@app.route('/api/dev/users/<int:uid>/toggle-dev', methods=['POST'])
@dev_required
def dev_toggle_developer(uid):
    user = User.query.get_or_404(uid)
    user.is_developer = not user.is_developer
    db.session.commit()
    return jsonify({'success': True, 'username': user.username, 'is_developer': user.is_developer})

@app.route('/api/dev/test-ai', methods=['POST'])
@dev_required
def dev_test_ai():
    try:
        data    = request.json or {}
        message = data.get('message', 'Hola, ¿funcionas correctamente?').strip()
        prompt  = data.get('system_prompt', get_config('system_prompt'))

        llm = LLMEngine()
        result = llm.chat(user_message=message, system_prompt=prompt, max_tokens=500)
        return jsonify({
            'test_message': message,
            'response':     result['response'],
            'provider':     result.get('provider'),
            'model':        result.get('model'),
            'tokens':       result.get('tokens', 0),
            'success':      result.get('success', False)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/setup', methods=['POST'])
def dev_setup():
    existing_dev = User.query.filter_by(is_developer=True).first()
    if existing_dev:
        return jsonify({'error': 'Ya existe un usuario desarrollador. Endpoint deshabilitado.'}), 403

    data      = request.json or {}
    username  = data.get('username', '').strip()
    password  = data.get('password', '')
    email     = data.get('email', f'{username}@cic.local')
    setup_key = data.get('setup_key', '')

    expected_key = os.environ.get('SETUP_KEY', '')
    if expected_key and setup_key != expected_key:
        return jsonify({'error': 'setup_key inválida'}), 403

    if not username or not password or len(password) < 8:
        return jsonify({'error': 'username y password (mín 8 chars) requeridos'}), 400

    try:
        user = User(username=username, email=email, is_developer=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        token   = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(days=90)
        sess    = UserSession(user_id=user.id, token=token, expires_at=expires)
        db.session.add(sess)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Desarrollador "{username}" creado.',
            'token':   token,
            'user_id': user.id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ========== MANEJO DE ERRORES ==========

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint no encontrado'}), 404
    try:
        return render_template('index.html')
    except Exception:
        return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Error interno del servidor'}), 500

@app.errorhandler(413)
def too_large(error):
    return jsonify({'error': 'Archivo demasiado grande (máx 32MB)'}), 413

# ========== INICIO ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
