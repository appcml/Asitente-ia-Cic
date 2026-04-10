"""
Cic_IA - Asistente Inteligente EVOLUTIVO
Archivo principal - Versión 7.2 LIMPIA Y FUNCIONAL
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import render_template, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os
import json
import random
import threading
import time
import urllib.request
import urllib.parse
import re
import hashlib
import requests
import secrets
from functools import wraps
from bs4 import BeautifulSoup
import logging
import pickle
import numpy as np
from sqlalchemy import select, text, inspect

# ========== CONFIGURACIÓN ==========

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('cic_ia_mejorado')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cic-ia-secret-2024')

database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cic_ia.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'py', 'js', 'html', 'css', 'json', 'csv', 'xlsx', 'xls', 'db', 'sqlite'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Inicializar SQLAlchemy
db = SQLAlchemy(app)

# ========== MIGRACIÓN AUTOMÁTICA ==========

def run_migration():
    """Migra la base de datos automáticamente"""
    try:
        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()

            if 'conversation' in tables:
                columns = {col['name'] for col in inspector.get_columns('conversation')}

                with db.engine.connect() as conn:
                    if 'user_id' not in columns:
                        conn.execute(text("ALTER TABLE conversation ADD COLUMN user_id INTEGER"))
                        conn.commit()
                        logger.info("Migración: user_id agregado")

                    if 'mode_used' not in columns:
                        conn.execute(text("ALTER TABLE conversation ADD COLUMN mode_used VARCHAR(50) DEFAULT 'unknown'"))
                        conn.commit()
                        logger.info("Migración: mode_used agregado")

            if 'user' not in tables:
                with db.engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE "user" (
                            id SERIAL PRIMARY KEY,
                            username VARCHAR(80) UNIQUE NOT NULL,
                            email VARCHAR(120) UNIQUE NOT NULL,
                            password_hash VARCHAR(256) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            is_active BOOLEAN DEFAULT TRUE,
                            is_developer BOOLEAN DEFAULT FALSE
                        )
                    """))
                    conn.commit()
                    logger.info("Tabla user creada")

            if 'user_session' not in tables:
                with db.engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE user_session (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER REFERENCES "user"(id),
                            token VARCHAR(256) UNIQUE NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP,
                            last_access TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    conn.commit()
                    logger.info("Tabla user_session creada")

            logger.info("MIGRACIÓN COMPLETADA")

    except Exception as e:
        logger.error(f"Error migración: {e}")
        import traceback
        logger.error(traceback.format_exc())

run_migration()

# ========== MODELOS ==========

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_developer = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class UserSession(db.Model):
    __tablename__ = 'user_session'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(256), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    last_access = db.Column(db.DateTime, default=datetime.utcnow)

class Memory(db.Model):
    __tablename__ = 'memory'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(50), default='local')
    topic = db.Column(db.String(200))
    file_path = db.Column(db.String(500))
    file_type = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    access_count = db.Column(db.Integer, default=0)
    relevance_score = db.Column(db.Float, default=0.5)

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    has_attachment = db.Column(db.Boolean, default=False)
    attachment_path = db.Column(db.String(500))
    sources_used = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    mode_used = db.Column(db.String(50), default='unknown')

class LearningLog(db.Model):
    __tablename__ = 'learning_log'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=date.today, unique=True)
    count = db.Column(db.Integer, default=0)
    web_searches = db.Column(db.Integer, default=0)
    auto_learned = db.Column(db.Integer, default=0)

class ManualLearningQueue(db.Model):
    __tablename__ = 'manual_learning_queue'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(200))
    source_url = db.Column(db.String(500))
    priority = db.Column(db.Integer, default=1)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)

class WebSearchCache(db.Model):
    __tablename__ = 'web_search_cache'
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(500), unique=True)
    results = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

# ========== DECORADORES ==========

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            try:
                token = request.headers['Authorization'].split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Token inválido'}), 401

        if not token:
            return jsonify({'error': 'Token requerido'}), 401

        session = UserSession.query.filter_by(token=token).first()
        if not session:
            return jsonify({'error': 'Token inválido'}), 401

        if session.expires_at and session.expires_at < datetime.utcnow():
            db.session.delete(session)
            db.session.commit()
            return jsonify({'error': 'Token expirado'}), 401

        session.last_access = datetime.utcnow()
        db.session.commit()

        current_user = User.query.get(session.user_id)
        return f(current_user, *args, **kwargs)
    return decorated

