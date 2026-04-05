"""
Cic_IA - Asistente Inteligente con Modo Desarrollador
✅ Interfaz tipo ChatGPT/Claude
✅ Modo desarrollador con autenticación
✅ Adjuntar documentos e imágenes
✅ Menú lateral con secciones
✅ Sistema de memoria y aprendizaje
"""
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os
import json
import random
import threading
import time
import urllib.request
import urllib.parse
import re
import hashlib

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
    source = db.Column(db.String(50), default='local')
    topic = db.Column(db.String(200))
    file_path = db.Column(db.String(500))  # NUEVO: Archivo adjunto
    file_type = db.Column(db.String(50))   # NUEVO: Tipo de archivo
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    access_count = db.Column(db.Integer, default=0)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    has_attachment = db.Column(db.Boolean, default=False)  # NUEVO
    attachment_path = db.Column(db.String(500))            # NUEVO
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LearningLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=date.today, unique=True)
    count = db.Column(db.Integer, default=0)

class DeveloperSession(db.Model):  # NUEVO: Sesiones de desarrollador
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_access = db.Column(db.DateTime, default=datetime.utcnow)

# Crear tablas
with app.app_context():
    db.create_all()
    print("✅ Base de datos inicializada")

# ============ CONFIGURACIÓN DESARROLLADOR ============
DEV_PASSWORD_HASH = hashlib.sha256("CicDev2024!".encode()).hexdigest()  # Cambia esta contraseña

def verify_dev_token(token):
    """Verificar si el token de desarrollador es válido"""
    if not token:
        return False
    with app.app_context():
        session = DeveloperSession.query.filter_by(token=token).first()
        if session:
            session.last_access = datetime.utcnow()
            db.session.commit()
            return True
    return False

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
        'keywords': ['qué día es', 'qué hora es', 'fecha actual', 'hora actual', 'hoy es']
    },
    'cic_ia': {
        'respuestas': [
            "Soy Cic_IA, una inteligencia artificial en desarrollo creada para aprender y asistir.",
            "Cic_IA está construida con Python y Flask, alojada en Render con PostgreSQL."
        ],
        'keywords': ['quién eres', 'qué eres', 'cic_ia', 'tu nombre', 'presentación']
    },
    'default': {
        'respuestas': [
            "Interesante tema sobre '{tema}'. Puedo investigar más si usas el botón 📚 **Wiki**.",
            "Estoy aprendiendo sobre '{tema}'. ¿Quieres enseñarme más con el botón 🎓 **Enseñar**?"
        ],
        'keywords': []
    }
}

