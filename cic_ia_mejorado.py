"""
Cic_IA v7.4 - Asistente Inteligente EVOLUTIVO con Módulos Especializados
- Módulos: Datos, Imágenes, Código, Historial, Archivos
- Modos: Básico, Rápido, Avanzado
- Auto-aprendizaje web cada 1 hora
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

# ========== IMPORTAR MÓDULOS ==========
try:
    from modules import (
        DataAnalysisModule,
        ImageGeneratorModule,
        CodeAssistantModule,
        ChatHistoryModule,
        FileManagerModule
    )
    MODULES_AVAILABLE = True
    logger = logging.getLogger('cic_ia')
    logger.info("✅ Módulos especializados cargados")
except ImportError as e:
    MODULES_AVAILABLE = False
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('cic_ia')
    logger.warning(f"⚠️ Módulos no disponibles: {e}")

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
    preferred_mode = db.Column(db.String(20), default='balanced')
    
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
    source = db.Column(db.String(50), default='unknown')
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
    module_used = db.Column(db.String(50), default=None)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LearningLog(db.Model):
    __tablename__ = 'learning_logs'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    count = db.Column(db.Integer, default=0, nullable=False)
    auto_learned = db.Column(db.Integer, default=0, nullable=False)

class UploadedFile(db.Model):
    __tablename__ = 'uploaded_files'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'))
    original_name = db.Column(db.String(255))
    saved_name = db.Column(db.String(255))
    file_path = db.Column(db.String(500))
    file_type = db.Column(db.String(50))
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed = db.Column(db.Boolean, default=False)

# Crear tablas
with app.app_context():
    db.create_all()

# ========== KNOWLEDGE BASE ==========

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
        'advanced': "¡Hola! Soy Cic_IA, tu asistente con auto-aprendizaje y módulos especializados. Puedo ayudarte con: análisis de datos, generación de imágenes, programación, y más. ¿Qué necesitas?"
    },
    'cic_ia': {
        'basic': "Soy Cic_IA.",
        'fast': "Soy Cic_IA, un asistente IA que aprende automáticamente cada hora.",
        'advanced': """Soy Cic_IA v7.4, una inteligencia artificial evolutiva con módulos especializados:

🔧 **Módulos disponibles:**
• 📊 Análisis de Datos (CSV, Excel, JSON)
• 🎨 Generación de Imágenes (DALL-E, Stable Diffusion)
• 💻 Asistente de Programación (15+ lenguajes)
• 📚 Historial de Conversaciones
• 📁 Gestión de Archivos

⚡ **Modos de respuesta:** Básico | Rápido | Avanzado