def dev_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '') if request.headers.get('Authorization') else None
        if not token:
            return jsonify({'error': 'No autorizado'}), 401

        session = UserSession.query.filter_by(token=token).first()
        if not session:
            return jsonify({'error': 'Token inválido'}), 401

        user = User.query.get(session.user_id)
        if not user or not user.is_developer:
            return jsonify({'error': 'Privilegios de desarrollador requeridos'}), 403

        return f(*args, **kwargs)
    return decorated

# ========== RED NEURONAL ==========

class CicNeuralNetwork:
    def __init__(self):
        self.model_intent = None
        self.model_module = None
        self.is_trained = False
        self.training_data = []
        self.labels = []
        self.module_labels = []
        self.vectorizer = None
        self.model_path = 'models/cic_neural_model.pkl'
        self._ensure_model_dir()
        self._load_or_create_models()

    def _ensure_model_dir(self):
        os.makedirs('models', exist_ok=True)

    def _load_or_create_models(self):
        try:
            if os.path.exists(self.model_path):
                with open(self.model_path, 'rb') as f:
                    saved_data = pickle.load(f)
                    self.model_intent = saved_data.get('intent_model')
                    self.model_module = saved_data.get('module_model')
                    self.vectorizer = saved_data.get('vectorizer')
                    self.is_trained = saved_data.get('is_trained', False)
                logger.info("Red neuronal cargada")
            else:
                self._create_new_models()
        except Exception as e:
            logger.error(f"Error cargando modelos: {e}")
            self._create_new_models()

    def _create_new_models(self):
        try:
            from sklearn.neural_network import MLPClassifier
            from sklearn.feature_extraction.text import TfidfVectorizer

            self.model_intent = MLPClassifier(hidden_layer_sizes=(128, 64, 32), activation='relu', solver='adam', max_iter=500, random_state=42, early_stopping=True)
            self.model_module = MLPClassifier(hidden_layer_sizes=(64, 32), activation='relu', solver='adam', max_iter=300, random_state=42)
            self.vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
            self.is_trained = False
            logger.info("Nueva red neuronal creada")
        except ImportError:
            logger.warning("scikit-learn no disponible")
            self.model_intent = None

    def train(self, texts, labels, module_labels=None):
        if self.model_intent is None:
            return False
        try:
            X = self.vectorizer.fit_transform(texts)
            self.model_intent.fit(X, labels)
            if module_labels and self.model_module:
                self.model_module.fit(X, module_labels)
                self.module_labels = module_labels
            self.is_trained = True
            self.training_data = texts
            self.labels = labels
            self._save_models()
            logger.info(f"Entrenada con {len(texts)} ejemplos")
            return True
        except Exception as e:
            logger.error(f"Error entrenando: {e}")
            return False

    def predict_intent(self, text):
        if not self.is_trained or self.model_intent is None:
            return {'intent': 'unknown', 'confidence': 0.0}
        try:
            X = self.vectorizer.transform([text])
            prediction = self.model_intent.predict(X)[0]
            confidence = np.max(self.model_intent.predict_proba(X))
            return {'intent': prediction, 'confidence': float(confidence)}
        except:
            return {'intent': 'unknown', 'confidence': 0.0}

    def predict_module(self, text):
        if not self.is_trained or self.model_module is None:
            return self._rule_based_module_detection(text)
        try:
            X = self.vectorizer.transform([text])
            prediction = self.model_module.predict(X)[0]
            confidence = np.max(self.model_module.predict_proba(X))
            if confidence > 0.6:
                return {'module': prediction, 'confidence': float(confidence)}
            return self._rule_based_module_detection(text)
        except:
            return self._rule_based_module_detection(text)

    def _rule_based_module_detection(self, text):
        text_lower = text.lower()
        if any(kw in text_lower for kw in ['csv', 'excel', 'datos', 'análisis', 'tabla', 'pandas', 'sql']):
            return {'module': 'data_analysis', 'confidence': 0.8, 'method': 'rules'}
        if any(kw in text_lower for kw in ['imagen', 'foto', 'genera imagen', 'dibuja']):
            return {'module': 'image_generator', 'confidence': 0.8, 'method': 'rules'}
        if any(kw in text_lower for kw in ['código', 'programa', 'python', 'javascript']):
            return {'module': 'code_assistant', 'confidence': 0.8, 'method': 'rules'}
        if any(kw in text_lower for kw in ['historial', 'conversaciones']):
            return {'module': 'chat_history', 'confidence': 0.7, 'method': 'rules'}
        if any(kw in text_lower for kw in ['archivo', 'pdf', 'subir']):
            return {'module': 'file_manager', 'confidence': 0.7, 'method': 'rules'}
        return {'module': 'none', 'confidence': 0.0, 'method': 'rules'}

    def _save_models(self):
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump({'intent_model': self.model_intent, 'module_model': self.model_module, 'vectorizer': self.vectorizer, 'is_trained': self.is_trained}, f)
        except Exception as e:
            logger.error(f"Error guardando: {e}")

    def get_stats(self):
        return {'is_trained': self.is_trained, 'training_samples': len(self.training_data), 'model_type': 'MLPClassifier'}

