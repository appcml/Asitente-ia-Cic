"""
Cic_IA v7.2 - Asistente Inteligente EVOLUTIVO
Modo Desarrollador + Modo Usuario con sistema de cuentas
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os
import json
import random
import threading
import time
import re
import logging
import urllib.parse
import pickle
import numpy as np
from sqlalchemy import select, func
import requests
from bs4 import BeautifulSoup
import hashlib
import secrets

# Intentar importar módulos v7.2
try:
    from models import db, init_database, Memory, Conversation, LearningLog, FeedbackLog
    from models import CuriosityGap, TrainingBatch, DeveloperSession, WebSearchCache
    from models import KnowledgeEvolution, ManualLearningQueue, WorkingMemorySnapshot
    from neural_engine import CicNeuralEngine
    from feedback_system import FeedbackCollector
    from curiosity_engine import CuriosityEngine
    from working_memory import WorkingMemory
    V7_MODULES_AVAILABLE = True
    print("✅ Módulos v7.2 cargados correctamente")
except ImportError as e:
    print(f"⚠️ Módulos no disponibles: {e}")
    V7_MODULES_AVAILABLE = False
    db = None

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('cic_ia')

# ========== INICIALIZACIÓN FLASK ==========

app = Flask(__name__)

# Configuración crítica para sesiones
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cic-ia-secret-2024-v7-desarrollo')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cic_ia_v7.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True
}

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'py', 'js', 'html', 'css', 'json'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Credenciales desarrollador
DEV_USERNAME = os.environ.get('DEV_USERNAME', 'admin')
DEV_PASSWORD = os.environ.get('DEV_PASSWORD', 'CicDev2024!')

# Inicializar DB
if V7_MODULES_AVAILABLE:
    init_database(app)
else:
    db = SQLAlchemy(app)

# ========== MODELOS ADICIONALES PARA USUARIOS ==========

class UserAccount(db.Model):
    """Sistema de cuentas de usuario"""
    __tablename__ = 'user_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    personality_mode = db.Column(db.String(20), default='kimi')
    preferred_topics = db.Column(db.JSON, default=list)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'personality_mode': self.personality_mode
        }

# Crear tablas adicionales
with app.app_context():
    db.create_all()

# ========== KNOWLEDGE BASE ==========

KNOWLEDGE_BASE = {
    'ia': {
        'respuestas': [
            "La Inteligencia Artificial (IA) es la simulación de procesos de inteligencia humana por sistemas informáticos.",
            "La IA permite a las máquinas aprender, razonar y resolver problemas de manera autónoma."
        ],
        'keywords': ['inteligencia artificial', 'machine learning', 'deep learning', 'neural network', 'red neuronal']
    },
    'python': {
        'respuestas': [
            "Python es el lenguaje líder en IA por su sintaxis clara y bibliotecas como TensorFlow, PyTorch y scikit-learn.",
            "Python fue creado por Guido van Rossum y es ideal para prototipado rápido."
        ],
        'keywords': ['python', 'programacion', 'codigo', 'desarrollo', 'flask', 'django']
    },
    'hola': {
        'respuestas': [
            "¡Hola! Soy Cic_IA, tu asistente con auto-aprendizaje. ¿En qué puedo ayudarte?",
            "¡Bienvenido! Estoy aprendiendo continuamente para servirte mejor."
        ],
        'keywords': ['hola', 'buenas', 'saludos', 'buenos dias', 'buenas tardes']
    },
    'cic_ia': {
        'respuestas': [
            "Soy Cic_IA, una inteligencia artificial evolutiva que aprende automáticamente y mejora con cada conversación.",
            "Cic_IA es un asistente IA que aprende de internet, memoriza conversaciones y detecta curiosidades."
        ],
        'keywords': ['quien eres', 'que eres', 'cic_ia', 'tu nombre', 'version']
    },
    'default': {
        'respuestas': [
            "Interesante pregunta sobre '{tema}'. Déjame buscar información actualizada.",
            "Voy a investigar sobre '{tema}' para darte información precisa."
        ],
        'keywords': []
    }
}

# ========== RED NEURONAL LEGACY ==========

class CicNeuralNetwork:
    def __init__(self):
        self.model_intent = None
        self.model_relevance = None
        self.is_trained = False
        self.training_data = []
        self.labels = []
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
                    self.model_relevance = saved_data.get('relevance_model')
                    self.vectorizer = saved_data.get('vectorizer')
                    self.is_trained = saved_data.get('is_trained', False)
        except Exception as e:
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
                early_stopping=True
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
        except ImportError:
            self.model_intent = None

    def train(self, texts, labels):
        if self.model_intent is None:
            return False
        try:
            X = self.vectorizer.fit_transform(texts)
            self.model_intent.fit(X, labels)
            self.is_trained = True
            self.training_data = texts
            self.labels = labels
            self._save_models()
            return True
        except Exception as e:
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

    def _save_models(self):
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump({
                    'intent_model': self.model_intent,
                    'relevance_model': self.model_relevance,
                    'vectorizer': self.vectorizer,
                    'is_trained': self.is_trained
                }, f)
        except:
            pass

neural_net = CicNeuralNetwork()

# ========== SERVICIOS ==========

class WebSearchEngine:
    @staticmethod
    def search_duckduckgo(query, max_results=5):
        try:
            try:
                from duckduckgo_search import DDGS
                results = []
                ddgs = DDGS()
                for result in ddgs.text(query, max_results=max_results):
                    results.append({
                        'title': result.get('title', ''),
                        'url': result.get('href', ''),
                        'snippet': result.get('body', ''),
                        'source': 'duckduckgo'
                    })
                return results
            except ImportError:
                return WebSearchEngine._search_fallback(query, max_results)
        except Exception as e:
            return []

    @staticmethod
    def _search_fallback(query, max_results=5):
        try:
            url = f"https://html.duckduckgo.com/?q={urllib.parse.quote(query)}"
            headers = {'User-Agent': 'Mozilla/5.0'}
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
        except:
            return []

# ========== CLASE PRINCIPAL CIC_IA ==========

class CicIA:
    def __init__(self):
        self.learning_active = True
        self.web_search_engine = WebSearchEngine()
        self.current_learning_topic = None
        self._auto_learned_session = 0
        
        # Componentes v7.2
        if V7_MODULES_AVAILABLE:
            self.neural_engine = CicNeuralEngine()
            self.feedback_collector = FeedbackCollector(db.session)
            self.curiosity_engine = CuriosityEngine(db.session, self.web_search_engine)
            self.working_memory = WorkingMemory(max_turns=15)
        
        # Temas de aprendizaje
        self.auto_learning_topics = [
            'física cuántica avances 2024', 'biología sintética descubrimientos',
            'neurociencia cognitiva', 'inteligencia artificial noticias 2024',
            'machine learning avances', 'computación cuántica progreso',
            'cambio climático soluciones', 'energía renovable tecnología',
            'desarrollo software arquitectura', 'ciberseguridad tendencias',
            'blockchain aplicaciones', 'Internet de las cosas IoT',
            'realidad virtual aumentada', 'robótica humanoides',
            'biotecnología longevidad', 'espacio colonización',
            'economía global tendencias', 'educación innovación',
            'salud mental bienestar', 'arte inteligencia artificial'
        ]

        # Estadísticas
        with app.app_context():
            self.stats = {
                'memories': Memory.query.count() if V7_MODULES_AVAILABLE else 0,
                'conversations': Conversation.query.count() if V7_MODULES_AVAILABLE else 0,
                'today_learned': self._get_today_count(),
                'users': UserAccount.query.count()
            }

        self._start_background_threads()
        self._print_startup_message()

    def _print_startup_message(self):
        logger.info("=" * 70)
        logger.info("🚀 CIC_IA v7.2 - MODO DESARROLLO + USUARIO")
        logger.info(f"📚 Memorias: {self.stats['memories']}")
        logger.info(f"👥 Usuarios registrados: {self.stats['users']}")
        logger.info(f"🧠 Auto-aprendizaje: ACTIVADO")
        logger.info("=" * 70)

    def _start_background_threads(self):
        threads = [
            (self._continuous_learning_loop, "Auto-aprendizaje"),
            (self._nightly_training_loop, "Reentrenamiento"),
        ]
        for target, name in threads:
            t = threading.Thread(target=target, daemon=True)
            t.name = name
            t.start()

    def _continuous_learning_loop(self):
        time.sleep(60)
        while self.learning_active:
            try:
                self._perform_auto_learning()
            except Exception as e:
                logger.error(f"Error auto-aprendizaje: {e}")
            time.sleep(900)

    def _nightly_training_loop(self):
        while self.learning_active:
            now = datetime.now()
            if now.hour == 3 and now.minute < 5:
                try:
                    self._perform_nightly_training()
                except Exception as e:
                    logger.error(f"Error reentrenamiento: {e}")
                time.sleep(3600)
            else:
                time.sleep(300)

    def _perform_auto_learning(self, custom_topic=None):
        with app.app_context():
            topic = custom_topic or self.current_learning_topic or random.choice(self.auto_learning_topics)
            self.current_learning_topic = None
            
            logger.info(f"🤖 Auto-aprendizaje: '{topic}'")
            
            results = self.web_search_engine.search_duckduckgo(topic, max_results=3)
            if not results:
                return 0
            
            learned_count = 0
            for result in results:
                try:
                    if V7_MODULES_AVAILABLE:
                        preview = result['snippet'][:50] if result['snippet'] else ''
                        exists = Memory.query.filter(Memory.content.ilike(f'%{preview}%')).first()
                        if exists:
                            continue
                        
                        memory = Memory(
                            content=f"{result['title']}\n\n{result['snippet']}\n\nFuente: {result['url']}",
                            source='auto_learning',
                            topic=topic,
                            relevance_score=0.6,
                            confidence_score=0.5
                        )
                        db.session.add(memory)
                        
                        evolution = KnowledgeEvolution(
                            topic=topic,
                            action='learned',
                            new_content=result['snippet'][:200] if result['snippet'] else '',
                            source='auto_learning',
                            triggered_by='auto'
                        )
                        db.session.add(evolution)
                        
                        db.session.commit()
                    
                    learned_count += 1
                    logger.info(f"✅ Aprendido: {result['title'][:60]}...")
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando: {e}")
                    continue
            
            return learned_count

    def _perform_nightly_training(self):
        if not V7_MODULES_AVAILABLE or not self.neural_engine:
            return
        
        logger.info("🌙 Reentrenamiento nocturno...")
        
        with app.app_context():
            feedback_data = self.feedback_collector.get_feedback_for_training(min_samples=5)
            
            if len(feedback_data) < 5:
                logger.info(f"ℹ️ Insuficiente feedback ({len(feedback_data)})")
                return
            
            result = self.neural_engine.retrain_with_feedback(feedback_data)
            
            if result['success']:
                batch = TrainingBatch(
                    samples_used=len(feedback_data),
                    accuracy_after=result['metrics'].get('train_accuracy'),
                    loss=result['metrics'].get('loss'),
                    status='completed',
                    completed_at=datetime.utcnow()
                )
                db.session.add(batch)
                db.session.commit()
                logger.info(f"✅ Reentrenado: accuracy={result['metrics']['train_accuracy']:.3f}")

    def _get_today_count(self):
        if not V7_MODULES_AVAILABLE:
            return 0
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        return log.count if log else 0

    def process_chat(self, user_input, mode='balanced', user_id=None):
        """Procesa mensaje del usuario"""
        input_lower = user_input.lower().strip()
        
        # Fecha/hora
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_conversation(user_input, response, 'system_time', user_id=user_id)
        
        # Contexto working memory
        context_summary = ""
        if V7_MODULES_AVAILABLE and self.working_memory:
            context_summary = self.working_memory.get_context_summary()
        
        # Predecir intención
        intent_info = {'intent': 'unknown', 'confidence': 0.0}
        if V7_MODULES_AVAILABLE and self.neural_engine:
            intent_info = self.neural_engine.predict_intent(user_input)
        else:
            intent_info = neural_net.predict_intent(user_input)
        
        # Actualizar working memory
        if V7_MODULES_AVAILABLE and self.working_memory:
            entities = self._extract_entities(user_input)
            self.working_memory.add_turn(
                user_message=user_input,
                bot_response="",
                intent=intent_info['intent'],
                entities=entities
            )
        
        # Generar respuesta
        best_topic = self._find_best_topic(input_lower)
        
        with app.app_context():
            memories = Memory.query.all() if V7_MODULES_AVAILABLE else []
            relevant_memories = self._find_relevant_memories(user_input, memories, intent_info)
            
            response, sources = self._generate_response(
                user_input=user_input,
                best_topic=best_topic,
                relevant_memories=relevant_memories,
                intent_info=intent_info,
                mode=mode
            )
            
            # Actualizar working memory con respuesta
            if V7_MODULES_AVAILABLE and self.working_memory and self.working_memory.turns:
                self.working_memory.turns[-1].bot_response = response
            
            return self._save_conversation(
                user_input=user_input,
                response=response,
                source=sources[0] if sources else 'learning',
                user_id=user_id,
                intent=intent_info['intent'],
                confidence=intent_info['confidence']
            )

    def _generate_response(self, user_input, best_topic, relevant_memories, intent_info, mode):
        sources = []
        response = ""
        
        # Knowledge base
        if best_topic and best_topic != 'default':
            respuestas = KNOWLEDGE_BASE[best_topic]['respuestas']
            response = random.choice(respuestas)
            sources.append('knowledge_base')
        
        # Memorias relevantes
        elif relevant_memories:
            mem = relevant_memories[0]
            recall_context = ""
            if V7_MODULES_AVAILABLE and self.working_memory:
                recall_context = self.working_memory.recall_related_info()
            
            if recall_context:
                response = f"Basándome en lo que conversamos: {mem.content[:250]}"
            else:
                response = f"Según mi conocimiento: {mem.content[:300]}"
            
            sources.append(f"memory_{mem.source}")
            
            if V7_MODULES_AVAILABLE:
                mem.access_count += 1
                db.session.commit()
        
        # Búsqueda web
        else:
            tema = user_input[:40] if len(user_input) > 5 else "este tema"
            web_results = self._search_and_learn(user_input)
            
            if web_results:
                response = f"He investigado sobre '{tema}':\n\n{web_results['summary']}"
                sources.append('web_search')
            else:
                respuestas_default = KNOWLEDGE_BASE['default']['respuestas']
                response = random.choice(respuestas_default).format(tema=tema)
                sources.append('uncertain')
        
        # Ajustar según modo
        if mode == 'fast':
            response = response.split('.')[0] + '.' if '.' in response else response[:100]
        
        return response, sources

    def _find_relevant_memories(self, query, memories, intent_info):
        if not V7_MODULES_AVAILABLE:
            query_words = set(query.lower().split())
            relevant = []
            for mem in memories:
                mem_words = set(mem.content.lower().split())
                overlap = len(query_words & mem_words)
                if overlap >= 2:
                    relevant.append(mem)
            return relevant
        
        if self.neural_engine and self.neural_engine.is_trained and intent_info.get('confidence', 0) > 0.5:
            relevant = []
            for mem in memories:
                relevance = self.neural_engine.predict_relevance(query, mem.content)
                if relevance > 0.5:
                    relevant.append((mem, relevance))
                    mem.access_count += 1
            
            relevant.sort(key=lambda x: x[1], reverse=True)
            db.session.commit()
            return [mem for mem, _ in relevant[:5]]
        else:
            return self._keyword_memory_search(query, memories)

    def _keyword_memory_search(self, query, memories):
        query_words = set(query.lower().split())
        relevant = []
        
        for mem in memories:
            mem_words = set(mem.content.lower().split())
            overlap = len(query_words & mem_words)
            
            if overlap >= 2:
                relevant.append(mem)
                if V7_MODULES_AVAILABLE:
                    mem.access_count += 1
        
        if V7_MODULES_AVAILABLE:
            db.session.commit()
        
        return relevant

    def _search_and_learn(self, query):
        try:
            with app.app_context():
                if V7_MODULES_AVAILABLE:
                    cached = WebSearchCache.query.filter_by(query=query).first()
                    if cached and cached.expires_at > datetime.utcnow():
                        cached.usage_count += 1
                        db.session.commit()
                        return cached.results
                
                results = self.web_search_engine.search_duckduckgo(query, max_results=3)
                
                if not results:
                    return None
                
                summary = ""
                for i, result in enumerate(results, 1):
                    summary += f"{i}. **{result['title']}**\n   {result['snippet']}\n\n"
                    
                    if V7_MODULES_AVAILABLE:
                        memory = Memory(
                            content=result['snippet'],
                            source='web_search',
                            topic=query,
                            relevance_score=0.7,
                            confidence_score=0.6
                        )
                        db.session.add(memory)
                
                if V7_MODULES_AVAILABLE:
                    cache_entry = WebSearchCache(
                        query=query,
                        results={'summary': summary, 'raw_results': results},
                        expires_at=datetime.utcnow() + timedelta(hours=24)
                    )
                    db.session.add(cache_entry)
                    db.session.commit()
                
                return {'summary': summary, 'raw_results': results}
                
        except Exception as e:
            logger.error(f"❌ Error búsqueda: {e}")
            return None

    def _save_conversation(self, user_input, response, source, user_id=None, intent=None, confidence=None):
        with app.app_context():
            conv = Conversation(
                user_message=user_input,
                bot_response=response,
                sources_used=[source],
                intent_detected=intent,
                confidence=confidence,
                user_id=user_id
            ) if V7_MODULES_AVAILABLE else None
            
            if V7_MODULES_AVAILABLE:
                db.session.add(conv)
                db.session.commit()
                
                today = date.today()
                log = LearningLog.query.filter_by(date=today).first()
                if not log:
                    log = LearningLog(date=today)
                    db.session.add(log)
                log.count += 1
                db.session.commit()
                
                total_mem = Memory.query.count()
            else:
                total_mem = 0
        
        return {
            'response': response,
            'model_used': 'cic_ia_v7.2',
            'sources_used': [source],
            'total_memories': total_mem,
            'intent_detected': intent,
            'confidence': confidence
        }

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

    def _extract_entities(self, text):
        entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        quoted = re.findall(r'"([^"]+)"', text)
        return list(set(entities + quoted))

    def _is_date_time_question(self, text):
        keywords = ['qué día', 'qué hora', 'fecha', 'hora actual', 'hoy es', 'dia es', 'día es']
        return any(kw in text for kw in keywords)

    def _get_dynamic_date_response(self, text):
        now = datetime.now()
        dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        fecha = f"📅 Hoy es {dias[now.weekday()]}, {now.day} de {meses[now.month-1]} de {now.year}"
        hora = f"🕐 Son las {now.strftime('%H:%M:%S')}"
        
        return f"{fecha}\n{hora}"

    def force_learn(self, topic):
        """Forzar aprendizaje de un tema específico"""
        logger.info(f"🎯 Forzando aprendizaje: '{topic}'")
        count = self._perform_auto_learning(custom_topic=topic)
        return {'success': True, 'topic': topic, 'learned_count': count}

    def get_learning_stats(self):
        if not V7_MODULES_AVAILABLE:
            return {'error': 'Módulos no disponibles'}
        
        with app.app_context():
            return {
                'total_memories': Memory.query.count(),
                'by_source': {
                    'auto_learning': Memory.query.filter_by(source='auto_learning').count(),
                    'web_search': Memory.query.filter_by(source='web_search').count(),
                    'curiosity': Memory.query.filter_by(source='curiosity').count(),
                    'manual_learning': Memory.query.filter_by(source='manual_learning').count(),
                },
                'feedback': {
                    'total': FeedbackLog.query.count(),
                    'implicit': FeedbackLog.query.filter_by(feedback_type='implicit').count(),
                    'explicit': FeedbackLog.query.filter_by(feedback_type='explicit').count(),
                },
                'curiosity': {
                    'pending': CuriosityGap.query.filter_by(status='pending').count(),
                    'learned': CuriosityGap.query.filter_by(status='learned').count(),
                },
                'users': UserAccount.query.count(),
                'version': '7.2'
            }

# Instancia global
cic_ia = CicIA()

# ========== DECORADORES DE AUTENTICACIÓN ==========

def dev_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Verificar sesión de desarrollador
        if session.get('dev_mode') and session.get('dev_username') == DEV_USERNAME:
            return f(*args, **kwargs)
        
        # Verificar header de token
        token = request.headers.get('X-Dev-Token')
        if token:
            # Validar token simple (en producción usar JWT)
            try:
                data = json.loads(secrets.token_urlsafe.decode(token))
                if data.get('user') == DEV_USERNAME:
                    return f(*args, **kwargs)
            except:
                pass
        
        return jsonify({'error': 'No autorizado - Modo desarrollador requerido'}), 401
    return decorated_function

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ========== RUTAS DE AUTENTICACIÓN ==========

@app.route('/')
def index():
    """Redirige según modo"""
    if session.get('dev_mode'):
        return redirect(url_for('dev_dashboard'))
    if 'user_id' in session:
        return redirect(url_for('chat_page'))
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Login de usuarios normales"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = UserAccount.query.filter_by(username=username, is_active=True).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('chat_page'))
        
        return render_template('login.html', error='Credenciales inválidas')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    """Registro de nuevos usuarios"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        # Validaciones
        if len(username) < 3:
            return render_template('register.html', error='Usuario mínimo 3 caracteres')
        if len(password) < 6:
            return render_template('register.html', error='Contraseña mínimo 6 caracteres')
        
        # Verificar existente
        if UserAccount.query.filter_by(username=username).first():
            return render_template('register.html', error='Usuario ya existe')
        if UserAccount.query.filter_by(email=email).first():
            return render_template('register.html', error='Email ya registrado')
        
        # Crear usuario
        user = UserAccount(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        return redirect(url_for('login_page', registered='true'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    """Cerrar sesión"""
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/dev-login', methods=['GET', 'POST'])
def dev_login_page():
    """Login modo desarrollador"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == DEV_USERNAME and password == DEV_PASSWORD:
            session['dev_mode'] = True
            session['dev_username'] = DEV_USERNAME
            session.permanent = True
            return redirect(url_for('dev_dashboard'))
        
        return render_template('dev_login.html', error='Credenciales inválidas')
    
    return render_template('dev_login.html')

@app.route('/dev-logout')
def dev_logout():
    """Salir modo desarrollador"""
    session.pop('dev_mode', None)
    session.pop('dev_username', None)
    return redirect(url_for('index'))

# ========== RUTAS DE APLICACIÓN ==========

@app.route('/chat')
@login_required
def chat_page():
    """Chat para usuarios normales"""
    return render_template('chat.html', 
                         username=session.get('username'),
                         is_dev=False)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """API de chat - accesible para usuarios logueados o dev"""
    try:
        data = request.json
        message = data.get('message', '').strip()
        mode = data.get('mode', 'balanced')
        
        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        # Determinar usuario
        user_id = session.get('user_id')
        
        result = cic_ia.process_chat(message, mode=mode, user_id=user_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error en /api/chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def api_status():
    """Estado público del sistema"""
    try:
        stats = cic_ia.get_learning_stats()
        today = date.today()
        
        if V7_MODULES_AVAILABLE:
            log = LearningLog.query.filter_by(date=today).first()
            today_count = log.count if log else 0
            today_auto = log.auto_learned if log else 0
        else:
            today_count = today_auto = 0
        
        return jsonify({
            'stage': 'v7.2',
            'total_memories': stats.get('total_memories', 0),
            'today_conversations': today_count,
            'today_auto_learned': today_auto,
            'total_users': stats.get('users', 0),
            'features': ['chat', 'web_search', 'auto_learning', 'memory', 'user_accounts', 'dev_mode']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check simple"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '7.2.0'
    })

# ========== RUTAS DE DESARROLLADOR ==========

@app.route('/dev')
@dev_required
def dev_dashboard():
    """Dashboard de desarrollador"""
    return render_template('dev_dashboard.html')

@app.route('/api/dev/stats')
@dev_required
def dev_stats():
    """Estadísticas completas para desarrollador"""
    try:
        stats = cic_ia.get_learning_stats()
        
        # Estadísticas adicionales
        recent_memories = Memory.query.order_by(
            Memory.created_at.desc()
        ).limit(10).all() if V7_MODULES_AVAILABLE else []
        
        recent_conversations = Conversation.query.order_by(
            Conversation.timestamp.desc()
        ).limit(10).all() if V7_MODULES_AVAILABLE else []
        
        return jsonify({
            'system': {
                'version': '7.2',
                'v7_modules': V7_MODULES_AVAILABLE,
                'timestamp': datetime.utcnow().isoformat()
            },
            'learning': stats,
            'recent_memories': [{
                'id': m.id,
                'topic': m.topic,
                'source': m.source,
                'created_at': m.created_at.isoformat(),
                'preview': m.content[:100]
            } for m in recent_memories],
            'recent_conversations': [{
                'id': c.id,
                'user_message': c.user_message[:50],
                'intent': c.intent_detected,
                'timestamp': c.timestamp.isoformat()
            } for c in recent_conversations],
            'working_memory': cic_ia.working_memory.get_stats() if (V7_MODULES_AVAILABLE and cic_ia.working_memory) else {}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/force-learn', methods=['POST'])
@dev_required
def dev_force_learn():
    """Forzar aprendizaje de un tema"""
    try:
        topic = request.json.get('topic', '').strip()
        if not topic:
            return jsonify({'error': 'Tema requerido'}), 400
        
        result = cic_ia.force_learn(topic)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/memories')
@dev_required
def dev_memories():
    """Listar todas las memorias"""
    try:
        if not V7_MODULES_AVAILABLE:
            return jsonify({'error': 'Módulos no disponibles'}), 500
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        pagination = Memory.query.order_by(Memory.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'memories': [{
                'id': m.id,
                'topic': m.topic,
                'source': m.source,
                'content': m.content,
                'relevance_score': m.relevance_score,
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
    """Eliminar una memoria"""
    try:
        if not V7_MODULES_AVAILABLE:
            return jsonify({'error': 'Módulos no disponibles'}), 500
        
        memory = Memory.query.get_or_404(id)
        db.session.delete(memory)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Memoria {id} eliminada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/users')
@dev_required
def dev_users():
    """Listar usuarios registrados"""
    try:
        users = UserAccount.query.all()
        return jsonify({
            'count': len(users),
            'users': [u.to_dict() for u in users]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/toggle-mode', methods=['POST'])
@dev_required
def dev_toggle_mode():
    """Cambiar entre modo dev y modo usuario para testing"""
    try:
        mode = request.json.get('mode', 'dev')  # 'dev' o 'user'
        
        if mode == 'user':
            # Simular ser usuario normal
            session.pop('dev_mode', None)
            # Crear sesión de usuario de prueba si no existe
            if 'user_id' not in session:
                test_user = UserAccount.query.filter_by(username='test_dev').first()
                if not test_user:
                    test_user = UserAccount(
                        username='test_dev',
                        email='test@dev.local',
                        personality_mode='kimi'
                    )
                    test_user.set_password('test123')
                    db.session.add(test_user)
                    db.session.commit()
                
                session['user_id'] = test_user.id
                session['username'] = test_user.username
            
            return jsonify({
                'success': True,
                'mode': 'user',
                'message': 'Modo usuario activado - ahora ves lo que ven los usuarios',
                'redirect': '/chat'
            })
        else:
            # Volver a modo dev
            session['dev_mode'] = True
            session.pop('user_id', None)
            session.pop('username', None)
            return jsonify({
                'success': True,
                'mode': 'dev',
                'message': 'Modo desarrollador reactivado',
                'redirect': '/dev'
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.errorhandler(404)
def not_found(error):
    return render_template('index.html')

@app.errorhandler(500)
def internal_error(error):
    if V7_MODULES_AVAILABLE:
        db.session.rollback()
    return jsonify({'error': 'Error interno'}), 500

# ========== INICIALIZACIÓN ==========

application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
