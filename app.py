"""
Bebé IA Pro - VERSIÓN HÍBRIDA (API + Offline)
✅ Intenta usar HuggingFace API primero
✅ Fallback automático a modo offline si falla
✅ Respuestas dinámicas para fecha/hora
✅ Botones todos funcionales
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
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bebe-ia-secret-key-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///bebe_ia.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

# Configuración de HuggingFace
HF_API_TOKEN = os.environ.get('HF_API_TOKEN', '')
HF_MODEL = "google/gemma-2b-it"  # Modelo gratuito y rápido

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

# Crear tablas
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

# ============ IA HÍBRIDA (API + Offline) ============
class BebeIA:
    def __init__(self):
        self.learning_active = True
        self.daily_learned = 0
        self.last_reset = datetime.now()
        self.api_available = self._check_api()
        
        # Iniciar aprendizaje automático
        self.learn_thread = threading.Thread(target=self._auto_learn_loop, daemon=True)
        self.learn_thread.start()
        
        print("=" * 60)
        print("🚀 BEBÉ IA PRO - MODO HÍBRIDO")
        print(f"📚 {Memory.query.count()} memorias en base de datos")
        print(f"🤖 API HuggingFace: {'✅ ACTIVA' if self.api_available else '❌ OFFLINE'}")
        print("🔄 Aprendizaje automático: ACTIVO")
        print("=" * 60)
    
    def _check_api(self) -> bool:
        """Verificar si HuggingFace API está disponible"""
        if not HF_API_TOKEN:
            return False
        try:
            # Test rápido de conexión
            response = requests.get(
                "https://api-inference.huggingface.co/status",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def chat(self, user_input: str, mode: str = 'balanced') -> dict:
        """Procesar mensaje del usuario - Híbrido API/Offline"""
        
        input_lower = user_input.lower().strip()
        
        # 1. PRIORIDAD: Preguntas de fecha/hora (siempre offline)
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._format_response(response, 'system_time', 0, 'high', mode)
        
        # 2. Intentar usar HuggingFace API si está disponible
        if self.api_available and HF_API_TOKEN:
            try:
                api_response = self._call_huggingface_api(user_input, mode)
                if api_response:
                    return self._format_response(
                        api_response, 
                        'huggingface', 
                        0, 
                        'high', 
                        mode,
                        model_used=HF_MODEL
                    )
            except Exception as e:
                print(f"⚠️ API falló, usando offline: {e}")
        
        # 3. FALLBACK: Modo Offline Inteligente
        return self._offline_response(user_input, mode)
    
    def _call_huggingface_api(self, message: str, mode: str) -> str:
        """Llamar a HuggingFace API"""
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        
        # Ajustar prompt según modo
        if mode == 'fast':
            prompt = f"<start_of_turn>user\n{message}\nResponde brevemente.<end_of_turn>\n<start_of_turn>model\n"
        elif mode == 'complete':
            prompt = f"<start_of_turn>user\n{message}\nResponde con detalle.<end_of_turn>\n<start_of_turn>model\n"
        else:
            prompt = f"<start_of_turn>user\n{message}<end_of_turn>\n<start_of_turn>model\n"
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 150 if mode == 'fast' else 400,
                "temperature": 0.7,
                "return_full_text": False
            }
        }
        
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{HF_MODEL}",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0].get('generated_text', '').strip()
        
        return None
    
    def _offline_response(self, user_input: str, mode: str) -> dict:
        """Generar respuesta offline cuando la API falla"""
        input_lower = user_input.lower().strip()
        
        # Buscar en base de conocimiento
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
        
        # Buscar en memorias
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
        
        # Generar respuesta
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
            self._schedule_learning(user_input)
        
        # Ajustar según modo
        if mode == 'fast':
            sentences = response.split('.')
            response = sentences[0] + '.' if len(sentences) > 1 else response[:150]
        elif mode == 'complete' and best_topic:
            response += f"\n\n¿Te gustaría que investigue más sobre {best_topic.replace('_', ' ')}?"
        
        return self._format_response(response, source, len(relevant_memories), confidence, mode)
    
    def _format_response(self, response: str, source: str, memories_found: int, 
                        confidence: str, mode: str, model_used: str = 'bebe_ia_local') -> dict:
        """Formatear respuesta estándar"""
        
        # Guardar conversación
        conv = Conversation(user_message=response, bot_response=response)
        db.session.add(conv)
        db.session.commit()
        
        return {
            'response': response,
            'model_used': model_used,
            'mode': mode,
            'sources_used': [source],
            'memories_found': memories_found,
            'confidence': confidence,
            'total_memories': Memory.query.count()
        }
    
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
    
    def _auto_learn_loop(self):
        """Bucle de aprendizaje automático cada 15 minutos"""
        while self.learning_active:
            try:
                if (datetime.now() - self.last_reset).days >= 1:
                    self.daily_learned = 0
                    self.last_reset = datetime.now()
                
                if Memory.query.count() < 50 and self.daily_learned < 20:
                    topics = ['inteligencia artificial', 'python', 'tecnología', 'ciencia', 'programación']
                    topic = random.choice(topics)
                    self._learn_from_wikipedia(topic)
                    self.daily_learned += 1
                
                time.sleep(900)
                
            except Exception as e:
                print(f"Error en auto-learn: {e}")
                time.sleep(300)
    
    def _learn_from_wikipedia(self, query: str):
        """Aprender de Wikipedia"""
        try:
            print(f"🎓 Aprendiendo de Wikipedia: {query}")
            
            search_url = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&srlimit=2"
            
            with urllib.request.urlopen(search_url, timeout=15) as response:
                search_data = json.loads(response.read())
            
            articles_found = 0
            for item in search_data['query']['search']:
                title = item['title']
                content_url = f"https://es.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&exchars=1500&titles={urllib.parse.quote(title)}&format=json"
                
                with urllib.request.urlopen(content_url, timeout=15) as resp:
                    content_data = json.loads(resp.read())
                
                pages = content_data['query']['pages']
                content = list(pages.values())[0].get('extract', '')
                
                if content and len(content) > 100:
                    memory = Memory(
                        content=f"Wikipedia - {title}: {content[:1000]}",
                        source='wikipedia',
                        topic=title
                    )
                    db.session.add(memory)
                    articles_found += 1
                    print(f"   ✅ {title[:50]}...")
            
            if articles_found > 0:
                db.session.commit()
                print(f"   📚 Total aprendido: {articles_found} artículos")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    def force_learn(self, source: str, query: str) -> str:
        """Aprendizaje forzado por el usuario"""
        try:
            if source == 'wikipedia':
                self._learn_from_wikipedia(query)
                count = Memory.query.filter(Memory.topic.contains(query)).count()
                return f"✅ Aprendí sobre '{query}' de Wikipedia. Ahora tengo {count} artículos relacionados."
            
            elif source == 'arxiv':
                self._learn_from_wikipedia(query)
                return f"✅ Investigación completada sobre '{query}' (usando Wikipedia como fuente principal)"
            
            else:
                return "❌ Fuente no disponible. Usa 'wikipedia'."
                
        except Exception as e:
            return f"❌ Error al aprender: {str(e)}"
    
    def teach(self, text: str) -> str:
        """Enseñar manualmente a la IA"""
        try:
            memory = Memory(
                content=text,
                source='user_teaching',
                topic='manual_teaching',
                access_count=1
            )
            db.session.add(memory)
            db.session.commit()
            return f"🎓 ¡Aprendido! He guardado: '{text[:50]}...' en mi memoria permanente."
        except Exception as e:
            return f"❌ Error guardando: {str(e)}"
    
    def get_status(self) -> dict:
        """Obtener estado del sistema"""
        total_memories = Memory.query.count()
        
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
            'total_conversations': Conversation.query.count(),
            'daily_learned': self.daily_learned,
            'learning_active': self.learning_active,
            'api_status': 'online' if self.api_available else 'offline',
            'mode': 'hybrid',
            'status': 'Funcionando correctamente'
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
        print(f"Error en chat: {e}")
        # Último fallback
        return jsonify({
            'response': 'Lo siento, tuve un problema. Estoy funcionando en modo offline limitado. Intenta preguntarme sobre IA, Python, o usa los botones de Wiki/Enseñar.',
            'model_used': 'emergency_fallback',
            'sources_used': ['emergency'],
            'error': str(e)
        }), 200  # Return 200 para no romper el frontend

@app.route('/learn', methods=['POST'])
def learn():
    """Endpoint para forzar aprendizaje"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        source = data.get('source', 'wikipedia')
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        result = bebe.force_learn(source, query)
        return jsonify({'message': result})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/teach', methods=['POST'])
def teach():
    """Endpoint para enseñar manualmente"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        text = data.get('correct', '').strip()
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        result = bebe.teach(text)
        return jsonify({'message': result})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """Endpoint de estado"""
    try:
        return jsonify(bebe.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/memories', methods=['GET'])
def get_memories():
    """Ver últimas memorias"""
    try:
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
        return jsonify({'error': str(e)}), 500

@app.route('/history', methods=['GET'])
def get_history():
    """Ver historial de conversaciones"""
    try:
        conversations = Conversation.query.order_by(Conversation.timestamp.desc()).limit(20).all()
        return jsonify([{
            'id': c.id,
            'user': c.user_message,
            'bot': arregla esto, el error persiste, mira el error exacto en los logs de render
            'timestamp': c.timestamp.isoformat()
        } for c in conversations])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