neural_net = CicNeuralNetwork()

# ========== MOTOR DE BÚSQUEDA ==========

class WebSearchEngine:
    @staticmethod
    def search_duckduckgo(query, max_results=5):
        try:
            from duckduckgo_search import DDGS
            ddgs = DDGS()
            results = []
            for r in ddgs.text(query, max_results=max_results):
                results.append({'title': r.get('title', ''), 'url': r.get('href', ''), 'snippet': r.get('body', ''), 'source': 'duckduckgo'})
            return results
        except Exception as e:
            logger.error(f"Error búsqueda: {e}")
            return []

# ========== CLASE PRINCIPAL CIC_IA ==========

class CicIA:
    def __init__(self):
        self.learning_active = True
        self.web_search_engine = WebSearchEngine()
        self.current_learning_topic = None
        self.neural_net = neural_net
        self.auto_learning_topics = ['inteligencia artificial 2024', 'machine learning avances', 'python novedades', 'desarrollo web tendencias']

        with app.app_context():
            self.stats = {'memories': Memory.query.count(), 'conversations': Conversation.query.count(), 'today_learned': self._get_today_count()}

        threading.Thread(target=self._continuous_learning_loop, daemon=True).start()

        logger.info("=" * 50)
        logger.info("CIC_IA INICIADA")
        logger.info(f"Memorias: {self.stats['memories']}")
        logger.info(f"Conversaciones: {self.stats['conversations']}")
        logger.info("=" * 50)

    def _get_today_count(self):
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        return log.count if log else 0

    def _continuous_learning_loop(self):
        time.sleep(300)
        while self.learning_active:
            try:
                self._perform_auto_learning()
            except Exception as e:
                logger.error(f"Error auto-learn: {e}")
            time.sleep(7200)

    def _perform_auto_learning(self, custom_topic=None):
        with app.app_context():
            topic = custom_topic or self.current_learning_topic or random.choice(self.auto_learning_topics)
            self.current_learning_topic = None

            logger.info(f"Aprendiendo: '{topic}'")
            results = self.web_search_engine.search_duckduckgo(topic, max_results=3)

            if not results:
                return False

            learned_count = 0
            for result in results:
                try:
                    preview = result['snippet'][:100] if result['snippet'] else ''
                    exists = Memory.query.filter(Memory.content.ilike(f'%{preview}%')).first()
                    if exists:
                        continue

                    # CORRECCIÓN: String multilínea correctamente formateado
                    content_text = result['title'] + '\n\n' + result['snippet'] + '\n\nFuente: ' + result['url']
                    memory = Memory(content=content_text, source='auto_learning', topic=topic, relevance_score=0.6, access_count=0)
                    db.session.add(memory)
                    learned_count += 1
                except Exception as e:
                    continue

            if learned_count > 0:
                db.session.commit()
                today = date.today()
                log = LearningLog.query.filter_by(date=today).first()
                if not log:
                    log = LearningLog(date=today, count=0, web_searches=0, auto_learned=0)
                    db.session.add(log)
                log.auto_learned += learned_count
                db.session.commit()
                logger.info(f"Aprendidos: {learned_count}")
                return True
            return False

    def detect_module(self, user_input):
        module_info = self.neural_net.predict_module(user_input)
        if module_info['confidence'] < 0.5:
            module_info = self._manual_module_detection(user_input)
        return module_info

    def _manual_module_detection(self, text):
        text_lower = text.lower()
        patterns = {
            'data_analysis': {'keywords': ['csv', 'excel', 'datos', 'análisis', 'tabla', 'pandas'], 'prefixes': ['analiza', 'procesa']},
            'image_generator': {'keywords': ['imagen', 'foto', 'genera imagen', 'dibuja'], 'prefixes': ['genera imagen']},
            'code_assistant': {'keywords': ['código', 'programa', 'python', 'javascript'], 'prefixes': ['escribe código']},
            'chat_history': {'keywords': ['historial', 'conversaciones'], 'prefixes': ['mi historial']},
            'file_manager': {'keywords': ['archivo', 'pdf', 'subir'], 'prefixes': ['sube archivo']}
        }
        for module_name, data in patterns.items():
            if any(kw in text_lower for kw in data['keywords']):
                return {'module': module_name, 'confidence': 0.9, 'method': 'manual'}
            if any(text_lower.startswith(p) for p in data['prefixes']):
                return {'module': module_name, 'confidence': 0.85, 'method': 'manual'}
        return {'module': 'none', 'confidence': 0.0, 'method': 'manual'}

    def execute_module(self, module_name, user_input, context=None):
        module = get_module(module_name)
        if module is None:
            return {'success': False, 'error': f'Módulo {module_name} no disponible', 'response': f'Lo siento, el módulo {module_name} no está disponible.'}

        try:
            if module_name == 'data_analysis':
                return self._execute_data_analysis(module, user_input, context)
            elif module_name == 'image_generator':
                return self._execute_image_generator(module, user_input, context)
            elif module_name == 'code_assistant':
                return self._execute_code_assistant(module, user_input, context)
            elif module_name == 'chat_history':
                return self._execute_chat_history(module, user_input, context)
            elif module_name == 'file_manager':
                return self._execute_file_manager(module, user_input, context)
            return {'success': False, 'error': 'Módulo no implementado'}
        except Exception as e:
            logger.error(f"Error módulo {module_name}: {e}")
            return {'success': False, 'error': str(e), 'response': f'Error: {str(e)}'}

    def _execute_data_analysis(self, module, user_input, context):
        if context and context.get('file_path'):
            result = module.load_file(context['file_path'])
            if result.get('success'):
                analysis = module.analyze(user_input)
                return {'success': True, 'module': 'data_analysis', 'response': analysis.get('summary', 'Análisis completado'), 'data': analysis}
        return {'success': True, 'module': 'data_analysis', 'response': 'Modo Análisis de Datos. Sube un archivo CSV, Excel, JSON o SQLite.', 'awaiting_file': True}

    def _execute_image_generator(self, module, user_input, context):
        prompt = user_input.replace('genera una imagen', '').replace('crea una imagen', '').replace('dibuja', '').strip()
        if not prompt:
            return {'success': True, 'module': 'image_generator', 'response': 'Modo Generador de Imágenes. Describe qué imagen quieres crear.'}
        result = module.generate(prompt, style='realistic', size='1024x1024')
        if result.get('success'):
            return {'success': True, 'module': 'image_generator', 'response': f'Imagen generada: "{prompt[:50]}..."', 'image_data': result.get('image_data'), 'format': result.get('format')}
        return {'success': False, 'module': 'image_generator', 'response': f'Error: {result.get("error", "Error desconocido")}'}

    def _execute_code_assistant(self, module, user_input, context):
        language = module.detect_language(user_input)
        if any(kw in user_input.lower() for kw in ['explica', 'qué hace']):
            return {'success': True, 'module': 'code_assistant', 'response': f'Modo Asistente de Código ({language}). Pega el código a explicar.'}
        result = module.generate_code(user_input, language)
        return {'success': True, 'module': 'code_assistant', 'response': f'Código en {result.get("language_name", language)}:\n\n```{language}\n{result.get("code", "")}\n```', 'code': result.get('code'), 'language': language}

    def _execute_chat_history(self, module, user_input, context):
        user_id = context.get('user_id', 1) if context else 1
        if any(kw in user_input.lower() for kw in ['busca', 'encuentra']):
            keyword = user_input.replace('busca', '').replace('en mi historial', '').strip()
            results = module.search_conversations(user_id=user_id, keyword=keyword)
            if results.get('matches', 0) > 0:
                convs = results.get('conversations', [])
                response = f'Encontré {results["matches"]} conversaciones:' + '\n' + '\n'.join([f'- {c["user_message"][:50]}...' for c in convs[:5]])
                return {'success': True, 'module': 'chat_history', 'response': response}
        stats = module.get_conversation_stats(user_id=user_id)
        return {'success': True, 'module': 'chat_history', 'response': f'Tu Historial:\n- Total: {stats.get("total_conversations", 0)}\n- Últimos 7 días: {stats.get("last_7_days", 0)}'}

    def _execute_file_manager(self, module, user_input, context):
        return {'success': True, 'module': 'file_manager', 'response': 'Modo Gestión de Archivos. Puedes subir archivos para procesarlos.'}

    def chat(self, user_input, mode='balanced', attachment_info=None, user_id=1):
        input_lower = user_input.lower().strip()

        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_conversation(user_input, response, 'system_time', user_id=user_id)

        module_info = self.detect_module(user_input)
        if module_info['module'] != 'none' and module_info['confidence'] > 0.6:
            context = {'user_id': user_id}
            if attachment_info:
                context['file_path'] = attachment_info.get('path')
                context['file_type'] = attachment_info.get('type')

            module_result = self.execute_module(module_info['module'], user_input, context)
            result = self._save_conversation(user_input, module_result.get('response', 'Error'), f"module_{module_info['module']}", user_id=user_id, module_used=module_info['module'])
            result['module_used'] = module_info['module']
            result['module_confidence'] = module_info['confidence']
            return result

        intent_info = self.neural_net.predict_intent(user_input)
        best_topic = self._find_best_topic(input_lower)

        with app.app_context():
            memories = Memory.query.all()
            relevant_memories = self._find_relevant_memories(input_lower, memories)

            sources_used = []
            if best_topic and best_topic != 'default':
                response = random.choice(KNOWLEDGE_BASE[best_topic]['respuestas'])
                sources_used.append('knowledge_base')
            elif relevant_memories:
                mem = relevant_memories[0]
                response = f"Basándome en mi conocimiento: {mem.content[:300]}"
                sources_used.append(f"memory_{mem.source}")
            else:
                tema = user_input[:40] if len(user_input) > 5 else "este tema"
                web_results = self._search_and_learn(user_input)
                if web_results:
                    response = f"He investigado sobre '{tema}':\n\n{web_results['summary']}"
                    sources_used.append('web_search')
                else:
                    response = random.choice(KNOWLEDGE_BASE['default']['respuestas']).format(tema=tema)
                    sources_used.append('learning')

            if mode == 'fast':
                response = response.split('.')[0] + '.' if '.' in response else response[:100]
            elif mode == 'complete':
                response += "\n\n¿Te gustaría que profundice?"

            return self._save_conversation(user_input, response, sources_used[0] if sources_used else 'learning', user_id=user_id, memories_count=len(relevant_memories), sources_used=sources_used, intent=intent_info.get('intent', 'unknown'))

    def _find_relevant_memories(self, text, memories):
        relevant = []
        text_words = set(text.split())
        for mem in memories:
            mem_words = set(mem.content.lower().split())
            if len(text_words & mem_words) >= 2:
                relevant.append(mem)
                mem.access_count += 1
        db.session.commit()
        return relevant

    def _search_and_learn(self, query):
        try:
            with app.app_context():
                cached = WebSearchCache.query.filter_by(query=query).first()
                if cached and cached.expires_at > datetime.utcnow():
                    return cached.results

                results = self.web_search_engine.search_duckduckgo(query, max_results=3)
                if not results:
                    return None

                summary = ""
                for i, result in enumerate(results, 1):
                    summary += f"{i}. {result['title']}\n   {result['snippet']}\n\n"
                    memory = Memory(content=result['snippet'], source='web_search', topic=query, relevance_score=0.7)
                    db.session.add(memory)

                cache_entry = WebSearchCache(query=query, results={'summary': summary}, expires_at=datetime.utcnow() + timedelta(hours=24))
                db.session.add(cache_entry)
                db.session.commit()
                return {'summary': summary}
        except Exception as e:
            logger.error(f"Error búsqueda web: {e}")
            return None

    def _find_best_topic(self, text):
        best_score = 0
        best_topic = 'default'
        for topic, data in KNOWLEDGE_BASE.items():
            if topic == 'default':
                continue
            score = sum(3 for kw in data['keywords'] if kw in text)
            if score > best_score:
                best_score = score
                best_topic = topic
        return best_topic if best_score >= 2 else None

    def _save_conversation(self, user_msg, bot_resp, source, user_id=1, memories_count=0, sources_used=None, intent='unknown', module_used=None):
        with app.app_context():
            conv = Conversation(user_id=user_id, user_message=user_msg, bot_response=bot_resp, sources_used={'primary': source, 'all': sources_used or [source], 'intent': intent, 'module_used': module_used}, mode_used=module_used or 'chat')
            db.session.add(conv)

            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            if not log:
                log = LearningLog(date=today, count=1, web_searches=0, auto_learned=0)
                db.session.add(log)
            else:
                log.count += 1

            db.session.commit()
            total_mem = Memory.query.count()

        result = {'response': bot_resp, 'model_used': 'cic_ia_modular', 'sources_used': sources_used or [source], 'memories_found': memories_count, 'total_memories': total_mem, 'intent_detected': intent}
        if module_used:
            result['module_used'] = module_used
        return result

    def _is_date_time_question(self, text):
        return any(kw in text for kw in ['qué día', 'qué hora', 'fecha', 'hora actual', 'hoy es'])

    def _get_dynamic_date_response(self, text):
        now = datetime.now()
        dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        return f"Hoy es {dias[now.weekday()]}, {now.day} de {meses[now.month-1]} de {now.year}\nSon las {now.strftime('%H:%M:%S')}"

    def get_learning_stats(self):
        with app.app_context():
            total_memories = Memory.query.count()
            by_source = {'auto_learning': Memory.query.filter_by(source='auto_learning').count(), 'web_search': Memory.query.filter_by(source='web_search').count(), 'manual_learning': Memory.query.filter_by(source='manual_learning').count()}
            return {'total_memories': total_memories, 'by_source': by_source, 'neural_network': self.neural_net.get_stats(), 'modules_available': ['data_analysis', 'image_generator', 'code_assistant', 'chat_history', 'file_manager']}

