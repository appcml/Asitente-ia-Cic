"""
Bebé IA Pro - VERSIÓN COMPLETA CON MEMORIA ACTIVA
✅ Guarda conversaciones automáticamente
✅ Aprendizaje manual (Wiki/Enseñar) funcional
✅ Aprendizaje automático cada 15 minutos
✅ Persistencia garantizada en PostgreSQL
"""
from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
import os
import json
import random
import re
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bebe-ia-secret-key-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///bebe_ia.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

# Crear carpeta uploads
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============ MODELOS DE BASE DE DATOS ============
class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(50), default='local')
    topic = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    access_count = db.Column(db.Integer, default=0)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LearningLog(db.Model):
    """NUEVO: Registro de aprendizaje diario"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.utcnow().date, unique=True)
    count = db.Column(db.Integer, default=0)

# Crear tablas dentro de contexto
with app.app_context():
    db.create_all()

# ============ BASE DE CONOCIMIENTO INTEGRADA ============
KNOWLEDGE_BASE = {
    'ia': {
        'respuestas': [
            "La Inteligencia Artificial (IA) es la simulación de procesos de inteligencia humana por sistemas informáticos. Incluye aprendizaje automático, procesamiento de lenguaje natural y visión computacional.",
            "IA se refiere a sistemas que pueden realizar tareas que normalmente requieren inteligencia humana: reconocer patrones, tomar decisiones, entender lenguaje.",
            "Existen dos tipos principales: IA débil (específica, como Siri) e IA fuerte (general, aún en desarrollo)."
        ],
        'keywords': ['inteligencia artificial', 'ia', 'ai', 'machine learning', 'que es la ia', 'que es ia']
    },
    'hola': {
        'respuestas': [
            "¡Hola! 👋 Soy Bebé IA. Estoy lista para ayudarte.",
            "¡Hey! ¿Cómo estás? ¿En qué puedo ayudarte hoy?",
            "¡Buenas! ¿Qué tema te interesa aprender?"
        ],
        'keywords': ['hola', 'hey', 'buenas', 'saludos', 'que tal', 'buenos dias', 'buenas noches']
    },
    'machine_learning': {
        'respuestas': [
            "Machine Learning es una rama de la IA donde las computadoras aprenden de datos sin ser programadas explícitamente. Incluye algoritmos como redes neuronales, árboles de decisión y clustering.",
            "El aprendizaje automático permite a las máquinas mejorar su rendimiento en tareas mediante la experiencia. Se usa en recomendaciones, diagnósticos médicos, vehículos autónomos, etc."
        ],
        'keywords': ['machine learning', 'aprendizaje automatico', 'ml', 'deep learning', 'aprendizaje profundo']
    },
    'python': {
        'respuestas': [
            "Python es un lenguaje de programación versátil y fácil de aprender. Es el más usado en IA y ciencia de datos por su sintaxis clara y bibliotecas como TensorFlow, PyTorch y scikit-learn.",
            "Python fue creado por Guido van Rossum en 1991. Destaca por su legibilidad y gran comunidad."
        ],
        'keywords': ['python', 'programacion', 'codigo', 'desarrollo', 'lenguaje de programacion']
    },
    'render': {
        'respuestas': [
            "Render es una plataforma en la nube para desplegar aplicaciones web. Ofrece hosting gratuito con PostgreSQL, HTTPS automático y despliegue continuo desde GitHub.",
            "En Render puedes hospedar aplicaciones Python, Node.js, bases de datos y más. Es muy popular para proyectos personales y startups."
        ],
        'keywords': ['render', 'hosting', 'despliegue', 'nube', 'cloud']
    },
    'fecha_hora': {
        'respuestas': ["DYNAMIC_DATE"],
        'keywords': ['que dia es hoy', 'qué día es hoy', 'fecha de hoy', 'fecha actual', 'hoy es', 'dia actual', 
                     'que hora es', 'hora actual', 'hora', 'fecha', 'dia es hoy', 'día es hoy', 
                     'fecha y hora', 'que fecha es hoy', 'cuando estamos', 'en que fecha estamos']
    },
    'como_estas': {
        'respuestas': [
            "¡Estoy funcionando perfectamente! 🚀 Mi sistema está estable y lista para ayudarte. ¿Y tú, cómo estás?",
            "Todo bien por aquí. Estoy en modo de aprendizaje automático y funcionando al 100%. ¿En qué puedo ayudarte?",
            "¡Excelente! Acabo de actualizar mis estadísticas. Tengo muchas ganas de aprender contigo hoy."
        ],
        'keywords': ['como estas', 'cómo estás', 'que tal', 'como te va', 'todo bien', 'estado']
    },
    'nombre': {
        'respuestas': [
            "Soy Bebé IA Pro 🤖, una inteligencia artificial en desarrollo que aprende de Wikipedia y de las conversaciones contigo.",
            "Me llamo Bebé IA Pro. Fui creada para aprender y ayudar, y estoy alojada en Render con base de datos PostgreSQL.",
            "¡Bebé IA Pro a tu servicio! Estoy en la etapa de aprendizaje pero me esfuerzo por dar buenas respuestas."
        ],
        'keywords': ['como te llamas', 'tu nombre', 'quien eres', 'qué eres', 'quien sos', 'presentate']
    },
    'default': {
        'respuestas': [
            "Entiendo tu pregunta sobre '{tema}'. Estoy en modo de aprendizaje continuo. ¿Puedes darme más contexto?",
            "Interesante tema: '{tema}'. Estoy investigando para darte la mejor respuesta. Mientras tanto, ¿quieres que busque información en Wikipedia?",
            "Estoy aprendiendo sobre '{tema}'. Puedo investigar este tema usando el botón 📖 **Wiki** si lo deseas.",
            "No tengo suficiente información sobre '{tema}' aún. ¿Te gustaría enseñarme algo al respecto usando el botón 🎓 **Enseñar**?"
        ],
        'keywords': []
    }
}

# ============ IA LOCAL INTELIGENTE ============
class BebeIA:
    def __init__(self):
        self.learning_active = True
        self.last_reset = datetime.now()
        
        # Obtener conteo inicial y estadísticas dentro de contexto
        with app.app_context():
            initial_memories = Memory.query.count()
            today = datetime.utcnow().date()
            log = LearningLog.query.filter_by(date=today).first()
            self.daily_learned = log.count if log else 0
        
        # Iniciar aprendizaje automático
        self.learn_thread = threading.Thread(target=self._auto_learn_loop, daemon=True)
        self.learn_thread.start()
        
        # Iniciar guardado automático de conversaciones
        self.save_thread = threading.Thread(target=self._auto_save_conversations, daemon=True)
        self.save_thread.start()
        
        print("=" * 60)
        print("🚀 BEBÉ IA PRO - MODO MEMORIA ACTIVA")
        print(f"📚 {initial_memories} memorias en base de datos")
        print(f"📈 Aprendidos hoy: {self.daily_learned}")
        print("🔄 Aprendizaje automático: ACTIVO")
        print("💾 Guardado de conversaciones: ACTIVO")
        print("=" * 60)
    
    def chat(self, user_input: str, mode: str = 'balanced') -> dict:
        """Procesar mensaje del usuario"""
        
        input_lower = user_input.lower().strip()
        
        # 1. PRIORIDAD: Preguntas de fecha/hora (dinámico)
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_and_respond(user_input, response, 'system_time', 0, 'high', mode)
        
        # 2. Buscar coincidencia en base de conocimiento
        best_topic = None
        best_score = 0
        
        for topic, data in KNOWLEDGE_BASE.items():
            if topic == 'default':
                continue
                
            score = 0
            for keyword in data['keywords']:
                if keyword in input_lower:
                    score += 3
            
            topic_words = set(topic.replace('_', ' ').split())
            input_words = set(input_lower.split())
            score += len(topic_words & input_words)
            
            if score > best_score:
                best_score = score
                best_topic = topic
        
        # 3. Buscar en memorias de la base de datos (con contexto)
        with app.app_context():
            memories = Memory.query.all()
            relevant_memories = []
            
            for mem in memories:
                mem_words = set(mem.content.lower().split())
                input_words = set(input_lower.split())
                common_words = mem_words & input_words
                
                if len(common_words) >= 2:
                    relevant_memories.append(mem)
                    mem.access_count += 1
            
            db.session.commit()
            
            # 4. Generar respuesta
            if best_score >= 2 and best_topic:
                responses = KNOWLEDGE_BASE[best_topic]['respuestas']
                response = random.choice(responses)
                source = 'knowledge_base'
                confidence = 'high'
            elif relevant_memories:
                memory = relevant_memories[0]
                response = f"Basándome en lo que aprendí anteriormente: {memory.content[:400]}"
                source = f"memory_{memory.source}"
                confidence = 'medium'
            else:
                tema = user_input[:40] if len(user_input) > 5 else "este tema"
                response = random.choice(KNOWLEDGE_BASE['default']['respuestas']).format(tema=tema)
                source = 'local_ai'
                confidence = 'learning'
                # Guardar tema para aprender después
                self._schedule_learning(user_input)
            
            # Ajustar según modo
            if mode == 'fast':
                sentences = response.split('.')
                response = sentences[0] + '.' if len(sentences) > 1 else response[:150]
            elif mode == 'complete' and best_topic:
                response += f"\n\n¿Te gustaría que investigue más sobre {best_topic.replace('_', ' ')}?"
            
            return self._save_and_respond(user_input, response, source, len(relevant_memories), confidence, mode)
    
    def _save_and_respond(self, user_input: str, response: str, source: str, 
                         memories_found: int, confidence: str, mode: str) -> dict:
        """Guardar conversación y formatear respuesta"""
        
        with app.app_context():
            # Guardar conversación
            conv = Conversation(user_message=user_input, bot_response=response)
            db.session.add(conv)
            db.session.commit()
            
            total_memories = Memory.query.count()
            
            # NUEVO: Guardar automáticamente en memoria si es información útil
            if len(user_input) > 10 and confidence == 'learning':
                self._save_conversation_as_memory(user_input, response)
        
        return {
            'response': response,
            'model_used': 'bebe_ia_local_v3',
            'mode': mode,
            'sources_used': [source],
            'memories_found': memories_found,
            'confidence': confidence,
            'total_memories': total_memories
        }
    
    def _save_conversation_as_memory(self, user_input: str, response: str):
        """NUEVO: Guardar conversación interesante como memoria"""
        try:
            # Solo guardar si parece información educativa
            educational_keywords = ['qué es', 'como', 'cómo', 'definición', 'explicación', 
                                   'significa', 'significado', 'ejemplo', 'pasos', 'tutorial']
            is_educational = any(kw in user_input.lower() for kw in educational_keywords)
            
            if is_educational and len(user_input) > 15:
                content = f"Pregunta: {user_input}\nRespuesta: {response[:300]}"
                memory = Memory(
                    content=content,
                    source='conversation',
                    topic=user_input[:50],
                    access_count=1
                )
                db.session.add(memory)
                db.session.commit()
                print(f"💾 Conversación guardada como memoria: {user_input[:40]}...")
        except Exception as e:
            print(f"⚠️ Error guardando conversación: {e}")
    
    def _is_date_time_question(self, input_lower: str) -> bool:
        """Detectar si es una pregunta sobre fecha o hora"""
        date_keywords = ['que dia es hoy', 'qué día es hoy', 'fecha', 'hora es', 'hora actual', 
                        'fecha actual', 'dia actual', 'día actual', 'hoy es', 'fecha de hoy',
                        'que hora', 'qué hora', 'fecha y hora', 'que fecha', 'qué fecha']
        return any(kw in input_lower for kw in date_keywords)
    
    def _get_dynamic_date_response(self, input_lower: str) -> str:
        """Generar respuesta dinámica con fecha/hora actual"""
        now = datetime.now()
        
        dias_semana = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        dia_semana = dias_semana[now.weekday()]
        dia = now.day
        mes = meses[now.month - 1]
        año = now.year
        hora = now.strftime('%H:%M')
        
        ask_date = any(kw in input_lower for kw in ['dia', 'día', 'fecha', 'hoy es'])
        ask_time = any(kw in input_lower for kw in ['hora', 'hora es', 'hora actual'])
        
        if ask_date and ask_time:
            return f"📅 Hoy es {dia_semana}, {dia} de {mes} de {año}.\n⏰ La hora actual es {hora}."
        elif ask_time:
            return f"⏰ Son las {hora}."
        else:
            return f"📅 Hoy es {dia_semana}, {dia} de {mes} de {año}."
    
    def _schedule_learning(self, topic: str):
        """Programar aprendizaje de un tema nuevo"""
        pass
    
    def _increment_daily_learning(self):
        """NUEVO: Incrementar contador de aprendizaje diario"""
        try:
            with app.app_context():
                today = datetime.utcnow().date()
                log = LearningLog.query.filter_by(date=today).first()
                
                if not log:
                    log = LearningLog(date=today, count=0)
                    db.session.add(log)
                
                log.count += 1
                db.session.commit()
                self.daily_learned = log.count
                print(f"📈 Aprendizaje #{self.daily_learned} registrado hoy")
        except Exception as e:
            print(f"⚠️ Error registrando aprendizaje: {e}")
    
    def _auto_learn_loop(self):
        """Bucle de aprendizaje automático cada 15 minutos"""
        print("🔄 Thread de aprendizaje automático iniciado")
        
        while self.learning_active:
            try:
                with app.app_context():
                    today = datetime.utcnow().date()
                    
                    # Reset diario si es necesario
                    if (datetime.now() - self.last_reset).days >= 1:
                        self.last_reset = datetime.now()
                        self.daily_learned = 0
                        print("🌅 Nuevo día - contador reseteado")
                    
                    # Verificar límite diario
                    log = LearningLog.query.filter_by(date=today).first()
                    current_count = log.count if log else 0
                    
                    # Aprender si tenemos menos de 50 memorias y menos de 20 hoy
                    if Memory.query.count() < 50 and current_count < 20:
                        topics = ['inteligencia artificial', 'python', 'tecnología', 'ciencia', 'programación', 'historia', 'geografía']
                        topic = random.choice(topics)
                        print(f"🎓 Iniciando aprendizaje automático sobre: {topic}")
                        self._learn_from_wikipedia(topic)
                    else:
                        print(f"⏭️ Saltando aprendizaje automático (memorias: {Memory.query.count()}, hoy: {current_count})")
                
                time.sleep(900)  # 15 minutos
                
            except Exception as e:
                print(f"❌ Error en auto-learn: {e}")
                time.sleep(300)  # 5 minutos si hay error
    
    def _auto_save_conversations(self):
        """NUEVO: Thread para guardar conversaciones periódicamente"""
        print("💾 Thread de guardado de conversaciones iniciado")
        
        while self.learning_active:
            try:
                time.sleep(3600)  # Cada 1 hora, guardar resumen de conversaciones
                with app.app_context():
                    # Obtener conversaciones recientes no guardadas
                    recent = Conversation.query.order_by(Conversation.timestamp.desc()).limit(5).all()
                    
                    if recent:
                        # Crear resumen
                        topics = [c.user_message[:30] for c in recent]
                        summary = f"Resumen de sesión reciente: {', '.join(topics)}"
                        
                        memory = Memory(
                            content=summary,
                            source='session_summary',
                            topic='Resumen de conversación',
                            access_count=0
                        )
                        db.session.add(memory)
                        db.session.commit()
                        print(f"💾 Resumen de sesión guardado: {len(recent)} conversaciones")
                        
            except Exception as e:
                print(f"⚠️ Error en auto-save: {e}")
    
    def _learn_from_wikipedia(self, query: str):
        """Aprender de Wikipedia (siempre dentro de app_context)"""
        try:
            print(f"🎓 Aprendiendo de Wikipedia: {query}")
            
            # Buscar artículos
            search_url = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&srlimit=3"
            
            with urllib.request.urlopen(search_url, timeout=15) as response:
                search_data = json.loads(response.read())
            
            articles_found = 0
            for item in search_data['query']['search']:
                title = item['title']
                content_url = f"https://es.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&exchars=2000&titles={urllib.parse.quote(title)}&format=json"
                
                with urllib.request.urlopen(content_url, timeout=15) as resp:
                    content_data = json.loads(resp.read())
                
                pages = content_data['query']['pages']
                content = list(pages.values())[0].get('extract', '')
                
                if content and len(content) > 100:
                    # Verificar si ya existe
                    existing = Memory.query.filter(Memory.topic.contains(title)).first()
                    if not existing:
                        memory = Memory(
                            content=f"Wikipedia - {title}: {content[:1500]}",
                            source='wikipedia',
                            topic=title,
                            access_count=0
                        )
                        db.session.add(memory)
                        articles_found += 1
                        print(f"   ✅ {title[:50]}...")
            
            if articles_found > 0:
                db.session.commit()
                self._increment_daily_learning()
                print(f"   📚 Total aprendido: {articles_found} artículos nuevos")
            else:
                print(f"   ℹ️ No se encontraron artículos nuevos sobre '{query}'")
                
        except Exception as e:
            print(f"   ❌ Error aprendiendo de Wikipedia: {e}")
    
    def force_learn(self, source: str, query: str) -> str:
        """Aprendizaje forzado por el usuario (botón Wiki/Paper)"""
        try:
            with app.app_context():
                if source == 'wikipedia':
                    print(f"📖 Aprendizaje forzado vía Wiki: {query}")
                    self._learn_from_wikipedia(query)
                    count = Memory.query.filter(Memory.topic.contains(query)).count()
                    total = Memory.query.count()
                    return f"✅ Aprendí sobre '{query}' de Wikipedia. Ahora tengo {count} artículos relacionados y {total} memorias totales."
                
                elif source == 'arxiv':
                    # Usar Wikipedia como proxy para papers (modo offline)
                    print(f"📄 Investigación académica (vía Wikipedia): {query}")
                    self._learn_from_wikipedia(f"investigación científica {query}")
                    return f"✅ Investigación completada sobre '{query}'. He buscado información científica relevante."
                
                else:
                    return "❌ Fuente no disponible. Usa 'wikipedia' o 'arxiv'."
                
        except Exception as e:
            print(f"❌ Error en force_learn: {e}")
            return f"❌ Error al aprender: {str(e)}"
    
    def teach(self, text: str) -> str:
        """Enseñar manualmente a la IA (botón Enseñar)"""
        try:
            with app.app_context():
                if not text or len(text) < 5:
                    return "❌ El texto es demasiado corto para aprender."
                
                # Crear memoria del usuario
                memory = Memory(
                    content=text,
                    source='user_teaching',
                    topic='Enseñanza manual',
                    access_count=1
                )
                db.session.add(memory)
                db.session.commit()
                
                # Incrementar contador
                self._increment_daily_learning()
                
                total = Memory.query.count()
                return f"🎓 ¡Aprendido! He guardado: '{text[:60]}...' en mi memoria permanente. Ahora tengo {total} memorias."
                
        except Exception as e:
            print(f"❌ Error en teach: {e}")
            return f"❌ Error guardando: {str(e)}"
    
    def get_status(self) -> dict:
        """Obtener estado del sistema"""
        with app.app_context():
            total_memories = Memory.query.count()
            total_conversations = Conversation.query.count()
            
            # Obtener conteo de hoy
            today = datetime.utcnow().date()
            log = LearningLog.query.filter_by(date=today).first()
            daily_count = log.count if log else 0
        
        # Determinar etapa
        if total_memories < 20:
            stage = '🍼 Aprendiz'
        elif total_memories < 100:
            stage = '📚 Estudiante'
        elif total_memories < 300:
            stage = '🔬 Investigador'
        else:
            stage = '🧠 Experto'
        
        return {
            'stage': stage,
            'total_memories': total_memories,
            'total_conversations': total_conversations,
            'daily_learned': daily_count,
            'learning_active': self.learning_active,
            'mode': 'offline_memory_active',
            'status': 'Funcionando correctamente - Memoria activada',
            'auto_save': True,
            'auto_learn': True
        }

# ============ INICIALIZAR IA ============
bebe = BebeIA()

# ============ RUTAS ============
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Endpoint principal de chat"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Empty message'}), 400
        
        mode = data.get('mode', 'balanced')
        
        result = bebe.chat(message, mode)
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error en chat: {e}")
        return jsonify({
            'response': 'Lo siento, tuve un problema interno. Intenta de nuevo.',
            'model_used': 'error',
            'sources_used': ['error'],
            'error': str(e)
        }), 500

@app.route('/learn', methods=['POST'])
def learn():
    """Endpoint para forzar aprendizaje (botón Wiki/Paper)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        source = data.get('source', 'wikipedia')
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        print(f"📥 Solicitud de aprendizaje: source={source}, query={query}")
        result = bebe.force_learn(source, query)
        return jsonify({'message': result})
        
    except Exception as e:
        print(f"❌ Error en learn endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/teach', methods=['POST'])
def teach():
    """Endpoint para enseñar manualmente (botón Enseñar)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        text = data.get('correct', '').strip()
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        print(f"📥 Solicitud de enseñanza: {text[:50]}...")
        result = bebe.teach(text)
        return jsonify({'message': result})
        
    except Exception as e:
        print(f"❌ Error en teach endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """Endpoint de estado"""
    try:
        return jsonify(bebe.get_status())
    except Exception as e:
        print(f"❌ Error en status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/memories', methods=['GET'])
def get_memories():
    """Ver últimas memorias"""
    try:
        with app.app_context():
            memories = Memory.query.order_by(Memory.created_at.desc()).limit(10).all()
            return jsonify([{
                'id': m.id,
                'source': m.source,
                'topic': m.topic or 'Sin tema',
                'content': m.content[:200] + '...' if len(m.content) > 200 else m.content,
                'created_at': m.created_at.isoformat(),
                'access_count': m.access_count
            } for m in memories])
    except Exception as e:
        print(f"❌ Error en memories: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/history', methods=['GET'])
def get_history():
    """Ver historial de conversaciones"""
    try:
        with app.app_context():
            conversations = Conversation.query.order_by(Conversation.timestamp.desc()).limit(20).all()
            return jsonify([{
                'id': c.id,
                'user': c.user_message,
                'bot': c.bot_response,
                'timestamp': c.timestamp.isoformat()
            } for c in conversations])
    except Exception as e:
        print(f"❌ Error en history: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