🧠 **Capacidades:** Auto-aprendizaje web, memoria persistente, búsqueda en tiempo real."""
    },
    'default': {
        'basic': "No tengo información sobre {tema}.",
        'fast': "Voy a buscar información sobre {tema} para ayudarte.",
        'advanced': "No tengo información específica sobre '{tema}' en mi base de conocimiento. Permíteme buscar en fuentes externas para darte una respuesta completa y actualizada."
    }
}

# ========== BÚSQUEDA WEB ==========

class WebSearchEngine:
    @staticmethod
    def search(query, max_results=3):
        logger.info(f"🔍 Buscando: '{query}'")
        
        try:
            results = WebSearchEngine._search_duckduckgo(query, max_results)
            if results:
                logger.info(f"✅ DuckDuckGo: {len(results)} resultados")
                return results
        except Exception as e:
            logger.warning(f"⚠️ DuckDuckGo falló: {e}")
        
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
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
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
            'internet de las cosas ejemplos'
        ]
        
        # Inicializar módulos
        self.modules = {}
        if MODULES_AVAILABLE:
            self.modules['data'] = DataAnalysisModule()
            self.modules['image'] = ImageGeneratorModule()
            self.modules['code'] = CodeAssistantModule()
            self.modules['file'] = FileManagerModule(upload_folder=UPLOAD_FOLDER)
            self.modules['history'] = None  # Se inicializa bajo demanda
            logger.info("✅ Módulos inicializados")
        else:
            logger.warning("⚠️ Módulos no disponibles - modo básico activo")
        
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
        logger.info("🚀 CIC_IA v7.4 - INICIADO")
        logger.info(f"📚 Memorias: {self.stats['memories']}")
        logger.info(f"👥 Usuarios: {self.stats['users']}")
        logger.info(f"🔧 Módulos: {'ACTIVADOS' if MODULES_AVAILABLE else 'DESACTIVADOS'}")
        logger.info(f"🧠 Auto-aprendizaje: CADA 1 HORA")
        logger.info("=" * 60)
    
    def _start_auto_learning(self):
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
        logger.info("⏰ Auto-aprendizaje activado")
    
    def _auto_learn(self, custom_topic=None):
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
    
    def detect_module_need(self, user_input):
        """Detecta si se necesita un módulo especializado"""
        input_lower = user_input.lower()
        
        # Data Analysis
        data_keywords = ['analiza', 'análisis', 'csv', 'excel', 'datos', 'ventas', 
                        'vendedor', 'producto', 'gráfico', 'estadística', 'promedio',
                        'dataset', 'dataframe', 'correlación', 'tendencia']
        data_score = sum(2 for kw in data_keywords if kw in input_lower)
        
        # Image Generation
        image_keywords = ['imagen', 'dibuja', 'genera imagen', 'crea imagen', 
                         'foto', 'ilustración', 'diseño', 'visual', 'arte', 'pintura']
        image_score = sum(2 for kw in image_keywords if kw in input_lower)
        
        # Code Assistant
        code_keywords = ['código', 'programa', 'script', 'función', 'clase', 
                        'html', 'css', 'javascript', 'python', 'sql', 'api',
                        'debug', 'error en código', 'no funciona', 'falla', 'depura',
                        'flask', 'django', 'react', 'node']
        code_score = sum(2 for kw in code_keywords if kw in input_lower)
        
        # File Management
        file_keywords = ['archivo', 'subir', 'cargar', 'descargar', 'adjunto',
                        'documento', 'pdf', 'foto', 'imagen adjunta']
        file_score = sum(1 for kw in file_keywords if kw in input_lower)
        
        scores = [
            ('data', data_score),
            ('image', image_score),
            ('code', code_score),
            ('file', file_score)
        ]
        
        best_module, best_score = max(scores, key=lambda x: x[1])
        
        if best_score >= 2:
            return best_module, min(0.3 + best_score * 0.1, 0.9), {}
        
        return None, 0, {}
    
    def predict_intent(self, text):
        text_lower = text.lower()
        intents = {
            'greeting': ['hola', 'buenas', 'saludos', 'hey', 'hi'],
            'question': ['que', 'qué', 'como', 'cómo', 'cuando', 'cuándo', 'donde', 'dónde', 'por que', 'por qué', '?'],
            'definition': ['definicion', 'definición', 'que es', 'qué es', 'significa'],
            'usage': ['usos', 'aplicaciones', 'para que sirve', 'ejemplos'],
            'comparison': ['diferencia', 'comparacion', 'versus', 'vs'],
            'tutorial': ['tutorial', 'guia', 'guía', 'paso a paso', 'aprender'],
            'farewell': ['adios', 'adiós', 'chao', 'hasta luego'],
            'thanks': ['gracias', 'thank', 'agradecido'],
            'identity': ['quien eres', 'que eres', 'tu nombre', 'cic_ia', 'cic-ia'],
            'modules': ['modulos', 'módulos', 'funciones', 'capacidades', 'que puedes hacer']
        }
        
        scores = {intent: sum(2 for kw in keywords if kw in text_lower) 
                  for intent, keywords in intents.items()}
        scores = {k: v for k, v in scores.items() if v > 0}
        
        if scores:
            best = max(scores, key=scores.get)
            return {'intent': best, 'confidence': min(0.4 + scores[best] * 0.15, 0.95)}
        
        return {'intent': 'general', 'confidence': 0.3}
    
    def find_best_topic(self, text):
        text_lower = text.lower()
        
        for topic, data in KNOWLEDGE_BASE.items():
            if topic == 'default':
                continue
            keywords = {
                'ia': ['ia', 'inteligencia artificial', 'machine learning', 'deep learning'],
                'python': ['python', 'programacion', 'codigo', 'desarrollo'],
                'hola': ['hola', 'saludos', 'buenas'],
                'cic_ia': ['cic_ia', 'quien eres', 'que eres', 'tu nombre', 'modulos', 'módulos']
            }.get(topic, [])
            
            if any(kw in text_lower for kw in keywords):
                return topic
        
        return None
    
    def find_relevant_memories(self, query, min_relevance=1):
        query_words = set(query.lower().split())
        memories = Memory.query.all()
        scored_memories = []
        
        for mem in memories:
            mem_words = set(mem.content.lower().split())
            overlap = len(query_words & mem_words)
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
        if mode == 'basic':
            return result['snippet'][:100] if len(result['snippet']) > 100 else result['snippet']
        elif mode == 'fast':
            return f"{result['title']}: {result['snippet'][:200]}"
        else:
            return f"**{result['title']}**\n\n{result['snippet']}\n\n📖 Fuente: {result['url']}"
    
    def generate_response(self, user_input, intent_info, mode='balanced'):
        input_lower = user_input.lower().strip()
        
        mode_map = {
            'basic': 'basic', 'basico': 'basic',
            'rápido': 'fast', 'rapido': 'fast', 'fast': 'fast',
            'avanzado': 'advanced', 'advanced': 'advanced',
            'balanced': 'fast'
        }
        actual_mode = mode_map.get(mode, 'fast')
        
        # Fecha/hora
        if any(kw in input_lower for kw in ['qué día', 'que dia', 'qué hora', 'que hora', 'fecha', 'hora actual']):
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
        
        # Knowledge base
        best_topic = self.find_best_topic(input_lower)
        if best_topic:
            return KNOWLEDGE_BASE[best_topic][actual_mode]
        
        # Memorias
        relevant = self.find_relevant_memories(user_input, min_relevance=2)
        if relevant:
            mem = relevant[0]
            content = mem.content
            
            if actual_mode == 'basic':
                sentences = content.split('.')
                return sentences[0] + '.' if sentences else content[:100]
            elif actual_mode == 'fast':
                paragraphs = content.split('\n\n')
                return paragraphs[0][:250] if paragraphs else content[:250]
            else:
                return f"{content}\n\n📚 Fuente: {mem.source}"
        
        # Web search
        web_results = self.web_search.search(user_input, max_results=3 if actual_mode == 'advanced' else 2)
        if web_results:
            responses = []
            for i, result in enumerate(web_results, 1):
                formatted = self.format_web_result(result, actual_mode)
                responses.append(f"{i}. {formatted}" if actual_mode == 'advanced' else formatted)
                
                try:
                    memory = Memory(
                        content=f"{result['title']}\n\n{result['snippet']}\n\nFuente: {result['url']}",
                        source='web_search',
                        topic=user_input[:50],
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
        
        # Default
        tema = user_input[:40] if len(user_input) > 5 else "este tema"
        return KNOWLEDGE_BASE['default'][actual_mode].format(tema=tema)
    
    def _save_to_history(self, user_input, response, intent, user_id, mode, module=None):
        """Guarda conversación en historial"""
        with app.app_context():
            conv = Conversation(
                user_message=user_input,
                bot_response=response,
                user_id=user_id,
                intent_detected=intent,
                mode_used=mode,
                module_used=module
            )
            db.session.add(conv)
            
            today = date.today()
            log = LearningLog.query.filter_by(date=today).first()
            if not log:
                log = LearningLog(date=today, count=0, auto_learned=0)
                db.session.add(log)
                db.session.commit()
            
            current = log.count if log.count is not None else 0
            log.count = current + 1
            db.session.commit()
    
    def process_chat(self, user_input, user_id=None, mode='balanced'):
        """Procesa mensaje con soporte de módulos"""
        
        # Verificar si necesita módulo especializado
        module_needed, confidence, params = self.detect_module_need(user_input)
        
        if module_needed and MODULES_AVAILABLE and module_needed in self.modules:
            logger.info(f"🔌 Activando módulo: {module_needed}")
            return self._process_with_module(user_input, module_needed, user_id, mode)
        
        # Procesamiento estándar
        return self._process_standard(user_input, user_id, mode)
    
    def _process_standard(self, user_input, user_id, mode):
        """Procesamiento estándar sin módulos"""
        intent_info = self.predict_intent(user_input)
        response = self.generate_response(user_input, intent_info, mode)
        
        self._save_to_history(user_input, response, intent_info['intent'], user_id, mode)
        
        with app.app_context():
            total_mem = Memory.query.count()
        
        return {
            'response': response,
            'intent': intent_info['intent'],
            'confidence': intent_info['confidence'],
            'mode': mode,
            'module': None,
            'total_memories': total_mem
        }
    
    def _process_with_module(self, user_input, module_name, user_id, mode):
        """Procesa usando módulo especializado - LLAMA A LOS MÓDULOS EXTERNOS"""
        
        if module_name == 'data':
            return self._handle_data_module(user_input, user_id, mode)
        elif module_name == 'image':
            return self._handle_image_module(user_input, user_id, mode)
        elif module_name == 'code':
            return self._handle_code_module(user_input, user_id, mode)
        elif module_name == 'file':
            return self._handle_file_module(user_input, user_id, mode)
        
        return self._process_standard(user_input, user_id, mode)
    
    def _handle_data_module(self, user_input, user_id, mode):
        """Maneja solicitudes de análisis de datos - USA EL MÓDULO EXTERNO"""
        if not MODULES_AVAILABLE or 'data' not in self.modules:
            return self._process_standard(user_input, user_id, mode)
        
        module = self.modules['data']
        
        # Verificar si hay archivo cargado para este usuario
        with app.app_context():
            last_file = UploadedFile.query.filter_by(
                user_id=user_id, 
                processed=False,
                file_type='data'
            ).order_by(UploadedFile.uploaded_at.desc()).first()
            
            if last_file and os.path.exists(last_file.file_path):
                # Cargar archivo automáticamente usando el módulo externo
                load_result = module.load_file(last_file.file_path)
                if load_result.get('success'):
                    last_file.processed = True
                    db.session.commit()
        
        # Realizar análisis usando el módulo externo
        result = module.analyze(user_input)
        
        if 'error' in result:
            response = f"""📊 **Módulo de Análisis de Datos**