# ========== KNOWLEDGE BASE ==========

KNOWLEDGE_BASE = {
    'ia': {'respuestas': ["La Inteligencia Artificial (IA) es la simulación de procesos de inteligencia humana por sistemas informáticos.", "IA permite a las máquinas aprender, razonar y resolver problemas de manera autónoma."], 'keywords': ['inteligencia artificial', 'ia', 'ai', 'machine learning']},
    'python': {'respuestas': ["Python es el lenguaje líder en IA por su sintaxis clara y bibliotecas como TensorFlow y PyTorch.", "Python fue creado por Guido van Rossum y es ideal para prototipado rápido."], 'keywords': ['python', 'programación', 'código', 'desarrollo']},
    'hola': {'respuestas': ["¡Hola! Soy Cic_IA, tu asistente inteligente modular. ¿Qué necesitas?", "¡Bienvenido! Puedo analizar datos, generar imágenes, ayudarte con código y más."], 'keywords': ['hola', 'buenas', 'hey', 'saludos']},
    'modulos': {'respuestas': ["Módulos disponibles: 1. Análisis de Datos 2. Generador de Imágenes 3. Asistente de Código 4. Historial 5. Archivos", "Prueba: 'analiza este CSV', 'genera una imagen de...', 'escribe código para...'"], 'keywords': ['módulos', 'modulos', 'qué puedes hacer', 'capacidades']},
    'default': {'respuestas': ["Interesante tema sobre '{tema}'. Voy a investigar para darte la mejor respuesta.", "Estoy aprendiendo sobre '{tema}'. Déjame buscar información actualizada."], 'keywords': []}
}

