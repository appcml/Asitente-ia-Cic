"""
Cic_IA - Asistente Inteligente EVOLUTIVO
Archivo principal - Versión 8.0 PRODUCTION READY
Mejoras: LLM real, seguridad, rendimiento, modo desarrollador completo
"""

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os
import json
import random
import threading
import time
import re
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

# SECRET_KEY siempre desde entorno — nunca hardcodeado
_secret = os.environ.get('SECRET_KEY')
if not _secret:
    _secret = secrets.token_hex(32)
    logger.warning("SECRET_KEY no configurada como variable de entorno. Generando aleatoria (sesiones no persistirán entre reinicios).")
app.config['SECRET_KEY'] = _secret

# Base de datos — con soporte SSL para Render/PostgreSQL
database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
# Render requiere SSL
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

# API Keys (desde entorno)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
OPENAI_API_KEY    = os.environ.get('OPENAI_API_KEY', '')

# Archivos
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt','pdf','png','jpg','jpeg','gif','doc','docx','py','js','html','css','json','csv','xlsx','xls','db','sqlite','md'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('models', exist_ok=True)

db = SQLAlchemy(app)

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
    """Conocimiento ingresado directamente por el desarrollador"""
    __tablename__ = 'manual_knowledge'
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), nullable=False)
    content     = db.Column(db.Text, nullable=False)
    category    = db.Column(db.String(100), index=True)
    tags        = db.Column(db.JSON, default=list)
    priority    = db.Column(db.Integer, default=1)  # 1=normal, 2=alta, 3=crítica
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
    """Configuración dinámica del sistema editable por el dev"""
    __tablename__ = 'system_config'
    id         = db.Column(db.Integer, primary_key=True)
    key        = db.Column(db.String(100), unique=True, nullable=False)
    value      = db.Column(db.Text)
    type       = db.Column(db.String(20), default='string')  # string, int, bool, json
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========== MIGRACIÓN ==========

def run_migration():
    """
    Migración segura: agrega columnas/tablas nuevas sin destruir datos existentes.
    Compatible con bases de datos de versiones anteriores (v7.x → v8.0).
    """
    try:
        with app.app_context():
            # Crear tablas nuevas que no existan (no toca las existentes)
            db.create_all()

            inspector = inspect(db.engine)
            tables    = inspector.get_table_names()

            def add_column_if_missing(table, column, definition):
                """Agrega una columna solo si no existe — safe para cualquier BD."""
                try:
                    cols = {col['name'] for col in inspector.get_columns(table)}
                    if column not in cols:
                        with db.engine.connect() as conn:
                            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                            conn.commit()
                        logger.info(f"Migración: columna {table}.{column} agregada")
                except Exception as e:
                    logger.warning(f"No se pudo agregar {table}.{column}: {e}")

            # ── Tabla: memory ──────────────────────────────────────────────
            if 'memory' in tables:
                add_column_if_missing('memory', 'tags', "JSON DEFAULT '[]'")

            # ── Tabla: conversation ────────────────────────────────────────
            if 'conversation' in tables:
                add_column_if_missing('conversation', 'tokens_used', 'INTEGER DEFAULT 0')
                add_column_if_missing('conversation', 'user_id',   'INTEGER')
                add_column_if_missing('conversation', 'mode_used', "VARCHAR(50) DEFAULT 'chat'")

            # ── Tabla: manual_knowledge ────────────────────────────────────
            # db.create_all() ya la creó si no existía

            # ── Tabla: system_config ───────────────────────────────────────
            # db.create_all() ya la creó si no existía

            # Config por defecto (solo inserta si no existe la clave)
            defaults = [
                ('ai_provider',                   'anthropic',                                                                                              'string'),
                ('ai_model',                      'claude-haiku-4-5-20251001',                                                                              'string'),
                ('system_prompt',                 'Eres Cic_IA, un asistente inteligente en español. Responde de forma clara, útil y amigable.',             'string'),
                ('max_tokens',                    '1000',                                                                                                    'int'),
                ('auto_learning_enabled',         'true',                                                                                                    'bool'),
                ('auto_learning_interval_hours',  '2',                                                                                                       'int'),
                ('max_memory_results',            '5',                                                                                                       'int'),
                ('web_search_enabled',            'true',                                                                                                    'bool'),
            ]
            for key, val, typ in defaults:
                try:
                    if not SystemConfig.query.filter_by(key=key).first():
                        db.session.add(SystemConfig(key=key, value=val, type=typ))
                except Exception:
                    pass
            db.session.commit()
            logger.info("✅ Migración completada")
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
    return request.args.get('token') or request.json.get('token') if request.is_json else None

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
        """Busca usando DuckDuckGo con fallback a búsqueda simple"""
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
            logger.warning(f"DuckDuckGo falló: {e}. Intentando método alternativo.")
            return WebSearchEngine._search_fallback(query, max_results)

    @staticmethod
    def _search_fallback(query: str, max_results: int = 3) -> list:
        """Fallback usando urllib"""
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

