"""
Cic_IA - Asistente Inteligente EVOLUTIVO con ARQUITECTURA MODULAR
Archivo principal - Versión 7.0 con Sistema de Usuarios + Modo Desarrollador
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
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
from sqlalchemy import select

# ========== IMPORTAR MÓDULOS ESPECIALIZADOS ==========
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

# Inicializar SQLAlchemy
db = SQLAlchemy(app)

# ========== MODELOS BASE DE DATOS ==========

class User(db.Model):
    """Usuarios registrados del sistema"""
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
    """Sesiones activas de usuarios"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(256), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    last_access = db.Column(db.DateTime, default=datetime.utcnow)

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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    has_attachment = db.Column(db.Boolean, default=False)
    attachment_path = db.Column(db.String(500))
    sources_used = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    mode_used = db.Column(db.String(50), default='unknown')

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

# ========== DECORADORES DE AUTENTICACIÓN ==========

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
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
    def decorated_function(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Token inválido'}), 401
        
        if not token:
            return jsonify({'error': 'No autorizado', 'code': 'INVALID_TOKEN'}), 401
            
        session = UserSession.query.filter_by(token=token).first()
        if not session:
            return jsonify({'error': 'Token inválido'}), 401
        
        user = User.query.get(session.user_id)
        if not user or not user.is_developer:
            return jsonify({'error': 'Se requieren privilegios de desarrollador'}), 403
        
        return f(*args, **kwargs)
    return decorated_function
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
        self.model_module = None
        self.model_relevance = None
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
            
            self.model_intent = MLPClassifier(
                hidden_layer_sizes=(128, 64, 32),
                activation='relu',
                solver='adam',
                max_iter=500,
                random_state=42,
                early_stopping=True,
                validation_fraction=0.1
            )
            
            self.model_module = MLPClassifier(
                hidden_layer_sizes=(64, 32),
                activation='relu',
                solver='adam',
                max_iter=300,
                random_state=42
            )
            
            self.model_relevance = MLPClassifier(
                hidden_layer_sizes=(64, 32),
                activation='tanh',
                solver='adam',
                max_iter=300,
                random_state=42
            )
            
            self.vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
            self.is_trained = False
            logger.info("🧠 Nueva red neuronal creada")
            
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
        """Predice qué módulo especializado debe usar el usuario"""
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
        
        data_keywords = ['csv', 'excel', 'datos', 'análisis', 'tabla', 'gráfico', 'pandas', 'sql']
        if any(kw in text_lower for kw in data_keywords):
            return {'module': 'data_analysis', 'confidence': 0.8, 'method': 'rules'}
        
        image_keywords = ['imagen', 'foto', 'genera imagen', 'dibuja', 'dall-e']
        if any(kw in text_lower for kw in image_keywords):
            return {'module': 'image_generator', 'confidence': 0.8, 'method': 'rules'}
        
        code_keywords = ['código', 'programa', 'python', 'javascript', 'html', 'debug']
        if any(kw in text_lower for kw in code_keywords):
            return {'module': 'code_assistant', 'confidence': 0.8, 'method': 'rules'}
        
        history_keywords = ['historial', 'conversaciones anteriores', 'chat pasado']
        if any(kw in text_lower for kw in history_keywords):
            return {'module': 'chat_history', 'confidence': 0.7, 'method': 'rules'}
        
        file_keywords = ['archivo', 'pdf', 'documento', 'subir']
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
        'version': '7.0_user_system',
        'features': ['chat', 'web_search', 'auto_learning', 'memory', 'users', 'auth', 'modules']
    })

# ========== RUTAS DE AUTENTICACIÓN ==========

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
        
        user = User(
            username=username,
            email=email or f"{username}@temp.com"
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Crear sesión
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=7)
        
        session = UserSession(
            user_id=user.id,
            token=token,
            expires_at=expires
        )
        db.session.add(session)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'is_developer': user.is_developer
            }
        })
        
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
        
        session = UserSession(
            user_id=user.id,
            token=token,
            expires_at=expires
        )
        db.session.add(session)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'is_developer': user.is_developer
            }
        })
        
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
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'is_developer': user.is_developer
        }
    })

# ========== RUTAS PROTEGIDAS ==========

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
        
        return jsonify({
            'success': True,
            'user_id': current_user.id,
            'username': current_user.username,
            'conversation_count': conv_count,
            'is_developer': current_user.is_developer
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def status():
    try:
        with app.app_context():
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            stats = cic_ia.get_learning_stats()
            
            return jsonify({
                'stage': 'v7.0_user_system',
                'total_memories': stats['total_memories'],
                'total_conversations': Conversation.query.count(),
                'today_learned': log.count if log else 0,
                'neural_network': stats.get('neural_network', {}),
                'modules': stats.get('modules_available', [])
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/modules/list', methods=['GET'])
def list_modules():
    return jsonify({
        'modules': [
            {'id': 'data_analysis', 'name': 'Análisis de Datos', 'icon': '📊'},
            {'id': 'image_generator', 'name': 'Generador de Imágenes', 'icon': '🎨'},
            {'id': 'code_assistant', 'name': 'Asistente de Código', 'icon': '💻'},
            {'id': 'chat_history', 'name': 'Historial', 'icon': '📜'},
            {'id': 'file_manager', 'name': 'Archivos', 'icon': '📁'}
        ]
    })

# ========== RUTAS DE DESARROLLADOR ==========

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
                'total_users': User.query.count(),
                'active_sessions': UserSession.query.count()
            },
            'today': {
                'conversations': db.session.query(db.func.sum(LearningLog.count)).filter(
                    LearningLog.date == today
                ).scalar() or 0
            },
            'neural_network': neural_net.get_stats()
        }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
                'content': m.content[:200],
                'source': m.source,
                'created_at': m.created_at.isoformat()
            } for m in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/neural/train', methods=['POST'])
@dev_required
def dev_train_neural():
    try:
        conversations = Conversation.query.order_by(
            Conversation.timestamp.desc()
        ).limit(100).all()
        
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
            return jsonify({
                'success': True,
                'message': '🧠 Red neuronal entrenada',
                'samples': len(texts),
                'stats': neural_net.get_stats()
            })
        else:
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
        
        threading.Thread(
            target=cic_ia._perform_auto_learning,
            args=(topic,),
            daemon=True
        ).start()
        
        return jsonify({
            'success': True,
            'message': '🤖 Aprendizaje iniciado' + (f' sobre "{topic}"' if topic else ''),
            'started_at': datetime.utcnow().isoformat()
        })
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
        
        # No eliminar usuarios, solo datos de aprendizaje
        Memory.query.delete()
        Conversation.query.delete()
        LearningLog.query.delete()
        WebSearchCache.query.delete()
        KnowledgeEvolution.query.delete()
        ManualLearningQueue.query.delete()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Base de datos limpiada (usuarios preservados)'
        })
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

# ========== INICIO DE LA APLICACIÓN ==========

if __name__ == '__main__':
    # Solo para desarrollo local - Render usa gunicorn
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