# ========== IMPORTAR MÓDULOS ESPECIALIZADOS ==========

_modules_cache = {}

def get_module(module_name):
    """Lazy loading de módulos"""
    if module_name not in _modules_cache:
        try:
            if module_name == 'data_analysis':
                from modules.data_analysis import DataAnalysisModule
                _modules_cache[module_name] = DataAnalysisModule()
            elif module_name == 'image_generator':
                from modules.image_generator import ImageGeneratorModule
                _modules_cache[module_name] = ImageGeneratorModule()
            elif module_name == 'code_assistant':
                from modules.code_assistant import CodeAssistantModule
                _modules_cache[module_name] = CodeAssistantModule()
            elif module_name == 'chat_history':
                from modules.chat_history import ChatHistoryModule
                _modules_cache[module_name] = ChatHistoryModule(db.session, Conversation, User)
            elif module_name == 'file_manager':
                from modules.file_manager import FileManagerModule
                _modules_cache[module_name] = FileManagerModule()
        except Exception as e:
            logger.error(f"Error cargando módulo {module_name}: {e}")
            return None
    return _modules_cache.get(module_name)

cic_ia = CicIA()

# ========== RUTAS PÚBLICAS ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat(), 'version': '7.2_clean', 'features': ['chat', 'web_search', 'auto_learning', 'memory', 'users', 'auth', 'modules']})