❌ {result['error']}

💡 **Para usar este módulo:**
1. Sube un archivo CSV, Excel o JSON en la pestaña 'Archivos'
2. Luego pregunta cosas como:
   • "¿Quién fue el mejor vendedor?"
   • "¿Cuál es el producto más vendido?"
   • "Analiza ventas por mes"
   • "Muestra el promedio de ventas"
   • "Genera un gráfico de tendencias"

📁 **Formatos soportados:** CSV, Excel (.xlsx), JSON, SQLite"""
        else:
            response = f"""📊 **Análisis de Datos: {result.get('analysis_type', 'General').replace('_', ' ').title()}**

{result.get('summary', 'Análisis completado')}

"""
            # Agregar detalles según modo
            if mode in ['advanced', 'balanced'] and 'result' in result:
                details = json.dumps(result['result'], indent=2, default=str)
                if len(details) > 800:
                    details = details[:800] + "\n... (truncado)"
                response += f"\n**Detalles técnicos:**\n```json\n{details}\n```"
            
            if mode == 'advanced':
                response += "\n\n💡 **Sugerencias de análisis:**"
                response += "\n• Pregunta por correlaciones entre variables"
                response += "\n• Solicita proyecciones o tendencias"
                response += "\n• Pide comparativas entre períodos"
        
        self._save_to_history(user_input, response, 'data_analysis', user_id, mode, 'data')
        
        return {
            'response': response,
            'intent': 'data_analysis',
            'module': 'data',
            'mode': mode,
            'raw_result': result
        }
    
    def _handle_image_module(self, user_input, user_id, mode):
        """Maneja generación de imágenes - USA EL MÓDULO EXTERNO"""
        if not MODULES_AVAILABLE or 'image' not in self.modules:
            return self._process_standard(user_input, user_id, mode)
        
        module = self.modules['image']
        
        # Extraer prompt
        prompt = user_input.lower()
        for kw in ['imagen', 'dibuja', 'genera', 'crea', 'de', 'una', 'foto', 'ilustración', 'ilustracion']:
            prompt = prompt.replace(kw, '')
        prompt = prompt.strip()
        
        if len(prompt) < 5:
            prompt = "paisaje futurista con tecnología avanzada"
        
        # Detectar estilo
        style = 'realistic'
        if any(w in user_input.lower() for w in ['anime', 'manga', 'japonés', 'japones']):
            style = 'anime'
        elif any(w in user_input.lower() for w in ['arte', 'artistico', 'artístico', 'pintura']):
            style = 'artistic'
        elif any(w in user_input.lower() for w in ['sketch', 'dibujo', 'boceto', 'lápiz', 'lapiz']):
            style = 'sketch'
        elif any(w in user_input.lower() for w in ['3d', 'render', 'blender', 'cinemático']):
            style = '3d'
        
        # Llamar al módulo externo
        result = module.generate(prompt, style=style)
        
        if result.get('success'):
            image_data = result.get('image_data', '')
            
            if result.get('model') == 'basic_placeholder':
                response = f"""🎨 **Generador de Imágenes**