# ============ CLASE CIC_IA ============
class CicIA:
    def __init__(self):
        self.learning_active = True
        
        with app.app_context():
            self.stats = {
                'memories': Memory.query.count(),
                'conversations': Conversation.query.count(),
                'today_learned': self._get_today_count()
            }
        
        # Iniciar threads
        threading.Thread(target=self._auto_learn_loop, daemon=True).start()
        
        print("=" * 60)
        print("🚀 CIC_IA INICIADA")
        print(f"📚 Memorias: {self.stats['memories']}")
        print(f"💬 Conversaciones: {self.stats['conversations']}")
        print(f"📈 Aprendidos hoy: {self.stats['today_learned']}")
        print("=" * 60)
    
    def _get_today_count(self):
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        return log.count if log else 0
    
    def chat(self, user_input, mode='balanced', attachment_info=None):
        """Procesar mensaje con soporte para adjuntos"""
        input_lower = user_input.lower().strip()
        
        # Fecha/hora dinámica
        if self._is_date_time_question(input_lower):
            response = self._get_dynamic_date_response(input_lower)
            return self._save_conversation(user_input, response, 'system_time', 
                                         attachment_info=attachment_info)
        
        # Buscar en conocimiento base
        best_topic = self._find_best_topic(input_lower)
        
        # Buscar en memorias
        with app.app_context():
            memories = Memory.query.all()
            relevant_memories = self._find_relevant_memories(input_lower, memories)
            
            # Generar respuesta
            if best_topic and best_topic != 'default':
                response = random.choice(KNOWLEDGE_BASE[best_topic]['respuestas'])
                source = 'knowledge_base'
            elif relevant_memories:
                mem = relevant_memories[0]
                response = f"Basándome en mi conocimiento: {mem.content[:300]}"
                source = f"memory_{mem.source}"
            else:
                tema = user_input[:40] if len(user_input) > 5 else "este tema"
                response = random.choice(KNOWLEDGE_BASE['default']['respuestas']).format(tema=tema)
                source = 'learning'
            
            # Ajustar según modo
            if mode == 'fast':
                response = response.split('.')[0] + '.' if '.' in response else response[:100]
            elif mode == 'complete':
                response += "\n\n¿Te gustaría que profundice en este tema?"
            
            return self._save_conversation(user_input, response, source,
                                         attachment_info=attachment_info,
                                         memories_count=len(relevant_memories))
    
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
                          attachment_info=None, memories_count=0):
        with app.app_context():
            conv = Conversation(
                user_message=user_msg,
                bot_response=bot_resp,
                has_attachment=attachment_info is not None,
                attachment_path=attachment_info.get('path') if attachment_info else None
            )
            db.session.add(conv)
            db.session.commit()
            
            total_mem = Memory.query.count()
        
        return {
            'response': bot_resp,
            'model_used': 'cic_ia_v1',
            'sources_used': [source],
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
        hora = f"⏰ Son las {now.strftime('%H:%M')}"
        
        if 'hora' in text:
            return f"{fecha}\n{hora}"
        return fecha
    
    def process_file(self, file_path, file_type):
        """Procesar archivo adjunto y extraer contenido"""
        try:
            if file_type == 'text' or file_path.endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()[:2000]  # Primeros 2000 chars
            
            elif file_path.endswith('.pdf'):
                return "[Documento PDF adjunto - contenido procesable]"
            
            elif file_type.startswith('image'):
                return "[Imagen adjunta - analizable]"
            
            else:
                return f"[Archivo {file_path.split('.')[-1]} adjunto]"
                
        except Exception as e:
            return f"[Error procesando archivo: {str(e)}]"
    
    def force_learn(self, query, source='wikipedia'):
        """Aprendizaje forzado"""
        try:
            with app.app_context():
                if source == 'wikipedia':
                    self._learn_from_wikipedia(query)
                    count = Memory.query.filter(Memory.topic.contains(query)).count()
                    total = Memory.query.count()
                    return f"✅ Aprendí sobre '{query}'. Total: {total} memorias."
                return "❌ Fuente no soportada."
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def teach(self, text, topic=None):
        """Enseñar manualmente"""
        try:
            with app.app_context():
                mem = Memory(
                    content=text,
                    source='user_teaching',
                    topic=topic or 'Manual',
                    access_count=1
                )
                db.session.add(mem)
                db.session.commit()
                self._increment_today_count()
                return f"🎓 Aprendido. Total: {Memory.query.count()} memorias."
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def _increment_today_count(self):
        today = date.today()
        log = LearningLog.query.filter_by(date=today).first()
        if not log:
            log = LearningLog(date=today, count=0)
            db.session.add(log)
        log.count += 1
        db.session.commit()
        self.stats['today_learned'] = log.count
    
    def _learn_from_wikipedia(self, query):
        try:
            url = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&srlimit=2"
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
            
            for item in data['query']['search']:
                title = item['title']
                content_url = f"https://es.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&exchars=1000&titles={urllib.parse.quote(title)}&format=json"
                
                with urllib.request.urlopen(content_url, timeout=15) as resp:
                    content_data = json.loads(resp.read())
                
                content = list(content_data['query']['pages'].values())[0].get('extract', '')
                
                if content and len(content) > 50 and not Memory.query.filter_by(topic=title).first():
                    mem = Memory(
                        content=f"Wikipedia - {title}: {content[:800]}",
                        source='wikipedia',
                        topic=title
                    )
                    db.session.add(mem)
                    db.session.commit()
                    self._increment_today_count()
                    print(f"✅ Aprendido: {title}")
                    
        except Exception as e:
            print(f"❌ Error Wikipedia: {e}")
    
    def _auto_learn_loop(self):
        while self.learning_active:
            try:
                with app.app_context():
                    if Memory.query.count() < 100:
                        topics = ['inteligencia artificial', 'python', 'tecnología', 'ciencia']
                        self._learn_from_wikipedia(random.choice(topics))
                time.sleep(900)
            except Exception as e:
                print(f"Error auto-learn: {e}")
                time.sleep(300)
    
    def get_stats(self):
        with app.app_context():
            return {
                'stage': '🧠 Experto' if Memory.query.count() > 300 else '🔬 Investigador' if Memory.query.count() > 100 else '📚 Estudiante' if Memory.query.count() > 20 else '🍼 Aprendiz',
                'total_memories': Memory.query.count(),
                'total_conversations': Conversation.query.count(),
                'today_learned': self._get_today_count(),
                'db_size': 'PostgreSQL' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite',
                'uploads_count': len(os.listdir(UPLOAD_FOLDER)) if os.path.exists(UPLOAD_FOLDER) else 0
            }

cic_ia = CicIA()

# ============ RUTAS API ============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        mode = data.get('mode', 'balanced')
        
        if not message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        result = cic_ia.chat(message, mode)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat-with-file', methods=['POST'])
def chat_with_file():
    """NUEVO: Chat con archivo adjunto"""
    try:
        message = request.form.get('message', '').strip()
        mode = request.form.get('mode', 'balanced')
        
        attachment_info = None
        
        if 'file' in request.files:
            file = request.files['file']
            if file.filename:
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                attachment_info = {
                    'path': filepath,
                    'filename': file.filename,
                    'type': file.content_type
                }
                
                # Procesar contenido del archivo
                file_content = cic_ia.process_file(filepath, file.content_type)
                message = f"{message}\n\n[Contenido del archivo: {file_content}]"
        
        result = cic_ia.chat(message, mode, attachment_info)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/learn', methods=['POST'])
def learn():
    try:
        data = request.get_json()
        result = cic_ia.force_learn(data.get('query'), data.get('source', 'wikipedia'))
        return jsonify({'message': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/teach', methods=['POST'])
def teach():
    try:
        data = request.get_json()
        result = cic_ia.teach(data.get('text'), data.get('topic'))
        return jsonify({'message': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def status():
    return jsonify(cic_ia.get_stats())

@app.route('/api/memories')
def get_memories():
    try:
        with app.app_context():
            mems = Memory.query.order_by(Memory.created_at.desc()).limit(20).all()
            return jsonify([{
                'id': m.id,
                'topic': m.topic,
                'source': m.source,
                'preview': m.content[:100] + '...',
                'date': m.created_at.strftime('%d/%m/%Y'),
                'has_file': m.file_path is not None
            } for m in mems])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history')
def get_history():
    try:
        with app.app_context():
            convs = Conversation.query.order_by(Conversation.timestamp.desc()).limit(50).all()
            return jsonify([{
                'id': c.id,
                'user': c.user_message[:100],
                'bot': c.bot_response[:100],
                'has_attachment': c.has_attachment,
                'date': c.timestamp.strftime('%d/%m/%Y %H:%M')
            } for c in convs])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ RUTAS DESARROLLADOR ============

@app.route('/api/dev/login', methods=['POST'])
def dev_login():
    """Login para modo desarrollador"""
    try:
        data = request.get_json()
        password = data.get('password', '')
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if password_hash == DEV_PASSWORD_HASH:
            # Crear token
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
    """Verificar token de desarrollador"""
    token = request.headers.get('X-Dev-Token')
    return jsonify({'valid': verify_dev_token(token)})

@app.route('/api/dev/logs')
def dev_logs():
    """Obtener logs del sistema (solo dev)"""
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
                    'dev_sessions': DeveloperSession.query.count()
                },
                'recent_memories': [{
                    'id': m.id,
                    'topic': m.topic,
                    'source': m.source,
                    'content': m.content[:200],
                    'created': m.created_at.isoformat()
                } for m in Memory.query.order_by(Memory.created_at.desc()).limit(5).all()],
                'files_in_uploads': os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else []
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dev/clear-db', methods=['POST'])
def dev_clear_db():
    """Limpiar base de datos (solo dev)"""
    token = request.headers.get('X-Dev-Token')
    if not verify_dev_token(token):
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        with app.app_context():
            Memory.query.delete()
            Conversation.query.delete()
            LearningLog.query.delete()
            db.session.commit()
            return jsonify({'message': 'Base de datos limpiada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Servir archivos subidos"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
