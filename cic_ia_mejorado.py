"""
Cic_IA v7.0 - Asistente Inteligente EVOLUTIVO
Versión mejorada con Auto-Aprendizaje, Feedback y Curiosidad
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
import os
import json
import random
import threading
import time
import re
import logging

# NUEVOS IMPORTS (tus archivos creados)
from models import db, init_database, Memory, Conversation, LearningLog, FeedbackLog
from models import CuriosityGap, TrainingBatch, DeveloperSession, WebSearchCache
from models import KnowledgeEvolution, ManualLearningQueue, WorkingMemorySnapshot
from neural_engine import CicNeuralEngine
from feedback_system import SatisfactionDetector, FeedbackCollector
from curiosity_engine import CuriosityEngine, ConceptExtractor
from working_memory import WorkingMemory

# ... resto de tu código actual ...

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

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'py', 'js', 'html', 'css', 'json'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DEV_USERNAME = os.environ.get('DEV_USERNAME', 'admin')
DEV_PASSWORD = os.environ.get('DEV_PASSWORD', 'CicDev2024!')

db = SQLAlchemy(app)

# ========== MODELOS ==========

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
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(200))
    source_url = db.Column(db.String(500))
    priority = db.Column(db.Integer, default=1)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)

with app.app_context():
    db.create_all()

# ========== KNOWLEDGE BASE ==========
# CORREGIDO: Keywords son palabras/frases individuales para mejor matching

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
            "¡Hola! Soy Cic_IA, tu asistente inteligente con red neuronal integrada. ¿En qué puedo ayudarte hoy?",
            "¡Bienvenido! Estoy lista para aprender y asistirte. ¿Qué deseas saber?"
        ],
        'keywords': ['hola', 'buenas', 'hey ', 'saludos', 'buenos dias', 'buenos días', 'buenas tardes', 'buenas noches', 'hi ']
    },
    'cic_ia': {
        'respuestas': [
            "Soy Cic_IA, una inteligencia artificial evolutiva creada por Carlos. Tengo red neuronal integrada y aprendo automáticamente cada 2 horas.",
            "Cic_IA es un asistente IA evolutivo que aprende de internet, memoriza conversaciones y mejora sus respuestas continuamente."
        ],
        'keywords': ['quien eres', 'quién eres', 'que eres', 'qué eres', 'cic_ia', 'tu nombre', 'presentacion', 'como te llamas', 'cómo te llamas']
    },
    'clima': {
        'respuestas': [
            "El clima es el conjunto de condiciones atmosféricas que caracterizan una región durante un período prolongado. Incluye temperatura, humedad, precipitaciones, viento y presión atmosférica.",
            "El clima se diferencia del tiempo meteorológico: el tiempo describe lo que ocurre hoy, mientras que el clima es el patrón promedio a largo plazo de una región."
        ],
        'keywords': ['clima', 'tiempo', 'meteorologia', 'meteorología', 'temperatura', 'lluvia', 'sol', 'nube', 'viento', 'atmosfera', 'atmosférica', 'calor', 'frio', 'frío']
    },
    'matematicas': {
        'respuestas': [
            "Las matemáticas son la ciencia del número, la cantidad, el espacio y el cambio. Son la base de la ciencia y la ingeniería.",
            "Las matemáticas incluyen álgebra, geometría, cálculo, estadística, probabilidad y muchas otras ramas del conocimiento."
        ],
        'keywords': ['matematicas', 'matemáticas', 'matematica', 'algebra', 'calculo', 'geometria', 'numero', 'suma', 'resta', 'multiplicacion', 'division', 'ecuacion']
    },
    'historia': {
        'respuestas': [
            "La historia es el estudio del pasado humano, sus civilizaciones, culturas y eventos que han moldeado el mundo actual.",
            "La historia nos permite comprender el presente y aprender de los errores y logros del pasado de la humanidad."
        ],
        'keywords': ['historia', 'pasado', 'civilizacion', 'civilización', 'antiguo', 'guerra', 'revolucion', 'cultura', 'siglo', 'historico', 'histórico']
    },
    'ciencia': {
        'respuestas': [
            "La ciencia es el conjunto de conocimientos obtenidos mediante la observación y el razonamiento sistemático. Incluye física, química, biología, astronomía y más.",
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

# ========== RED NEURONAL ==========

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
            logger.info(f"🧠 Red neuronal entrenada con {len(texts)} ejemplos")
            return True
        except Exception as e:
            logger.error(f"Error entrenando red neuronal: {e}")
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
            logger.info("💾 Modelos guardados")
        except Exception as e:
            logger.error(f"Error guardando modelos: {e}")

    def get_stats(self):
        return {
            'is_trained': self.is_trained,
            'training_samples': len(self.training_data),
            'model_type': 'MLPClassifier (scikit-learn)',
            'layers_intent': [128, 64, 32] if self.model_intent else [],
            'layers_relevance': [64, 32] if self.model_relevance else []
        }

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

# ========== CLASE PRINCIPAL CIC_IA ==========

class CicIA:
    def __init__(self):
        self.learning_active = True
        self.web_search_engine = WebSearchEngine()
        self.current_learning_topic = None
        self.neural_net = neural_net
        # Contador en memoria para reflejar auto-aprendizaje de sesión actual
        self._auto_learned_session = 0

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

        threading.Thread(target=self._auto_learn_loop, daemon=True).start()
        threading.Thread(target=self._auto_web_search_loop, daemon=True).start()
        threading.Thread(target=self._continuous_learning_loop, daemon=True).start()
        threading.Thread(target=self._process_manual_learning_queue, daemon=True).start()

        logger.info("=" * 70)
        logger.info("🚀 CIC_IA EVOLUTIVA CON RED NEURONAL INICIADA v6.5.0")
        logger.info(f"📚 Memorias: {self.stats['memories']}")
        logger.info(f"💬 Conversaciones: {self.stats['conversations']}")
        logger.info(f"📈 Aprendidos hoy: {self.stats['today_learned']}")
        logger.info(f"🤖 Auto-aprendidos total: {self.stats['auto_learned_total']}")
        logger.info("🌐 Búsqueda web: ACTIVADA")
        logger.info("🧠 Red Neuronal: " + ("ACTIVADA" if self.neural_net.is_trained else "EN ESPERA DE ENTRENAMIENTO"))
        logger.info("🧠 Auto-aprendizaje: ACTIVADO (cada 2 horas, primer ciclo en 5 min)")
        logger.info(f"🎯 Temas de aprendizaje: {len(self.auto_learning_topics)} categorías")
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
        logger.info(f"📌 Tema personalizado establecido: '{topic}'")
        return True

    def clear_custom_topic(self):
        self.current_learning_topic = None
        logger.info("📌 Tema personalizado limpiado")
        return True

    # ------------------------------------------------------------------ #
    #  AUTO-APRENDIZAJE                                                    #
    # ------------------------------------------------------------------ #

    def _continuous_learning_loop(self):
        """Primer ciclo a los 5 min, luego cada 2 horas."""
        logger.info("🧠 Iniciando loop de auto-aprendizaje evolutivo...")
        time.sleep(300)  # espera inicial 5 minutos
        while self.learning_active:
            try:
                count = self._perform_auto_learning()
                if count:
                    self._auto_learned_session += count
                    logger.info(f"🤖 Auto-aprendidos acumulados en sesión: {self._auto_learned_session}")
            except Exception as e:
                logger.error(f"❌ Error en auto-aprendizaje: {e}")
            logger.info("⏰ Auto-aprendizaje: esperando 2 horas...")
            time.sleep(7200)

    def _perform_auto_learning(self, custom_topic=None):
        """
        Ejecuta UN ciclo de aprendizaje.
        Retorna el número de elementos nuevos aprendidos (int).
        """
        learned_count = 0
        with app.app_context():
            # Elegir tema
            if custom_topic:
                topic = custom_topic
            elif self.current_learning_topic:
                topic = self.current_learning_topic
                self.current_learning_topic = None
            else:
                topic = random.choice(self.auto_learning_topics)

            logger.info(f"🤖 Auto-aprendizaje: investigando '{topic}'")

            results = self.web_search_engine.search_duckduckgo(topic, max_results=3)

            if not results:
                logger.warning(f"⚠️ Sin resultados web para '{topic}'")
                return 0

            for result in results:
                try:
                    snippet = result.get('snippet', '')
                    if not snippet:
                        continue

                    content_preview = snippet[:100]

                    # Evitar duplicados por contenido
                    exists_content = Memory.query.filter(
                        Memory.content.ilike(f'%{content_preview}%')
                    ).first()
                    if exists_content:
                        logger.info(f"⏭️ Ya conocido (contenido): {result['title'][:50]}")
                        continue

                    # Evitar duplicados por URL
                    url = result.get('url', '')
                    if url:
                        exists_url = Memory.query.filter(
                            Memory.content.contains(url)
                        ).first()
                        if exists_url:
                            logger.info(f"⏭️ Ya conocido (URL): {url[:50]}")
                            continue

                    memory = Memory(
                        content=f"{result['title']}\n\n{snippet}\n\nFuente: {url}",
                        source='auto_learning',
                        topic=topic,
                        relevance_score=0.6,
                        access_count=0
                    )
                    db.session.add(memory)

                    evolution = KnowledgeEvolution(
                        topic=topic,
                        action='learned',
                        new_content=snippet[:200],
                        source='auto_learning'
                    )
                    db.session.add(evolution)
                    learned_count += 1
                    logger.info(f"✅ Aprendido: {result['title'][:60]}")

                except Exception as e:
                    logger.error(f"❌ Error procesando resultado: {e}")
                    continue

            if learned_count > 0:
                db.session.commit()

                # Actualizar log de hoy
                today = date.today()
                log = LearningLog.query.filter_by(date=today).first()
                if not log:
                    log = LearningLog(date=today, count=0, web_searches=0, auto_learned=0)
                    db.session.add(log)
                log.auto_learned += learned_count
                log.web_searches += len(results)
                db.session.commit()

                logger.info(f"🎉 Ciclo completado: {learned_count} nuevos conocimientos sobre '{topic}'")
            else:
                logger.info(f"📝 Sin novedades para '{topic}'")

        return learned_count

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
                logger.info(f"📥 Cola manual: '{topic or 'Sin tema'}' (prioridad {priority})")
                return {'success': True, 'id': queue_item.id}
        except Exception as e:
            logger.error(f"❌ Error agregando aprendizaje manual: {e}")
            return {'success': False, 'error': str(e)}

    def _process_manual_learning_queue(self):
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

                            exists = Memory.query.filter(
                                Memory.content.ilike(f'%{item.content[:100]}%')
                            ).first()

                            if exists:
                                item.status = 'completed'
                                item.processed_at = datetime.utcnow()
                                db.session.commit()
                                logger.info(f"⏭️ Manual ya existente: {item.topic}")
                                continue

                            memory = Memory(
                                content=f"{item.content}\n\nFuente: {item.source_url or 'Aprendizaje manual'}",
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
                            logger.error(f"❌ Error procesando item manual: {e}")

            except Exception as e:
                logger.error(f"❌ Error en cola manual: {e}")
            time.sleep(300)

    def _auto_web_search_loop(self):
        """Limpia cache de búsqueda expirado cada hora."""
        while self.learning_active:
            try:
                with app.app_context():
                    stmt = select(WebSearchCache).where(
                        WebSearchCache.expires_at < datetime.utcnow()
                    )
                    expired = db.session.execute(stmt).scalars().all()
                    for entry in expired:
                        db.session.delete(entry)
                    db.session.commit()
                    if expired:
                        logger.info(f"🧹 Cache limpiado: {len(expired)} entradas")
            except Exception as e:
                logger.error(f"❌ Error limpiando cache: {e}")
            time.sleep(3600)

    def _auto_learn_loop(self):
        """Refresca relevance_score de memorias cada hora."""
        while self.learning_active:
            try:
                with app.app_context():
                    memories = Memory.query.all()
                    for mem in memories:
                        mem.relevance_score = min(1.0, mem.relevance_score + (mem.access_count * 0.01))
                    db.session.commit()
            except Exception as e:
                logger.error(f"❌ Error en auto-learn: {e}")
            time.sleep(3600)

    # ------------------------------------------------------------------ #
    #  LÓGICA DE CHAT - CORREGIDA                                          #
    # ------------------------------------------------------------------ #

    def _find_best_topic(self, text):
        """
        CORREGIDO: Busca el mejor tema en KNOWLEDGE_BASE usando texto normalizado.
        El score cuenta cuántas keywords del tema aparecen en el texto.
        Retorna la clave del tema o None.
        """
        # Normalizar: eliminar acentos no críticos, lowercase, agregar espacios en extremos
        text_lower = f" {text.lower()} "

        best_score = 0
        best_topic = None

        for topic_key, data in KNOWLEDGE_BASE.items():
            if topic_key == 'default':
                continue
            score = 0
            for kw in data['keywords']:
                # Buscar keyword (con espacios para evitar falsas coincidencias parciales)
                kw_padded = f" {kw.lower()} "
                if kw_padded in text_lower or kw.lower() in text_lower:
                    # Frases largas valen más
                    score += max(1, len(kw.split()))
            if score > best_score:
                best_score = score
                best_topic = topic_key

        logger.info(f"🔎 KB match: topic='{best_topic}' score={best_score}")
        # Umbral: al menos 1 coincidencia
        return best_topic if best_score >= 1 else None

    def _find_relevant_memories(self, text, memories):
        """
        CORREGIDO: Filtra stop-words y requiere ≥2 palabras significativas en común.
        Solo retorna memorias cuyo topic también coincide con la consulta.
        """
        STOP_WORDS = {
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'de', 'del',
            'en', 'es', 'que', 'y', 'a', 'se', 'no', 'con', 'por', 'para', 'su',
            'al', 'lo', 'le', 'me', 'mi', 'yo', 'tu', 'te', 'si', 'ya', 'como',
            'mas', 'más', 'pero', 'o', 'he', 'ha', 'hay', 'muy', 'bien', 'sobre',
            'cuando', 'tan', 'sin', 'ni', 'esto', 'ese', 'eso', 'esta', 'este',
            'ser', 'fue', 'era', 'son', 'sus', 'que', 'cual', 'quien', 'donde'
        }

        query_words = set(
            w for w in text.lower().split()
            if w not in STOP_WORDS and len(w) > 2
        )

        if not query_words:
            return []

        scored = []
        for mem in memories:
            mem_words = set(
                w for w in mem.content.lower().split()
                if w not in STOP_WORDS and len(w) > 2
            )
            common = query_words & mem_words
            if len(common) >= 2:
                # Verificar que el topic de la memoria también sea relevante
                topic_words = set(
                    w for w in (mem.topic or '').lower().split()
                    if w not in STOP_WORDS and len(w) > 2
                )
                topic_match = len(topic_words & query_words) >= 1 if topic_words else True
                if topic_match:
                    scored.append((mem, len(common)))
                    mem.access_count += 1

        scored.sort(key=lambda x: x[1], reverse=True)
        if scored:
            try:
                db.session.commit()
            except Exception:
                pass

        return [mem for mem, _ in scored[:5]]

    def _find_relevant_memories_neural(self, query, memories):
        relevant = []
        for mem in memories:
            relevance = self.neural_net.predict_relevance(query, mem.content)
            if relevance > 0.6:
                relevant.append((mem, relevance))
                mem.access_count += 1
        relevant.sort(key=lambda x: x[1], reverse=True)
        if relevant:
            try:
                db.session.commit()
            except Exception:
                pass
        return [mem for mem, _ in relevant[:5]]

    def process_chat(self, user_input, mode='balanced', attachment_info=None):
        """
        Procesa el mensaje del usuario y genera una respuesta.
        Orden de prioridad:
          1. Fecha/hora del sistema
          2. Knowledge Base (respuesta directa)
          3. Memorias relevantes (solo si el topic coincide)
          4. Búsqueda web en tiempo real
          5. Respuesta por defecto
        """
        input_lower = user_input.lower().strip()

        # --- 1. Fecha/hora ---
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_conversation(
                user_input, response, 'system_time',
                attachment_info=attachment_info
            )

        # --- 2. Intención neural (informativo, no bloquea el flujo) ---
        intent_info = self.neural_net.predict_intent(user_input)
        logger.info(f"🧠 Intención: {intent_info}")

        # --- 3. Knowledge Base ---
        best_topic = self._find_best_topic(input_lower)

        with app.app_context():
            sources_used = []
            response = ""
            memories_count = 0

            if best_topic:
                respuestas = KNOWLEDGE_BASE[best_topic]['respuestas']
                response = random.choice(respuestas)
                sources_used.append('knowledge_base')
                logger.info(f"✅ Respuesta KB → '{best_topic}'")

            else:
                # --- 4. Memorias relevantes ---
                all_memories = Memory.query.all()

                if self.neural_net.is_trained:
                    relevant = self._find_relevant_memories_neural(user_input, all_memories)
                else:
                    relevant = self._find_relevant_memories(input_lower, all_memories)

                memories_count = len(relevant)

                if relevant:
                    mem = relevant[0]
                    response = f"Basándome en mi conocimiento aprendido:\n\n{mem.content[:400]}"
                    sources_used.append(f"memory_{mem.source}")
                    logger.info(f"✅ Respuesta memoria → topic='{mem.topic}'")

                else:
                    # --- 5. Búsqueda web ---
                    tema = user_input[:60] if len(user_input) > 5 else "este tema"
                    logger.info(f"🌐 Sin respuesta local, buscando en web: '{tema}'")
                    web_results = self._search_and_learn(user_input)

                    if web_results and web_results.get('summary'):
                        response = f"He investigado en internet sobre '{tema}':\n\n"
                        response += web_results['summary']
                        sources_used.append('web_search')
                        logger.info("✅ Respuesta web search")
                    else:
                        # --- 6. Fallback ---
                        tema_corto = user_input[:40]
                        respuestas_default = KNOWLEDGE_BASE['default']['respuestas']
                        response = random.choice(respuestas_default).format(tema=tema_corto)
                        sources_used.append('learning')
                        logger.info("⚠️ Respuesta por defecto (sin resultados web)")

            # Ajuste según modo
            if mode == 'fast':
                response = (response.split('.')[0] + '.') if '.' in response else response[:150]
            elif mode == 'complete':
                response += "\n\n¿Te gustaría que profundice más en este tema?"

            return self._save_conversation(
                user_input, response,
                sources_used[0] if sources_used else 'learning',
                attachment_info=attachment_info,
                memories_count=memories_count,
                sources_used=sources_used,
                intent=intent_info.get('intent', 'unknown')
            )

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
            logger.error(f"❌ Error en búsqueda web: {e}")
            return None

    def _save_conversation(self, user_msg, bot_resp, source,
                           attachment_info=None, memories_count=0,
                           sources_used=None, intent='unknown'):
        with app.app_context():
            conv = Conversation(
                user_message=user_msg,
                bot_response=bot_resp,
                has_attachment=attachment_info is not None,
                attachment_path=attachment_info.get('path') if attachment_info else None,
                sources_used=sources_used or [source]
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

        return {
            'response': bot_resp,
            'model_used': 'cic_ia_neural_v6.5',
            'sources_used': sources_used or [source],
            'memories_found': memories_count,
            'total_memories': total_mem,
            'has_attachment': attachment_info is not None,
            'intent_detected': intent
        }

    def _is_date_time_question(self, text):
        keywords = ['qué día', 'qué hora', 'fecha actual', 'hora actual', 'hoy es',
                    'que dia', 'que hora', 'qué fecha', 'que fecha', 'dia de hoy',
                    'día de hoy', 'fecha de hoy']
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
                'knowledge_base': Memory.query.filter(
                    Memory.source.notin_(['auto_learning', 'web_search', 'user_taught', 'manual_learning'])
                ).count()
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
                t = mem.topic or 'unknown'
                topic_counts[t] = topic_counts.get(t, 0) + 1
            top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            manual_pending = ManualLearningQueue.query.filter_by(status='pending').count()
            manual_completed = ManualLearningQueue.query.filter_by(status='completed').count()

            # Total auto-aprendidos: DB + sesión actual
            auto_learned_db = db.session.query(db.func.sum(LearningLog.auto_learned)).scalar() or 0
            auto_learned_total = int(auto_learned_db) + self._auto_learned_session

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
                'auto_learned_total': auto_learned_total
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
        'version': '6.5.0_fixed',
        'features': ['chat', 'web_search', 'auto_learning', 'memory',
                     'evolution', '50_topics', 'neural_network', 'manual_learning']
    })

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """Endpoint principal de chat"""
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
            'response': 'Lo siento, ocurrió un error procesando tu mensaje. Por favor intenta de nuevo.'
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

        return jsonify({'query': query, 'results': results, 'count': len(results), 'source': 'duckduckgo'})
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
                'stage': 'v6.5.0_fixed',
                'total_memories': stats['total_memories'],
                'total_conversations': Conversation.query.count(),
                'today_learned': log.count if log else 0,
                'today_auto_learned': log.auto_learned if log else 0,
                'web_searches_today': log.web_searches if log else 0,
                'db_size': 'PostgreSQL' if database_url else 'SQLite',
                'auto_learning_active': True,
                'learning_frequency': 'cada 2 horas',
                'total_topics': len(cic_ia.auto_learning_topics),
                'auto_learned_total': stats.get('auto_learned_total', 0),
                'learning_stats': stats,
                'neural_network': stats.get('neural_network', {}),
                'features': ['chat', 'web_search', 'auto_learning', 'memory',
                             'evolution', '50_topics', 'attachments', 'neural_network', 'manual_learning']
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
            results = []
            if source == 'web':
                results = cic_ia.web_search_engine.search_duckduckgo(query, max_results=3)
                for result in results:
                    memory = Memory(content=result['snippet'], source='web_search',
                                    topic=query, relevance_score=0.8)
                    db.session.add(memory)
            else:
                memory = Memory(content=f"Información sobre {query}", source='wikipedia',
                                topic=query, relevance_score=0.7)
                db.session.add(memory)

            db.session.commit()
            return jsonify({
                'message': f'✅ He aprendido sobre {query} desde {source}',
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
                    topic=topic, action='manual_teach',
                    new_content=text[:200], source='developer'
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
                'id': m.id, 'topic': m.topic, 'source': m.source,
                'content': m.content[:100], 'relevance': m.relevance_score
            } for m in mems])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history')
def history():
    try:
        with app.app_context():
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
            return jsonify({'success': True, 'token': token, 'username': username, 'expires_in': '24h'})
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
            return jsonify({'success': False, 'error': 'Debes proporcionar contenido para aprender'}), 400
        if not topic:
            topic = content[:50] + '...' if len(content) > 50 else content

        try:
            priority = int(priority)
            if priority not in [1, 2, 3]:
                priority = 1
        except (ValueError, TypeError):
            priority = 1

        result = cic_ia.add_manual_learning(content=content, topic=topic,
                                             source_url=source_url, priority=priority)
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'📥 Contenido agregado a la cola (ID: {result["id"]})',
                'topic': topic, 'priority': priority,
                'note': 'Se procesará en los próximos 5 minutos'
            })
        return jsonify({'success': False, 'error': result.get('error', 'Error desconocido')}), 500
    except Exception as e:
        logger.error(f"Error en manual learning: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/learning/manual/queue', methods=['GET'])
@dev_required
def dev_manual_learning_queue():
    try:
        with app.app_context():
            pending = ManualLearningQueue.query.filter_by(status='pending').count()
            processing = ManualLearningQueue.query.filter_by(status='processing').count()
            completed = ManualLearningQueue.query.filter_by(status='completed').count()
            failed = ManualLearningQueue.query.filter_by(status='failed').count()
            recent = ManualLearningQueue.query.order_by(
                ManualLearningQueue.created_at.desc()).limit(10).all()

            return jsonify({
                'queue_stats': {
                    'pending': pending, 'processing': processing,
                    'completed': completed, 'failed': failed,
                    'total': pending + processing + completed + failed
                },
                'recent_items': [{
                    'id': item.id, 'topic': item.topic, 'status': item.status,
                    'priority': item.priority,
                    'created_at': item.created_at.isoformat(),
                    'processed_at': item.processed_at.isoformat() if item.processed_at else None
                } for item in recent]
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/neural/train', methods=['POST'])
@dev_required
def dev_train_neural_network():
    try:
        with app.app_context():
            conversations = Conversation.query.order_by(
                Conversation.timestamp.desc()).limit(100).all()

            if len(conversations) < 10:
                return jsonify({
                    'success': False,
                    'error': 'Se necesitan al menos 10 conversaciones para entrenar',
                    'current': len(conversations)
                }), 400

            texts = [conv.user_message for conv in conversations]
            labels = []
            for text in texts:
                tl = text.lower()
                if any(kw in tl for kw in ['hola', 'buenas', 'saludos']):
                    labels.append('greeting')
                elif any(kw in tl for kw in ['qué', 'cómo', 'cuándo', 'dónde', 'que', 'como', 'cuando']):
                    labels.append('question')
                elif any(kw in tl for kw in ['gracias', 'ok', 'bien', 'perfecto']):
                    labels.append('acknowledgment')
                else:
                    labels.append('statement')

            success = neural_net.train(texts, labels)
            if success:
                return jsonify({
                    'success': True,
                    'message': '🧠 Red neuronal entrenada exitosamente',
                    'samples_used': len(texts),
                    'labels': list(set(labels)),
                    'stats': neural_net.get_stats()
                })
            return jsonify({'success': False, 'error': 'Error durante el entrenamiento'}), 500
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
        topic = (data.get('topic') or '').strip()
        if not topic:
            return jsonify({'success': False, 'error': 'Debes proporcionar un tema'}), 400
        cic_ia.set_custom_topic(topic)
        return jsonify({
            'success': True,
            'message': f'📌 Tema establecido: "{topic}"',
            'topic': topic,
            'note': 'Se usará en el próximo ciclo de aprendizaje'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/learning/clear-topic', methods=['POST'])
@dev_required
def dev_clear_learning_topic():
    try:
        cic_ia.clear_custom_topic()
        return jsonify({'success': True, 'message': 'Tema personalizado eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/evolution/learn-now', methods=['POST'])
@dev_required
def evolution_learn_now():
    try:
        data = request.get_json() or {}
        topic = (data.get('topic') or '').strip() or None

        if topic:
            cic_ia.set_custom_topic(topic)

        def _learn_and_count(t):
            count = cic_ia._perform_auto_learning(t)
            if count:
                cic_ia._auto_learned_session += count
                logger.info(f"🤖 Forzado: +{count} aprendidos, sesión total={cic_ia._auto_learned_session}")

        threading.Thread(target=_learn_and_count, args=(topic,), daemon=True).start()

        message_text = '🤖 Auto-aprendizaje iniciado manualmente'
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
        pagination = Memory.query.order_by(Memory.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'memories': [{
                'id': m.id, 'topic': m.topic, 'content': m.content,
                'source': m.source, 'relevance': m.relevance_score,
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
                    LearningLog.date == today).scalar() or 0,
                'auto_learned': db.session.query(db.func.sum(LearningLog.auto_learned)).filter(
                    LearningLog.date == today).scalar() or 0
            },
            'this_week': {
                'conversations': db.session.query(db.func.sum(LearningLog.count)).filter(
                    LearningLog.date >= week_ago).scalar() or 0,
                'web_searches': db.session.query(db.func.sum(LearningLog.web_searches)).filter(
                    LearningLog.date >= week_ago).scalar() or 0
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
            }
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

        return jsonify({'success': True, 'message': 'Base de datos completamente eliminada', 'deleted': counts})
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
