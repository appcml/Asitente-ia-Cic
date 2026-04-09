"""
Cic_IA v7.3 - Asistente Inteligente EVOLUTIVO
- Modos: Básico, Rápido, Avanzado
- Auto-aprendizaje web cada 1 hora
- Aprendizaje manual forzado
- Respuestas coherentes y contextuales
"""

# ========== IMPORTS ==========
import os
import json
import random
import threading
import time
import re
import logging
import urllib.parse
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, render_template_string, request, jsonify, send_from_directory, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from bs4 import BeautifulSoup

# ========== CONFIGURACIÓN ==========
app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cic-ia-secret-2024-v7')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cic_ia_v7.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DEV_USERNAME = os.environ.get('DEV_USERNAME', 'admin')
DEV_PASSWORD = os.environ.get('DEV_PASSWORD', 'CicDev2024!')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('cic_ia')

db = SQLAlchemy(app)

# ========== MODELOS ==========

class UserAccount(db.Model):
    __tablename__ = 'user_accounts'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    preferred_mode = db.Column(db.String(20), default='balanced')  # basic, fast, advanced
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'preferred_mode': self.preferred_mode,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class Memory(db.Model):
    __tablename__ = 'memories'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(50), default='unknown')  # auto_learning, web_search, manual, curiosity
    topic = db.Column(db.String(100))
    relevance_score = db.Column(db.Float, default=0.5)
    access_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'))
    intent_detected = db.Column(db.String(50))
    mode_used = db.Column(db.String(20), default='balanced')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LearningLog(db.Model):
    __tablename__ = 'learning_logs'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    count = db.Column(db.Integer, default=0, nullable=False)
    auto_learned = db.Column(db.Integer, default=0, nullable=False)

# Crear tablas
with app.app_context():
    db.create_all()

# ========== KNOWLEDGE BASE AMPLIADA ==========

KNOWLEDGE_BASE = {
    'ia': {
        'basic': "La IA es la inteligencia artificial.",
        'fast': "La IA permite a las máquinas aprender y razonar como humanos.",
        'advanced': """La Inteligencia Artificial (IA) es la simulación de procesos de inteligencia humana por sistemas informáticos. 
        
Incluye:
• Machine Learning: Aprendizaje automático a partir de datos
• Deep Learning: Redes neuronales profundas
• Procesamiento de lenguaje natural
• Visión por computadora
• Robótica inteligente

Aplicaciones actuales: asistentes virtuales, diagnóstico médico, vehículos autónomos, traducción automática, generación de contenido."""
    },
    'python': {
        'basic': "Python es un lenguaje de programación.",
        'fast': "Python es el lenguaje líder en IA por su sintaxis simple y librerías como TensorFlow.",
        'advanced': """Python es un lenguaje de programación de alto nivel, interpretado y de propósito general.

Características:
• Sintaxis clara y legible
• Tipado dinámico
• Gran ecosistema de librerías (NumPy, Pandas, TensorFlow, PyTorch)
• Multiplataforma
• Comunidad activa

Uso en IA: prototipado rápido, análisis de datos, machine learning, deep learning, automatización."""
    },
    'hola': {
        'basic': "¡Hola!",
        'fast': "¡Hola! Soy Cic_IA, tu asistente inteligente. ¿En qué puedo ayudarte?",
        'advanced': "¡Hola! Soy Cic_IA, tu asistente con auto-aprendizaje. Puedo responder en modo básico, rápido o avanzado. ¿Qué necesitas saber?"
    },
    'cic_ia': {
        'basic': "Soy Cic_IA.",
        'fast': "Soy Cic_IA, un asistente IA que aprende automáticamente cada hora.",
        'advanced': """Soy Cic_IA v7.3, una inteligencia artificial evolutiva con las siguientes capacidades:

• Auto-aprendizaje web cada 1 hora
• Tres modos de respuesta: Básico, Rápido y Avanzado
• Memoria persistente de conversaciones
• Aprendizaje manual forzado (modo dev)
• Búsqueda en tiempo real cuando no tengo información

Modos disponibles:
- BÁSICO: Respuestas simples y directas
- RÁPIDO: Respuestas concisas pero informativas  
- AVANZADO: Respuestas detalladas con contexto y ejemplos"""
    },
    'default': {
        'basic': "No tengo información sobre {tema}.",
        'fast': "Voy a buscar información sobre {tema} para ayudarte.",
        'advanced': "No tengo información específica sobre '{tema}' en mi base de conocimiento. Permíteme buscar en fuentes externas para darte una respuesta completa y actualizada."
    }
}