# ========== MOTOR LLM REAL ==========

class LLMEngine:
    """
    Motor de IA multi-proveedor con fallback automático.
    Orden de prioridad:
      1. Groq  (Llama 3 / Mixtral — gratis, rápido, 24/7)
      2. Ollama (modelo local en servidor propio / Colab)
      3. Anthropic Claude (si hay API key)
      4. OpenAI GPT (si hay API key)
      5. Respuesta básica (sin IA externa)
    """

    def __init__(self):
        self.anthropic_key = ANTHROPIC_API_KEY
        self.openai_key    = OPENAI_API_KEY
        self.groq_key      = os.environ.get('GROQ_API_KEY', '')
        self.ollama_url    = os.environ.get('OLLAMA_URL', '')   # ej: https://xxxx.ngrok.io
        self.groq_model    = os.environ.get('GROQ_MODEL',   'llama-3.1-8b-instant')
        self.ollama_model  = os.environ.get('OLLAMA_MODEL', 'llama3.2')

    def _build_context(self, user_message: str, memories: list, manual_knowledge: list) -> str:
        parts = []
        if manual_knowledge:
            parts.append("=== CONOCIMIENTO BASE ===")
            for mk in manual_knowledge[:5]:
                parts.append(f"[{mk.category or 'General'}] {mk.title}:\n{mk.content[:500]}")
            parts.append("")
        if memories:
            parts.append("=== CONOCIMIENTO APRENDIDO ===")
            for mem in memories[:3]:
                parts.append(f"Tema: {mem.topic or 'general'}\n{mem.content[:300]}")
            parts.append("")
        return "\n".join(parts)

    def chat(self, user_message: str, system_prompt: str, context: str = "",
             conversation_history: list = None, max_tokens: int = 1000) -> dict:
        """Intenta cada proveedor en orden hasta obtener respuesta exitosa."""

        full_system = system_prompt
        if context:
            full_system += f"\n\n{context}"

        # Orden de prioridad configurable
        provider = get_config('ai_provider', 'auto')

        if provider == 'auto':
            # Intentar en orden: Groq → Ollama → Anthropic → OpenAI → fallback
            providers = ['groq', 'ollama', 'anthropic', 'openai']
        else:
            providers = [provider]

        for p in providers:
            result = self._try_provider(p, user_message, full_system, conversation_history, max_tokens)
            if result.get('success'):
                logger.info(f"✅ Respuesta exitosa via {p}")
                return result
            else:
                logger.warning(f"⚠️ Proveedor {p} falló: {result.get('error', 'desconocido')}")

        # Si todo falla, respuesta básica
        return self._fallback_response(user_message)

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

    # ── GROQ (Llama 3 gratis — prioridad 1) ────────────────────────────────
    def _call_groq(self, user_message: str, system: str,
                   history: list = None, max_tokens: int = 1000) -> dict:
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
        return {
            'success':  True,
            'response': text,
            'tokens':   tokens,
            'provider': 'groq',
            'model':    self.groq_model
        }

    # ── OLLAMA (modelo local / Colab — prioridad 2) ─────────────────────────
    def _call_ollama(self, user_message: str, system: str,
                     history: list = None, max_tokens: int = 1000) -> dict:
        if not self.ollama_url:
            return {'success': False, 'error': 'Sin OLLAMA_URL'}

        # Construir prompt con historial
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
            timeout=120  # Ollama puede ser lento en Colab
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get('message', {}).get('content', '')
        if not text:
            return {'success': False, 'error': 'Ollama retornó respuesta vacía'}
        return {
            'success':  True,
            'response': text,
            'tokens':   data.get('eval_count', 0),
            'provider': 'ollama',
            'model':    self.ollama_model
        }

    # ── ANTHROPIC Claude ────────────────────────────────────────────────────
    def _call_anthropic(self, user_message: str, system: str,
                        history: list = None, max_tokens: int = 1000) -> dict:
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
        return {'success': True, 'response': text, 'tokens': tokens, 'provider': 'anthropic', 'model': model}

    # ── OPENAI GPT ──────────────────────────────────────────────────────────
    def _call_openai(self, user_message: str, system: str,
                     history: list = None, max_tokens: int = 1000) -> dict:
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
        return {'success': True, 'response': text, 'tokens': tokens, 'provider': 'openai', 'model': model}

    # ── FALLBACK (sin motor de IA) ──────────────────────────────────────────
    def _fallback_response(self, user_message: str) -> dict:
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ['hola', 'buenas', 'hey', 'saludos']):
            r = ("¡Hola! Soy Cic_IA. Actualmente no tengo ningún motor de IA conectado. "
                 "El desarrollador debe configurar GROQ_API_KEY (gratis) u OLLAMA_URL.")
        elif any(w in msg_lower for w in ['qué hora', 'qué día', 'fecha', 'hoy']):
            now   = datetime.now()
            dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
            meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
                     'septiembre','octubre','noviembre','diciembre']
            r = f"Hoy es {dias[now.weekday()]}, {now.day} de {meses[now.month-1]} de {now.year} — {now.strftime('%H:%M')}"
        else:
            r = (f"Recibí: '{user_message[:80]}'. "
                 "⚠️ Sin motor de IA activo. Configura GROQ_API_KEY o OLLAMA_URL en las variables de entorno.")
        return {'success': False, 'response': r, 'provider': 'fallback', 'tokens': 0}


