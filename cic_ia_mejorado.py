"""
Cic_IA v7.2 - Asistente Inteligente EVOLUTIVO
Modo Desarrollador + Modo Usuario - VERSIÓN FINAL
"""

# ========== IMPORTACIONES CORREGIDAS ==========
from flask import Flask, render_template, render_template_string, request, jsonify, send_from_directory, session, redirect, url_for
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
from sqlalchemy import select, func, or_
import requests
from bs4 import BeautifulSoup
import hashlib
import secrets

# ========== CONFIGURACIÓN INICIAL ==========

app = Flask(__name__, template_folder='templates')

# Configuración crítica para sesiones
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cic-ia-secret-2024-v7-desarrollo')
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
os.makedirs('templates', exist_ok=True)

# Credenciales desarrollador
DEV_USERNAME = os.environ.get('DEV_USERNAME', 'admin')
DEV_PASSWORD = os.environ.get('DEV_PASSWORD', 'CicDev2024!')

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('cic_ia')

# ========== INICIALIZAR DB ==========

db = SQLAlchemy(app)

# ========== MODELOS DE BASE DE DATOS ==========

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
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'personality_mode': self.personality_mode
        }

class Memory(db.Model):
    """Memorias de la IA"""
    __tablename__ = 'memories'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(50), default='unknown')
    topic = db.Column(db.String(100))
    relevance_score = db.Column(db.Float, default=0.5)
    confidence_score = db.Column(db.Float, default=0.5)
    access_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Conversation(db.Model):
    """Conversaciones con usuarios"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'))
    sources_used = db.Column(db.JSON, default=list)
    intent_detected = db.Column(db.String(50))
    confidence = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LearningLog(db.Model):
    """Log de aprendizaje diario"""
    __tablename__ = 'learning_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    count = db.Column(db.Integer, default=0)
    auto_learned = db.Column(db.Integer, default=0)
    web_searches = db.Column(db.Integer, default=0)

class KnowledgeEvolution(db.Model):
    """Evolución del conocimiento"""
    __tablename__ = 'knowledge_evolution'
    
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(50))
    new_content = db.Column(db.Text)
    source = db.Column(db.String(50))
    triggered_by = db.Column(db.String(50))
    date = db.Column(db.DateTime, default=datetime.utcnow)

class CuriosityGap(db.Model):
    """Gaps de curiosidad"""
    __tablename__ = 'curiosity_gaps'
    
    id = db.Column(db.Integer, primary_key=True)
    concept = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')
    mention_count = db.Column(db.Integer, default=1)
    context_examples = db.Column(db.JSON, default=list)
    last_mentioned = db.Column(db.DateTime, default=datetime.utcnow)

class WebSearchCache(db.Model):
    """Caché de búsquedas web"""
    __tablename__ = 'web_search_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(500), unique=True)
    results = db.Column(db.JSON)
    expires_at = db.Column(db.DateTime)
    usage_count = db.Column(db.Integer, default=1)

class FeedbackLog(db.Model):
    """Feedback de usuarios"""
    __tablename__ = 'feedback_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'))
    feedback_type = db.Column(db.String(20))
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Crear todas las tablas
with app.app_context():
    db.create_all()

# ========== INTENTAR IMPORTAR MÓDULOS AVANZADOS ==========

V7_MODULES_AVAILABLE = False
neural_engine = None
feedback_collector = None
curiosity_engine = None
working_memory = None

try:
    from neural_engine import CicNeuralEngine
    from feedback_system import FeedbackCollector
    from curiosity_engine import CuriosityEngine
    from working_memory import WorkingMemory
    V7_MODULES_AVAILABLE = True
    logger.info("✅ Módulos v7.2 avanzados cargados")
except ImportError as e:
    logger.warning(f"⚠️ Módulos avanzados no disponibles: {e}")
    V7_MODULES_AVAILABLE = False

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

# ========== RED NEURONAL SIMPLE ==========

class SimpleNeuralNetwork:
    def predict_intent(self, text):
        text_lower = text.lower()
        intents = {
            'greeting': ['hola', 'buenas', 'saludos', 'hey', 'hi'],
            'question': ['que', 'qué', 'como', 'cómo', 'cuando', 'cuándo', 'donde', 'dónde', 'por que', 'por qué'],
            'farewell': ['adios', 'adiós', 'chao', 'hasta luego', 'nos vemos'],
            'thanks': ['gracias', 'thank', 'thanks', 'agradecido'],
            'identity': ['quien eres', 'que eres', 'tu nombre', 'cic_ia', 'cic-ia']
        }
        
        scores = {}
        for intent, keywords in intents.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[intent] = score
        
        if scores:
            best_intent = max(scores, key=scores.get)
            confidence = min(0.5 + (scores[best_intent] * 0.2), 0.95)
            return {'intent': best_intent, 'confidence': confidence}
        
        return {'intent': 'statement', 'confidence': 0.3}

simple_neural = SimpleNeuralNetwork()

# ========== WORKING MEMORY SIMPLE ==========

class SimpleWorkingMemory:
    def __init__(self, max_turns=15):
        self.max_turns = max_turns
        self.turns = []
        self.current_topic = None
        self.user_facts = {}
        self.session_start = datetime.utcnow()
    
    def add_turn(self, user_message, bot_response, intent, entities=None):
        turn = {
            'user': user_message,
            'bot': bot_response,
            'intent': intent,
            'entities': entities or [],
            'timestamp': datetime.utcnow(),
            'topic': self.current_topic
        }
        self.turns.append(turn)
        if len(self.turns) > self.max_turns:
            self.turns.pop(0)
        self._extract_facts(user_message)
    
    def _extract_facts(self, message):
        message_lower = message.lower()
        patterns = [
            (r'me llamo (\w+)', 'nombre'),
            (r'mi nombre es (\w+)', 'nombre'),
            (r'trabajo (?:como|de) (\w+)', 'trabajo'),
            (r'soy (\w+) de profesión', 'profesion'),
            (r'tengo (\d+) años', 'edad'),
            (r'vivo en (\w+)', 'ubicacion'),
        ]
        
        for pattern, key in patterns:
            match = re.search(pattern, message_lower)
            if match:
                value = match.group(1).strip()
                self.user_facts[key] = value
                logger.info(f"👤 Hecho extraído: {key} = {value}")
    
    def get_context_summary(self):
        parts = []
        if self.user_facts.get('nombre'):
            parts.append(f"Usuario: {self.user_facts['nombre']}")
        if self.current_topic:
            parts.append(f"Tema: {self.current_topic}")
        if self.turns:
            recent_intents = [t['intent'] for t in self.turns[-3:]]
            parts.append(f"Últimas intenciones: {', '.join(set(recent_intents))}")
        return " | ".join(parts) if parts else "Nuevo contexto"
    
    def get_stats(self):
        return {
            'total_turns': len(self.turns),
            'max_turns': self.max_turns,
            'session_duration_min': (datetime.utcnow() - self.session_start).total_seconds() / 60,
            'user_facts': self.user_facts,
            'current_topic': self.current_topic
        }

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
            logger.error(f"Error búsqueda: {e}")
            return []

    @staticmethod
    def _search_fallback(query, max_results=5):
        try:
            url = f"https://html.duckduckgo.com/?q={urllib.parse.quote(query)}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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
            logger.error(f"Error fallback: {e}")
            return []

# ========== CLASE PRINCIPAL CIC_IA ==========

class CicIA:
    def __init__(self):
        self.learning_active = True
        self.web_search_engine = WebSearchEngine()
        self.current_learning_topic = None
        self._auto_learned_session = 0
        
        self.neural_engine = None
        self.feedback_collector = None
        self.curiosity_engine = None
        self.working_memory = None
        
        if V7_MODULES_AVAILABLE:
            try:
                self.neural_engine = CicNeuralEngine()
                self.feedback_collector = FeedbackCollector(db.session)
                self.curiosity_engine = CuriosityEngine(db.session, self.web_search_engine)
                self.working_memory = WorkingMemory(max_turns=15)
                logger.info("✅ Componentes avanzados inicializados")
            except Exception as e:
                logger.warning(f"⚠️ Error inicializando componentes avanzados: {e}")
                self._init_simple_components()
        else:
            self._init_simple_components()
        
        self.auto_learning_topics = [
            'física cuántica avances 2024', 'biología sintética descubrimientos',
            'neurociencia cognitiva', 'inteligencia artificial noticias 2024',
            'machine learning avances', 'computación cuántica progreso',
            'cambio climático soluciones', 'energía renovable tecnología',
            'desarrollo software arquitectura', 'ciberseguridad tendencias'
        ]

        with app.app_context():
            self.stats = {
                'memories': Memory.query.count(),
                'conversations': Conversation.query.count(),
                'today_learned': self._get_today_count(),
                'users': UserAccount.query.count()
            }

        self._start_background_threads()
        self._print_startup_message()

    def _init_simple_components(self):
        self.neural_engine = simple_neural
        self.working_memory = SimpleWorkingMemory(max_turns=15)
        logger.info("✅ Componentes simples inicializados (fallback)")

    def _print_startup_message(self):
        logger.info("=" * 70)
        logger.info("🚀 CIC_IA v7.2 - MODO DESARROLLO + USUARIO")
        logger.info(f"📚 Memorias: {self.stats['memories']}")
        logger.info(f"👥 Usuarios: {self.stats['users']}")
        logger.info(f"🧠 Auto-aprendizaje: ACTIVADO")
        logger.info(f"🔧 Módulos avanzados: {'SÍ' if V7_MODULES_AVAILABLE else 'NO (modo simple)'}")
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
                logger.warning(f"⚠️ Sin resultados para '{topic}'")
                return 0
            
            learned_count = 0
            for result in results:
                try:
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
                    logger.info(f"✅ Aprendido: {result['title'][:60]}")
                    
                except Exception as e:
                    logger.error(f"❌ Error: {e}")
                    db.session.rollback()
                    continue
            
            if learned_count > 0:
                today = date.today()
                log = LearningLog.query.filter_by(date=today).first()
                if not log:
                    log = LearningLog(date=today)
                    db.session.add(log)
                log.auto_learned += learned_count
                db.session.commit()
            
            return learned_count

    def _perform_nightly_training(self):
        logger.info("🌙 Reentrenamiento nocturno iniciado")

    def _get_today_count(self):
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        return log.count if log else 0

    def process_chat(self, user_input, mode='balanced', user_id=None):
        input_lower = user_input.lower().strip()
        
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_conversation(user_input, response, 'system_time', user_id=user_id)
        
        context_summary = ""
        if self.working_memory:
            context_summary = self.working_memory.get_context_summary()
        
        intent_info = {'intent': 'unknown', 'confidence': 0.0}
        if self.neural_engine:
            intent_info = self.neural_engine.predict_intent(user_input)
        
        if self.working_memory:
            entities = self._extract_entities(user_input)
            self.working_memory.add_turn(
                user_message=user_input,
                bot_response="",
                intent=intent_info['intent'],
                entities=entities
            )
        
        best_topic = self._find_best_topic(input_lower)
        
        with app.app_context():
            memories = Memory.query.all()
            relevant_memories = self._find_relevant_memories(user_input, memories, intent_info)
            
            response, sources = self._generate_response(
                user_input=user_input,
                best_topic=best_topic,
                relevant_memories=relevant_memories,
                intent_info=intent_info,
                mode=mode
            )
            
            if self.working_memory and self.working_memory.turns:
                if isinstance(self.working_memory.turns, list) and len(self.working_memory.turns) > 0:
                    self.working_memory.turns[-1]['bot'] = response
            
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
        
        if best_topic and best_topic != 'default':
            respuestas = KNOWLEDGE_BASE[best_topic]['respuestas']
            response = random.choice(respuestas)
            sources.append('knowledge_base')
        elif relevant_memories:
            mem = relevant_memories[0]
            response = f"Según mi conocimiento: {mem.content[:300]}"
            sources.append(f"memory_{mem.source}")
            mem.access_count += 1
            db.session.commit()
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
        
        if mode == 'fast':
            response = response.split('.')[0] + '.' if '.' in response else response[:100]
        
        return response, sources

    def _find_relevant_memories(self, query, memories, intent_info):
        if not memories:
            return []
        
        if (self.neural_engine and 
            hasattr(self.neural_engine, 'is_trained') and 
            getattr(self.neural_engine, 'is_trained', False) and 
            intent_info.get('confidence', 0) > 0.5):
            try:
                relevant = []
                for mem in memories:
                    relevance = self.neural_engine.predict_relevance(query, mem.content)
                    if relevance > 0.5:
                        relevant.append((mem, relevance))
                        mem.access_count += 1
                
                relevant.sort(key=lambda x: x[1], reverse=True)
                db.session.commit()
                return [mem for mem, _ in relevant[:5]]
            except:
                pass
        
        return self._keyword_memory_search(query, memories)

    def _keyword_memory_search(self, query, memories):
        query_words = set(query.lower().split())
        relevant = []
        
        for mem in memories:
            mem_words = set(mem.content.lower().split())
            overlap = len(query_words & mem_words)
            if overlap >= 2:
                relevant.append(mem)
                mem.access_count += 1
        
        db.session.commit()
        return relevant

    def _search_and_learn(self, query):
        try:
            with app.app_context():
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
                    
                    memory = Memory(
                        content=result['snippet'],
                        source='web_search',
                        topic=query,
                        relevance_score=0.7,
                        confidence_score=0.6
                    )
                    db.session.add(memory)
                
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
            )
            db.session.add(conv)
            db.session.flush()
            db.session.commit()
            
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            if not log:
                log = LearningLog(date=today)
                db.session.add(log)
            log.count += 1
            db.session.commit()
            
            total_mem = Memory.query.count()
        
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
        logger.info(f"🎯 Forzando aprendizaje: '{topic}'")
        count = self._perform_auto_learning(custom_topic=topic)
        return {'success': True, 'topic': topic, 'learned_count': count}

    def get_learning_stats(self):
        with app.app_context():
            return {
                'total_memories': Memory.query.count(),
                'by_source': {
                    'auto_learning': Memory.query.filter_by(source='auto_learning').count(),
                    'web_search': Memory.query.filter_by(source='web_search').count(),
                    'curiosity': Memory.query.filter_by(source='curiosity').count(),
                    'manual_learning': Memory.query.filter_by(source='manual_learning').count(),
                },
                'feedback': {'total': FeedbackLog.query.count()},
                'curiosity': {
                    'pending': CuriosityGap.query.filter_by(status='pending').count(),
                    'learned': CuriosityGap.query.filter_by(status='learned').count(),
                },
                'users': UserAccount.query.count(),
                'version': '7.2'
            }

cic_ia = CicIA()

# ========== DECORADORES ==========

def dev_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('dev_mode') and session.get('dev_username') == DEV_USERNAME:
            return f(*args, **kwargs)
        if request.headers.get('X-Dev-Token') == 'dev-token-12345':
            return f(*args, **kwargs)
        return jsonify({'error': 'No autorizado - Modo desarrollador requerido'}), 401
    return decorated_function

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'No autenticado'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ========== RUTAS ==========

@app.route('/')
def index():
    if session.get('dev_mode'):
        return redirect(url_for('dev_dashboard'))
    if 'user_id' in session:
        return redirect(url_for('chat_page'))
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
        else:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
        
        user = UserAccount.query.filter_by(username=username, is_active=True).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'redirect': '/chat'})
            return redirect(url_for('chat_page'))
        
        error = 'Credenciales inválidas'
        if request.is_json:
            return jsonify({'success': False, 'error': error}), 401
        
        # CORREGIDO: Usar render_template_string con comillas triples
        return render_template_string(LOGIN_TEMPLATE, error=error)
    
    # GET
    return render_template_string(LOGIN_TEMPLATE, error=None)

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        errors = []
        if len(username) < 3:
            errors.append('Usuario mínimo 3 caracteres')
        if len(password) < 6:
            errors.append('Contraseña mínimo 6 caracteres')
        if '@' not in email:
            errors.append('Email inválido')
        
        if errors:
            return render_template_string(REGISTER_TEMPLATE, error=' | '.join(errors))
        
        if UserAccount.query.filter_by(username=username).first():
            return render_template_string(REGISTER_TEMPLATE, error='Usuario ya existe')
        
        if UserAccount.query.filter_by(email=email).first():
            return render_template_string(REGISTER_TEMPLATE, error='Email ya registrado')
        
        try:
            user = UserAccount(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login_page', registered='true'))
        except Exception as e:
            db.session.rollback()
            return render_template_string(REGISTER_TEMPLATE, error=f'Error: {str(e)}')
    
    return render_template_string(REGISTER_TEMPLATE, error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/dev-login', methods=['GET', 'POST'])
def dev_login_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == DEV_USERNAME and password == DEV_PASSWORD:
            session['dev_mode'] = True
            session['dev_username'] = DEV_USERNAME
            session.permanent = True
            return redirect(url_for('dev_dashboard'))
        
        return render_template_string(DEV_LOGIN_TEMPLATE, error='Credenciales inválidas')
    
    return render_template_string(DEV_LOGIN_TEMPLATE, error=None)

@app.route('/dev-logout')
def dev_logout():
    session.pop('dev_mode', None)
    session.pop('dev_username', None)
    return redirect(url_for('index'))

@app.route('/chat')
@login_required
def chat_page():
    return render_template_string(CHAT_TEMPLATE, 
                                username=session.get('username'),
                                is_dev=session.get('dev_mode', False))

@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400
            
        message = data.get('message', '').strip()
        mode = data.get('mode', 'balanced')
        
        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        user_id = session.get('user_id')
        result = cic_ia.process_chat(message, mode=mode, user_id=user_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error en /api/chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def api_status():
    try:
        stats = cic_ia.get_learning_stats()
        today = date.today()
        
        log = LearningLog.query.filter_by(date=today).first()
        today_count = log.count if log else 0
        today_auto = log.auto_learned if log else 0
        
        return jsonify({
            'stage': 'v7.2',
            'total_memories': stats.get('total_memories', 0),
            'today_conversations': today_count,
            'today_auto_learned': today_auto,
            'total_users': stats.get('users', 0),
            'v7_modules_available': V7_MODULES_AVAILABLE,
            'features': ['chat', 'web_search', 'auto_learning', 'memory', 'user_accounts', 'dev_mode']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '7.2.0'
    })

@app.route('/dev')
@dev_required
def dev_dashboard():
    return render_template_string(DEV_DASHBOARD_TEMPLATE)

@app.route('/api/dev/stats')
@dev_required
def dev_stats():
    try:
        stats = cic_ia.get_learning_stats()
        
        recent_memories = Memory.query.order_by(Memory.created_at.desc()).limit(10).all()
        recent_conversations = Conversation.query.order_by(Conversation.timestamp.desc()).limit(10).all()
        
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
                'created_at': m.created_at.isoformat() if m.created_at else None,
                'preview': m.content[:100] if m.content else ''
            } for m in recent_memories],
            'recent_conversations': [{
                'id': c.id,
                'user_message': c.user_message[:50] if c.user_message else '',
                'intent': c.intent_detected,
                'timestamp': c.timestamp.isoformat() if c.timestamp else None
            } for c in recent_conversations],
            'working_memory': stats.get('working_memory', {})
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/force-learn', methods=['POST'])
@dev_required
def dev_force_learn():
    try:
        data = request.get_json()
        topic = data.get('topic', '').strip() if data else ''
        if not topic:
            return jsonify({'error': 'Tema requerido'}), 400
        
        result = cic_ia.force_learn(topic)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/memories')
@dev_required
def dev_memories():
    try:
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
                'created_at': m.created_at.isoformat() if m.created_at else None
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

@app.route('/api/dev/users')
@dev_required
def dev_users():
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
    try:
        data = request.get_json()
        mode = data.get('mode', 'dev') if data else 'dev'
        
        if mode == 'user':
            session.pop('dev_mode', None)
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
                'message': 'Modo usuario activado',
                'redirect': '/chat'
            })
        else:
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
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint no encontrado'}), 404
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    logger.error(f"Error 500: {error}")
    return jsonify({'error': 'Error interno del servidor', 'detail': str(error)}), 500

# ========== TEMPLATES INLINE ==========

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cic_IA - Iniciar Sesión</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
        }
        .logo { text-align: center; margin-bottom: 30px; }
        .logo h1 { font-size: 2.5em; color: #667eea; }
        .logo p { color: #888; margin-top: 5px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #333; font-weight: 500; }
        input[type="text"], input[type="password"] {
            width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0;
            border-radius: 10px; font-size: 16px; transition: border-color 0.3s;
        }
        input:focus { outline: none; border-color: #667eea; }
        .btn {
            width: 100%; padding: 14px; background: #667eea; color: white;
            border: none; border-radius: 10px; font-size: 16px; font-weight: 600;
            cursor: pointer; transition: transform 0.2s;
        }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4); }
        .error {
            background: #ffebee; color: #c62828; padding: 12px;
            border-radius: 8px; margin-bottom: 20px; font-size: 14px;
        }
        .links { text-align: center; margin-top: 20px; color: #666; }
        .links a { color: #667eea; text-decoration: none; }
        .dev-link {
            position: fixed; bottom: 20px; right: 20px;
            color: rgba(255,255,255,0.7); text-decoration: none; font-size: 12px;
        }
        .dev-link:hover { color: white; }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">
            <h1>🧠 Cic_IA</h1>
            <p>Asistente Inteligente Evolutivo</p>
        </div>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="username">Usuario</label>
                <input type="text" id="username" name="username" required placeholder="Tu nombre de usuario">
            </div>
            <div class="form-group">
                <label for="password">Contraseña</label>
                <input type="password" id="password" name="password" required placeholder="Tu contraseña">
            </div>
            <button type="submit" class="btn">Iniciar Sesión</button>
        </form>
        <div class="links">
            <p>¿No tienes cuenta? <a href="/register">Regístrate</a></p>
        </div>
    </div>
    <a href="/dev-login" class="dev-link">Modo Desarrollador →</a>
</body>
</html>
'''

REGISTER_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cic_IA - Registro</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .register-container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
        }
        .logo { text-align: center; margin-bottom: 30px; }
        .logo h1 { font-size: 2.5em; color: #667eea; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #333; font-weight: 500; }
        input[type="text"], input[type="email"], input[type="password"] {
            width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0;
            border-radius: 10px; font-size: 16px;
        }
        input:focus { outline: none; border-color: #667eea; }
        .btn {
            width: 100%; padding: 14px; background: #667eea; color: white;
            border: none; border-radius: 10px; font-size: 16px; font-weight: 600;
            cursor: pointer;
        }
        .error {
            background: #ffebee; color: #c62828; padding: 12px;
            border-radius: 8px; margin-bottom: 20px;
        }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #667eea; text-decoration: none; }
    </style>
</head>
<body>
    <div class="register-container">
        <div class="logo">
            <h1>🧠 Cic_IA</h1>
            <p>Crear nueva cuenta</p>
        </div>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST" action="/register">
            <div class="form-group">
                <label for="username">Usuario *</label>
                <input type="text" id="username" name="username" required minlength="3" placeholder="Mínimo 3 caracteres">
            </div>
            <div class="form-group">
                <label for="email">Email *</label>
                <input type="email" id="email" name="email" required placeholder="tu@email.com">
            </div>
            <div class="form-group">
                <label for="password">Contraseña *</label>
                <input type="password" id="password" name="password" required minlength="6" placeholder="Mínimo 6 caracteres">
            </div>
            <button type="submit" class="btn">Crear Cuenta</button>
        </form>
        <div class="links">
            <p>¿Ya tienes cuenta? <a href="/login">Inicia sesión</a></p>
        </div>
    </div>
</body>
</html>
'''

DEV_LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cic_IA - Modo Desarrollador</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .dev-container {
            background: #0f3460;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            width: 100%;
            max-width: 400px;
            border: 2px solid #e94560;
        }
        .dev-badge { text-align: center; margin-bottom: 30px; }
        .dev-badge h1 { font-size: 2em; color: #e94560; }
        .dev-badge p { color: #eaeaea; margin-top: 10px; font-family: monospace; }
        .warning {
            background: rgba(233, 69, 96, 0.2);
            border: 1px solid #e94560;
            color: #eaeaea;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-size: 13px;
        }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #eaeaea; font-weight: 500; }
        input[type="text"], input[type="password"] {
            width: 100%; padding: 12px 15px;
            background: #1a1a2e; border: 2px solid #16213e;
            border-radius: 10px; font-size: 16px; color: #eaeaea;
        }
        input:focus { outline: none; border-color: #e94560; }
        .btn {
            width: 100%; padding: 14px; background: #e94560; color: white;
            border: none; border-radius: 10px; font-size: 16px;
            font-weight: 600; cursor: pointer; text-transform: uppercase;
        }
        .error {
            background: rgba(255, 0, 0, 0.2);
            color: #ff6b6b;
            padding: 12px; border-radius: 8px;
            margin-bottom: 20px;
        }
        .back-link { text-align: center; margin-top: 20px; }
        .back-link a { color: #eaeaea; text-decoration: none; font-size: 14px; }
    </style>
</head>
<body>
    <div class="dev-container">
        <div class="dev-badge">
            <h1>⚡ DEV MODE</h1>
            <p>Cic_IA v7.2 - Panel de Control</p>
        </div>
        <div class="warning">
            ⚠️ Acceso restringido. Este modo permite forzar aprendizaje, 
            ver memorias, eliminar datos y simular usuarios.
        </div>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST" action="/dev-login">
            <div class="form-group">
                <label for="username">Usuario Dev</label>
                <input type="text" id="username" name="username" required placeholder="admin">
            </div>
            <div class="form-group">
                <label for="password">Contraseña</label>
                <input type="password" id="password" name="password" required placeholder="••••••••">
            </div>
            <button type="submit" class="btn">Acceder al Sistema</button>
        </form>
        <div class="back-link">
            <a href="/login">← Volver a login normal</a>
        </div>
    </div>
</body>
</html>
'''

CHAT_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cic_IA - Chat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f7fa;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: white;
            padding: 15px 25px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header-left { display: flex; align-items: center; gap: 15px; }
        .header h1 { font-size: 1.5em; color: #667eea; }
        .user-badge {
            background: #667eea;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
        }
        .header-right { display: flex; gap: 10px; align-items: center; }
        .mode-badge {
            background: #e8f5e9;
            color: #2e7d32;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 12px;
        }
        .mode-badge.dev { background: #ffebee; color: #c62828; }
        .btn-small {
            padding: 8px 15px;
            border-radius: 8px;
            text-decoration: none;
            font-size: 13px;
        }
        .btn-dev { background: #667eea; color: white; }
        .btn-logout { background: #f5f5f5; color: #666; }
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            max-width: 900px;
            margin: 0 auto;
            width: 100%;
        }
        .message {
            margin-bottom: 20px;
            max-width: 80%;
        }
        .message.user { margin-left: auto; }
        .message-bubble {
            padding: 15px 20px;
            border-radius: 20px;
            line-height: 1.6;
        }
        .message.user .message-bubble {
            background: #667eea;
            color: white;
            border-bottom-right-radius: 5px;
        }
        .message.bot .message-bubble {
            background: white;
            color: #333;
            border-bottom-left-radius: 5px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .message-meta {
            font-size: 12px;
            color: #888;
            margin-top: 5px;
            padding: 0 10px;
        }
        .input-area {
            background: white;
            padding: 20px;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
        }
        .input-container {
            max-width: 900px;
            margin: 0 auto;
            display: flex;
            gap: 10px;
        }
        #message-input {
            flex: 1;
            padding: 15px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 30px;
            font-size: 16px;
            outline: none;
        }
        #message-input:focus { border-color: #667eea; }
        #send-btn {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            border: none;
            background: #667eea;
            color: white;
            font-size: 20px;
            cursor: pointer;
        }
        #send-btn:disabled { background: #ccc; }
        .typing {
            display: none;
            align-items: center;
            gap: 5px;
            padding: 15px 20px;
            color: #888;
        }
        .typing.active { display: flex; }
        .welcome {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        .welcome h2 { color: #667eea; margin-bottom: 10px; }
        .suggestions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: center;
            margin-top: 20px;
        }
        .suggestion {
            background: white;
            border: 1px solid #e0e0e0;
            padding: 10px 20px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
        }
        .suggestion:hover {
            border-color: #667eea;
            color: #667eea;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>🧠 Cic_IA</h1>
            <span class="user-badge">@{{ username }}</span>
        </div>
        <div class="header-right">
            {% if is_dev %}
            <span class="mode-badge dev">🔴 DEV MODE</span>
            <a href="/dev" class="btn-small btn-dev">Panel Dev</a>
            {% endif %}
            <a href="/logout" class="btn-small btn-logout">Salir</a>
        </div>
    </div>
    
    <div class="chat-container" id="chat-container">
        <div class="welcome">
            <h2>¡Hola, {{ username }}! 👋</h2>
            <p>Soy Cic_IA, tu asistente que aprende contigo.</p>
            <div class="suggestions">
                <span class="suggestion" onclick="sendSuggestion('¿Qué es la inteligencia artificial?')">¿Qué es la IA?</span>
                <span class="suggestion" onclick="sendSuggestion('Explícame física cuántica')">Física cuántica</span>
                <span class="suggestion" onclick="sendSuggestion('Me llamo {{ username }}')">Presentarme</span>
            </div>
        </div>
    </div>
    
    <div class="typing" id="typing">
        <span>Cic_IA está escribiendo...</span>
    </div>
    
    <div class="input-area">
        <div class="input-container">
            <input type="text" id="message-input" placeholder="Escribe tu mensaje..." maxlength="500">
            <button id="send-btn" onclick="sendMessage()">➤</button>
        </div>
    </div>

    <script>
        const chatContainer = document.getElementById('chat-container');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const typing = document.getElementById('typing');
        
        function addMessage(text, isUser = false) {
            const welcome = document.querySelector('.welcome');
            if (welcome) welcome.remove();
            
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;
            
            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            bubble.textContent = text;
            
            const meta = document.createElement('div');
            meta.className = 'message-meta';
            meta.textContent = new Date().toLocaleTimeString();
            
            messageDiv.appendChild(bubble);
            messageDiv.appendChild(meta);
            chatContainer.appendChild(messageDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function showTyping() {
            typing.classList.add('active');
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function hideTyping() {
            typing.classList.remove('active');
        }
        
        async function sendMessage() {
            const text = messageInput.value.trim();
            if (!text) return;
            
            addMessage(text, true);
            messageInput.value = '';
            sendBtn.disabled = true;
            showTyping();
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, mode: 'balanced' })
                });
                
                const data = await response.json();
                hideTyping();
                
                if (data.error) {
                    addMessage('❌ Error: ' + data.error);
                } else {
                    addMessage(data.response);
                }
            } catch (e) {
                hideTyping();
                addMessage('❌ Error de conexión');
            }
            
            sendBtn.disabled = false;
            messageInput.focus();
        }
        
        function sendSuggestion(text) {
            messageInput.value = text;
            sendMessage();
        }
        
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
        
        messageInput.focus();
    </script>
</body>
</html>
'''

DEV_DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cic_IA - Panel de Desarrollador</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
        }
        .dev-header {
            background: #1e293b;
            padding: 20px 30px;
            border-bottom: 2px solid #e94560;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .dev-header h1 { color: #e94560; font-size: 1.8em; display: flex; align-items: center; gap: 10px; }
        .dev-nav { display: flex; gap: 15px; }
        .dev-nav a, .dev-nav button {
            background: #334155; color: #e2e8f0; border: none;
            padding: 10px 20px; border-radius: 8px;
            text-decoration: none; cursor: pointer; font-size: 14px;
        }
        .dev-nav a:hover, .dev-nav button:hover { background: #e94560; }
        .container { max-width: 1400px; margin: 0 auto; padding: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 25px; }
        .card {
            background: #1e293b;
            border-radius: 16px;
            padding: 25px;
            border: 1px solid #334155;
        }
        .card h2 { color: #e94560; margin-bottom: 20px; font-size: 1.3em; }
        .stat-value { font-size: 3em; font-weight: bold; color: #60a5fa; }
        .stat-label { color: #94a3b8; margin-top: 5px; }
        .btn-action {
            width: 100%; padding: 15px; background: #059669; color: white;
            border: none; border-radius: 10px; font-size: 16px;
            cursor: pointer; margin-bottom: 10px;
        }
        .btn-action:hover { background: #047857; }
        .btn-danger { background: #dc2626; }
        .btn-danger:hover { background: #b91c1c; }
        .input-group { margin-bottom: 15px; }
        .input-group label { display: block; margin-bottom: 8px; color: #94a3b8; font-size: 14px; }
        .input-group input {
            width: 100%; padding: 12px; background: #0f172a;
            border: 1px solid #334155; border-radius: 8px;
            color: #e2e8f0; font-size: 14px;
        }
        .memory-list { max-height: 400px; overflow-y: auto; }
        .memory-item {
            background: #0f172a;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 10px;
            border-left: 4px solid #60a5fa;
        }
        .memory-item.auto_learning { border-color: #4ade80; }
        .memory-item.web_search { border-color: #60a5fa; }
        .memory-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
        .memory-topic { font-weight: 600; color: #e2e8f0; }
        .memory-source { font-size: 12px; padding: 3px 10px; border-radius: 20px; background: #334155; }
        .memory-content { color: #94a3b8; font-size: 13px; line-height: 1.5; }
        .memory-meta { display: flex; gap: 15px; margin-top: 10px; font-size: 12px; color: #64748b; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab {
            padding: 10px 20px; background: #334155;
            border: none; border-radius: 8px;
            color: #e2e8f0; cursor: pointer;
        }
        .tab.active { background: #e94560; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .result-box {
            background: #0f172a;
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
            border-left: 4px solid #4ade80;
        }
        .result-box.error { border-color: #dc2626; }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #334155;
            border-top-color: #e94560;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #e94560; font-weight: 600; }
        tr:hover { background: #0f172a; }
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
        }
        .badge.success { background: #059669; color: white; }
        .badge.warning { background: #d97706; color: white; }
    </style>
</head>
<body>
    <header class="dev-header">
        <h1><span>⚡</span> Cic_IA v7.2 - Panel de Desarrollador</h1>
        <nav class="dev-nav">
            <button onclick="toggleMode()" id="mode-btn">🔄 Modo Usuario</button>
            <a href="/chat">💬 Ir al Chat</a>
            <a href="/dev-logout" style="background: #dc2626;">🚪 Salir Dev</a>
        </nav>
    </header>
    
    <div class="container">
        <div class="tabs">
            <button class="tab active" onclick="showTab('overview')">📊 Resumen</button>
            <button class="tab" onclick="showTab('learning')">🧠 Aprendizaje</button>
            <button class="tab" onclick="showTab('memories')">💾 Memorias</button>
            <button class="tab" onclick="showTab('users')">👥 Usuarios</button>
        </div>
        
        <div id="tab-overview" class="tab-content active">
            <div class="grid">
                <div class="card">
                    <h2>📚 Memorias</h2>
                    <div class="stat-value" id="stat-memories">-</div>
                    <div class="stat-label">Total en base de datos</div>
                </div>
                <div class="card">
                    <h2>💬 Conversaciones Hoy</h2>
                    <div class="stat-value" id="stat-conversations">-</div>
                    <div class="stat-label">Interacciones registradas</div>
                </div>
                <div class="card">
                    <h2>🤖 Auto-Aprendizaje</h2>
                    <div class="stat-value" id="stat-auto">-</div>
                    <div class="stat-label">Elementos aprendidos hoy</div>
                </div>
                <div class="card">
                    <h2>👥 Usuarios</h2>
                    <div class="stat-value" id="stat-users">-</div>
                    <div class="stat-label">Cuentas registradas</div>
                </div>
            </div>
        </div>
        
        <div id="tab-learning" class="tab-content">
            <div class="grid">
                <div class="card">
                    <h2>🎯 Forzar Aprendizaje</h2>
                    <div class="input-group">
                        <label>Tema a aprender</label>
                        <input type="text" id="learn-topic" placeholder="Ej: inteligencia artificial 2024">
                    </div>
                    <button class="btn-action" onclick="forceLearn()">🚀 Iniciar Aprendizaje</button>
                    <div id="learn-result"></div>
                </div>
                <div class="card">
                    <h2>📈 Estadísticas por Fuente</h2>
                    <div id="source-stats"><div class="loading"></div></div>
                </div>
                <div class="card">
                    <h2>🔍 Curiosidad Engine</h2>
                    <div id="curiosity-stats">
                        <p>Pendientes: <span class="badge warning" id="curiosity-pending">-</span></p>
                        <p style="margin-top: 10px;">Aprendidas: <span class="badge success" id="curiosity-learned">-</span></p>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="tab-memories" class="tab-content">
            <div class="card">
                <h2>💾 Todas las Memorias</h2>
                <div class="input-group">
                    <input type="text" id="memory-search" placeholder="🔍 Buscar en memorias..." onkeyup="searchMemories(this.value)">
                </div>
                <div class="memory-list" id="memory-list"><div class="loading"></div></div>
                <div style="margin-top: 15px; display: flex; gap: 10px;">
                    <button class="btn-action" onclick="loadMemories()">🔄 Actualizar</button>
                    <button class="btn-action btn-danger" onclick="deleteAllMemories()">⚠️ Eliminar Todo</button>
                </div>
            </div>
        </div>
        
        <div id="tab-users" class="tab-content">
            <div class="card">
                <h2>👥 Usuarios Registrados</h2>
                <div id="users-list"><div class="loading"></div></div>
            </div>
        </div>
    </div>

    <script>
        let memories = [];
        
        document.addEventListener('DOMContentLoaded', () => {
            loadStats();
            loadMemories();
            loadUsers();
            setInterval(loadStats, 10000);
        });
        
        function showTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(`tab-${tabName}`).classList.add('active');
            if (tabName === 'memories') loadMemories();
            if (tabName === 'users') loadUsers();
        }
        
        async function loadStats() {
            try {
                const res = await fetch('/api/dev/stats');
                const data = await res.json();
                if (data.error) return;
                
                document.getElementById('stat-memories').textContent = data.learning?.total_memories || 0;
                document.getElementById('stat-users').textContent = data.learning?.users || 0;
                document.getElementById('stat-conversations').textContent = data.recent_conversations?.length || 0;
                
                const todayLearned = data.recent_memories?.filter(m => {
                    const date = new Date(m.created_at);
                    const today = new Date();
                    return date.toDateString() === today.toDateString();
                }).length || 0;
                document.getElementById('stat-auto').textContent = todayLearned;
                
                if (data.learning?.curiosity) {
                    document.getElementById('curiosity-pending').textContent = data.learning.curiosity.pending;
                    document.getElementById('curiosity-learned').textContent = data.learning.curiosity.learned;
                }
                
                if (data.learning?.by_source) {
                    const s = data.learning.by_source;
                    document.getElementById('source-stats').innerHTML = `
                        <div style="display: grid; gap: 10px;">
                            <div>🤖 Auto: <strong>${s.auto_learning || 0}</strong></div>
                            <div>🌐 Web: <strong>${s.web_search || 0}</strong></div>
                            <div>🔍 Curiosidad: <strong>${s.curiosity || 0}</strong></div>
                        </div>
                    `;
                }
            } catch (e) {
                console.error('Error cargando stats:', e);
            }
        }
        
        async function forceLearn() {
            const topic = document.getElementById('learn-topic').value.trim();
            if (!topic) return alert('Ingresa un tema');
            
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Aprendiendo...';
            
            try {
                const res = await fetch('/api/dev/force-learn', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ topic })
                });
                
                const data = await res.json();
                const resultDiv = document.getElementById('learn-result');
                
                if (data.success) {
                    resultDiv.innerHTML = `<div class="result-box">✅ <strong>Éxito!</strong><br>Tema: ${data.topic}<br>Elementos: ${data.learned_count}</div>`;
                    loadStats();
                    loadMemories();
                } else {
                    resultDiv.innerHTML = `<div class="result-box error">❌ ${data.error}</div>`;
                }
            } catch (e) {
                document.getElementById('learn-result').innerHTML = `<div class="result-box error">Error: ${e.message}</div>`;
            }
            
            btn.disabled = false;
            btn.textContent = '🚀 Iniciar Aprendizaje';
        }
        
        async function loadMemories() {
            try {
                const res = await fetch('/api/dev/memories?page=1&per_page=50');
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                
                memories = data.memories || [];
                renderMemories(memories);
            } catch (e) {
                document.getElementById('memory-list').innerHTML = `<p style="color: #f87171;">Error: ${e.message}</p>`;
            }
        }
        
        function renderMemories(list) {
            const container = document.getElementById('memory-list');
            if (list.length === 0) {
                container.innerHTML = '<p style="color: #64748b; text-align: center; padding: 40px;">No hay memorias</p>';
                return;
            }
            
            container.innerHTML = list.map(m => `
                <div class="memory-item ${m.source}">
                    <div class="memory-header">
                        <span class="memory-topic">${m.topic || 'Sin tema'}</span>
                        <span class="memory-source">${m.source}</span>
                    </div>
                    <div class="memory-content">${m.content?.substring(0, 200) || ''}...</div>
                    <div class="memory-meta">
                        <span>📅 ${new Date(m.created_at).toLocaleString()}</span>
                        <span>⭐ ${m.relevance_score?.toFixed(2) || '-'}</span>
                        <span>👁️ ${m.access_count || 0}</span>
                    </div>
                    <div style="margin-top: 10px;">
                        <button onclick="deleteMemory(${m.id})" style="background: #dc2626; color: white; border: none; padding: 5px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">🗑️ Eliminar</button>
                    </div>
                </div>
            `).join('');
        }
        
        function searchMemories(query) {
            if (!query) {
                renderMemories(memories);
                return;
            }
            const filtered = memories.filter(m => 
                (m.topic || '').toLowerCase().includes(query.toLowerCase()) ||
                (m.content || '').toLowerCase().includes(query.toLowerCase())
            );
            renderMemories(filtered);
        }
        
        async function deleteMemory(id) {
            if (!confirm(`¿Eliminar memoria ${id}?`)) return;
            try {
                const res = await fetch(`/api/dev/memories/${id}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    loadMemories();
                    loadStats();
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function deleteAllMemories() {
            if (!confirm('⚠️ ¿ELIMINAR TODAS LAS MEMORIAS?')) return;
            if (prompt('Escribe "ELIMINAR" para confirmar:') !== 'ELIMINAR') return;
            
            let deleted = 0;
            for (const m of [...memories]) {
                try {
                    await fetch(`/api/dev/memories/${m.id}`, { method: 'DELETE' });
                    deleted++;
                } catch (e) {}
            }
            alert(`Eliminadas ${deleted} memorias`);
            loadMemories();
            loadStats();
        }
        
        async function loadUsers() {
            try {
                const res = await fetch('/api/dev/users');
                const data = await res.json();
                const container = document.getElementById('users-list');
                
                if (data.error || !data.users) {
                    container.innerHTML = `<p style="color: #f87171;">${data.error || 'Sin datos'}</p>`;
                    return;
                }
                
                container.innerHTML = `
                    <table>
                        <thead>
                            <tr><th>ID</th><th>Usuario</th><th>Email</th><th>Registro</th><th>Último Login</th></tr>
                        </thead>
                        <tbody>
                            ${data.users.map(u => `
                                <tr>
                                    <td>${u.id}</td>
                                    <td><strong>${u.username}</strong></td>
                                    <td>${u.email}</td>
                                    <td>${new Date(u.created_at).toLocaleDateString()}</td>
                                    <td>${u.last_login ? new Date(u.last_login).toLocaleString() : 'Nunca'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                    <p style="margin-top: 15px; color: #64748b;">Total: ${data.count} usuarios</p>
                `;
            } catch (e) {
                document.getElementById('users-list').innerHTML = `<p style="color: #f87171;">Error: ${e.message}</p>`;
            }
        }
        
        async function toggleMode() {
            const btn = document.getElementById('mode-btn');
            const isUserMode = btn.textContent.includes('Usuario');
            
            try {
                const res = await fetch('/api/dev/toggle-mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode: isUserMode ? 'user' : 'dev' })
                });
                
                const data = await res.json();
                if (data.success) {
                    window.location.href = data.redirect;
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
    </script>
</body>
</html>
'''

# ========== INICIALIZACIÓN FINAL ==========

application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
    @app.route('/create-emergency-admin')
def create_emergency_admin():
    """Crear admin de emergencia - eliminar después de usar"""
    try:
        # Crear en ambas tablas
        admin_user = UserAccount.query.filter_by(username='emergency').first()
        if not admin_user:
            admin_user = UserAccount(
                username='emergency',
                email='emergency@dev.local',
                personality_mode='kimi'
            )
            admin_user.set_password('Emergency123!')
            db.session.add(admin_user)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Usuario de emergencia creado',
                'credentials': {
                    'username': 'emergency',
                    'password': 'Emergency123!'
                },
                'note': 'Usar en /login (no /dev-login)'
            })
        else:
            return jsonify({
                'message': 'Usuario emergency ya existe',
                'credentials': {
                    'username': 'emergency',
                    'password': 'Emergency123!'
                }
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