# ========== BÚSQUEDA WEB MEJORADA ==========

class WebSearchEngine:
    @staticmethod
    def search(query, max_results=5):
        logger.info(f"🔍 Buscando: '{query}'")
        
        # Intentar DuckDuckGo primero
        try:
            results = WebSearchEngine._search_duckduckgo(query, max_results)
            if results:
                logger.info(f"✅ DuckDuckGo: {len(results)} resultados")
                return results
        except Exception as e:
            logger.warning(f"⚠️ DuckDuckGo falló: {e}")
        
        # Fallback a Wikipedia
        try:
            results = WebSearchEngine._search_wikipedia(query, max_results)
            if results:
                logger.info(f"✅ Wikipedia: {len(results)} resultados")
                return results
        except Exception as e:
            logger.warning(f"⚠️ Wikipedia falló: {e}")
        
        return []
    
    @staticmethod
    def _search_duckduckgo(query, max_results):
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        for result in soup.find_all('div', class_='result')[:max_results]:
            try:
                title_elem = result.find('a', class_='result__a')
                snippet_elem = result.find('a', class_='result__snippet')
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    url_result = title_elem.get('href', '')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else title
                    
                    if url_result.startswith('/'):
                        match = re.search(r'uddg=([^&]+)', url_result)
                        if match:
                            url_result = urllib.parse.unquote(match.group(1))
                    
                    results.append({
                        'title': title,
                        'url': url_result if url_result.startswith('http') else f'https://duckduckgo.com{url_result}',
                        'snippet': snippet
                    })
            except:
                continue
        
        return results
    
    @staticmethod
    def _search_wikipedia(query, max_results):
        search_query = urllib.parse.quote(query)
        url = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={search_query}&format=json&srlimit={max_results}"
        
        headers = {'User-Agent': 'Cic_IA/1.0'}
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        results = []
        for item in data.get('query', {}).get('search', []):
            title = item.get('title', '')
            snippet = item.get('snippet', '').replace('<span class="searchmatch">', '').replace('</span>', '')
            
            results.append({
                'title': f"{title} - Wikipedia",
                'url': f"https://es.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                'snippet': snippet
            })
        
        return results

# ========== CLASE PRINCIPAL CIC_IA ==========