# ========== MOTOR DE BÚSQUEDA DE MEMORIAS (optimizado) ==========

class MemoryEngine:
    @staticmethod
    def search(query: str, limit: int = 5) -> list:
        """Búsqueda eficiente por palabras clave — sin cargar toda la BD en RAM"""
        words = [w for w in query.lower().split() if len(w) > 3]
        if not words:
            return []

        try:
            # Búsqueda por topic primero (indexado)
            results = set()
            for word in words[:5]:
                mems = Memory.query.filter(
                    Memory.topic.ilike(f'%{word}%')
                ).order_by(Memory.relevance_score.desc()).limit(10).all()
                results.update(m.id for m in mems)

            # Búsqueda en contenido si no hay suficientes resultados
            if len(results) < 3:
                for word in words[:3]:
                    mems = Memory.query.filter(
                        Memory.content.ilike(f'%{word}%')
                    ).order_by(Memory.relevance_score.desc()).limit(10).all()
                    results.update(m.id for m in mems)

            if not results:
                return []

            memories = Memory.query.filter(Memory.id.in_(list(results))).order_by(
                Memory.relevance_score.desc(), Memory.access_count.desc()
            ).limit(limit).all()

            # Actualizar access_count en batch (eficiente)
            ids = [m.id for m in memories]
            if ids:
                Memory.query.filter(Memory.id.in_(ids)).update(
                    {'access_count': Memory.access_count + 1},
                    synchronize_session=False
                )
                db.session.commit()

            return memories
        except Exception as e:
            logger.error(f"Error buscando memorias: {e}")
            return []

    @staticmethod
    def search_manual_knowledge(query: str, limit: int = 5) -> list:
        """Busca en el conocimiento manual del desarrollador"""
        words = [w for w in query.lower().split() if len(w) > 2]
        if not words:
            return ManualKnowledge.query.filter_by(active=True).order_by(
                ManualKnowledge.priority.desc()
            ).limit(limit).all()

        results = set()
        for word in words[:5]:
            items = ManualKnowledge.query.filter(
                ManualKnowledge.active == True,
                db.or_(
                    ManualKnowledge.content.ilike(f'%{word}%'),
                    ManualKnowledge.title.ilike(f'%{word}%'),
                    ManualKnowledge.category.ilike(f'%{word}%')
                )
            ).order_by(ManualKnowledge.priority.desc()).limit(10).all()
            results.update(m.id for m in items)

        if not results:
            return []

        return ManualKnowledge.query.filter(
            ManualKnowledge.id.in_(list(results))
        ).order_by(ManualKnowledge.priority.desc()).limit(limit).all()

# ========== CLASE PRINCIPAL CIC_IA ==========