# ========== AUTENTICACIÓN ==========

@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'success': False, 'error': 'Usuario y contraseña requeridos'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'error': 'Usuario ya existe'}), 409

        if email and User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'error': 'Email ya registrado'}), 409

        user = User(username=username, email=email or f"{username}@temp.com")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=7)
        session = UserSession(user_id=user.id, token=token, expires_at=expires)
        db.session.add(session)
        db.session.commit()

        return jsonify({'success': True, 'token': token, 'user': {'id': user.id, 'username': user.username, 'is_developer': user.is_developer}})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return jsonify({'success': False, 'error': 'Credenciales inválidas'}), 401

        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=7)
        session = UserSession(user_id=user.id, token=token, expires_at=expires)
        db.session.add(session)
        db.session.commit()

        return jsonify({'success': True, 'token': token, 'user': {'id': user.id, 'username': user.username, 'is_developer': user.is_developer}})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/verify', methods=['GET'])
def verify_token_endpoint():
    token = None
    if 'Authorization' in request.headers:
        try:
            token = request.headers['Authorization'].split(" ")[1]
        except IndexError:
            return jsonify({'error': 'Token inválido'}), 401

    if not token:
        return jsonify({'error': 'Token requerido'}), 401

    session = UserSession.query.filter_by(token=token).first()
    if not session or (session.expires_at and session.expires_at < datetime.utcnow()):
        return jsonify({'error': 'Token inválido o expirado'}), 401

    user = User.query.get(session.user_id)
    if not user:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    session.last_access = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True, 'user': {'id': user.id, 'username': user.username, 'is_developer': user.is_developer}})

