"""
Cic_IA - Asistente Inteligente EVOLUTIVO con ARQUITECTURA MODULAR
Archivo principal - Versión 6.4.2 Compatible + Neural Network + Módulos Especializados
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
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
from bs4 import BeautifulSoup
import logging
import pickle
import numpy as np
from sqlalchemy import select

# ========== IMPORTAR MÓDULOS ESPECIALIZADOS ==========
# Estos se cargan bajo demanda para no sobrecargar el inicio
_modules_cache = {}

def get_module(module_name):
    """Lazy loading de módulos - solo se cargan cuando se usan"""
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
                _modules_cache[module_name] = ChatHistoryModule(db.session, Conversation, Memory)
            elif module_name == 'file_manager':
                from modules.file_manager import FileManagerModule
                _modules_cache[module_name] = FileManagerModule()
        except Exception as e:
            logging.error(f"Error cargando módulo {module_name}: {e}")
            return None
    return _modules_cache.get(module_name)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('cic_ia_mejorado')

# Inicializar Flask
app = Flask(__name__)

# ========== CONFIGURACIÓN ==========
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cic-ia-secret-2024')

database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cic_ia.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración de uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'py', 'js', 'html', 'css', 'json', 'csv', 'xlsx', 'xls', 'db', 'sqlite'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Credenciales DESARROLLADOR
DEV_USERNAME = os.environ.get('DEV_USERNAME', 'admin')
DEV_PASSWORD = os.environ.get('DEV_PASSWORD', 'CicDev2024!')

# Inicializar SQLAlchemy
db = SQLAlchemy(app)

# ========== MODELOS BASE DE DATOS ==========

class Memory(db.Model):
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
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    has_attachment = db.Column(db.Boolean, default=False)
    attachment_path = db.Column(db.String(500))
    sources_used = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LearningLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=date.today, unique=True)
    count = db.Column(db.Integer, default=0)
    web_searches = db.Column(db.Integer, default=0)
    auto_learned = db.Column(db.Integer, default=0)

class DeveloperSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True)
    username = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_access = db.Column(db.DateTime, default=datetime.utcnow)

class WebSearchCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(500), unique=True)
    results = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

class KnowledgeEvolution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    topic = db.Column(db.String(200))
    action = db.Column(db.String(50))
    old_content = db.Column(db.Text)
    new_content = db.Column(db.Text)
    source = db.Column(db.String(50))

class ManualLearningQueue(db.Model):
    """Cola de aprendizaje manual pendiente"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(200))
    source_url = db.Column(db.String(500))
    priority = db.Column(db.Integer, default=1)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)

# Crear tablas
with app.app_context():
    db.create_all()
    print("✅ Base de datos inicializada")

# ========== RED NEURONAL PARA CIC_IA ==========

class CicNeuralNetwork:
    """
    Red Neuronal integrada para Cic_IA.
    Usa MLPClassifier de scikit-learn para:
    - Clasificación de intenciones del usuario
    - Predicción de relevancia de respuestas
    - Detección de qué módulo usar
    """
    
    def __init__(self):
        self.model_intent = None
        self.model_module = None  # Nuevo: predice qué módulo usar
        self.model_relevance = None
        self.is_trained = False
        self.training_data = []
        self.labels = []
        self.module_labels = []  # Para clasificación de módulos
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
                    self.model_relevance = saved_data.get('relevance_model')
                    self.vectorizer = saved_data.get('vectorizer')
                    self.is_trained = saved_data.get('is_trained', False)
                logger.info("🧠 Red neuronal cargada desde disco")
            else:
                self._create_new_models()
        except Exception as e:
            logger.error(f"Error cargando modelos: {e}")
            self._create_new_models()
    
    def _create_new_models(self):
        try:
            from sklearn.neural_network import MLPClassifier
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # Modelo para clasificación de intenciones
            self.model_intent = MLPClassifier(
                hidden_layer_sizes=(128, 64, 32),
                activation='relu',
                solver='adam',
                max_iter=500,
                random_state=42,
                early_stopping=True,
                validation_fraction=0.1
            )
            
            # NUEVO: Modelo para detectar qué módulo usar
            self.model_module = MLPClassifier(
                hidden_layer_sizes=(64, 32),
                activation='relu',
                solver='adam',
                max_iter=300,
                random_state=42
            )
            
            # Modelo para predicción de relevancia
            self.model_relevance = MLPClassifier(
                hidden_layer_sizes=(64, 32),
                activation='tanh',
                solver='adam',
                max_iter=300,
                random_state=42
            )
            
            self.vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
            self.is_trained = False
            logger.info("🧠 Nueva red neuronal creada (con detector de módulos)")
            
        except ImportError:
            logger.warning("scikit-learn no disponible, red neuronal desactivada")
            self.model_intent = None
    
    def train(self, texts, labels, module_labels=None):
        """Entrena la red neuronal"""
        if self.model_intent is None:
            return False
        
        try:
            X = self.vectorizer.fit_transform(texts)
            self.model_intent.fit(X, labels)
            
            # Entrenar detector de módulos si hay datos
            if module_labels and self.model_module:
                self.model_module.fit(X, module_labels)
                self.module_labels = module_labels
            
            self.is_trained = True
            self.training_data = texts
            self.labels = labels
            self._save_models()
            
            logger.info(f"🧠 Red neuronal entrenada con {len(texts)} ejemplos")
            return True
            
        except Exception as e:
            logger.error(f"Error entrenando red neuronal: {e}")
            return False
    
    def predict_intent(self, text):
        """Predice la intención del usuario"""
        if not self.is_trained or self.model_intent is None:
            return {'intent': 'unknown', 'confidence': 0.0}
        
        try:
            X = self.vectorizer.transform([text])
            prediction = self.model_intent.predict(X)[0]
            confidence = np.max(self.model_intent.predict_proba(X))
            return {'intent': prediction, 'confidence': float(confidence)}
        except Exception as e:
            return {'intent': 'unknown', 'confidence': 0.0}
    
    def predict_module(self, text):
        """
        Predice qué módulo especializado debe usar el usuario.
        Retorna: 'none', 'data_analysis', 'image_generator', 'code_assistant', etc.
        """
        if not self.is_trained or self.model_module is None:
            return self._rule_based_module_detection(text)
        
        try:
            X = self.vectorizer.transform([text])
            prediction = self.model_module.predict(X)[0]
            confidence = np.max(self.model_module.predict_proba(X))
            
            if confidence > 0.6:
                return {'module': prediction, 'confidence': float(confidence)}
            else:
                return self._rule_based_module_detection(text)
                
        except Exception as e:
            return self._rule_based_module_detection(text)
    
    def _rule_based_module_detection(self, text):
        """Detección de módulo basada en reglas (fallback)"""
        text_lower = text.lower()
        
        # Data Analysis
        data_keywords = ['csv', 'excel', 'datos', 'análisis', 'tabla', 'gráfico', 'chart', 'pandas', 'dataframe', 'sqlite', 'sql']
        if any(kw in text_lower for kw in data_keywords):
            return {'module': 'data_analysis', 'confidence': 0.8, 'method': 'rules'}
        
        # Image Generator
        image_keywords = ['imagen', 'foto', 'genera imagen', 'dibuja', 'crea una imagen', 'dall-e', 'stable diffusion', 'pixel']
        if any(kw in text_lower for kw in image_keywords):
            return {'module': 'image_generator', 'confidence': 0.8, 'method': 'rules'}
        
        # Code Assistant
        code_keywords = ['código', 'programa', 'python', 'javascript', 'html', 'css', 'función', 'clase', 'debug', 'error', 'script']
        if any(kw in text_lower for kw in code_keywords):
            return {'module': 'code_assistant', 'confidence': 0.8, 'method': 'rules'}
        
        # Chat History
        history_keywords = ['historial', 'conversaciones anteriores', 'chat pasado', 'recordar']
        if any(kw in text_lower for kw in history_keywords):
            return {'module': 'chat_history', 'confidence': 0.7, 'method': 'rules'}
        
        # File Manager
        file_keywords = ['archivo', 'subir', 'upload', 'pdf', 'documento', 'guardar archivo']
        if any(kw in text_lower for kw in file_keywords):
            return {'module': 'file_manager', 'confidence': 0.7, 'method': 'rules'}
        
        return {'module': 'none', 'confidence': 0.0, 'method': 'rules'}
    
    def predict_relevance(self, query, memory_content):
        """Predice relevancia de memoria"""
        if not self.is_trained or self.model_relevance is None:
            return 0.5
        
        try:
            combined = f"{query} {memory_content}"
            X = self.vectorizer.transform([combined])
            relevance = self.model_relevance.predict_proba(X)[0][1]
            return float(relevance)
        except Exception as e:
            return 0.5
    
    def _save_models(self):
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump({
                    'intent_model': self.model_intent,
                    'module_model': self.model_module,
                    'relevance_model': self.model_relevance,
                    'vectorizer': self.vectorizer,
                    'is_trained': self.is_trained
                }, f)
        except Exception as e:
            logger.error(f"Error guardando modelos: {e}")
    
    def get_stats(self):
        return {
            'is_trained': self.is_trained,
            'training_samples': len(self.training_data),
            'model_type': 'MLPClassifier (scikit-learn)',
            'layers_intent': [128, 64, 32] if self.model_intent else [],
            'layers_module': [64, 32] if self.model_module else [],
            'layers_relevance': [64, 32] if self.model_relevance else []
        }