class CicIA:
    def __init__(self):
        self.search_engine  = WebSearchEngine()
        self.llm            = LLMEngine()
        self.memory_engine  = MemoryEngine()
        self._learning_thread = None
        self._start_auto_learning()

        with app.app_context():
            logger.info("=" * 55)
            logger.info("🤖 CIC_IA v8.0 INICIADA")
            logger.info(f"   Memorias: {Memory.query.count()}")
            logger.info(f"   Conversaciones: {Conversation.query.count()}")
            logger.info(f"   Conocimiento manual: {ManualKnowledge.query.count()}")
            provider = get_config('ai_provider', 'anthropic')
            has_key  = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY)
            logger.info(f"   Proveedor IA: {provider} ({'✅ API Key OK' if has_key else '⚠️ Sin API Key'})")
            logger.info("=" * 55)

    def _start_auto_learning(self):
        self._learning_thread = threading.Thread(
            target=self._auto_learning_loop, daemon=True
        )
        self._learning_thread.start()
        # Iniciar keepalive para evitar que Render se duerma
        threading.Thread(target=self._keepalive_loop, daemon=True).start()

    def _keepalive_loop(self):
        """
        Ping cada 10 minutos al propio servidor para evitar el sleep de Render.
        Render duerme servicios gratuitos tras 15 min de inactividad.
        """
        import urllib.request
        time.sleep(30)  # Espera inicial
        app_url = os.environ.get('RENDER_EXTERNAL_URL', '')
        if not app_url:
            logger.info("ℹ️ RENDER_EXTERNAL_URL no configurada — keepalive desactivado")
            return
        logger.info(f"💓 Keepalive activo → {app_url}/health cada 10 min")
        while True:
            try:
                req = urllib.request.Request(
                    f"{app_url}/health",
                    headers={'User-Agent': 'CicIA-Keepalive/1.0'}
                )
                urllib.request.urlopen(req, timeout=10)
                logger.info("💓 Keepalive OK")
            except Exception as e:
                logger.warning(f"💓 Keepalive error: {e}")
            time.sleep(600)  # cada 10 minutos

    def _auto_learning_loop(self):
        time.sleep(60)  # Espera inicial
        while True:
            try:
                with app.app_context():
                    if get_config('auto_learning_enabled', True):
                        self._perform_auto_learning()
            except Exception as e:
                logger.error(f"Error auto-learning: {e}")
            interval = get_config('auto_learning_interval_hours', 2)
            time.sleep(interval * 3600)

    def _perform_auto_learning(self, topic: str = None) -> dict:
        """Aprendizaje automático desde web"""
        default_topics = [
            'inteligencia artificial 2025', 'machine learning novedades',
            'python avances', 'desarrollo web tendencias', 'ciencia datos'
        ]
        query = topic or random.choice(default_topics)
        logger.info(f"🔍 Auto-aprendiendo: '{query}'")

        results = self.search_engine.search(query, max_results=4)
        if not results:
            return {'learned': 0, 'topic': query, 'error': 'Sin resultados web'}

        learned = 0
        for r in results:
            try:
                snippet = r['snippet'][:120] if r['snippet'] else ''
                if not snippet:
                    continue
                # Evitar duplicados eficientemente
                exists = Memory.query.filter(Memory.content.ilike(f'%{snippet[:60]}%')).first()
                if exists:
                    continue
                content = f"{r['title']}\n\n{r['snippet']}\n\nFuente: {r['url']}"
                mem = Memory(
                    content=content, source='auto_learning',
                    topic=query, relevance_score=0.6
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

        logger.info(f"✅ Aprendidos {learned} memorias sobre '{query}'")
        return {'learned': learned, 'topic': query}

    def force_learn(self, topic: str, content: str = None, user_id: int = None) -> dict:
        """Forzar aprendizaje sobre un tema — modo desarrollador"""
        with app.app_context():
            learned_items = []

            # Si se provee contenido directo, guardarlo como conocimiento manual
            if content:
                mk = ManualKnowledge(
                    title=topic,
                    content=content,
                    category='forzado',
                    priority=2,
                    added_by=user_id,
                    tags=['forced_learning']
                )
                db.session.add(mk)
                # También guardar como Memory para que el LLM lo use
                mem = Memory(
                    content=content,
                    source='manual_dev',
                    topic=topic,
                    relevance_score=0.95,
                    tags=['priority', 'manual']
                )
                db.session.add(mem)
                db.session.commit()
                learned_items.append({'type': 'manual', 'title': topic})

            # Buscar en web también
            web_result = self._perform_auto_learning(topic)
            if web_result.get('learned', 0) > 0:
                learned_items.append({'type': 'web', 'count': web_result['learned']})

            return {
                'success': True,
                'topic': topic,
                'manual_saved': bool(content),
                'web_learned': web_result.get('learned', 0),
                'total': len(learned_items)
            }

    def _get_user_conversation_history(self, user_id: int, limit: int = 10) -> list:
        """
        Recupera el historial real de conversaciones del usuario desde la BD.
        Esto permite que la IA recuerde conversaciones ANTERIORES, no solo la actual.
        """
        if not user_id:
            return []
        try:
            recent = Conversation.query.filter_by(user_id=user_id).order_by(
                Conversation.timestamp.desc()
            ).limit(limit).all()
            history = []
            for conv in reversed(recent):
                history.append({'role': 'user',      'content': conv.user_message[:500]})
                history.append({'role': 'assistant',  'content': conv.bot_response[:500]})
            return history
        except Exception as e:
            logger.error(f"Error recuperando historial: {e}")
            return []

    def _build_reasoning_prompt(self, user_message: str, memories: list,
                                 manual_knowledge: list, user_history: list) -> str:
        """
        Construye un system prompt enriquecido con:
        - Instrucciones de razonamiento paso a paso (Chain of Thought)
        - Conocimiento manual del desarrollador
        - Memorias aprendidas relevantes
        - Resumen del perfil del usuario basado en su historial
        """
        base_prompt = get_config(
            'system_prompt',
            'Eres Cic_IA, un asistente inteligente en español. Responde de forma clara, útil y amigable.'
        )

        parts = [base_prompt, ""]

        # ── Chain of Thought: razonamiento paso a paso ──────────────────
        parts.append("""=== INSTRUCCIONES DE RAZONAMIENTO ===
Antes de responder, analiza internamente:
1. ¿Qué está pidiendo exactamente el usuario?
2. ¿Tengo información relevante en mi conocimiento?
3. ¿El historial de conversación da contexto adicional?
4. ¿Cuál es la respuesta más útil y precisa?
Luego responde directamente sin mostrar este proceso al usuario.""")
        parts.append("")

        # ── Conocimiento manual (mayor prioridad) ───────────────────────
        if manual_knowledge:
            parts.append("=== CONOCIMIENTO BASE (usa esto como fuente prioritaria) ===")
            for mk in manual_knowledge[:5]:
                parts.append(f"[{mk.category or 'General'}] {mk.title}:\n{mk.content[:600]}")
            parts.append("")

        # ── Memorias aprendidas ─────────────────────────────────────────
        if memories:
            parts.append("=== CONOCIMIENTO APRENDIDO ===")
            for mem in memories[:4]:
                parts.append(f"Tema: {mem.topic or 'general'}\n{mem.content[:400]}")
            parts.append("")

        # ── Perfil del usuario basado en historial ──────────────────────
        if user_history and len(user_history) >= 4:
            parts.append("=== CONTEXTO DEL USUARIO ===")
            parts.append("Has conversado antes con este usuario. Aquí hay contexto de conversaciones anteriores:")
            # Resumir últimas 3 interacciones
            for i in range(0, min(6, len(user_history)), 2):
                if i+1 < len(user_history):
                    u = user_history[i]['content'][:100]
                    a = user_history[i+1]['content'][:100]
                    parts.append(f"- Usuario preguntó: '{u}...' → Respondiste: '{a}...'")
            parts.append("Usa este contexto para dar respuestas más personalizadas y coherentes.")
            parts.append("")

        return "\n".join(parts)

    def chat(self, user_message: str, user_id: int = None,
             conversation_history: list = None, mode: str = 'balanced') -> dict:
        """
        Procesamiento principal del chat con razonamiento mejorado.
        
        Capas de razonamiento:
        1. Memoria persistente: historial real de la BD
        2. Chain of Thought: razona antes de responder  
        3. Contexto conversacional: historial de la sesión actual
        """

        # Validar longitud
        if len(user_message) > 4000:
            user_message = user_message[:4000]

        # ── Capa 1: Recuperar historial persistente de la BD ────────────
        db_history = self._get_user_conversation_history(user_id, limit=8)

        # ── Combinar historial de BD con historial de sesión actual ─────
        # La sesión actual tiene prioridad (más reciente)
        combined_history = db_history
        if conversation_history:
            # Solo agregar mensajes de sesión que no dupliquen los de BD
            combined_history = db_history + conversation_history[-6:]

        # ── Buscar memorias y conocimiento relevante ────────────────────
        memories         = self.memory_engine.search(user_message, limit=get_config('max_memory_results', 5))
        manual_knowledge = self.memory_engine.search_manual_knowledge(user_message, limit=5)

        # ── Capa 2: Construir prompt con Chain of Thought ───────────────
        reasoning_prompt = self._build_reasoning_prompt(
            user_message, memories, manual_knowledge, db_history
        )

        # ── Tokens según modo ───────────────────────────────────────────
        tokens_map = {'fast': 600, 'balanced': 1200, 'complete': 2500}
        max_tokens = tokens_map.get(mode, 1200)

        # ── Capa 3: Llamar al LLM con contexto completo ─────────────────
        llm_result = self.llm.chat(
            user_message=user_message,
            system_prompt=reasoning_prompt,
            context="",  # ya está en el reasoning_prompt
            conversation_history=combined_history,
            max_tokens=max_tokens
        )

        response_text = llm_result['response']

        # ── Búsqueda web si el LLM falla ────────────────────────────────
        if not llm_result.get('success') and get_config('web_search_enabled', True):
            web_data = self._search_and_cache(user_message)
            if web_data:
                response_text += f"\n\n📖 Información encontrada en la web:\n{web_data}"

        # ── Guardar en BD para memoria futura ───────────────────────────
        self._save_conversation(
            user_msg=user_message,
            bot_resp=response_text,
            user_id=user_id,
            tokens=llm_result.get('tokens', 0),
            sources=['llm', llm_result.get('provider', 'unknown')]
        )

        return {
            'response':        response_text,
            'provider':        llm_result.get('provider', 'unknown'),
            'model':           llm_result.get('model', 'unknown'),
            'tokens_used':     llm_result.get('tokens', 0),
            'memories_used':   len(memories),
            'manual_kb_used':  len(manual_knowledge),
            'history_used':    len(combined_history),
            'success':         llm_result.get('success', False)
        }

    def _search_and_cache(self, query: str) -> str:
        """Busca en web con caché"""
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

            # Cachear
            cache = WebSearchCache(
                query=query,
                results={'summary': summary},
                expires_at=datetime.utcnow() + timedelta(hours=6)
            )
            db.session.merge(cache)
            db.session.commit()
            return summary
        except Exception as e:
            logger.error(f"Error web search: {e}")
            return ''

    def _save_conversation(self, user_msg: str, bot_resp: str,
                           user_id: int = None, tokens: int = 0, sources: list = None):
        try:
            conv = Conversation(
                user_id=user_id,
                user_message=user_msg[:2000],
                bot_response=bot_resp[:4000],
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
                'total_memories':    Memory.query.count(),
                'total_conversations': Conversation.query.count(),
                'manual_knowledge':  ManualKnowledge.query.filter_by(active=True).count(),
                'today_conversations': log.count if log else 0,
                'today_auto_learned':  log.auto_learned if log else 0,
                'ai_provider':       get_config('ai_provider', 'anthropic'),
                'ai_model':          get_config('ai_model', 'claude-haiku-4-5-20251001'),
                'has_api_key':       bool(ANTHROPIC_API_KEY or OPENAI_API_KEY),
                'web_search_enabled': get_config('web_search_enabled', True),
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
        'version':   '8.0',
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
    return jsonify({'success': True, 'message': 'Sesión cerrada'})

# ========== CHAT ==========

@app.route('/api/chat', methods=['POST'])
@token_required
def chat(current_user):
    try:
        data    = request.json or {}
        message = data.get('message', '').strip()
        mode    = data.get('mode', 'balanced')
        history = data.get('history', [])  # historial del frontend

        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        if len(message) > 4000:
            return jsonify({'error': 'Mensaje demasiado largo (máx 4000 caracteres)'}), 400

        result = cic_ia.chat(
            user_message=message,
            user_id=current_user.id,
            conversation_history=history,
            mode=mode
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error chat: {e}")
        return jsonify({'error': str(e)}), 500

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

# ========== MÓDULOS (compatibilidad) ==========

@app.route('/api/modules/list', methods=['GET'])
def list_modules():
    return jsonify({'modules': [
        {'id': 'chat',          'name': 'Chat IA',              'icon': '🤖', 'status': 'active'},
        {'id': 'web_search',    'name': 'Búsqueda Web',         'icon': '🔍', 'status': 'active'},
        {'id': 'memory',        'name': 'Memoria',              'icon': '🧠', 'status': 'active'},
        {'id': 'data_analysis', 'name': 'Análisis de Datos',    'icon': '📊', 'status': 'available'},
        {'id': 'code_assistant','name': 'Asistente de Código',  'icon': '💻', 'status': 'available'},
        {'id': 'file_manager',  'name': 'Archivos',             'icon': '📁', 'status': 'available'},
    ]})

# ==========================================
# ========== PANEL DESARROLLADOR ==========
# ==========================================

@app.route('/developer')
def developer_panel():
    """Panel de desarrollador — renderiza template o retorna info básica"""
    try:
        return render_template('developer.html')
    except Exception:
        return jsonify({'message': 'Panel desarrollador activo. Usa la API /api/dev/*'})

# --- Estadísticas detalladas ---

@app.route('/api/dev/stats', methods=['GET'])
@dev_required
def dev_stats():
    try:
        today = date.today()
        log   = LearningLog.query.filter_by(date=today).first()

        # Historial de aprendizaje (últimos 7 días)
        week_logs = LearningLog.query.filter(
            LearningLog.date >= today - timedelta(days=7)
        ).order_by(LearningLog.date.desc()).all()

        # Últimas conversaciones
        last_convs = Conversation.query.order_by(
            Conversation.timestamp.desc()
        ).limit(5).all()

        return jsonify({
            'system': {
                'total_memories':      Memory.query.count(),
                'total_conversations': Conversation.query.count(),
                'total_users':         User.query.count(),
                'active_sessions':     UserSession.query.count(),
                'manual_knowledge':    ManualKnowledge.query.filter_by(active=True).count(),
                'cached_searches':     WebSearchCache.query.count(),
            },
            'today': {
                'conversations': log.count if log else 0,
                'auto_learned':  log.auto_learned if log else 0,
                'web_searches':  log.web_searches if log else 0,
            },
            'week_activity': [{
                'date':         l.date.isoformat(),
                'conversations': l.count,
                'auto_learned': l.auto_learned,
            } for l in week_logs],
            'recent_conversations': [{
                'user':     c.user_message[:80],
                'bot':      c.bot_response[:80],
                'time':     c.timestamp.isoformat(),
                'tokens':   c.tokens_used,
            } for c in last_convs],
            'ai_config': {
                'provider':        get_config('ai_provider'),
                'model':           get_config('ai_model'),
                'has_anthropic':   bool(ANTHROPIC_API_KEY),
                'has_openai':      bool(OPENAI_API_KEY),
                'system_prompt':   get_config('system_prompt'),
                'max_tokens':      get_config('max_tokens'),
                'auto_learning':   get_config('auto_learning_enabled'),
                'web_search':      get_config('web_search_enabled'),
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Gestión de conocimiento manual ---

@app.route('/api/dev/knowledge', methods=['GET'])
@dev_required
def dev_get_knowledge():
    """Lista todo el conocimiento manual"""
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
            'id':       k.id,
            'title':    k.title,
            'category': k.category,
            'content':  k.content[:300],
            'priority': k.priority,
            'tags':     k.tags,
            'created':  k.created_at.isoformat()
        } for k in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages
    })

@app.route('/api/dev/knowledge', methods=['POST'])
@dev_required
def dev_add_knowledge():
    """Agregar conocimiento manual — el dev enseña a la IA directamente"""
    try:
        data    = request.json or {}
        title   = data.get('title', '').strip()
        content = data.get('content', '').strip()

        if not title or not content:
            return jsonify({'error': 'title y content son requeridos'}), 400

        # Obtener user_id del token
        token   = _get_token_from_request()
        session = UserSession.query.filter_by(token=token).first()
        user_id = session.user_id if session else None

        mk = ManualKnowledge(
            title=title,
            content=content,
            category=data.get('category', 'general'),
            tags=data.get('tags', []),
            priority=data.get('priority', 1),
            added_by=user_id
        )
        db.session.add(mk)

        # También agregar a Memory para que el LLM lo use en contexto
        mem = Memory(
            content=f"{title}\n\n{content}",
            source='manual_dev',
            topic=title,
            relevance_score=0.9 + (data.get('priority', 1) * 0.03),
            tags=data.get('tags', [])
        )
        db.session.add(mem)
        db.session.commit()

        return jsonify({
            'success':     True,
            'id':          mk.id,
            'message':     f'Conocimiento "{title}" agregado exitosamente',
            'memory_id':   mem.id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/knowledge/<int:kid>', methods=['PUT'])
@dev_required
def dev_update_knowledge(kid):
    """Actualizar conocimiento existente"""
    try:
        mk = ManualKnowledge.query.get_or_404(kid)
        data = request.json or {}
        if 'title'    in data: mk.title    = data['title']
        if 'content'  in data: mk.content  = data['content']
        if 'category' in data: mk.category = data['category']
        if 'tags'     in data: mk.tags     = data['tags']
        if 'priority' in data: mk.priority = data['priority']
        if 'active'   in data: mk.active   = data['active']
        mk.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Actualizado correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/knowledge/<int:kid>', methods=['DELETE'])
@dev_required
def dev_delete_knowledge(kid):
    """Eliminar conocimiento"""
    mk = ManualKnowledge.query.get_or_404(kid)
    mk.active = False  # Soft delete
    db.session.commit()
    return jsonify({'success': True, 'message': 'Conocimiento desactivado'})

# --- Aprendizaje forzado ---

@app.route('/api/dev/learn', methods=['POST'])
@dev_required
def dev_force_learn():
    """Forzar aprendizaje sobre un tema específico"""
    try:
        data    = request.json or {}
        topic   = data.get('topic', '').strip()
        content = data.get('content', '').strip()  # Opcional: contenido directo

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
    """Aprendizaje masivo — lista de temas o textos"""
    try:
        data  = request.json or {}
        items = data.get('items', [])  # [{topic, content?}, ...]

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
            time.sleep(0.5)  # Respetar rate limits

        total_learned = sum(r.get('web_learned', 0) for r in results)
        return jsonify({
            'success': True,
            'processed': len(results),
            'total_learned': total_learned,
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Configuración del sistema ---

@app.route('/api/dev/config', methods=['GET'])
@dev_required
def dev_get_config():
    """Ver toda la configuración del sistema"""
    configs = SystemConfig.query.all()
    return jsonify({
        'config': {c.key: {'value': c.value, 'type': c.type, 'updated': c.updated_at.isoformat()} for c in configs}
    })

@app.route('/api/dev/config', methods=['PUT'])
@dev_required
def dev_update_config():
    """Actualizar configuración en tiempo real"""
    try:
        data    = request.json or {}
        updates = data.get('updates', {})  # {key: value, ...}

        if not updates:
            return jsonify({'error': 'updates es requerido'}), 400

        # Keys protegidas que no se pueden cambiar por API
        protected = {'SECRET_KEY', 'DATABASE_URL'}
        updated = []
        for key, value in updates.items():
            if key in protected:
                continue
            set_config(key, value)
            updated.append(key)

        return jsonify({
            'success': True,
            'updated': updated,
            'message': f'{len(updated)} configuraciones actualizadas'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/config/prompt', methods=['PUT'])
@dev_required
def dev_update_prompt():
    """Actualizar el system prompt de la IA"""
    try:
        data   = request.json or {}
        prompt = data.get('prompt', '').strip()
        if not prompt:
            return jsonify({'error': 'prompt es requerido'}), 400
        if len(prompt) > 2000:
            return jsonify({'error': 'Prompt muy largo (máx 2000 caracteres)'}), 400
        set_config('system_prompt', prompt)
        return jsonify({'success': True, 'message': 'System prompt actualizado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Gestión de memorias ---

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

    pagination = query.order_by(
        Memory.relevance_score.desc(), Memory.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'memories': [{
            'id':        m.id,
            'topic':     m.topic,
            'content':   m.content[:400],
            'source':    m.source,
            'score':     m.relevance_score,
            'accesses':  m.access_count,
            'created':   m.created_at.isoformat()
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
    """Limpiar memorias por fuente"""
    data   = request.json or {}
    source = data.get('source', '')
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

# --- Usuarios ---

@app.route('/api/dev/users', methods=['GET'])
@dev_required
def dev_list_users():
    users = User.query.all()
    return jsonify({'users': [{
        'id':          u.id,
        'username':    u.username,
        'email':       u.email,
        'is_developer': u.is_developer,
        'is_active':   u.is_active,
        'created_at':  u.created_at.isoformat(),
        'conversations': Conversation.query.filter_by(user_id=u.id).count()
    } for u in users]})

@app.route('/api/dev/users/<int:uid>/toggle-dev', methods=['POST'])
@dev_required
def dev_toggle_developer(uid):
    """Dar/quitar rol de desarrollador"""
    user = User.query.get_or_404(uid)
    user.is_developer = not user.is_developer
    db.session.commit()
    return jsonify({'success': True, 'username': user.username, 'is_developer': user.is_developer})

# --- Test de IA ---

@app.route('/api/dev/test-ai', methods=['POST'])
@dev_required
def dev_test_ai():
    """Probar la IA con un mensaje sin guardar en BD"""
    try:
        data    = request.json or {}
        message = data.get('message', 'Hola, ¿funcionas correctamente?').strip()
        prompt  = data.get('system_prompt', get_config('system_prompt'))

        llm = LLMEngine()
        result = llm.chat(
            user_message=message,
            system_prompt=prompt,
            max_tokens=500
        )
        return jsonify({
            'test_message':  message,
            'response':      result['response'],
            'provider':      result.get('provider'),
            'model':         result.get('model'),
            'tokens':        result.get('tokens', 0),
            'success':       result.get('success', False)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Crear primer usuario desarrollador (setup inicial) ---

@app.route('/api/dev/setup', methods=['POST'])
def dev_setup():
    """
    Setup inicial — SOLO funciona si NO existe ningún usuario desarrollador.
    Una vez que existe un dev, este endpoint queda bloqueado automáticamente.
    """
    existing_dev = User.query.filter_by(is_developer=True).first()
    if existing_dev:
        return jsonify({'error': 'Ya existe un usuario desarrollador. Este endpoint está deshabilitado.'}), 403

    data     = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    email    = data.get('email', f'{username}@cic.local')
    setup_key = data.get('setup_key', '')

    # Requiere una clave de setup configurada como variable de entorno
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
            'success':  True,
            'message':  f'Desarrollador "{username}" creado. Guarda tu token.',
            'token':    token,
            'user_id':  user.id
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