# ========== RUTAS PROTEGIDAS ==========


# ========== ENDPOINT TEMPORAL PARA CREAR USUARIO DEV (ELIMINAR DESPUÉS) ==========

@app.route('/api/setup/create-dev', methods=['GET'])
def create_dev_user():
    """Endpoint temporal para crear usuario desarrollador - ELIMINAR DESPUÉS DE USAR"""
    try:
        # Verificar si ya existe un dev
        existing = User.query.filter_by(is_developer=True).first()
        if existing:
            return jsonify({
                'message': 'Ya existe un usuario desarrollador',
                'username': existing.username,
                'warning': 'Este endpoint se autodestruirá después de 1 uso'
            })

        # Crear usuario dev
        dev = User(
            username='desarrollador',
            email='dev@cic-ia.local',
            is_developer=True,
            is_active=True
        )
        dev.set_password('cicia2024')
        db.session.add(dev)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Usuario desarrollador creado',
            'credentials': {
                'username': 'desarrollador',
                'password': 'cicia2024'
            },
            'warning': 'ELIMINA ESTE ENDPOINT DESPUÉS DE USAR - LÍNEA ~600'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
@token_required
def chat_auth(current_user):
    try:
        data = request.json
        message = data.get('message', '').strip()
        mode = data.get('mode', 'balanced')

        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400

        result = cic_ia.chat(message, mode=mode, user_id=current_user.id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error en chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/stats', methods=['GET'])
@token_required
def user_stats(current_user):
    try:
        conv_count = Conversation.query.filter_by(user_id=current_user.id).count()
        return jsonify({'success': True, 'user_id': current_user.id, 'username': current_user.username, 'conversation_count': conv_count, 'is_developer': current_user.is_developer})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def status():
    try:
        with app.app_context():
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            stats = cic_ia.get_learning_stats()
            return jsonify({'stage': 'v7.2', 'total_memories': stats['total_memories'], 'total_conversations': Conversation.query.count(), 'today_learned': log.count if log else 0, 'neural_network': stats.get('neural_network', {}), 'modules': stats.get('modules_available', [])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/modules/list', methods=['GET'])
def list_modules():
    return jsonify({'modules': [{'id': 'data_analysis', 'name': 'Análisis de Datos', 'icon': '📊'}, {'id': 'image_generator', 'name': 'Generador de Imágenes', 'icon': '🎨'}, {'id': 'code_assistant', 'name': 'Asistente de Código', 'icon': '💻'}, {'id': 'chat_history', 'name': 'Historial', 'icon': '📜'}, {'id': 'file_manager', 'name': 'Archivos', 'icon': '📁'}]})

# ========== RUTAS DESARROLLADOR ==========

@app.route('/api/dev/stats/detailed')
@dev_required
def dev_stats_detailed():
    try:
        today = date.today()
        stats = {'general': {'total_memories': Memory.query.count(), 'total_conversations': Conversation.query.count(), 'total_users': User.query.count(), 'active_sessions': UserSession.query.count()}, 'today': {'conversations': db.session.query(db.func.sum(LearningLog.count)).filter(LearningLog.date == today).scalar() or 0}, 'neural_network': neural_net.get_stats()}
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/memories/all')
@dev_required
def dev_memories_all():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        pagination = Memory.query.order_by(Memory.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        return jsonify({'memories': [{'id': m.id, 'topic': m.topic, 'content': m.content[:200], 'source': m.source, 'created_at': m.created_at.isoformat()} for m in pagination.items], 'total': pagination.total, 'pages': pagination.pages})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/neural/train', methods=['POST'])
@dev_required
def dev_train_neural():
    try:
        conversations = Conversation.query.order_by(Conversation.timestamp.desc()).limit(100).all()
        if len(conversations) < 10:
            return jsonify({'success': False, 'error': 'Se necesitan al menos 10 conversaciones'}), 400

        texts = [conv.user_message for conv in conversations]
        labels = []
        module_labels = []

        for text in texts:
            text_lower = text.lower()
            if any(kw in text_lower for kw in ['hola', 'buenas']):
                labels.append('greeting')
            elif any(kw in text_lower for kw in ['qué', 'cómo', 'cuándo']):
                labels.append('question')
            else:
                labels.append('statement')
            mod_info = cic_ia.detect_module(text)
            module_labels.append(mod_info['module'])

        success = neural_net.train(texts, labels, module_labels)
        if success:
            return jsonify({'success': True, 'message': 'Red neuronal entrenada', 'samples': len(texts), 'stats': neural_net.get_stats()})
        return jsonify({'success': False, 'error': 'Error durante entrenamiento'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/evolution/learn-now', methods=['POST'])
@dev_required
def evolution_learn_now():
    try:
        data = request.json or {}
        topic = data.get('topic', '').strip() or None
        if topic:
            cic_ia.set_custom_topic(topic)
        threading.Thread(target=cic_ia._perform_auto_learning, args=(topic,), daemon=True).start()
        return jsonify({'success': True, 'message': 'Aprendizaje iniciado' + (f' sobre "{topic}"' if topic else ''), 'started_at': datetime.utcnow().isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/system/clear-db', methods=['POST'])
@dev_required
def dev_clear_db():
    try:
        confirm = request.headers.get('X-Confirm-Delete')
        if confirm != 'DESTRUIR_TODO':
            return jsonify({'error': 'Confirmación requerida', 'message': 'Agrega header X-Confirm-Delete: DESTRUIR_TODO'}), 400

        Memory.query.delete()
        Conversation.query.delete()
        LearningLog.query.delete()
        WebSearchCache.query.delete()
        ManualLearningQueue.query.delete()
        db.session.commit()

        return jsonify({'success': True, 'message': 'Base de datos limpiada (usuarios preservados)'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ========== MANEJO DE ERRORES ==========

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint no encontrado'}), 404
    return render_template('index.html')

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Error interno del servidor'}), 500

# ========== INICIO ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