# Instancia global
neural_net = CicNeuralNetwork()

# ========== SERVICIO DE AUTENTICACIÓN ==========

class DevAuthService:
    def __init__(self):
        self.active_sessions = {}
    
    def verify_credentials(self, username, password):
        return username == DEV_USERNAME and password == DEV_PASSWORD
    
    def generate_token(self, username):
        import secrets
        token = secrets.token_urlsafe(32)
        self.active_sessions[token] = {
            'username': username,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(hours=24),
            'last_used': datetime.utcnow()
        }
        return token
    
    def verify_token(self, token):
        if not token or token not in self.active_sessions:
            return False
        
        session = self.active_sessions[token]
        if datetime.utcnow() > session['expires_at']:
            del self.active_sessions[token]
            return False
        
        session['last_used'] = datetime.utcnow()
        return True
    
    def revoke_token(self, token):
        if token in self.active_sessions:
            del self.active_sessions[token]
            return True
        return False

dev_auth = DevAuthService()

def dev_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Dev-Token')
        if not token or not dev_auth.verify_token(token):
            return jsonify({'error': 'No autorizado', 'code': 'INVALID_TOKEN'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ========== MOTOR DE BÚSQUEDA ==========

class WebSearchEngine:
    @staticmethod
    def search_duckduckgo(query, max_results=5):
        try:
            try:
                from duckduckgo_search import DDGS
                results = []
                ddgs = DDGS()
                search_results = ddgs.text(query, max_results=max_results)
                
                for result in search_results:
                    results.append({
                        'title': result.get('title', ''),
                        'url': result.get('href', ''),
                        'snippet': result.get('body', ''),
                        'source': 'duckduckgo'
                    })
                
                logger.info(f"🔍 Búsqueda exitosa: '{query}' - {len(results)} resultados")
                return results
                
            except ImportError as ie:
                logger.warning(f"duckduckgo-search no instalada: {ie}")
                return WebSearchEngine._search_fallback(query, max_results)
                
        except Exception as e:
            logger.error(f"❌ Error en búsqueda DuckDuckGo: {e}")
            return []
    
    @staticmethod
    def _search_fallback(query, max_results=5):
        try:
            url = f"https://html.duckduckgo.com/?q={urllib.parse.quote(query)}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            results = []
            
            for result in soup.find_all('div', class_='result')[:max_results]:
                try:
                    title_elem = result.find('a', class_='result__a')
                    snippet_elem = result.find('a', class_='result__snippet')
                    if title_elem and snippet_elem:
                        results.append({
                            'title': title_elem.get_text(strip=True),
                            'url': title_elem.get('href', ''),
                            'snippet': snippet_elem.get_text(strip=True),
                            'source': 'duckduckgo_fallback'
                        })
                except:
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en fallback: {e}")
            return []

# ========== CLASE PRINCIPAL CIC_IA ==========

class CicIA:
    def __init__(self):
        self.learning_active = True
        self.web_search_engine = WebSearchEngine()
        self.current_learning_topic = None
        self.neural_net = neural_net
        
        self.auto_learning_topics = [
            'física cuántica avances 2024', 'biología sintética descubrimientos',
            'neurociencia cognitiva', 'matemáticas teoría nuevas',
            'química materiales revolucionarios', 'astronomía exoplanetas',
            'paleontología fósiles recientes', 'genética edición CRISPR',
            'psicología conducta humana', 'filosofía mente artificial',
            'inteligencia artificial noticias 2024', 'machine learning avances',
            'desarrollo software arquitectura', 'python programación novedades',
            'código limpio mejores prácticas', 'DevOps CI/CD tendencias',
            'blockchain aplicaciones reales', 'Internet de las cosas IoT',
            'realidad virtual aumentada', 'ciberseguridad ética hacking',
            'computación cuántica progreso', 'edge computing computación borde',
            'economía global tendencias', 'geopolítica análisis actual',
            'cambio climático soluciones', 'educación innovación pedagógica',
            'salud mental bienestar', 'arte inteligencia artificial',
            'historia civilizaciones antiguas', 'lingüística evolución idiomas',
            'derecho tecnología regulación', 'sociología cambios sociales',
            'productividad métodos eficaces', 'aprendizaje acelerado técnicas',
            'creatividad innovación pensamiento', 'comunicación persuasión',
            'liderazgo gestión equipos', 'finanzas personales inversión',
            'negociación conflictos resolución', 'mindfulness atención plena',
            'inteligencia emocional', 'emprendimiento startups casos éxito',
            'biotecnología longevidad', 'nanotecnología medicina',
            'energía fusión nuclear', 'transporte eléctrico aviones',
            'espacio colonización', 'metaverso evolución',
            'robótica humanoides', 'transhumanismo mejoramiento',
        ]
        
        with app.app_context():
            self.stats = {
                'memories': Memory.query.count(),
                'conversations': Conversation.query.count(),
                'today_learned': self._get_today_count(),
                'auto_learned_total': self._get_auto_learned_total()
            }
        
        # Iniciar hilos
        threading.Thread(target=self._auto_learn_loop, daemon=True).start()
        threading.Thread(target=self._auto_web_search_loop, daemon=True).start()
        threading.Thread(target=self._continuous_learning_loop, daemon=True).start()
        threading.Thread(target=self._process_manual_learning_queue, daemon=True).start()
        
        logger.info("=" * 70)
        logger.info("🚀 CIC_IA MODULAR INICIADA")
        logger.info(f"📚 Memorias: {self.stats['memories']}")
        logger.info(f"💬 Conversaciones: {self.stats['conversations']}")
        logger.info(f"🤖 Auto-aprendidos: {self.stats['auto_learned_total']}")
        logger.info("🧠 Red Neuronal: " + ("ACTIVADA" if self.neural_net.is_trained else "EN ESPERA"))
        logger.info("🧩 Módulos: data_analysis, image_generator, code_assistant, chat_history, file_manager")
        logger.info("=" * 70)
    
    def _get_today_count(self):
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        return log.count if log else 0
    
    def _get_auto_learned_total(self):
        total = db.session.query(db.func.sum(LearningLog.auto_learned)).scalar()
        return int(total) if total else 0
    
    def set_custom_topic(self, topic):
        self.current_learning_topic = topic
        logger.info(f"📌 Tema establecido: '{topic}'")
        return True
    
    def clear_custom_topic(self):
        self.current_learning_topic = None
        logger.info("📌 Tema limpiado")
        return True
    
    def _continuous_learning_loop(self):
        logger.info("🧠 Loop de auto-aprendizaje iniciado...")
        time.sleep(300)
        
        while self.learning_active:
            try:
                self._perform_auto_learning()
            except Exception as e:
                logger.error(f"❌ Error auto-aprendizaje: {e}")
            
            logger.info("⏰ Esperando 2 horas...")
            time.sleep(7200)
    
    def _perform_auto_learning(self, custom_topic=None):
        with app.app_context():
            if custom_topic:
                topic = custom_topic
            elif self.current_learning_topic:
                topic = self.current_learning_topic
                self.current_learning_topic = None
            else:
                topic = random.choice(self.auto_learning_topics)
            
            logger.info(f"🤖 Aprendiendo: '{topic}'")
            
            results = self.web_search_engine.search_duckduckgo(topic, max_results=3)
            
            if not results:
                logger.warning(f"⚠️ Sin resultados para '{topic}'")
                return False
            
            learned_count = 0
            
            for result in results:
                try:
                    content_preview = result['snippet'][:100] if result['snippet'] else ''
                    exists = Memory.query.filter(
                        Memory.content.ilike(f'%{content_preview}%')
                    ).first()
                    
                    if exists:
                        continue
                    
                    memory = Memory(
                        content=f"{result['title']}\n\n{result['snippet']}\n\nFuente: {result['url']}",
                        source='auto_learning',
                        topic=topic,
                        relevance_score=0.6,
                        access_count=0
                    )
                    db.session.add(memory)
                    learned_count += 1
                    
                    evolution = KnowledgeEvolution(
                        topic=topic,
                        action='learned',
                        new_content=result['snippet'][:200] if result['snippet'] else '',
                        source='auto_learning'
                    )
                    db.session.add(evolution)
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando: {e}")
                    continue
            
            if learned_count > 0:
                db.session.commit()
                
                today = date.today()
                log = LearningLog.query.filter_by(date=today).first()
                if not log:
                    log = LearningLog(date=today, count=0, web_searches=0, auto_learned=0)
                    db.session.add(log)
                
                log.auto_learned += learned_count
                log.web_searches += len(results)
                db.session.commit()
                
                logger.info(f"🎉 Aprendidos: {learned_count}")
                return True
            else:
                logger.info("📝 Sin novedades")
                return False
    
    def add_manual_learning(self, content, topic=None, source_url=None, priority=1):
        """Agrega a cola de aprendizaje manual"""
        try:
            with app.app_context():
                # ✅ CORRECCIÓN: Verificar que content no sea None
                if content is None:
                    content = ''
                
                content = str(content).strip()
                topic = str(topic).strip() if topic else 'manual_learning'
                
                if not content:
                    return {'success': False, 'error': 'Contenido vacío'}
                
                queue_item = ManualLearningQueue(
                    content=content,
                    topic=topic,
                    source_url=source_url,
                    priority=priority,
                    status='pending'
                )
                db.session.add(queue_item)
                db.session.commit()
                
                logger.info(f"📥 Manual agregado: '{topic}' (prio {priority})")
                return {'success': True, 'id': queue_item.id}
        except Exception as e:
            logger.error(f"❌ Error manual learning: {e}")
            return {'success': False, 'error': str(e)}
    
    def _process_manual_learning_queue(self):
        """Procesa cola manual cada 5 minutos"""
        while self.learning_active:
            try:
                with app.app_context():
                    pending = ManualLearningQueue.query.filter_by(status='pending')\
                        .order_by(ManualLearningQueue.priority.desc())\
                        .limit(5).all()
                    
                    for item in pending:
                        try:
                            item.status = 'processing'
                            db.session.commit()
                            
                            # Verificar duplicados
                            exists = Memory.query.filter(
                                Memory.content.ilike(f'%{item.content[:100]}%')
                            ).first()
                            
                            if exists:
                                item.status = 'completed'
                                item.processed_at = datetime.utcnow()
                                db.session.commit()
                                continue
                            
                            # Crear memoria
                            memory = Memory(
                                content=f"{item.content}\n\nFuente: {item.source_url or 'Manual'}",
                                source='manual_learning',
                                topic=item.topic,
                                relevance_score=0.9 if item.priority >= 2 else 0.8,
                                access_count=0
                            )
                            db.session.add(memory)
                            
                            evolution = KnowledgeEvolution(
                                topic=item.topic,
                                action='manual_learned',
                                new_content=item.content[:200],
                                source='manual_learning'
                            )
                            db.session.add(evolution)
                            
                            item.status = 'completed'
                            item.processed_at = datetime.utcnow()
                            db.session.commit()
                            
                            logger.info(f"✅ Manual procesado: {item.topic}")
                            
                        except Exception as e:
                            item.status = 'failed'
                            db.session.commit()
                            logger.error(f"❌ Error procesando manual: {e}")
                
            except Exception as e:
                logger.error(f"❌ Error cola manual: {e}")
            
            time.sleep(300)
    
    def _auto_web_search_loop(self):
        while self.learning_active:
            try:
                with app.app_context():
                    stmt = select(WebSearchCache).where(
                        WebSearchCache.expires_at < datetime.utcnow()
                    )
                    expired = db.session.execute(stmt).scalars().all()
                    for cache_entry in expired:
                        db.session.delete(cache_entry)
                    db.session.commit()
            except Exception as e:
                logger.error(f"❌ Error limpiando cache: {e}")
            time.sleep(3600)
    
    def _auto_learn_loop(self):
        while self.learning_active:
            try:
                with app.app_context():
                    memories = Memory.query.all()
                    for mem in memories:
                        mem.relevance_score = min(1.0, mem.relevance_score + (mem.access_count * 0.01))
                    db.session.commit()
            except Exception as e:
                logger.error(f"❌ Error auto-learn: {e}")
            time.sleep(3600)
    
    # ========== SISTEMA MODULAR ==========
    
    def detect_module(self, user_input):
        """
        Detecta si el usuario quiere usar un módulo especializado.
        Usa red neuronal + reglas como fallback.
        """
        # Primero intentar con red neuronal
        module_info = self.neural_net.predict_module(user_input)
        
        # Si la confianza es baja, usar detección manual
        if module_info['confidence'] < 0.5:
            module_info = self._manual_module_detection(user_input)
        
        return module_info
    
    def _manual_module_detection(self, text):
        """Detección manual de módulos por palabras clave"""
        text_lower = text.lower()
        
        # Patrones específicos para cada módulo
        patterns = {
            'data_analysis': {
                'keywords': ['analiza estos datos', 'csv', 'excel', 'tabla', 'dataframe', 'gráfico de barras', 'plot', 'sqlite', 'base de datos', 'estadísticas de'],
                'prefixes': ['analiza', 'procesa', 'genera gráfico', 'calcula promedio']
            },
            'image_generator': {
                'keywords': ['genera una imagen', 'crea una imagen', 'dibuja', 'imagen de', 'foto de', 'ilustración de', 'dall-e', 'stable diffusion'],
                'prefixes': ['genera imagen', 'crea imagen', 'dibuja']
            },
            'code_assistant': {
                'keywords': ['escribe código', 'función en python', 'script para', 'debug este código', 'explica este código', 'convierte a javascript', 'html para', 'css para'],
                'prefixes': ['código', 'programa', 'script', 'función', 'clase', 'debug', 'explica código']
            },
            'chat_history': {
                'keywords': ['mi historial', 'conversaciones anteriores', 'chat pasado', 'recordar que dije', 'busca en historial'],
                'prefixes': ['historial', 'conversaciones pasadas', 'recordar']
            },
            'file_manager': {
                'keywords': ['sube este archivo', 'procesa pdf', 'lee documento', 'guarda archivo', 'adjunta archivo'],
                'prefixes': ['archivo', 'documento', 'pdf', 'subir', 'adjuntar']
            }
        }
        
        for module_name, patterns_data in patterns.items():
            # Verificar keywords
            if any(kw in text_lower for kw in patterns_data['keywords']):
                return {'module': module_name, 'confidence': 0.9, 'method': 'manual'}
            
            # Verificar prefijos (inicio del mensaje)
            for prefix in patterns_data['prefixes']:
                if text_lower.startswith(prefix):
                    return {'module': module_name, 'confidence': 0.85, 'method': 'manual'}
        
        return {'module': 'none', 'confidence': 0.0, 'method': 'manual'}
    
    def execute_module(self, module_name, user_input, context=None):
        """
        Ejecuta un módulo especializado y retorna la respuesta.
        """
        module = get_module(module_name)
        
        if module is None:
            return {
                'success': False,
                'error': f'Módulo {module_name} no disponible',
                'response': f'Lo siento, el módulo {module_name} no está disponible en este momento.'
            }
        
        try:
            logger.info(f"🧩 Ejecutando módulo: {module_name}")
            
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
            else:
                return {
                    'success': False,
                    'error': 'Módulo no implementado',
                    'response': 'Este módulo aún no está implementado.'
                }
                
        except Exception as e:
            logger.error(f"❌ Error en módulo {module_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'response': f'Error ejecutando {module_name}: {str(e)}'
            }
    
    def _execute_data_analysis(self, module, user_input, context):
        """Ejecuta análisis de datos"""
        # Verificar si hay archivo adjunto en contexto
        if context and context.get('file_path'):
            result = module.load_file(context['file_path'])
            if result.get('success'):
                # Analizar según la consulta
                analysis = module.analyze(user_input)
                return {
                    'success': True,
                    'module': 'data_analysis',
                    'response': analysis.get('summary', 'Análisis completado'),
                    'data': analysis
                }
        
        # Sin archivo, preguntar por uno
        return {
            'success': True,
            'module': 'data_analysis',
            'response': '📊 Modo Análisis de Datos activado. Por favor, sube un archivo (CSV, Excel, JSON, SQLite) para analizar.',
            'awaiting_file': True
        }
    
    def _execute_image_generator(self, module, user_input, context):
        """Ejecuta generador de imágenes"""
        # Extraer prompt de la solicitud
        prompt = user_input.replace('genera una imagen', '').replace('crea una imagen', '').replace('dibuja', '').strip()
        
        if not prompt:
            return {
                'success': True,
                'module': 'image_generator',
                'response': '🎨 Modo Generador de Imágenes activado. Describe qué imagen quieres crear.'
            }
        
        # Generar imagen
        result = module.generate(prompt, style='realistic', size='1024x1024')
        
        if result.get('success'):
            return {
                'success': True,
                'module': 'image_generator',
                'response': f'🎨 Imagen generada: "{prompt[:50]}..."',
                'image_data': result.get('image_data'),
                'format': result.get('format')
            }
        else:
            return {
                'success': False,
                'module': 'image_generator',
                'response': f'⚠️ No pude generar la imagen: {result.get("error", "Error desconocido")}',
                'fallback': result.get('note', '')
            }
    
    def _execute_code_assistant(self, module, user_input, context):
        """Ejecuta asistente de código"""
        # Detectar lenguaje y tarea
        language = module.detect_language(user_input)
        
        # Verificar si es explicación, generación o debug
        if any(kw in user_input.lower() for kw in ['explica', 'explicar', 'qué hace', 'cómo funciona']):
            # Necesitaríamos el código a explicar
            return {
                'success': True,
                'module': 'code_assistant',
                'response': f'💻 Modo Asistente de Código activado (detectado: {language}). Pega el código que quieres que explique.'
            }
        elif any(kw in user_input.lower() for kw in ['debug', 'error', 'arregla', 'corrige']):
            return {
                'success': True,
                'module': 'code_assistant',
                'response': '🐛 Modo Debug activado. Pega el código con error y el mensaje de error si lo tienes.'
            }
        else:
            # Generar código
            result = module.generate_code(user_input, language)
            return {
                'success': True,
                'module': 'code_assistant',
                'response': f'💻 Código generado en {result.get("language_name", language)}:\n\n```{language}\n{result.get("code", "")}\n```\n\n**Explicación:** {result.get("explanation", "")}',
                'code': result.get('code'),
                'language': language,
                'suggestions': result.get('suggestions', [])
            }
    
    def _execute_chat_history(self, module, user_input, context):
        """Ejecuta gestión de historial"""
        # Buscar en historial
        if any(kw in user_input.lower() for kw in ['busca', 'encuentra', 'buscar']):
            keyword = user_input.replace('busca', '').replace('en mi historial', '').replace('buscar', '').strip()
            results = module.search_conversations(user_id=context.get('user_id', 1), keyword=keyword)
            
            if results.get('matches', 0) > 0:
                convs = results.get('conversations', [])
                response = f'🔍 Encontré {results["matches"]} conversaciones:\n\n'
                for conv in convs[:5]:
                    response += f'- **{conv["user_message"][:50]}...** ({conv["timestamp"][:10]})\n'
                return {
                    'success': True,
                    'module': 'chat_history',
                    'response': response
                }
            else:
                return {
                    'success': True,
                    'module': 'chat_history',
                    'response': f'🔍 No encontré conversaciones con "{keyword}" en tu historial.'
                }
        
        # Estadísticas de historial
        stats = module.get_conversation_stats(user_id=context.get('user_id', 1))
        return {
            'success': True,
            'module': 'chat_history',
            'response': f'📊 **Tu Historial:**\n- Total conversaciones: {stats.get("total_conversations", 0)}\n- Últimos 7 días: {stats.get("last_7_days", 0)}\n- Primera conversación: {stats.get("first_conversation", "N/A")[:10] if stats.get("first_conversation") else "N/A"}',
            'stats': stats
        }
    
    def _execute_file_manager(self, module, user_input, context):
        """Ejecuta gestor de archivos"""
        return {
            'success': True,
            'module': 'file_manager',
            'response': '📁 Modo Gestión de Archivos activado. Puedes subir archivos para que los procese o analice.',
            'supported_formats': module.supported_formats if hasattr(module, 'supported_formats') else ['.pdf', '.docx', '.txt', '.csv', '.xlsx']
        }
    
    def chat(self, user_input, mode='balanced', attachment_info=None, user_id=1):
        """
        Procesa mensajes del usuario con detección de módulos.
        """
        input_lower = user_input.lower().strip()
        
        # Preguntas de fecha/hora
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_conversation(user_input, response, 'system_time', 
                                         attachment_info=attachment_info, user_id=user_id)
        
        # ========== DETECCIÓN DE MÓDULOS ==========
        module_info = self.detect_module(user_input)
        
        if module_info['module'] != 'none' and module_info['confidence'] > 0.6:
            # Ejecutar módulo especializado
            context = {
                'user_id': user_id,
                'file_path': attachment_info.get('path') if attachment_info else None,
                'file_type': attachment_info.get('type') if attachment_info else None
            }
            
            module_result = self.execute_module(module_info['module'], user_input, context)
            
            # Guardar conversación con info del módulo
            result = self._save_conversation(
                user_input, 
                module_result.get('response', 'Error en módulo'),
                f"module_{module_info['module']}",
                attachment_info=attachment_info,
                user_id=user_id,
                module_used=module_info['module'],
                module_confidence=module_info['confidence']
            )
            
            # Agregar info del módulo al resultado
            result['module_used'] = module_info['module']
            result['module_confidence'] = module_info['confidence']
            result['module_method'] = module_info.get('method', 'unknown')
            
            if module_result.get('awaiting_file'):
                result['awaiting_file'] = True
                result['module_awaiting'] = module_info['module']
            
            return result
        
        # ========== CHAT NORMAL ==========
        intent_info = self.neural_net.predict_intent(user_input)
        best_topic = self._find_best_topic(input_lower)
        
        with app.app_context():
            memories = Memory.query.all()
            
            if self.neural_net.is_trained:
                relevant_memories = self._find_relevant_memories_neural(user_input, memories)
            else:
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
                    response = f"He investigado en internet sobre '{tema}':\n\n"
                    response += web_results['summary']
                    sources_used.append('web_search')
                else:
                    response = random.choice(KNOWLEDGE_BASE['default']['respuestas']).format(tema=tema)
                    sources_used.append('learning')
            
            if mode == 'fast':
                response = response.split('.')[0] + '.' if '.' in response else response[:100]
            elif mode == 'complete':
                response += "\n\n¿Te gustaría que profundice en este tema?"
            
            return self._save_conversation(
                user_input, response, 
                sources_used[0] if sources_used else 'learning',
                attachment_info=attachment_info,
                user_id=user_id,
                memories_count=len(relevant_memories),
                sources_used=sources_used,
                intent=intent_info.get('intent', 'unknown')
            )
    
    def _find_relevant_memories_neural(self, query, memories):
        """Usa red neuronal para rankear memorias"""
        relevant = []
        for mem in memories:
            relevance = self.neural_net.predict_relevance(query, mem.content)
            if relevance > 0.6:
                relevant.append((mem, relevance))
                mem.access_count += 1
        
        relevant.sort(key=lambda x: x[1], reverse=True)
        db.session.commit()
        
        return [mem for mem, _ in relevant[:5]]
    
    def _search_and_learn(self, query):
        """Busca en web y guarda"""
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
                    summary += f"{i}. **{result['title']}**\n"
                    summary += f"   {result['snippet']}\n\n"
                    
                    memory = Memory(
                        content=result['snippet'],
                        source='web_search',
                        topic=query,
                        relevance_score=0.7
                    )
                    db.session.add(memory)
                
                cache_entry = WebSearchCache(
                    query=query,
                    results={'summary': summary},
                    expires_at=datetime.utcnow() + timedelta(hours=24)
                )
                db.session.add(cache_entry)
                db.session.commit()
                
                return {'summary': summary}
        except Exception as e:
            logger.error(f"❌ Error búsqueda web: {e}")
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
    
    def _save_conversation(self, user_msg, bot_resp, source, 
                          attachment_info=None, user_id=1, memories_count=0, 
                          sources_used=None, intent='unknown', 
                          module_used=None, module_confidence=None):
        """Guarda conversación con metadatos extendidos"""
        with app.app_context():
            conv = Conversation(
                user_message=user_msg,
                bot_response=bot_resp,
                has_attachment=attachment_info is not None,
                attachment_path=attachment_info.get('path') if attachment_info else None,
                sources_used={
                    'primary': source,
                    'all': sources_used or [source],
                    'intent': intent,
                    'module_used': module_used,
                    'module_confidence': module_confidence
                }
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
            total_mem = Memory.query.count()
        
        result = {
            'response': bot_resp,
            'model_used': 'cic_ia_modular',
            'sources_used': sources_used or [source],
            'memories_found': memories_count,
            'total_memories': total_mem,
            'has_attachment': attachment_info is not None,
            'intent_detected': intent
        }
        
        if module_used:
            result['module_used'] = module_used
            result['module_confidence'] = module_confidence
        
        return result
    
    def _is_date_time_question(self, text):
        keywords = ['qué día', 'qué hora', 'fecha', 'hora actual', 'hoy es']
        return any(kw in text for kw in keywords)
    
    def _get_dynamic_date_response(self, text):
        now = datetime.now()
        dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        fecha = f"📅 Hoy es {dias[now.weekday()]}, {now.day} de {meses[now.month-1]} de {now.year}"
        hora = f"🕐 Son las {now.strftime('%H:%M:%S')}"
        
        return f"{fecha}\n{hora}"
    
    def get_learning_stats(self):
        with app.app_context():
            total_memories = Memory.query.count()
            by_source = {
                'auto_learning': Memory.query.filter_by(source='auto_learning').count(),
                'web_search': Memory.query.filter_by(source='web_search').count(),
                'user_taught': Memory.query.filter_by(source='user_taught').count(),
                'manual_learning': Memory.query.filter_by(source='manual_learning').count(),
                'knowledge_base': Memory.query.filter(Memory.source.notin_(['auto_learning', 'web_search', 'user_taught', 'manual_learning'])).count()
            }
            
            week_ago = date.today() - timedelta(days=7)
            recent_logs = LearningLog.query.filter(LearningLog.date >= week_ago).all()
            
            weekly_stats = {
                'conversations': sum(log.count for log in recent_logs),
                'web_searches': sum(log.web_searches for log in recent_logs),
                'auto_learned': sum(log.auto_learned for log in recent_logs)
            }
            
            topic_counts = {}
            for mem in Memory.query.filter(Memory.source == 'auto_learning').all():
                topic = mem.topic or 'unknown'
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
            
            top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            manual_pending = ManualLearningQueue.query.filter_by(status='pending').count()
            manual_completed = ManualLearningQueue.query.filter_by(status='completed').count()
            
            return {
                'total_memories': total_memories,
                'by_source': by_source,
                'last_7_days': weekly_stats,
                'top_topics': top_topics,
                'learning_frequency': 'cada 2 horas',
                'total_topics_available': len(self.auto_learning_topics),
                'evolution_ready': True,
                'custom_topic_pending': self.current_learning_topic is not None,
                'custom_topic': self.current_learning_topic,
                'neural_network': self.neural_net.get_stats(),
                'manual_learning_queue': {
                    'pending': manual_pending,
                    'completed': manual_completed
                },
                'modules_available': ['data_analysis', 'image_generator', 'code_assistant', 'chat_history', 'file_manager']
            }

# ========== KNOWLEDGE BASE ==========

KNOWLEDGE_BASE = {
    'ia': {
        'respuestas': [
            "La Inteligencia Artificial (IA) es la simulación de procesos de inteligencia humana por sistemas informáticos.",
            "IA permite a las máquinas aprender, razonar y resolver problemas de manera autónoma."
        ],
        'keywords': ['inteligencia artificial', 'ia', 'ai', 'machine learning', 'deep learning']
    },
    'python': {
        'respuestas': [
            "Python es el lenguaje líder en IA por su sintaxis clara y bibliotecas como TensorFlow y PyTorch.",
            "Python fue creado por Guido van Rossum y es ideal para prototipado rápido."
        ],
        'keywords': ['python', 'programación', 'código', 'desarrollo']
    },
    'hola': {
        'respuestas': [
            "¡Hola! Soy Cic_IA, tu asistente inteligente modular. Puedo analizar datos, generar imágenes, ayudarte con código y más. ¿Qué necesitas?",
            "¡Bienvenido! Estoy lista para asistirte. Prueba decirme: 'analiza estos datos', 'genera una imagen de...', o 'escribe código para...'"
        ],
        'keywords': ['hola', 'buenas', 'hey', 'saludos']
    },
    'modulos': {
        'respuestas': [
            "🧩 **Módulos disponibles:**\n1. 📊 Análisis de Datos (CSV, Excel, JSON, SQLite)\n2. 🎨 Generador de Imágenes\n3. 💻 Asistente de Código\n4. 📜 Historial de Conversaciones\n5. 📁 Gestor de Archivos\n\nDime qué necesitas hacer.",
            "Puedo ayudarte con:\n- **Datos**: 'analiza este CSV'\n- **Imágenes**: 'genera una imagen de...'\n- **Código**: 'escribe una función en Python'\n- **Historial**: 'busca en mis conversaciones'\n- **Archivos**: 'procesa este PDF'"
        ],
        'keywords': ['módulos', 'modulos', 'qué puedes hacer', 'capacidades', 'funciones', 'ayuda']
    },
    'fecha_hora': {
        'respuestas': ['DYNAMIC_DATE'],
        'keywords': ['qué día', 'qué hora', 'fecha', 'hora actual', 'hoy es']
    },
    'cic_ia': {
        'respuestas': [
            "Soy Cic_IA v4.0 - Asistente evolutivo con arquitectura modular, red neuronal integrada y 5 módulos especializados.",
            "Cic_IA aprende automáticamente cada 2 horas y puede analizar datos, generar imágenes, asistir con código y más."
        ],
        'keywords': ['quién eres', 'qué eres', 'cic_ia', 'tu nombre', 'presentación']
    },
    'default': {
        'respuestas': [
            "Interesante tema sobre '{tema}'. Voy a investigar en internet para darte la mejor respuesta.",
            "Estoy aprendiendo sobre '{tema}'. Déjame buscar información actualizada para ti."
        ],
        'keywords': []
    }
}

cic_ia = CicIA()

# ========== RUTAS PÚBLICAS ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat')
def chat_page():
    return render_template('index.html')

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '4.0_modular',
        'features': ['chat', 'web_search', 'auto_learning', 'memory', 'evolution', '50_topics', 'neural_network', 'manual_learning', 'modules']
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '').strip()
        mode = data.get('mode', 'balanced')
        user_id = data.get('user_id', 1)
        
        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        result = cic_ia.chat(message, mode=mode, user_id=user_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error en chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/modules/list', methods=['GET'])
def list_modules():
    """Lista los módulos disponibles"""
    return jsonify({
        'modules': [
            {
                'id': 'data_analysis',
                'name': 'Análisis de Datos',
                'description': 'Analiza CSV, Excel, JSON, SQLite. Genera gráficos y estadísticas.',
                'icon': '📊',
                'triggers': ['analiza datos', 'csv', 'excel', 'tabla', 'gráfico']
            },
            {
                'id': 'image_generator',
                'name': 'Generador de Imágenes',
                'description': 'Crea imágenes desde descripciones usando IA.',
                'icon': '🎨',
                'triggers': ['genera imagen', 'crea imagen', 'dibuja', 'ilustración']
            },
            {
                'id': 'code_assistant',
                'name': 'Asistente de Código',
                'description': 'Genera, explica y debuguea código en múltiples lenguajes.',
                'icon': '💻',
                'triggers': ['código', 'programa', 'python', 'javascript', 'debug']
            },
            {
                'id': 'chat_history',
                'name': 'Historial de Chat',
                'description': 'Busca y analiza conversaciones anteriores.',
                'icon': '📜',
                'triggers': ['historial', 'conversaciones pasadas', 'buscar en chat']
            },
            {
                'id': 'file_manager',
                'name': 'Gestor de Archivos',
                'description': 'Procesa PDFs, documentos Word, imágenes y más.',
                'icon': '📁',
                'triggers': ['archivo', 'pdf', 'documento', 'subir']
            }
        ]
    })

@app.route('/api/modules/execute', methods=['POST'])
def execute_module_direct():
    """
    Ejecuta un módulo directamente sin pasar por el chat.
    Útil para llamadas específicas desde el frontend.
    """
    try:
        data = request.json
        module_name = data.get('module')
        user_input = data.get('input', '')
        context = data.get('context', {})
        
        if not module_name:
            return jsonify({'error': 'Módulo no especificado'}), 400
        
        # Verificar módulo válido
        valid_modules = ['data_analysis', 'image_generator', 'code_assistant', 'chat_history', 'file_manager']
        if module_name not in valid_modules:
            return jsonify({'error': f'Módulo {module_name} no válido'}), 400
        
        result = cic_ia.execute_module(module_name, user_input, context)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error ejecutando módulo: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def status():
    try:
        with app.app_context():
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            stats = cic_ia.get_learning_stats()
            
            return jsonify({
                'stage': 'v4.0_modular',
                'total_memories': stats['total_memories'],
                'total_conversations': Conversation.query.count(),
                'today_learned': log.count if log else 0,
                'today_auto_learned': log.auto_learned if log else 0,
                'web_searches_today': log.web_searches if log else 0,
                'db_size': 'PostgreSQL' if database_url else 'SQLite',
                'auto_learning_active': True,
                'learning_frequency': 'cada 2 horas',
                'total_topics': len(cic_ia.auto_learning_topics),
                'learning_stats': stats,
                'neural_network': stats.get('neural_network', {}),
                'modules': stats.get('modules_available', []),
                'features': ['chat', 'web_search', 'auto_learning', 'memory', 'evolution', '50_topics', 'neural_network', 'manual_learning', 'modules']
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ... (resto de rutas: teach, memories, history, evolution/stats, dev/login, dev/logout, etc.)
# Incluyo las rutas de desarrollador que faltan:

@app.route('/api/teach', methods=['POST'])
def teach():
    try:
        data = request.json
        text = data.get('text', '').strip()
        topic = data.get('topic', '').strip()
        source = data.get('source', 'user_taught')
        
        token = request.headers.get('X-Dev-Token')
        is_dev = dev_auth.verify_token(token) if token else False
        
        if not text:
            return jsonify({'error': 'Texto vacío'}), 400
        
        if not topic:
            topic = text[:50]
        
        with app.app_context():
            memory = Memory(
                content=text,
                source='developer' if is_dev else source,
                topic=topic,
                relevance_score=0.95 if is_dev else 0.9,
                access_count=0
            )
            db.session.add(memory)
            
            if is_dev:
                evolution = KnowledgeEvolution(
                    topic=topic,
                    action='manual_teach',
                    new_content=text[:200],
                    source='developer'
                )
                db.session.add(evolution)
            
            db.session.commit()
            
            return jsonify({
                'message': 'He aprendido lo que me enseñaste',
                'memory_id': memory.id,
                'topic': topic,
                'is_dev_mode': is_dev
            })
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/memories')
def memories():
    try:
        with app.app_context():
            mems = Memory.query.order_by(Memory.created_at.desc()).limit(10).all()
            return jsonify([{
                'id': m.id,
                'topic': m.topic,
                'source': m.source,
                'content': m.content[:100],
                'relevance': m.relevance_score
            } for m in mems])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history')
def history():
    try:
        with app.app_context():
            convs = Conversation.query.order_by(Conversation.timestamp.desc()).limit(5).all()
            return jsonify([{
                'user': c.user_message,
                'bot': c.bot_response,
                'sources': c.sources_used
            } for c in convs])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/evolution/stats')
def evolution_stats():
    try:
        stats = cic_ia.get_learning_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== RUTAS DESARROLLADOR ==========

@app.route('/api/dev/login', methods=['POST'])
def dev_login():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if dev_auth.verify_credentials(username, password):
            token = dev_auth.generate_token(username)
            return jsonify({
                'success': True,
                'token': token,
                'username': username,
                'expires_in': '24h'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Credenciales inválidas'
            }), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/logout', methods=['POST'])
def dev_logout():
    token = request.headers.get('X-Dev-Token')
    if token:
        dev_auth.revoke_token(token)
    return jsonify({'success': True, 'message': 'Sesión cerrada'})

@app.route('/api/dev/verify')
def dev_verify():
    token = request.headers.get('X-Dev-Token')
    if dev_auth.verify_token(token):
        session = dev_auth.active_sessions.get(token)
        return jsonify({
            'valid': True,
            'username': session['username'],
            'expires_at': session['expires_at'].isoformat()
        })
    return jsonify({'valid': False}), 401

@app.route('/api/dev/learning/manual', methods=['POST'])
@dev_required
def dev_manual_learning():
    """Endpoint para aprendizaje manual"""
    try:
        data = request.json or {}
        
        # ✅ CORRECCIÓN: Manejar caso donde data es None
        if data is None:
            data = {}
        
        content = data.get('content')
        topic = data.get('topic', '').strip()
        source_url = data.get('source_url', '').strip() or None
        priority = data.get('priority', 1)
        
        # ✅ CORRECCIÓN: Verificar content de forma segura
        if content is None:
            return jsonify({
                'success': False,
                'error': 'Debes proporcionar contenido para aprender (campo "content")'
            }), 400
        
        # Convertir a string y limpiar
        content = str(content).strip()
        
        if not content:
            return jsonify({
                'success': False,
                'error': 'El contenido no puede estar vacío'
            }), 400
        
        if not topic:
            topic = content[:50] + '...' if len(content) > 50 else content
        
        # Validar prioridad
        try:
            priority = int(priority)
            if priority not in [1, 2, 3]:
                priority = 1
        except (ValueError, TypeError):
            priority = 1
        
        result = cic_ia.add_manual_learning(
            content=content,
            topic=topic,
            source_url=source_url,
            priority=priority
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'📥 Contenido agregado a la cola (ID: {result["id"]})',
                'topic': topic,
                'priority': priority,
                'content_preview': content[:100] + '...' if len(content) > 100 else content,
                'note': 'Se procesará en los próximos 5 minutos'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Error desconocido')
            }), 500
            
    except Exception as e:
        logger.error(f"Error en manual learning: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/learning/manual/queue', methods=['GET'])
@dev_required
def dev_manual_learning_queue():
    """Obtiene estado de cola manual"""
    try:
        with app.app_context():
            pending = ManualLearningQueue.query.filter_by(status='pending').count()
            processing = ManualLearningQueue.query.filter_by(status='processing').count()
            completed = ManualLearningQueue.query.filter_by(status='completed').count()
            failed = ManualLearningQueue.query.filter_by(status='failed').count()
            
            recent = ManualLearningQueue.query.order_by(
                ManualLearningQueue.created_at.desc()
            ).limit(10).all()
            
            return jsonify({
                'queue_stats': {
                    'pending': pending,
                    'processing': processing,
                    'completed': completed,
                    'failed': failed,
                    'total': pending + processing + completed + failed
                },
                'recent_items': [{
                    'id': item.id,
                    'topic': item.topic,
                    'status': item.status,
                    'priority': item.priority,
                    'content_preview': item.content[:80] + '...' if len(item.content) > 80 else item.content,
                    'created_at': item.created_at.isoformat(),
                    'processed_at': item.processed_at.isoformat() if item.processed_at else None
                } for item in recent]
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/neural/train', methods=['POST'])
@dev_required
def dev_train_neural_network():
    """Entrena red neuronal"""
    try:
        with app.app_context():
            conversations = Conversation.query.order_by(
                Conversation.timestamp.desc()
            ).limit(100).all()
            
            if len(conversations) < 10:
                return jsonify({
                    'success': False,
                    'error': 'Se necesitan al menos 10 conversaciones',
                    'current': len(conversations)
                }), 400
            
            texts = [conv.user_message for conv in conversations]
            labels = []
            module_labels = []
            
            for text in texts:
                text_lower = text.lower()
                
                # Etiquetas de intención
                if any(kw in text_lower for kw in ['hola', 'buenas', 'saludos']):
                    labels.append('greeting')
                elif any(kw in text_lower for kw in ['qué', 'cómo', 'cuándo', 'dónde', 'por qué']):
                    labels.append('question')
                elif any(kw in text_lower for kw in ['gracias', 'ok', 'bien', 'perfecto']):
                    labels.append('acknowledgment')
                else:
                    labels.append('statement')
                
                # Etiquetas de módulo
                mod_info = cic_ia.detect_module(text)
                module_labels.append(mod_info['module'])
            
            success = neural_net.train(texts, labels, module_labels)
            
            if success:
                return jsonify({
                    'success': True,
                    'message': '🧠 Red neuronal entrenada',
                    'samples': len(texts),
                    'intents': list(set(labels)),
                    'modules': list(set(module_labels)),
                    'stats': neural_net.get_stats()
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Error durante entrenamiento'
                }), 500
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/neural/stats', methods=['GET'])
@dev_required
def dev_neural_stats():
    return jsonify(neural_net.get_stats())

@app.route('/api/dev/learning/set-topic', methods=['POST'])
@dev_required
def dev_set_learning_topic():
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        
        if not topic:
            return jsonify({
                'success': False,
                'error': 'Debes proporcionar un tema'
            }), 400
        
        cic_ia.set_custom_topic(topic)
        
        return jsonify({
            'success': True,
            'message': f'📌 Tema establecido: "{topic}"',
            'topic': topic
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/learning/clear-topic', methods=['POST'])
@dev_required
def dev_clear_learning_topic():
    try:
        cic_ia.clear_custom_topic()
        return jsonify({
            'success': True,
            'message': 'Tema personalizado eliminado'
        })
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
        
        threading.Thread(
            target=cic_ia._perform_auto_learning,
            args=(topic,),
            daemon=True
        ).start()
        
        message_text = "🤖 Auto-aprendizaje iniciado"
        if topic:
            message_text += f' sobre "{topic}"'
        
        return jsonify({
            'success': True,
            'message': message_text,
            'started_at': datetime.utcnow().isoformat(),
            'topic': topic or cic_ia.current_learning_topic or 'aleatorio'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/system/force-learning', methods=['POST'])
@dev_required
def dev_force_learning():
    return evolution_learn_now()

@app.route('/api/dev/memories/all')
@dev_required
def dev_memories_all():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        pagination = Memory.query.order_by(
            Memory.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'memories': [{
                'id': m.id,
                'topic': m.topic,
                'content': m.content,
                'source': m.source,
                'relevance': m.relevance_score,
                'access_count': m.access_count,
                'created_at': m.created_at.isoformat()
            } for m in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/memories/<int:id>', methods=['DELETE'])
@dev_required
def dev_delete_memory(id):
    try:
        memory = Memory.query.get_or_404(id)
        db.session.delete(memory)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Memoria {id} eliminada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/stats/detailed')
@dev_required
def dev_stats_detailed():
    try:
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        stats = {
            'general': {
                'total_memories': Memory.query.count(),
                'total_conversations': Conversation.query.count(),
                'total_learning_logs': LearningLog.query.count(),
                'active_sessions': len(dev_auth.active_sessions)
            },
            'by_source': {
                'auto_learning': Memory.query.filter_by(source='auto_learning').count(),
                'web_search': Memory.query.filter_by(source='web_search').count(),
                'user_taught': Memory.query.filter_by(source='user_taught').count(),
                'manual_learning': Memory.query.filter_by(source='manual_learning').count(),
                'developer': Memory.query.filter_by(source='developer').count()
            },
            'today': {
                'conversations': db.session.query(db.func.sum(LearningLog.count)).filter(
                    LearningLog.date == today
                ).scalar() or 0,
                'auto_learned': db.session.query(db.func.sum(LearningLog.auto_learned)).filter(
                    LearningLog.date == today
                ).scalar() or 0
            },
            'this_week': {
                'conversations': db.session.query(db.func.sum(LearningLog.count)).filter(
                    LearningLog.date >= week_ago
                ).scalar() or 0,
                'web_searches': db.session.query(db.func.sum(LearningLog.web_searches)).filter(
                    LearningLog.date >= week_ago
                ).scalar() or 0
            },
            'learning': {
                'frequency': 'cada 2 horas',
                'custom_topic_pending': cic_ia.current_learning_topic is not None,
                'custom_topic': cic_ia.current_learning_topic,
                'total_available_topics': len(cic_ia.auto_learning_topics)
            },
            'neural_network': neural_net.get_stats(),
            'manual_queue': {
                'pending': ManualLearningQueue.query.filter_by(status='pending').count(),
                'completed': ManualLearningQueue.query.filter_by(status='completed').count()
            },
            'modules_available': ['data_analysis', 'image_generator', 'code_assistant', 'chat_history', 'file_manager']
        }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/system/clear-db', methods=['POST'])
@dev_required
def dev_clear_db():
    try:
        confirm = request.headers.get('X-Confirm-Delete')
        if confirm != 'DESTRUIR_TODO':
            return jsonify({
                'error': 'Confirmación requerida',
                'message': 'Agrega header X-Confirm-Delete: DESTRUIR_TODO'
            }), 400
        
        counts = {
            'memories': Memory.query.count(),
            'conversations': Conversation.query.count(),
            'logs': LearningLog.query.count(),
            'manual_queue': ManualLearningQueue.query.count()
        }
        
        Memory.query.delete()
        Conversation.query.delete()
        LearningLog.query.delete()
        WebSearchCache.query.delete()
        KnowledgeEvolution.query.delete()
        DeveloperSession.query.delete()
        ManualLearningQueue.query.delete()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Base de datos eliminada',
            'deleted': counts
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/sessions')
@dev_required
def dev_sessions():
    try:
        sessions = []
        for token, session in dev_auth.active_sessions.items():
            sessions.append({
                'username': session['username'],
                'created_at': session['created_at'].isoformat(),
                'expires_at': session['expires_at'].isoformat(),
                'last_used': session['last_used'].isoformat(),
                'token_preview': token[:8] + '...'
            })
        
        return jsonify({
            'active_sessions': len(sessions),
            'sessions': sessions
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint no encontrado'}), 404
    return render_template('index.html')

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Error interno del servidor'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