**Prompt:** {prompt}
**Estilo:** {style}

⚠️ **Modo Placeholder Activo**

Para generar imágenes reales con IA, configura en Render:
• `OPENAI_API_KEY` - Para DALL-E 3 (recomendado, alta calidad)
• `HUGGINGFACE_TOKEN` - Para Stable Diffusion XL (open source)

**Instrucciones de configuración:**
1. Ve a tu servicio en [dashboard.render.com](https://dashboard.render.com)
2. Environment → Add Environment Variable
3. Agrega OPENAI_API_KEY con tu clave de [platform.openai.com](https://platform.openai.com)

📋 **Prompt utilizado:** `{result.get('prompt_used', prompt)}`
"""
            else:
                response = f"""🎨 **Imagen Generada Exitosamente**

**Prompt:** {prompt}
**Modelo:** {result.get('model', 'IA')}
**Estilo:** {style}
**Tamaño:** {result.get('size', '1024x1024')}

✅ La imagen está lista. Se mostrará en el chat si el frontend soporta imágenes base64.

💡 **Consejos para mejores resultados:**
• Sé específico: "un gato" → "un gato siamés en un sofá de terciopelo rojo, luz natural"
• Incluye detalles de estilo: "fotografía profesional", "ilustración digital", "óleo"
• Especifica iluminación: "luz dorada de atardecer", "iluminación de estudio"
"""
        else:
            fallback = result.get('fallback', {})
            response = f"""🎨 **Error en Generación de Imagen**

❌ **Error técnico:** {result.get('error', 'Desconocido')}

📝 **Descripción textual alternativa:**

{fallback.get('description', 'No se pudo generar la descripción.')}

🔧 **Solución:**
Configura al menos una API key en las variables de entorno de Render para habilitar la generación real de imágenes.
"""
        
        self._save_to_history(user_input, response, 'image_generation', user_id, mode, 'image')
        
        # Incluir datos de imagen si existen
        return {
            'response': response,
            'intent': 'image_generation',
            'module': 'image',
            'mode': mode,
            'image_data': result.get('image_data') if result.get('success') else None,
            'image_format': result.get('format', 'png'),
            'raw_result': result
        }
    
    def _handle_code_module(self, user_input, user_id, mode):
        """Maneja solicitudes de programación - USA EL MÓDULO EXTERNO"""
        if not MODULES_AVAILABLE or 'code' not in self.modules:
            return self._process_standard(user_input, user_id, mode)
        
        module = self.modules['code']
        
        # Detectar si es explicación, generación o debug
        is_explain = any(w in user_input.lower() for w in ['explica', 'qué hace', 'como funciona', 'análisis de código'])
        is_debug = any(w in user_input.lower() for w in ['error', 'bug', 'no funciona', 'falla', 'debug', 'arregla'])
        
        if is_explain:
            # Extraer código de la consulta (entre backticks o como está)
            code_match = re.search(r'```(\w+)?\n(.*?)```', user_input, re.DOTALL)
            if code_match:
                code = code_match.group(2)
                # Llamar al módulo externo
                explanation = module.explain_code(code)
                
                response = f"""💻 **Análisis de Código**

**Lenguaje detectado:** {explanation.get('language', 'unknown')}
**Total de líneas:** {explanation.get('total_lines', 0)}

**Explicación línea por línea:**
"""
                for line_exp in explanation.get('explanation', [])[:20]:  # Limitar a 20 líneas
                    response += f"\n• {line_exp}"
                
                if len(explanation.get('explanation', [])) > 20:
                    response += f"\n\n... y {len(explanation['explanation']) - 20} líneas más."
                
                response += f"\n\n**Resumen:** {explanation.get('summary', '')}"
            else:
                response = """💻 **Análisis de Código**

Por favor, pega el código entre triple backticks para analizarlo:
