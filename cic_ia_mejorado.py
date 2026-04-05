"""
Cic_IA - Asistente Inteligente MEJORADO con Búsqueda Web Autónoma
✅ Interfaz tipo ChatGPT/Claude
✅ Modo desarrollador con autenticación
✅ Adjuntar documentos e imágenes
✅ Sistema de memoria y aprendizaje
✅ NUEVO: Búsqueda web autónoma con DuckDuckGo
✅ NUEVO: Análisis semántico de respuestas
✅ NUEVO: Aprendizaje continuo mejorado
✅ NUEVO: Auto-aprendizaje cada 6 horas
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
import urllib.request
import urllib.parse
import re
import hashlib
import requests
from bs4 import BeautifulSoup
import logging
from sqlalchemy import select

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cic-ia-secret-2024')

# Configuración de Base de Datos
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cic_ia.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración de Uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'py', 'js', 'html', 'css', 'json'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ============ MODELOS ============

class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(50), default='local')  # local, wikipedia, web, user_taught, auto_learning
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
    auto_learned = db.Column(db.Integer, default=0)  # NUEVO: Contador de auto-aprendizaje

class DeveloperSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_access = db.Column(db.DateTime, default=datetime.utcnow)

class WebSearchCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(500), unique=True)
    results = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

class KnowledgeEvolution(db.Model):  # NUEVO: Trackear evolución del conocimiento
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    topic = db.Column(db.String(200))
    action = db.Column(db.String(50))  # 'learned', 'updated', 'forgotten'
    old_content = db.Column(db.Text)
    new_content = db.Column(db.Text)
    source = db.Column(db.String(50))

# Crear tablas
with app.app_context():
    db.create_all()
    print("✅ Base de datos inicializada")

# ============ CONFIGURACIÓN DESARROLLADOR ============
DEV_PASSWORD_HASH = hashlib.sha256("CicDev2024!".encode()).hexdigest()

def verify_dev_token(token):
    if not token:
        return False
    with app.app_context():
        session = DeveloperSession.query.filter_by(token=token).first()
        if session:
            session.last_access = datetime.utcnow()
            db.session.commit()
            return True
    return False

# ============ BÚSQUEDA WEB AUTÓNOMA ============

class WebSearchEngine:
    @staticmethod
    def search_duckduckgo(query, max_results=5):
        try:
            try:
                from duckduckgo_search import DDGS
                results = []
                with DDGS() as ddgs:
                    for result in ddgs.text(query, max_results=max_results):
                        results.append({
                            'title': result.get('title'),
                            'url': result.get('href'),
                            'snippet': result.get('body'),
                            'source': 'duckduckgo'
                        })
                return results
            except ImportError:
                logger.warning("duckduckgo-search no instalada, usando fallback")
                return WebSearchEngine._search_fallback(query, max_results)
        except Exception as e:
            logger.error(f"Error en búsqueda DuckDuckGo: {e}")
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
                            'title': title_elem.get_text(),
                            'url': title_elem.get('href', ''),
                            'snippet': snippet_elem.get_text(),
                            'source': 'duckduckgo'
                        })
                except:
                    continue
            return results
        except Exception as e:
            logger.error(f"Error en fallback de búsqueda: {e}")
            return []

# ============ BASE DE CONOCIMIENTO ============
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
            "¡Hola! Soy Cic_IA, tu asistente inteligente. ¿En qué puedo ayudarte hoy?",
            "¡Bienvenido! Estoy lista para aprender y asistirte."
        ],
        'keywords': ['hola', 'buenas', 'hey', 'saludos']
    },
    'fecha_hora': {
        'respuestas': ['DYNAMIC_DATE'],
        'keywords': ['qué día', 'qué hora', 'fecha', 'hora actual', 'hoy es']
    },
    'cic_ia': {
        'respuestas': [
            "Soy Cic_IA, una inteligencia artificial en desarrollo creada para aprender y asistir.",
            "Cic_IA está construida con Python y Flask, con búsqueda web autónoma y aprendizaje continuo."
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

# ============ CLASE CIC_IA MEJORADA ============
class CicIA:
    def __init__(self):
        self.learning_active = True
        self.web_search_engine = WebSearchEngine()
        
        # Temas para auto-aprendizaje continuo
        self.auto_learning_topics = [
            'inteligencia artificial noticias 2024',
            'machine learning avances',
            'python programación novedades',
            'tecnología futuro',
            'ciencia de datos tendencias',
            'deep learning aplicaciones',
            'IA ética y regulación',
            'computación cuántica',
            'robótica avances',
            'procesamiento lenguaje natural',
            'visión artificial',
            'redes neuronales',
            'big data analytics',
            'cloud computing tendencias',
            'ciberseguridad IA'
        ]
        
        with app.app_context():
            self.stats = {
                'memories': Memory.query.count(),
                'conversations': Conversation.query.count(),
                'today_learned': self._get_today_count(),
                'auto_learned_total': self._get_auto_learned_total()
            }
        
        # Iniciar threads
        threading.Thread(target=self._auto_learn_loop, daemon=True).start()
        threading.Thread(target=self._auto_web_search_loop, daemon=True).start()
        threading.Thread(target=self._continuous_learning_loop, daemon=True).start()  # NUEVO
        
        print("=" * 60)
        print("🚀 CIC_IA MEJORADA INICIADA")
        print(f"📚 Memorias: {self.stats['memories']}")
        print(f"💬 Conversaciones: {self.stats['conversations']}")
        print(f"📈 Aprendidos hoy: {self.stats['today_learned']}")
        print(f"🤖 Auto-aprendidos total: {self.stats['auto_learned_total']}")
        print("🌐 Búsqueda web: ACTIVADA")
        print("🧠 Auto-aprendizaje: ACTIVADO (cada 6 horas)")
        print("=" * 60)
    
    def _get_today_count(self):
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        return log.count if log else 0
    
    def _get_auto_learned_total(self):
        total = db.session.query(db.func.sum(LearningLog.auto_learned)).scalar()
        return int(total) if total else 0
    
    # ============ AUTO-APRENDIZAJE CONTINUO (NUEVO) ============
    
    def _continuous_learning_loop(self):
        """Loop de aprendizaje continuo - cada 6 horas aprende algo nuevo"""
        logger.info("🧠 Iniciando loop de auto-aprendizaje continuo...")
        
        # Primera ejecución después de 5 minutos (para no sobrecargar al inicio)
        time.sleep(300)
        
        while self.learning_active:
            try:
                self._perform_auto_learning()
            except Exception as e:
                logger.error(f"Error en auto-aprendizaje: {e}")
            
            # Esperar 6 horas antes de volver a aprender
            logger.info("⏰ Auto-aprendizaje: esperando 6 horas...")
            time.sleep(21600)  # 6 horas en segundos
    
    def _perform_auto_learning(self):
        """Realizar una sesión de auto-aprendizaje"""
        with app.app_context():
            # Elegir tema aleatorio
            topic = random.choice(self.auto_learning_topics)
            logger.info(f"🤖 Auto-aprendizaje: investigando sobre '{topic}'")
            
            # Buscar información
            results = self.web_search_engine.search_duckduckgo(topic, max_results=3)
            
            if not results:
                logger.warning(f"No se encontraron resultados para '{topic}'")
                return
            
            learned_count = 0
            
            for result in results:
                try:
                    # Verificar si ya existe contenido similar (evitar duplicados)
                    content_preview = result['snippet'][:100]
                    exists = Memory.query.filter(
                        Memory.content.ilike(f'%{content_preview}%')
                    ).first()
                    
                    if exists:
                        logger.info(f"⏭️ Ya existe información similar: {result['title'][:50]}...")
                        continue
                    
                    # Verificar duplicado por URL
                    url_exists = Memory.query.filter(
                        Memory.content.contains(result['url'])
                    ).first()
                    
                    if url_exists:
                        logger.info(f"⏭️ URL ya conocida: {result['url'][:50]}...")
                        continue
                    
                    # Crear memoria
                    memory = Memory(
                        content=f"{result['title']}\n\n{result['snippet']}\n\nFuente: {result['url']}",
                        source='auto_learning',
                        topic=topic,
                        relevance_score=0.6,
                        access_count=0
                    )
                    db.session.add(memory)
                    learned_count += 1
                    
                    # Registrar evolución
                    evolution = KnowledgeEvolution(
                        topic=topic,
                        action='learned',
                        new_content=result['snippet'][:200],
                        source='auto_learning'
                    )
                    db.session.add(evolution)
                    
                    logger.info(f"✅ Aprendido: {result['title'][:60]}...")
                    
                except Exception as e:
                    logger.error(f"Error procesando resultado: {e}")
                    continue
            
            # Actualizar contadores
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
                
                logger.info(f"🎉 Auto-aprendizaje completado: {learned_count} nuevos conocimientos")
            else:
                logger.info("📝 No se aprendió nada nuevo en esta ronda")
    
    def _auto_web_search_loop(self):
        """Limpiar cache de búsquedas web expiradas"""
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
                    if len(expired) > 0:
                        logger.info(f"🧹 Cache limpiado: {len(expired)} entradas eliminadas")
            except Exception as e:
                logger.error(f"Error limpiando cache: {e}")
            time.sleep(3600)
    
    def _auto_learn_loop(self):
        """Actualizar puntuaciones de relevancia"""
        while self.learning_active:
            try:
                with app.app_context():
                    memories = Memory.query.all()
                    for mem in memories:
                        mem.relevance_score = min(1.0, mem.relevance_score + (mem.access_count * 0.01))
                    db.session.commit()
            except Exception as e:
                logger.error(f"Error en auto-learn: {e}")
            time.sleep(3600)
    
    # ============ CHAT Y RESPUESTAS ============
    
    def chat(self, user_input, mode='balanced', attachment_info=None):
        input_lower = user_input.lower().strip()
        
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_conversation(user_input, response, 'system_time', 
                                         attachment_info=attachment_info)
        
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
            
            return self._save_conversation(user_input, response, sources_used[0] if sources_used else 'learning',
                                         attachment_info=attachment_info,
                                         memories_count=len(relevant_memories),
                                         sources_used=sources_used)
    
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
            logger.error(f"Error en búsqueda web: {e}")
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
                          attachment_info=None, memories_count=0, sources_used=None):
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
            'model_used': 'cic_ia_v2_mejorada',
            'sources_used': sources_used or [source],
            'memories_found': memories_count,
            'total_memories': total_mem,
            'has_attachment': attachment_info is not None
        }
    
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
    
    # ============ NUEVOS MÉTODOS PARA EVOLUCIÓN ============
    
    def get_learning_stats(self):
        """Obtener estadísticas de aprendizaje"""
        with app.app_context():
            total_memories = Memory.query.count()
            auto_learned = Memory.query.filter_by(source='auto_learning').count()
            web_learned = Memory.query.filter_by(source='web_search').count()
            user_taught = Memory.query.filter_by(source='user_taught').count()
            
            # Últimos 7 días
            week_ago = date.today() - timedelta(days=7)
            recent_logs = LearningLog.query.filter(LearningLog.date >= week_ago).all()
            
            weekly_stats = {
                'conversations': sum(log.count for log in recent_logs),
                'web_searches': sum(log.web_searches for log in recent_logs),
                'auto_learned': sum(log.auto_learned for log in recent_logs)
            }
            
            return {
                'total_memories': total_memories,
                'by_source': {
                    'auto_learning': auto_learned,
                    'web_search': web_learned,
                    'user_taught': user_taught,
                    'knowledge_base': total_memories - auto_learned - web_learned - user_taught
                },
                'last_7_days': weekly_stats,
                'evolution_ready': True
            }

# Instancia global
cic_ia = CicIA()

# ============ RUTAS DE PÁGINAS WEB ============

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
        'version': '2.1',
        'features': ['chat', 'web_search', 'auto_learning', 'memory', 'evolution']
    })

# ============ RUTAS API ============

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '').strip()
        mode = data.get('mode', 'balanced')
        
        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        result = cic_ia.chat(message, mode=mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        
        return jsonify({
            'query': query,
            'results': results,
            'count': len(results),
            'source': 'duckduckgo'
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
                'stage': 'v2.1_evolution',
                'total_memories': stats['total_memories'],
                'total_conversations': Conversation.query.count(),
                'today_learned': log.count if log else 0,
                'today_auto_learned': log.auto_learned if log else 0,
                'web_searches_today': log.web_searches if log else 0,
                'db_size': 'PostgreSQL' if database_url else 'SQLite',
                'auto_learning_active': True,
                'learning_stats': stats,
                'features': ['chat', 'web_search', 'auto_learning', 'memory', 'evolution', 'attachments']
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
                'message': f'✅ He aprendido sobre {query} desde {source}',
                'memories_added': len(results) if source == 'web' else 1
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/teach', methods=['POST'])
def teach():
    try:
        text = request.json.get('text', '')
        
        with app.app_context():
            memory = Memory(
                content=text,
                source='user_taught',
                topic=text[:50],
                relevance_score=0.9
            )
            db.session.add(memory)
            db.session.commit()
            
            return jsonify({'message': '✅ He aprendido lo que me enseñaste'})
    except Exception as e:
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

# NUEVO: Endpoint para estadísticas de evolución
@app.route('/api/evolution/stats')
def evolution_stats():
    try:
        stats = cic_ia.get_learning_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# NUEVO: Endpoint para forzar auto-aprendizaje (modo dev)
@app.route('/api/evolution/learn-now', methods=['POST'])
def force_learning():
    token = request.headers.get('X-Dev-Token')
    if not verify_dev_token(token):
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        threading.Thread(target=cic_ia._perform_auto_learning, daemon=True).start()
        return jsonify({'message': '🤖 Auto-aprendizaje iniciado manualmente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/login', methods=['POST'])
def dev_login():
    try:
        password = request.json.get('password', '')
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if password_hash == DEV_PASSWORD_HASH:
            token = hashlib.sha256(f"{password}{datetime.utcnow()}".encode()).hexdigest()[:32]
            session = DeveloperSession(token=token)
            db.session.add(session)
            db.session.commit()
            return jsonify({'success': True, 'token': token})
        else:
            return jsonify({'success': False, 'error': 'Contraseña incorrecta'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/verify')
def dev_verify():
    token = request.headers.get('X-Dev-Token')
    return jsonify({'valid': verify_dev_token(token)})

@app.route('/api/dev/logs')
def dev_logs():
    token = request.headers.get('X-Dev-Token')
    if not verify_dev_token(token):
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        with app.app_context():
            return jsonify({
                'database': {
                    'memories': Memory.query.count(),
                    'conversations': Conversation.query.count(),
                    'learning_logs': LearningLog.query.count(),
                    'web_searches': WebSearchCache.query.count(),
                    'knowledge_evolution': KnowledgeEvolution.query.count()
                },
                'recent_memories': [{
                    'id': m.id,
                    'topic': m.topic,
                    'source': m.source,
                    'content': m.content[:200],
                    'relevance': m.relevance_score,
                    'created': m.created_at.isoformat()
                } for m in Memory.query.order_by(Memory.created_at.desc()).limit(5).all()],
                'recent_evolution': [{
                    'id': e.id,
                    'topic': e.topic,
                    'action': e.action,
                    'date': e.date.isoformat()
                } for e in KnowledgeEvolution.query.order_by(KnowledgeEvolution.date.desc()).limit(5).all()]
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/clear-db', methods=['POST'])
def dev_clear_db():
    token = request.headers.get('X-Dev-Token')
    if not verify_dev_token(token):
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        with app.app_context():
            Memory.query.delete()
            Conversation.query.delete()
            LearningLog.query.delete()
            WebSearchCache.query.delete()
            KnowledgeEvolution.query.delete()
            db.session.commit()
            return jsonify({'message': 'Base de datos limpiada completamente'})
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
