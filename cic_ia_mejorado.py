"""
Cic_IA v7.0 - Asistente Inteligente EVOLUTIVO
Versión mejorada con Auto-Aprendizaje, Feedback y Curiosidad
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
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
from sqlalchemy import select
import requests
from bs4 import BeautifulSoup
import hashlib

# NUEVOS IMPORTS (tus archivos creados)
from models import db, init_database, Memory, Conversation, LearningLog, FeedbackLog
from models import CuriosityGap, TrainingBatch, DeveloperSession, WebSearchCache
from models import KnowledgeEvolution, ManualLearningQueue, WorkingMemorySnapshot
from neural_engine import CicNeuralEngine
from feedback_system import SatisfactionDetector, FeedbackCollector
from curiosity_engine import CuriosityEngine, ConceptExtractor
from working_memory import WorkingMemory

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('cic_ia_mejorado')

# ========== INICIALIZACIÓN FLASK ==========

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cic-ia-secret-2024-v7')

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

DEV_USERNAME = os.environ.get('DEV_USERNAME', 'admin')
DEV_PASSWORD = os.environ.get('DEV_PASSWORD', 'CicDev2024!')

# Inicializar DB desde models.py
init_database(app)

# ========== KNOWLEDGE BASE ==========

KNOWLEDGE_BASE = {
    'ia': {
        'respuestas': [
            "La Inteligencia Artificial (IA) es la simulación de procesos de inteligencia humana por sistemas informáticos. Incluye aprendizaje automático, razonamiento y resolución de problemas.",
            "La IA permite a las máquinas aprender, razonar y resolver problemas de manera autónoma. Ramas principales: Machine Learning, Deep Learning, NLP y Visión por Computadora."
        ],
        'keywords': ['inteligencia artificial', 'machine learning', 'deep learning', 'neural network', 'red neuronal', 'algoritmo ia', 'aprendizaje automatico', 'aprendizaje automático']
    },
    'python': {
        'respuestas': [
            "Python es el lenguaje líder en IA por su sintaxis clara y bibliotecas como TensorFlow, PyTorch y scikit-learn.",
            "Python fue creado por Guido van Rossum. Es ideal para prototipado rápido, ciencia de datos y desarrollo web con Flask/Django."
        ],
        'keywords': ['python', 'programacion', 'programación', 'codigo', 'código', 'desarrollo', 'flask', 'django']
    },
    'hola': {
        'respuestas': [
            "¡Hola! Soy Cic_IA v7.0, tu asistente con auto-aprendizaje. ¿En qué puedo ayudarte?",
            "¡Bienvenido! Estoy aprendiendo continuamente para servirte mejor."
        ],
        'keywords': ['hola', 'buenas', 'hey ', 'saludos', 'buenos dias', 'buenos días', 'buenas tardes', 'buenas noches', 'hi ']
    },
    'cic_ia': {
        'respuestas': [
            "Soy Cic_IA v7.0, una inteligencia artificial evolutiva con red neuronal integrada. Aprendo automáticamente cada 2 horas y me reentreno con feedback.",
            "Cic_IA v7.0 es un asistente IA evolutivo que aprende de internet, memoriza conversaciones, detecta curiosidades y mejora sus respuestas continuamente."
        ],
        'keywords': ['quien eres', 'quién eres', 'que eres', 'qué eres', 'cic_ia', 'tu nombre', 'presentacion', 'como te llamas', 'cómo te llamas', 'version', 'versión']
    },
    'clima': {
        'respuestas': [
            "El clima es el conjunto de condiciones atmosféricas que caracterizan una región durante un período prolongado.",
            "El clima se diferencia del tiempo meteorológico: el tiempo describe lo que ocurre hoy, mientras que el clima es el patrón promedio a largo plazo."
        ],
        'keywords': ['clima', 'tiempo', 'meteorologia', 'meteorología', 'temperatura', 'lluvia', 'sol', 'nube', 'viento', 'atmosfera', 'atmosférica', 'calor', 'frio', 'frío']
    },
    'matematicas': {
        'respuestas': [
            "Las matemáticas son la ciencia del número, la cantidad, el espacio y el cambio. Son la base de la ciencia y la ingeniería.",
            "Las matemáticas incluyen álgebra, geometría, cálculo, estadística, probabilidad y muchas otras ramas."
        ],
        'keywords': ['matematicas', 'matemáticas', 'matematica', 'algebra', 'calculo', 'geometria', 'numero', 'suma', 'resta', 'multiplicacion', 'division', 'ecuacion']
    },
    'historia': {
        'respuestas': [
            "La historia es el estudio del pasado humano, sus civilizaciones, culturas y eventos que han moldeado el mundo actual.",
            "La historia nos permite comprender el presente y aprender de los errores y logros del pasado."
        ],
        'keywords': ['historia', 'pasado', 'civilizacion', 'civilización', 'antiguo', 'guerra', 'revolucion', 'cultura', 'siglo', 'historico', 'histórico']
    },
    'ciencia': {
        'respuestas': [
            "La ciencia es el conjunto de conocimientos obtenidos mediante la observación y el razonamiento sistemático.",
            "La ciencia utiliza el método científico para generar hipótesis, experimentos y teorías que explican el universo."
        ],
        'keywords': ['ciencia', 'fisica', 'física', 'quimica', 'química', 'biologia', 'biología', 'cientifico', 'científico', 'experimento', 'laboratorio', 'teoria', 'teoría']
    },
    'salud': {
        'respuestas': [
            "La salud es un estado de completo bienestar físico, mental y social, no solamente la ausencia de enfermedad.",
            "Mantener una buena salud requiere alimentación balanceada, ejercicio regular, sueño adecuado y manejo del estrés."
        ],
        'keywords': ['salud', 'medicina', 'enfermedad', 'doctor', 'medico', 'médico', 'hospital', 'sintoma', 'síntoma', 'cuerpo', 'bienestar', 'cura', 'tratamiento']
    },
    'tecnologia': {
        'respuestas': [
            "La tecnología es el conjunto de conocimientos técnicos que permiten diseñar y crear soluciones para satisfacer necesidades humanas.",
            "La tecnología avanza exponencialmente, transformando comunicaciones, transporte, medicina y prácticamente todos los aspectos de la vida moderna."
        ],
        'keywords': ['tecnologia', 'tecnología', 'internet', 'computadora', 'ordenador', 'software', 'hardware', 'app', 'digital', 'robot', 'celular', 'smartphone', 'red', 'web']
    },
    'geografia': {
        'respuestas': [
            "La geografía estudia la superficie terrestre, sus paisajes, regiones, países, océanos y la relación entre el ser humano y el medio natural.",
            "La geografía se divide en física (relieve, clima, hidrografía) y humana (población, ciudades, economía)."
        ],
        'keywords': ['geografia', 'geografía', 'pais', 'país', 'continente', 'oceano', 'océano', 'capital', 'ciudad', 'rio', 'río', 'montaña', 'mapa', 'region', 'región']
    },
    'default': {
        'respuestas': [
            "Interesante pregunta sobre '{tema}'. Déjame buscar información actualizada en internet para darte la mejor respuesta.",
            "Voy a investigar sobre '{tema}' para darte información precisa y actualizada."
        ],
        'keywords': []
    }
}

# ========== RED NEURONAL LEGACY (para compatibilidad) ==========

class CicNeuralNetwork:
    """
    Clase legacy - mantiene compatibilidad con código existente.
    La nueva funcionalidad está en CicNeuralEngine.
    """
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
                logger.info("🧠 Red neuronal (legacy) cargada")
            else:
                self._create_new_models()
        except Exception as e:
            logger.error(f"Error cargando modelos legacy: {e}")
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
            self.model_relevance = MLPClassifier(
                hidden_layer_sizes=(64, 32),
                activation='tanh',
                solver='adam',
                max_iter=300,
                random_state=42
            )
            self.vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
            self.is_trained = False
            logger.info("🧠 Nueva red neuronal (legacy) creada")
        except ImportError:
            logger.warning("scikit-learn no disponible")
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
            logger.info(f"🧠 Red neuronal (legacy) entrenada con {len(texts)} ejemplos")
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
        except Exception as e:
            logger.error(f"Error en predicción: {e}")
            return {'intent': 'unknown', 'confidence': 0.0}

    def predict_relevance(self, query, memory_content):
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
                    'relevance_model': self.model_relevance,
                    'vectorizer': self.vectorizer,
                    'is_trained': self.is_trained
                }, f)
        except Exception as e:
            logger.error(f"Error guardando: {e}")

    def get_stats(self):
        return {
            'is_trained': self.is_trained,
            'training_samples': len(self.training_data),
            'model_type': 'MLPClassifier (legacy)',
            'layers_intent': [128, 64, 32] if self.model_intent else [],
            'layers_relevance': [64, 32] if self.model_relevance else []
        }

# Instancia legacy para compatibilidad
neural_net = CicNeuralNetwork()

# ========== AUTENTICACIÓN ==========

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
            except ImportError:
                return WebSearchEngine._search_fallback(query, max_results)
        except Exception as e:
            logger.error(f"❌ Error en búsqueda: {e}")
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
            logger.error(f"❌ Error en fallback: {e}")
            return []

# ========== CLASE PRINCIPAL CIC_IA v7.0 ==========

class CicIA:
    def __init__(self):
        self.learning_active = True
        self.web_search_engine = WebSearchEngine()
        self.current_learning_topic = None
        self._auto_learned_session = 0
        
        # NUEVOS COMPONENTES v7.0
        self.neural_engine = CicNeuralEngine()
        self.feedback_collector = FeedbackCollector(db.session)
        self.curiosity_engine = CuriosityEngine(db.session, self.web_search_engine)
        self.working_memory = WorkingMemory(max_turns=7)

        # Temas de aprendizaje
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

        # Estadísticas
        with app.app_context():
            self.stats = {
                'memories': Memory.query.count(),
                'conversations': Conversation.query.count(),
                'today_learned': self._get_today_count(),
                'auto_learned_total': self._get_auto_learned_total(),
                'feedback_received': FeedbackLog.query.count(),
                'curiosity_gaps': CuriosityGap.query.filter_by(status='pending').count()
            }

        # Iniciar threads
        self._start_background_threads()

        logger.info("=" * 70)
        logger.info("🚀 CIC_IA v7.0 - SISTEMA EVOLUTIVO CON AUTO-APRENDIZAJE")
        logger.info(f"📚 Memorias: {self.stats['memories']}")
        logger.info(f"💬 Conversaciones: {self.stats['conversations']}")
        logger.info(f"📈 Aprendidos hoy: {self.stats['today_learned']}")
        logger.info(f"🤖 Auto-aprendidos total: {self.stats['auto_learned_total']}")
        logger.info(f"📊 Feedback recibido: {self.stats['feedback_received']}")
        logger.info(f"🔍 Curiosidad gaps: {self.stats['curiosity_gaps']}")
        logger.info("🌐 Búsqueda web: ACTIVADA")
        logger.info("🧠 Red Neuronal v2: " + ("ACTIVADA" if self.neural_engine.is_trained else "EN ESPERA"))
        logger.info("🧠 Red Neuronal (legacy): " + ("ACTIVADA" if neural_net.is_trained else "EN ESPERA"))
        logger.info("🧠 Auto-aprendizaje: ACTIVADO (cada 2 horas)")
        logger.info("🌙 Reentrenamiento: 3:00 AM diario")
        logger.info(f"🎯 Temas disponibles: {len(self.auto_learning_topics)} categorías")
        logger.info("=" * 70)

    # ========== INICIALIZACIÓN DE THREADS ==========

    def _start_background_threads(self):
        """Inicia todos los threads de background"""
        threads = [
            (self._continuous_learning_loop, "Auto-aprendizaje (2h)"),
            (self._nightly_training_loop, "Reentrenamiento nocturno"),
            (self._curiosity_loop, "Investigación curiosidad"),
            (self._feedback_analysis_loop, "Análisis de feedback"),
            (self._auto_web_search_loop, "Mantenimiento web cache"),
            (self._process_manual_learning_queue, "Cola aprendizaje manual"),
        ]
        
        for target, name in threads:
            t = threading.Thread(target=target, daemon=True)
            t.name = name
            t.start()
            logger.info(f"✅ Thread iniciado: {name}")

    # ========== LOOPS DE BACKGROUND ==========

    def _continuous_learning_loop(self):
        """Loop principal de auto-aprendizaje cada 2 horas"""
        time.sleep(300)  # Esperar 5 minutos al inicio
        
        while self.learning_active:
            try:
                count = self._perform_auto_learning()
                if count:
                    self._auto_learned_session += count
                    logger.info(f"🤖 Sesión: +{count}, total={self._auto_learned_session}")
            except Exception as e:
                logger.error(f"❌ Error en auto-aprendizaje: {e}")
            
            logger.info("⏰ Auto-aprendizaje: esperando 2 horas...")
            time.sleep(7200)

    def _nightly_training_loop(self):
        """Reentrena la red neuronal a las 3:00 AM"""
        while self.learning_active:
            now = datetime.now()
            
            if now.hour == 3 and now.minute < 5:
                try:
                    self._perform_nightly_training()
                except Exception as e:
                    logger.error(f"❌ Error reentrenamiento: {e}")
                
                time.sleep(3600)
            else:
                time.sleep(300)

    def _curiosity_loop(self):
        """Investiga gaps de curiosidad cada 30 minutos"""
        time.sleep(600)
        
        while self.learning_active:
            try:
                with app.app_context():
                    gaps = CuriosityGap.query.filter_by(status='pending').all()
                    
                    for gap in gaps:
                        if gap.mention_count >= 2:
                            result = self.curiosity_engine._investigate_concept(gap)
                            logger.info(f"🔍 Curiosidad: {result}")
                            time.sleep(60)
                            
            except Exception as e:
                logger.error(f"❌ Error en curiosidad: {e}")
            
            time.sleep(1800)

    def _feedback_analysis_loop(self):
        """Analiza feedback implícito cada 15 minutos"""
        time.sleep(900)
        
        while self.learning_active:
            try:
                with app.app_context():
                    recent_convs = Conversation.query.filter(
                        Conversation.timestamp > datetime.utcnow() - timedelta(minutes=20)
                    ).order_by(Conversation.timestamp.desc()).limit(10).all()
                    
                    for i in range(len(recent_convs) - 1):
                        current = recent_convs[i]
                        previous = recent_convs[i + 1]
                        
                        existing = FeedbackLog.query.filter_by(
                            conversation_id=previous.id
                        ).first()
                        
                        if not existing:
                            self.feedback_collector.collect_implicit_feedback(
                                conversation_id=previous.id,
                                user_message=current.user_message,
                                bot_message=previous.bot_response,
                                response_time=0.0
                            )
                            
            except Exception as e:
                logger.error(f"❌ Error análisis feedback: {e}")
            
            time.sleep(900)

    def _auto_web_search_loop(self):
        """Limpia caché de búsqueda cada hora"""
        while self.learning_active:
            try:
                with app.app_context():
                    expired = WebSearchCache.query.filter(
                        WebSearchCache.expires_at < datetime.utcnow()
                    ).all()
                    
                    for cache in expired:
                        db.session.delete(cache)
                    
                    if expired:
                        db.session.commit()
                        logger.info(f"🧹 Caché limpiado: {len(expired)} entradas")
                        
            except Exception as e:
                logger.error(f"❌ Error limpieza caché: {e}")
            
            time.sleep(3600)

    def _process_manual_learning_queue(self):
        """Procesa cola de aprendizaje manual cada 5 minutos"""
        time.sleep(300)
        
        while self.learning_active:
            try:
                with app.app_context():
                    pending = ManualLearningQueue.query.filter_by(
                        status='pending'
                    ).order_by(ManualLearningQueue.priority.desc()).limit(5).all()
                    
                    for item in pending:
                        try:
                            item.status = 'processing'
                            db.session.commit()
                            
                            exists = Memory.query.filter(
                                Memory.content.ilike(f'%{item.content[:100]}%')
                            ).first()
                            
                            if exists:
                                item.status = 'completed'
                                item.processed_at = datetime.utcnow()
                                db.session.commit()
                                continue
                            
                            memory = Memory(
                                content=f"{item.content}\n\nFuente: {item.source_url or 'Manual'}",
                                source='manual_learning',
                                topic=item.topic,
                                relevance_score=0.9 if item.priority >= 2 else 0.8,
                                confidence_score=0.8
                            )
                            db.session.add(memory)
                            
                            evolution = KnowledgeEvolution(
                                topic=item.topic,
                                action='manual_learned',
                                new_content=item.content[:200],
                                source='manual_learning',
                                triggered_by='manual'
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

    # ========== MÉTODOS DE APRENDIZAJE ==========

    def _perform_auto_learning(self, custom_topic=None):
        """Realiza una sesión de auto-aprendizaje"""
        with app.app_context():
            topic = custom_topic or self.current_learning_topic or random.choice(self.auto_learning_topics)
            self.current_learning_topic = None
            
            logger.info(f"🤖 Auto-aprendizaje: investigando '{topic}'")
            
            results = self.web_search_engine.search_duckduckgo(topic, max_results=3)
            
            if not results:
                logger.warning(f"⚠️ Sin resultados para '{topic}'")
                return 0
            
            learned_count = 0
            
            for result in results:
                try:
                    preview = result['snippet'][:50] if result['snippet'] else ''
                    exists = Memory.query.filter(
                        Memory.content.ilike(f'%{preview}%')
                    ).first()
                    
                    if exists:
                        logger.info(f"⏭️ Ya conocido: {result['title'][:50]}...")
                        continue
                    
                    url_exists = Memory.query.filter(
                        Memory.content.contains(result['url'])
                    ).first()
                    
                    if url_exists:
                        logger.info(f"⏭️ URL conocida: {result['url'][:50]}...")
                        continue
                    
                    memory = Memory(
                        content=f"{result['title']}\n\n{result['snippet']}\n\nFuente: {result['url']}",
                        source='auto_learning',
                        topic=topic,
                        relevance_score=0.6,
                        confidence_score=0.5,
                        usage_context=[{'learned_at': datetime.utcnow().isoformat(), 'source': 'auto'}]
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
                    
                    learned_count += 1
                    
                    logger.info(f"✅ Aprendido: {result['title'][:60]}...")
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando resultado: {e}")
                    continue
            
            if learned_count > 0:
                db.session.commit()
                
                today = date.today()
                log = LearningLog.query.filter_by(date=today).first()
                if not log:
                    log = LearningLog(date=today)
                    db.session.add(log)
                
                log.auto_learned += learned_count
                log.web_searches += len(results)
                db.session.commit()
                
                logger.info(f"🎉 Sesión completada: {learned_count} nuevos conocimientos")
            
            return learned_count

    def _perform_nightly_training(self):
        """Reentrena la red neuronal con feedback acumulado"""
        logger.info("🌙 Iniciando reentrenamiento nocturno...")
        
        with app.app_context():
            feedback_data = self.feedback_collector.get_feedback_for_training(
                min_samples=5,
                unused_only=True
            )
            
            if len(feedback_data) < 5:
                logger.info(f"ℹ️ Insuficiente feedback ({len(feedback_data)})")
                return
            
            logger.info(f"🧠 Reentrenando con {len(feedback_data)} muestras...")
            
            result = self.neural_engine.retrain_with_feedback(feedback_data)
            
            if result['success']:
                feedback_ids = [f['feedback_id'] for f in feedback_data]
                self.feedback_collector.mark_as_used_for_training(feedback_ids)
                
                batch = TrainingBatch(
                    samples_used=len(feedback_data),
                    accuracy_after=result['metrics'].get('train_accuracy'),
                    loss=result['metrics'].get('loss'),
                    status='completed',
                    completed_at=datetime.utcnow()
                )
                db.session.add(batch)
                db.session.commit()
                
                logger.info(f"✅ Reentrenamiento completado:")
                logger.info(f"   - Accuracy: {result['metrics']['train_accuracy']:.3f}")
                logger.info(f"   - Pérdida: {result['metrics']['loss']:.4f}")
                logger.info(f"   - Versión: {result['version']}")
            else:
                logger.warning(f"❌ Fallido: {result.get('error')}")

    # ========== PROCESAMIENTO DE CHAT ==========

    def process_chat(self, user_input, mode='balanced', attachment_info=None):
        """Procesa mensaje del usuario con sistema evolutivo completo"""
        input_lower = user_input.lower().strip()
        
        # 1. Fecha/hora
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_conversation(user_input, response, 'system_time', 
                                         attachment_info=attachment_info)
        
        # 2. Intención con nueva red neuronal
        intent_info = self.neural_engine.predict_intent(user_input)
        logger.info(f"🧠 Intención: {intent_info['intent']} (conf: {intent_info['confidence']:.2f})")
        
        # 3. Curiosidad
        curiosity_actions = self.curiosity_engine.process_conversation(
            user_message=user_input,
            bot_response=""
        )
        if curiosity_actions:
            logger.info(f"🔍 Curiosidad: {len(curiosity_actions)} acciones")
        
        # 4. Memoria de trabajo
        context = self.working_memory.add_turn(
            user_message=user_input,
            bot_response="",
            intent=intent_info['intent'],
            entities=self._extract_entities(user_input)
        )
        
        # 5. ¿Necesita aclaración?
        needs_clarification, clarification_msg = self.working_memory.should_ask_clarification()
        if needs_clarification:
            response = clarification_msg
            return self._save_conversation(user_input, response, 'clarification', 
                                         attachment_info=attachment_info,
                                         intent=intent_info['intent'], 
                                         context=context,
                                         confidence=intent_info['confidence'])
        
        # 6. Generar respuesta
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
            
            if self.working_memory.turns:
                self.working_memory.turns[-1].bot_response = response
            
            return self._save_conversation(
                user_input=user_input,
                response=response,
                source=sources[0] if sources else 'learning',
                attachment_info=attachment_info,
                intent=intent_info['intent'],
                context=context,
                memories_count=len(relevant_memories),
                sources_used=sources,
                confidence=intent_info['confidence']
            )

    def _generate_response(self, user_input, best_topic, relevant_memories, intent_info, mode):
        """Genera respuesta basada en fuentes disponibles"""
        sources = []
        response = ""
        
        if best_topic and best_topic != 'default':
            respuestas = KNOWLEDGE_BASE[best_topic]['respuestas']
            response = random.choice(respuestas)
            sources.append('knowledge_base')
        
        elif relevant_memories:
            mem = relevant_memories[0]
            response = f"Basándome en mi conocimiento: {mem.content[:300]}"
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
                sources.append('learning')
        
        if mode == 'fast':
            response = response.split('.')[0] + '.' if '.' in response else response[:100]
        elif mode == 'complete':
            response += "\n\n¿Te gustaría que profundice en este tema?"
        
        return response, sources

    def _find_relevant_memories(self, query, memories, intent_info):
        """Encuentra memorias relevantes"""
        if self.neural_engine.is_trained and intent_info['confidence'] > 0.5:
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
        """Búsqueda por palabras clave"""
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

    def _save_conversation(self, user_input, response, source, attachment_info=None,
                          intent=None, context=None, memories_count=0, sources_used=None,
                          confidence=None):
        """Guarda conversación con metadatos"""
        with app.app_context():
            conv = Conversation(
                user_message=user_input,
                bot_response=response,
                has_attachment=attachment_info is not None,
                attachment_path=attachment_info.get('path') if attachment_info else None,
                sources_used=sources_used or [source],
                intent_detected=intent,
                confidence=confidence,
                context_snapshot=context
            )
            db.session.add(conv)
            db.session.flush()
            
            if context:
                self.working_memory.save_snapshot(db.session, conv.id)
            
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
            'model_used': 'cic_ia_v7_neural',
            'sources_used': sources_used or [source],
            'memories_found': memories_count,
            'total_memories': total_mem,
            'has_attachment': attachment_info is not None,
            'intent_detected': intent,
            'confidence': confidence,
            'context_topic': context.get('current_topic') if context else None
        }

    def _search_and_learn(self, query):
        """Busca en web y aprende"""
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
                    summary += f"{i}. **{result['title']}**\n"
                    summary += f"   {result['snippet']}\n\n"
                    
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
                    results={'summary': summary},
                    expires_at=datetime.utcnow() + timedelta(hours=24)
                )
                db.session.add(cache_entry)
                db.session.commit()
                
                return {'summary': summary}
                
        except Exception as e:
            logger.error(f"❌ Error búsqueda web: {e}")
            return None

    # ========== MÉTODOS AUXILIARES ==========

    def _get_today_count(self):
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        return log.count if log else 0

    def _get_auto_learned_total(self):
        total = db.session.query(db.func.sum(LearningLog.auto_learned)).scalar()
        return int(total) if total else 0

    def set_custom_topic(self, topic):
        self.current_learning_topic = topic
        logger.info(f"📌 Tema personalizado: '{topic}'")
        return True

    def clear_custom_topic(self):
        self.current_learning_topic = None
        logger.info("📌 Tema personalizado limpiado")
        return True

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

    def add_manual_learning(self, content, topic=None, source_url=None, priority=1):
        try:
            with app.app_context():
                queue_item = ManualLearningQueue(
                    content=content,
                    topic=topic or 'manual_learning',
                    source_url=source_url,
                    priority=priority,
                    status='pending'
                )
                db.session.add(queue_item)
                db.session.commit()
                return {'success': True, 'id': queue_item.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

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
                'feedback': {
                    'total': FeedbackLog.query.count(),
                    'implicit': FeedbackLog.query.filter_by(feedback_type='implicit').count(),
                    'explicit': FeedbackLog.query.filter_by(feedback_type='explicit').count(),
                },
                'curiosity': {
                    'pending': CuriosityGap.query.filter_by(status='pending').count(),
                    'learned': CuriosityGap.query.filter_by(status='learned').count(),
                },
                'neural_network': self.neural_engine.get_stats(),
                'working_memory': {
                    'current_topic': self.working_memory.current_topic,
                    'session_turns': self.working_memory.total_turns,
                },
                'version': '7.0'
            }

# Instancia global
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
        'version': '7.0.0',
        'features': ['chat', 'web_search', 'auto_learning', 'memory', 'evolution', 
                     '50_topics', 'neural_network_v2', 'feedback_loop', 'curiosity', 'manual_learning']
    })

@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.json
        message = data.get('message', '').strip()
        mode = data.get('mode', 'balanced')
        
        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        result = cic_ia.process_chat(message, mode=mode)
        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Error en /api/chat: {e}")
        return jsonify({
            'error': str(e),
            'response': 'Lo siento, ocurrió un error. Por favor intenta de nuevo.'
        }), 500

@app.route('/api/web-search', methods=['POST'])
def web_search():
    try:
        query = request.json.get('query', '').strip()
        if not query:
            return jsonify({'error': 'Query vacío'}), 400
        
        results = cic_ia.web_search_engine.search_duckduckgo(query, max_results=5)
        
        with app.app_context():
            for result in results:
                memory = Memory(
                    content=result['snippet'],
                    source='web_search',
                    topic=query,
                    relevance_score=0.7
                )
                db.session.add(memory)
            db.session.commit()
        
        return jsonify({'query': query, 'results': results, 'count': len(results)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def status():
    try:
        stats = cic_ia.get_learning_stats()
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        
        return jsonify({
            'stage': 'v7.0.0',
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
            'neural_network': stats['neural_network'],
            'feedback': stats['feedback'],
            'curiosity': stats['curiosity']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/learn', methods=['POST'])
def learn():
    try:
        data = request.json
        query = data.get('query', '')
        source = data.get('source', 'wikipedia')
        
        with app.app_context():
            if source == 'web':
                results = cic_ia.web_search_engine.search_duckduckgo(query, max_results=3)
                for result in results:
                    memory = Memory(
                        content=result['snippet'],
                        source='web_search',
                        topic=query,
                        relevance_score=0.8
                    )
                    db.session.add(memory)
            else:
                memory = Memory(
                    content=f"Información sobre {query}",
                    source='wikipedia',
                    topic=query,
                    relevance_score=0.7
                )
                db.session.add(memory)
            
            db.session.commit()
            return jsonify({
                'message': f'✅ Aprendido sobre {query}',
                'memories_added': len(results) if source == 'web' else 1
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/teach', methods=['POST'])
def teach():
    try:
        data = request.json
        text = data.get('text', '').strip()
        topic = data.get('topic', '').strip()
        
        if not text:
            return jsonify({'error': 'Texto vacío'}), 400
        if not topic:
            topic = text[:50]
        
        with app.app_context():
            memory = Memory(
                content=text,
                source='user_taught',
                topic=topic,
                relevance_score=0.9
            )
            db.session.add(memory)
            db.session.commit()
            
            return jsonify({
                'message': 'He aprendido lo que me enseñaste',
                'memory_id': memory.id,
                'topic': topic
            })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/memories')
def memories():
    try:
        mems = Memory.query.order_by(Memory.created_at.desc()).limit(10).all()
        return jsonify([{
            'id': m.id, 'topic': m.topic, 'source': m.source,
            'content': m.content[:100], 'relevance': m.relevance_score
        } for m in mems])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history')
def history():
    try:
        convs = Conversation.query.order_by(Conversation.timestamp.desc()).limit(5).all()
        return jsonify([{
            'user': c.user_message, 'bot': c.bot_response, 'sources': c.sources_used
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
        return jsonify({'success': False, 'error': 'Credenciales inválidas'}), 401
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
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No se recibieron datos'}), 400
        
        content = (data.get('content') or '').strip()
        topic = (data.get('topic') or '').strip()
        source_url = (data.get('source_url') or '').strip() or None
        priority = data.get('priority', 1)
        
        if not content:
            return jsonify({'success': False, 'error': 'Contenido vacío'}), 400
        if not topic:
            topic = content[:50]
        
        try:
            priority = int(priority)
            if priority not in [1, 2, 3]:
                priority = 1
        except:
            priority = 1
        
        result = cic_ia.add_manual_learning(content, topic, source_url, priority)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'Agregado a cola (ID: {result["id"]})',
                'topic': topic,
                'priority': priority
            })
        return jsonify({'success': False, 'error': result.get('error')}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/learning/manual/queue', methods=['GET'])
@dev_required
def dev_manual_learning_queue():
    try:
        pending = ManualLearningQueue.query.filter_by(status='pending').count()
        completed = ManualLearningQueue.query.filter_by(status='completed').count()
        recent = ManualLearningQueue.query.order_by(
            ManualLearningQueue.created_at.desc()
        ).limit(10).all()
        
        return jsonify({
            'queue_stats': {'pending': pending, 'completed': completed},
            'recent_items': [{
                'id': item.id, 'topic': item.topic, 'status': item.status,
                'priority': item.priority,
                'created_at': item.created_at.isoformat()
            } for item in recent]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/neural/train', methods=['POST'])
@dev_required
def dev_train_neural_network():
    try:
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
        for text in texts:
            tl = text.lower()
            if any(kw in tl for kw in ['hola', 'buenas', 'saludos']):
                labels.append('greeting')
            elif any(kw in tl for kw in ['qué', 'cómo', 'cuándo', 'dónde']):
                labels.append('question')
            elif any(kw in tl for kw in ['gracias', 'ok', 'bien']):
                labels.append('acknowledgment')
            else:
                labels.append('statement')
        
        # Usar nueva red neuronal
        success = cic_ia.neural_engine.train(texts, labels)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Red neuronal v2 entrenada',
                'samples_used': len(texts),
                'stats': cic_ia.neural_engine.get_stats()
            })
        return jsonify({'success': False, 'error': 'Error en entrenamiento'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/neural/stats', methods=['GET'])
@dev_required
def dev_neural_stats():
    return jsonify({
        'neural_engine_v2': cic_ia.neural_engine.get_stats(),
        'neural_net_legacy': neural_net.get_stats()
    })

@app.route('/api/dev/learning/set-topic', methods=['POST'])
@dev_required
def dev_set_learning_topic():
    try:
        topic = (request.json.get('topic') or '').strip()
        if not topic:
            return jsonify({'success': False, 'error': 'Tema vacío'}), 400
        
        cic_ia.set_custom_topic(topic)
        return jsonify({
            'success': True,
            'message': f'Tema establecido: "{topic}"',
            'topic': topic
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/learning/clear-topic', methods=['POST'])
@dev_required
def dev_clear_learning_topic():
    cic_ia.clear_custom_topic()
    return jsonify({'success': True, 'message': 'Tema eliminado'})

@app.route('/api/evolution/learn-now', methods=['POST'])
@dev_required
def evolution_learn_now():
    try:
        topic = (request.json.get('topic') or '').strip() or None
        
        def _learn(t):
            count = cic_ia._perform_auto_learning(t)
            if count:
                cic_ia._auto_learned_session += count
        
        threading.Thread(target=_learn, args=(topic,), daemon=True).start()
        
        return jsonify({
            'success': True,
            'message': 'Auto-aprendizaje iniciado',
            'topic': topic or 'aleatorio'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/memories/all')
@dev_required
def dev_memories_all():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        pagination = Memory.query.order_by(Memory.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'memories': [{
                'id': m.id, 'topic': m.topic, 'content': m.content,
                'source': m.source, 'relevance': m.relevance_score,
                'access_count': m.access_count,
                'created_at': m.created_at.isoformat()
            } for m in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages
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
        stats = cic_ia.get_learning_stats()
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        return jsonify({
            'general': {
                'total_memories': Memory.query.count(),
                'total_conversations': Conversation.query.count(),
                'active_sessions': len(dev_auth.active_sessions)
            },
            'today': {
                'conversations': db.session.query(db.func.sum(LearningLog.count))
                    .filter(LearningLog.date == today).scalar() or 0,
                'auto_learned': db.session.query(db.func.sum(LearningLog.auto_learned))
                    .filter(LearningLog.date == today).scalar() or 0
            },
            'this_week': {
                'conversations': db.session.query(db.func.sum(LearningLog.count))
                    .filter(LearningLog.date >= week_ago).scalar() or 0
            },
            'learning': stats,
            'neural_network_v2': cic_ia.neural_engine.get_stats(),
            'neural_network_legacy': neural_net.get_stats()
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
                'message': 'Header X-Confirm-Delete: DESTRUIR_TODO'
            }), 400
        
        Memory.query.delete()
        Conversation.query.delete()
        LearningLog.query.delete()
        WebSearchCache.query.delete()
        KnowledgeEvolution.query.delete()
        DeveloperSession.query.delete()
        ManualLearningQueue.query.delete()
        FeedbackLog.query.delete()
        CuriosityGap.query.delete()
        TrainingBatch.query.delete()
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Base de datos eliminada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/sessions')
@dev_required
def dev_sessions():
    try:
        sessions = [{
            'username': s['username'],
            'created_at': s['created_at'].isoformat(),
            'expires_at': s['expires_at'].isoformat(),
            'last_used': s['last_used'].isoformat(),
            'token_preview': t[:8] + '...'
        } for t, s in dev_auth.active_sessions.items()]
        
        return jsonify({'active_sessions': len(sessions), 'sessions': sessions})
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