class CicIA:
    def __init__(self):
        self.learning_active = True
        self.web_search = WebSearchEngine()
        self.auto_learning_topics = [
            'inteligencia artificial aplicaciones 2024',
            'machine learning casos de uso',
            'python tutorial avanzado',
            'desarrollo web tendencias',
            'ciencia de datos ejemplos reales',
            'neurociencia cognitiva',
            'computación cuántica avances',
            'ciberseguridad mejores prácticas',
            'blockchain casos de uso',
            'internet de las cosas ejemplos',
            'procesamiento de lenguaje natural',
            'visión por computadora aplicaciones',
            'robótica inteligente',
            'ética en inteligencia artificial',
            'automatización con python'
        ]
        
        with app.app_context():
            self.stats = {
                'memories': Memory.query.count(),
                'conversations': Conversation.query.count(),
                'users': UserAccount.query.count()
            }
        
        self._start_auto_learning()
        self._print_startup()
    
    def _print_startup(self):
        logger.info("=" * 60)
        logger.info("🚀 CIC_IA v7.3 - INICIADO")
        logger.info(f"📚 Memorias: {self.stats['memories']}")
        logger.info(f"👥 Usuarios: {self.stats['users']}")
        logger.info(f"🧠 Auto-aprendizaje: CADA 1 HORA")
        logger.info(f"⚡ Modos: BÁSICO | RÁPIDO | AVANZADO")
        logger.info("=" * 60)
    
    def _start_auto_learning(self):
        """Inicia el hilo de auto-aprendizaje cada 1 hora"""
        def learning_loop():
            time.sleep(30)
            while self.learning_active:
                try:
                    self._auto_learn()
                except Exception as e:
                    logger.error(f"Error auto-aprendizaje: {e}")
                time.sleep(3600)
        
        thread = threading.Thread(target=learning_loop, daemon=True)
        thread.name = "AutoLearning"
        thread.start()
        logger.info("⏰ Auto-aprendizaje activado (cada 1 hora)")
    
    def _auto_learn(self, custom_topic=None):
        """Realiza el aprendizaje automático"""
        with app.app_context():
            topic = custom_topic or random.choice(self.auto_learning_topics)
            logger.info(f"🤖 Auto-aprendizaje: '{topic}'")
            
            results = self.web_search.search(topic, max_results=3)
            if not results:
                logger.warning(f"⚠️ Sin resultados para '{topic}'")
                return 0
            
            learned = 0
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
                        relevance_score=0.6
                    )
                    db.session.add(memory)
                    db.session.commit()
                    learned += 1
                    logger.info(f"✅ Aprendido: {result['title'][:50]}...")
                    
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"❌ Error guardando: {e}")
                    continue
            
            if learned > 0:
                today = date.today()
                log = LearningLog.query.filter_by(date=today).first()
                if not log:
                    log = LearningLog(date=today, count=0, auto_learned=0)
                    db.session.add(log)
                    db.session.commit()
                
                current = log.auto_learned if log.auto_learned is not None else 0
                log.auto_learned = current + learned
                db.session.commit()
            
            return learned
    
    def predict_intent(self, text):
        """Predice la intención del mensaje"""
        text_lower = text.lower()
        intents = {
            'greeting': ['hola', 'buenas', 'saludos', 'hey', 'hi', 'buenos dias', 'buenas tardes', 'buenas noches'],
            'question': ['que', 'qué', 'como', 'cómo', 'cuando', 'cuándo', 'donde', 'dónde', 'por que', 'por qué', 'porque', 'cual', 'cuál', '?'],
            'definition': ['definicion', 'definición', 'que es', 'qué es', 'significa', 'significado', 'concepto'],
            'usage': ['usos', 'aplicaciones', 'para que sirve', 'cómo se usa', 'ejemplos', 'casos de uso', 'donde se usa'],
            'comparison': ['diferencia', 'comparacion', 'comparación', 'versus', 'vs', 'mejor que', 'peor que'],
            'tutorial': ['tutorial', 'guia', 'guía', 'paso a paso', 'como hacer', 'cómo hacer', 'aprender', 'enseñame'],
            'farewell': ['adios', 'adiós', 'chao', 'hasta luego', 'nos vemos', 'bye'],
            'thanks': ['gracias', 'thank', 'thanks', 'agradecido', 'te agradezco'],
            'identity': ['quien eres', 'que eres', 'tu nombre', 'cic_ia', 'cic-ia', 'presentate', 'presentación']
        }
        
        scores = {intent: sum(2 for kw in keywords if kw in text_lower) 
                  for intent, keywords in intents.items()}
        scores = {k: v for k, v in scores.items() if v > 0}
        
        if scores:
            best = max(scores, key=scores.get)
            return {'intent': best, 'confidence': min(0.4 + scores[best] * 0.15, 0.95)}
        
        return {'intent': 'general', 'confidence': 0.3}
    
    def extract_topic(self, text, intent):
        """Extrae el tema principal de la pregunta"""
        text_lower = text.lower()
        
        # Patrones comunes
        patterns = [
            r'(?:qué es|que es|define|significa)\s+(.+?)(?:\?|$)',
            r'(?:usos de|aplicaciones de)\s+(.+?)(?:\?|$)',
            r'(?:cómo|cómo se|como se)\s+(.+?)(?:\?|$)',
            r'(?:diferencia entre|comparación de)\s+(.+?)(?:\?|$)',
            r'(?:tutorial de|guía de|guia de)\s+(.+?)(?:\?|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                return match.group(1).strip()
        
        # Si no hay patrón, quitar palabras comunes
        common_words = ['el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'en', 'con', 'por', 'para', 'es', 'son']
        words = [w for w in text_lower.split() if w not in common_words and len(w) > 3]
        return ' '.join(words[:3]) if words else text_lower[:30]
    
    def find_best_topic(self, text):
        """Encuentra el mejor tema en la base de conocimiento"""
        text_lower = text.lower()
        
        for topic, data in KNOWLEDGE_BASE.items():
            if topic == 'default':
                continue
            # Verificar keywords o coincidencia exacta
            keywords = ['ia', 'inteligencia artificial', 'machine learning'] if topic == 'ia' else \
                      ['python', 'programacion', 'codigo'] if topic == 'python' else \
                      ['hola', 'saludos', 'buenas'] if topic == 'hola' else \
                      ['cic_ia', 'quien eres', 'que eres', 'tu nombre'] if topic == 'cic_ia' else []
            
            if any(kw in text_lower for kw in keywords):
                return topic
        
        return None
    
    def find_relevant_memories(self, query, min_relevance=1):
        """Busca memorias relevantes con scoring mejorado"""
        query_words = set(query.lower().split())
        memories = Memory.query.all()
        scored_memories = []
        
        for mem in memories:
            mem_words = set(mem.content.lower().split())
            overlap = len(query_words & mem_words)
            
            # Bonus por palabras en el tópico
            topic_bonus = 2 if mem.topic and any(w in mem.topic.lower() for w in query_words) else 0
            
            score = overlap + topic_bonus
            
            if score >= min_relevance:
                scored_memories.append((mem, score))
                mem.access_count += 1
        
        if scored_memories:
            db.session.commit()
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            return [m for m, _ in scored_memories[:3]]
        
        return []
    
    def format_web_result(self, result, mode):
        """Formatea resultado web según el modo"""
        if mode == 'basic':
            return result['snippet'][:100] if len(result['snippet']) > 100 else result['snippet']
        elif mode == 'fast':
            return f"{result['title']}: {result['snippet'][:200]}"
        else:  # advanced
            return f"**{result['title']}**\n\n{result['snippet']}\n\n📖 Fuente: {result['url']}"
    
    def generate_response(self, user_input, intent_info, mode='balanced'):
        """Genera la respuesta según el modo seleccionado"""
        input_lower = user_input.lower().strip()
        
        # Mapear modos
        mode_map = {
            'basic': 'basic',
            'basico': 'basic',
            'rápido': 'fast',
            'rapido': 'fast',
            'fast': 'fast',
            'avanzado': 'advanced',
            'advanced': 'advanced',
            'balanced': 'fast'
        }
        actual_mode = mode_map.get(mode, 'fast')
        
        # Respuesta a fecha/hora
        if any(kw in input_lower for kw in ['qué día', 'que dia', 'qué hora', 'que hora', 'fecha', 'hora actual', 'hoy es']):
            now = datetime.now()
            dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            
            if actual_mode == 'basic':
                return f"Hoy es {now.day}/{now.month}/{now.year}"
            elif actual_mode == 'fast':
                return f"📅 {dias[now.weekday()]}, {now.day} de {meses[now.month-1]} - 🕐 {now.strftime('%H:%M')}"
            else:
                return f"📅 Hoy es {dias[now.weekday()]}, {now.day} de {meses[now.month-1]} de {now.year}\n🕐 Son las {now.strftime('%H:%M:%S')}\n📍 Zona horaria: UTC"
        
        # Buscar en knowledge base primero
        best_topic = self.find_best_topic(input_lower)
        if best_topic:
            return KNOWLEDGE_BASE[best_topic][actual_mode]
        
        # Buscar en memorias
        relevant = self.find_relevant_memories(user_input, min_relevance=2)
        if relevant:
            mem = relevant[0]
            content = mem.content
            
            if actual_mode == 'basic':
                # Solo la primera oración
                sentences = content.split('.')
                return sentences[0] + '.' if sentences else content[:100]
            elif actual_mode == 'fast':
                # Primer párrafo
                paragraphs = content.split('\n\n')
                return paragraphs[0][:250] if paragraphs else content[:250]
            else:
                # Contenido completo con fuente
                return f"{content}\n\n📚 Aprendido de: {mem.source}"
        
        # Buscar en web
        web_results = self.web_search.search(user_input, max_results=3 if actual_mode == 'advanced' else 2)
        if web_results:
            responses = []
            for i, result in enumerate(web_results, 1):
                formatted = self.format_web_result(result, actual_mode)
                responses.append(f"{i}. {formatted}" if actual_mode == 'advanced' else formatted)
                
                # Guardar en memoria
                try:
                    memory = Memory(
                        content=f"{result['title']}\n\n{result['snippet']}\n\nFuente: {result['url']}",
                        source='web_search',
                        topic=self.extract_topic(user_input, intent_info['intent']),
                        relevance_score=0.7
                    )
                    db.session.add(memory)
                    db.session.commit()
                except:
                    pass
            
            if actual_mode == 'advanced':
                return f"He investigado sobre esto:\n\n" + "\n\n".join(responses)
            elif actual_mode == 'fast':
                return responses[0]
            else:
                return responses[0][:100]
        
        # Respuesta por defecto
        tema = self.extract_topic(user_input, intent_info['intent'])
        return KNOWLEDGE_BASE['default'][actual_mode].format(tema=tema)
    
    def process_chat(self, user_input, user_id=None, mode='balanced'):
        """Procesa el mensaje del usuario"""
        intent_info = self.predict_intent(user_input)
        response = self.generate_response(user_input, intent_info, mode)
        
        # Guardar conversación
        with app.app_context():
            conv = Conversation(
                user_message=user_input,
                bot_response=response,
                user_id=user_id,
                intent_detected=intent_info['intent'],
                mode_used=mode
            )
            db.session.add(conv)
            
            # Actualizar contador diario
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            if not log:
                log = LearningLog(date=today, count=0, auto_learned=0)
                db.session.add(log)
                db.session.commit()
            
            current = log.count if log.count is not None else 0
            log.count = current + 1
            db.session.commit()
            
            total_mem = Memory.query.count()
        
        return {
            'response': response,
            'intent': intent_info['intent'],
            'confidence': intent_info['confidence'],
            'mode': mode,
            'total_memories': total_mem
        }
    
    def force_learn(self, topic, content=None):
        """Forzar aprendizaje de un tema específico (modo dev)"""
        logger.info(f"🎯 Forzando aprendizaje: '{topic}'")
        
        if content:
            # Aprendizaje manual directo
            with app.app_context():
                try:
                    memory = Memory(
                        content=content,
                        source='manual',
                        topic=topic,
                        relevance_score=0.9
                    )
                    db.session.add(memory)
                    db.session.commit()
                    logger.info(f"✅ Aprendido manualmente: {topic[:50]}")
                    return {'success': True, 'topic': topic, 'learned_count': 1, 'source': 'manual'}
                except Exception as e:
                    db.session.rollback()
                    return {'success': False, 'error': str(e)}
        else:
            # Búsqueda web
            count = self._auto_learn(custom_topic=topic)
            return {'success': True, 'topic': topic, 'learned_count': count, 'source': 'web_search'}
    
    def get_stats(self):
        """Obtiene estadísticas del sistema"""
        with app.app_context():
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            
            return {
                'total_memories': Memory.query.count(),
                'total_conversations': Conversation.query.count(),
                'total_users': UserAccount.query.count(),
                'today_conversations': log.count if log and log.count else 0,
                'today_learned': log.auto_learned if log and log.auto_learned else 0,
                'by_source': {
                    'auto_learning': Memory.query.filter_by(source='auto_learning').count(),
                    'web_search': Memory.query.filter_by(source='web_search').count(),
                    'manual': Memory.query.filter_by(source='manual').count()
                },
                'by_mode': {
                    'basic': Conversation.query.filter_by(mode_used='basic').count(),
                    'fast': Conversation.query.filter_by(mode_used='fast').count(),
                    'advanced': Conversation.query.filter_by(mode_used='advanced').count()
                }
            }

# Instancia global
cic_ia = CicIA()

# ========== DECORADORES ==========

def dev_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('dev_mode') and session.get('dev_username') == DEV_USERNAME:
            return f(*args, **kwargs)
        return jsonify({'error': 'No autorizado - Modo desarrollador requerido'}), 401
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'No autenticado'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

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
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = UserAccount.query.filter_by(username=username, is_active=True).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['preferred_mode'] = user.preferred_mode
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('chat_page'))
        
        error = 'Credenciales inválidas'
    
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        mode = request.form.get('mode', 'balanced')
        
        if len(username) < 3:
            error = 'Usuario mínimo 3 caracteres'
        elif len(password) < 6:
            error = 'Contraseña mínimo 6 caracteres'
        elif '@' not in email:
            error = 'Email inválido'
        elif UserAccount.query.filter_by(username=username).first():
            error = 'Usuario ya existe'
        elif UserAccount.query.filter_by(email=email).first():
            error = 'Email ya registrado'
        else:
            try:
                user = UserAccount(username=username, email=email, preferred_mode=mode)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                return redirect(url_for('login_page'))
            except Exception as e:
                db.session.rollback()
                error = f'Error: {str(e)}'
    
    return render_template_string(REGISTER_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/dev-login', methods=['GET', 'POST'])
def dev_login_page():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == DEV_USERNAME and password == DEV_PASSWORD:
            session['dev_mode'] = True
            session['dev_username'] = DEV_USERNAME
            session.permanent = True
            return redirect(url_for('dev_dashboard'))
        
        error = 'Credenciales inválidas'
    
    return render_template_string(DEV_LOGIN_TEMPLATE, error=error)

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
                                is_dev=session.get('dev_mode', False),
                                current_mode=session.get('preferred_mode', 'balanced'))

@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400
        
        message = data.get('message', '').strip()
        mode = data.get('mode', session.get('preferred_mode', 'balanced'))
        
        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        user_id = session.get('user_id')
        result = cic_ia.process_chat(message, user_id=user_id, mode=mode)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error en chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def api_status():
    try:
        stats = cic_ia.get_stats()
        return jsonify({
            'status': 'online',
            'version': '7.3',
            **stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '7.3.0'
    })

# ========== RUTAS DESARROLLADOR ==========

@app.route('/dev')
@dev_required
def dev_dashboard():
    return render_template_string(DEV_DASHBOARD_TEMPLATE)

@app.route('/api/dev/stats')
@dev_required
def dev_stats():
    try:
        stats = cic_ia.get_stats()
        recent_memories = Memory.query.order_by(Memory.created_at.desc()).limit(10).all()
        recent_conversations = Conversation.query.order_by(Conversation.timestamp.desc()).limit(10).all()
        
        return jsonify({
            'system': {
                'version': '7.3',
                'timestamp': datetime.utcnow().isoformat()
            },
            'stats': stats,
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
                'mode': c.mode_used,
                'timestamp': c.timestamp.isoformat() if c.timestamp else None
            } for c in recent_conversations]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/force-learn', methods=['POST'])
@dev_required
def dev_force_learn():
    try:
        data = request.get_json()
        topic = data.get('topic', '').strip() if data else ''
        content = data.get('content', '').strip() if data else None
        
        if not topic:
            return jsonify({'error': 'Tema requerido'}), 400
        
        result = cic_ia.force_learn(topic, content)
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
                'access_count': m.access_count,
                'created_at': m.created_at.isoformat() if m.created_at else None
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
                        preferred_mode='advanced'
                    )
                    test_user.set_password('test123')
                    db.session.add(test_user)
                    db.session.commit()
                
                session['user_id'] = test_user.id
                session['username'] = test_user.username
            
            return jsonify({
                'success': True,
                'mode': 'user',
                'redirect': '/chat'
            })
        else:
            session['dev_mode'] = True
            session.pop('user_id', None)
            return jsonify({
                'success': True,
                'mode': 'dev',
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
    return jsonify({'error': 'Error interno del servidor'}), 500

# ========== TEMPLATES ==========

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
        .container {
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
        input, select {
            width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0;
            border-radius: 10px; font-size: 16px;
        }
        input:focus, select:focus { outline: none; border-color: #667eea; }
        .btn {
            width: 100%; padding: 14px; background: #667eea; color: white;
            border: none; border-radius: 10px; font-size: 16px; font-weight: 600;
            cursor: pointer;
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
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>🧠 Cic_IA</h1>
            <p>Asistente Inteligente Evolutivo</p>
        </div>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST" action="/login">
            <div class="form-group">
                <label>Usuario</label>
                <input type="text" name="username" required placeholder="Tu nombre de usuario">
            </div>
            <div class="form-group">
                <label>Contraseña</label>
                <input type="password" name="password" required placeholder="Tu contraseña">
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
        .container {
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
        input, select {
            width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0;
            border-radius: 10px; font-size: 16px;
        }
        input:focus, select:focus { outline: none; border-color: #667eea; }
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
        .mode-info {
            font-size: 12px; color: #666; margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>🧠 Cic_IA</h1>
            <p>Crear nueva cuenta</p>
        </div>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST" action="/register">
            <div class="form-group">
                <label>Usuario *</label>
                <input type="text" name="username" required minlength="3" placeholder="Mínimo 3 caracteres">
            </div>
            <div class="form-group">
                <label>Email *</label>
                <input type="email" name="email" required placeholder="tu@email.com">
            </div>
            <div class="form-group">
                <label>Contraseña *</label>
                <input type="password" name="password" required minlength="6" placeholder="Mínimo 6 caracteres">
            </div>
            <div class="form-group">
                <label>Modo preferido</label>
                <select name="mode">
                    <option value="balanced">⚡ Rápido (recomendado)</option>
                    <option value="basic">🔹 Básico</option>
                    <option value="advanced">🔸 Avanzado</option>
                </select>
                <p class="mode-info">Básico: respuestas simples | Rápido: equilibrado | Avanzado: detallado</p>
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
        .container {
            background: #0f3460;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            width: 100%;
            max-width: 400px;
            border: 2px solid #e94560;
        }
        .logo { text-align: center; margin-bottom: 30px; }
        .logo h1 { font-size: 2em; color: #e94560; }
        .logo p { color: #eaeaea; margin-top: 10px; font-family: monospace; }
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
        input {
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
    <div class="container">
        <div class="logo">
            <h1>⚡ DEV MODE</h1>
            <p>Cic_IA v7.3 - Panel de Control</p>
        </div>
        <div class="warning">
            ⚠️ Acceso restringido. Permite forzar aprendizaje, ver memorias y gestionar usuarios.
        </div>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST" action="/dev-login">
            <div class="form-group">
                <label>Usuario Dev</label>
                <input type="text" name="username" required placeholder="admin">
            </div>
            <div class="form-group">
                <label>Contraseña</label>
                <input type="password" name="password" required placeholder="••••••••">
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
        .mode-selector {
            padding: 5px 10px;
            border-radius: 15px;
            border: 1px solid #e0e0e0;
            font-size: 13px;
            cursor: pointer;
        }
        .mode-badge {
            background: #ffebee;
            color: #c62828;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 12px;
        }
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
            white-space: pre-wrap;
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
            align-items: center;
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
            padding: 15px 20px;
            color: #888;
        }
        .typing.active { display: block; }
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
            <select class="mode-selector" id="mode-selector" onchange="changeMode(this.value)">
                <option value="basic" {% if current_mode == 'basic' %}selected{% endif %}>🔹 Básico</option>
                <option value="balanced" {% if current_mode in ['balanced', 'fast'] %}selected{% endif %}>⚡ Rápido</option>
                <option value="advanced" {% if current_mode == 'advanced' %}selected{% endif %}>🔸 Avanzado</option>
            </select>
            {% if is_dev %}
            <span class="mode-badge">🔴 DEV</span>
            <a href="/dev" class="btn-small btn-dev">Panel Dev</a>
            {% endif %}
            <a href="/logout" class="btn-small btn-logout">Salir</a>
        </div>
    </div>
    
    <div class="chat-container" id="chat-container">
        <div class="welcome">
            <h2>¡Hola, {{ username }}! 👋</h2>
            <p>Soy Cic_IA. Selecciona tu modo de respuesta arriba y empieza a conversar.</p>
            <div class="suggestions">
                <span class="suggestion" onclick="sendSuggestion('¿Qué es la inteligencia artificial?')">¿Qué es la IA?</span>
                <span class="suggestion" onclick="sendSuggestion('¿Cuáles son los usos de la IA?')">Usos de IA</span>
                <span class="suggestion" onclick="sendSuggestion('Explícame Python')">Python</span>
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
        let currentMode = '{{ current_mode }}';
        const chatContainer = document.getElementById('chat-container');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const typing = document.getElementById('typing');
        
        function changeMode(mode) {
            currentMode = mode;
            addMessage(`Modo cambiado a: ${mode === 'basic' ? '🔹 Básico' : mode === 'advanced' ? '🔸 Avanzado' : '⚡ Rápido'}`, false);
        }
        
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
        
        async function sendMessage() {
            const text = messageInput.value.trim();
            if (!text) return;
            
            addMessage(text, true);
            messageInput.value = '';
            sendBtn.disabled = true;
            typing.classList.add('active');
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, mode: currentMode })
                });
                
                const data = await response.json();
                typing.classList.remove('active');
                
                if (data.error) {
                    addMessage('❌ Error: ' + data.error);
                } else {
                    addMessage(data.response);
                }
            } catch (e) {
                typing.classList.remove('active');
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
        .input-group input, .input-group textarea {
            width: 100%; padding: 12px; background: #0f172a;
            border: 1px solid #334155; border-radius: 8px;
            color: #e2e8f0; font-size: 14px;
        }
        .input-group textarea { min-height: 100px; resize: vertical; }
        .memory-list { max-height: 400px; overflow-y: auto; }
        .memory-item {
            background: #0f172a;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 10px;
            border-left: 4px solid #60a5fa;
        }
        .memory-item.auto_learning { border-color: #4ade80; }
        .memory-item.manual { border-color: #f59e0b; }
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
        <h1><span>⚡</span> Cic_IA v7.3 - Panel de Desarrollador</h1>
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
            <div class="grid" style="margin-top: 25px;">
                <div class="card">
                    <h2>📈 Por Modo de Respuesta</h2>
                    <div id="mode-stats"><div class="loading"></div></div>
                </div>
                <div class="card">
                    <h2>📊 Por Fuente de Aprendizaje</h2>
                    <div id="source-stats"><div class="loading"></div></div>
                </div>
            </div>
        </div>
        
        <div id="tab-learning" class="tab-content">
            <div class="grid">
                <div class="card">
                    <h2>🌐 Forzar Aprendizaje Web</h2>
                    <div class="input-group">
                        <label>Tema a buscar y aprender</label>
                        <input type="text" id="learn-topic-web" placeholder="Ej: inteligencia artificial 2024">
                    </div>
                    <button class="btn-action" onclick="forceLearnWeb()">🌐 Buscar y Aprender</button>
                    <div id="learn-result-web"></div>
                </div>
                <div class="card">
                    <h2>📝 Aprendizaje Manual</h2>
                    <div class="input-group">
                        <label>Tema</label>
                        <input type="text" id="learn-topic-manual" placeholder="Ej: Mi empresa">
                    </div>
                    <div class="input-group">
                        <label>Contenido completo</label>
                        <textarea id="learn-content-manual" placeholder="Escribe aquí toda la información que quieres que aprenda la IA..."></textarea>
                    </div>
                    <button class="btn-action" onclick="forceLearnManual()" style="background: #f59e0b;">📝 Guardar Manualmente</button>
                    <div id="learn-result-manual"></div>
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
        }
        
        async function loadStats() {
            try {
                const res = await fetch('/api/dev/stats');
                const data = await res.json();
                if (data.error) return;
                
                document.getElementById('stat-memories').textContent = data.stats?.total_memories || 0;
                document.getElementById('stat-users').textContent = data.stats?.total_users || 0;
                document.getElementById('stat-conversations').textContent = data.stats?.today_conversations || 0;
                document.getElementById('stat-auto').textContent = data.stats?.today_learned || 0;
                
                if (data.stats?.by_source) {
                    const s = data.stats.by_source;
                    document.getElementById('source-stats').innerHTML = `
                        <div style="display: grid; gap: 10px;">
                            <div>🤖 Auto: <strong>${s.auto_learning || 0}</strong></div>
                            <div>🌐 Web: <strong>${s.web_search || 0}</strong></div>
                            <div>📝 Manual: <strong>${s.manual || 0}</strong></div>
                        </div>
                    `;
                }
                
                if (data.stats?.by_mode) {
                    const m = data.stats.by_mode;
                    document.getElementById('mode-stats').innerHTML = `
                        <div style="display: grid; gap: 10px;">
                            <div>🔹 Básico: <strong>${m.basic || 0}</strong></div>
                            <div>⚡ Rápido: <strong>${m.fast || 0}</strong></div>
                            <div>🔸 Avanzado: <strong>${m.advanced || 0}</strong></div>
                        </div>
                    `;
                }
            } catch (e) {
                console.error('Error cargando stats:', e);
            }
        }
        
        async function forceLearnWeb() {
            const topic = document.getElementById('learn-topic-web').value.trim();
            if (!topic) return alert('Ingresa un tema');
            
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Buscando...';
            
            try {
                const res = await fetch('/api/dev/force-learn', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ topic })
                });
                
                const data = await res.json();
                const resultDiv = document.getElementById('learn-result-web');
                
                if (data.success) {
                    resultDiv.innerHTML = `<div class="result-box">✅ <strong>Éxito!</strong><br>Tema: ${data.topic}<br>Elementos: ${data.learned_count}<br>Fuente: ${data.source}</div>`;
                    loadStats();
                    loadMemories();
                } else {
                    resultDiv.innerHTML = `<div class="result-box error">❌ ${data.error}</div>`;
                }
            } catch (e) {
                document.getElementById('learn-result-web').innerHTML = `<div class="result-box error">Error: ${e.message}</div>`;
            }
            
            btn.disabled = false;
            btn.textContent = '🌐 Buscar y Aprender';
        }
        
        async function forceLearnManual() {
            const topic = document.getElementById('learn-topic-manual').value.trim();
            const content = document.getElementById('learn-content-manual').value.trim();
            
            if (!topic || !content) return alert('Ingresa tema y contenido');
            
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Guardando...';
            
            try {
                const res = await fetch('/api/dev/force-learn', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ topic, content })
                });
                
                const data = await res.json();
                const resultDiv = document.getElementById('learn-result-manual');
                
                if (data.success) {
                    resultDiv.innerHTML = `<div class="result-box">✅ <strong>Guardado!</strong><br>Tema: ${data.topic}<br>Fuente: ${data.source}</div>`;
                    document.getElementById('learn-topic-manual').value = '';
                    document.getElementById('learn-content-manual').value = '';
                    loadStats();
                    loadMemories();
                } else {
                    resultDiv.innerHTML = `<div class="result-box error">❌ ${data.error}</div>`;
                }
            } catch (e) {
                document.getElementById('learn-result-manual').innerHTML = `<div class="result-box error">Error: ${e.message}</div>`;
            }
            
            btn.disabled = false;
            btn.textContent = '📝 Guardar Manualmente';
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
                            <tr><th>ID</th><th>Usuario</th><th>Email</th><th>Modo</th><th>Registro</th><th>Último Login</th></tr>
                        </thead>
                        <tbody>
                            ${data.users.map(u => `
                                <tr>
                                    <td>${u.id}</td>
                                    <td><strong>${u.username}</strong></td>
                                    <td>${u.email}</td>
                                    <td>${u.preferred_mode}</td>
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

# ========== INICIALIZACIÓN ==========

application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
