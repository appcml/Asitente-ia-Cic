"""
Bebé IA Pro - Funcional con APIs y Auto-entrenamiento
"""
from flask import Flask, render_template, request, jsonify
import torch
import torch.nn as nn
import os
import json
import random
import re
import requests
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)

# ============ CONFIGURACIÓN ============
class Config:
    OPENWEATHER_API = os.environ.get('OPENWEATHER_API', '')  # API Key opcional
    NEWS_API = os.environ.get('NEWS_API', '')  # API Key opcional
    MEMORY_FILE = 'bebe_memory.json'
    LEARNING_FILE = 'bebe_learning.json'

# ============ MODELO NEURAL MEJORADO ============
class NeuralBrain(nn.Module):
    def __init__(self, vocab_size=1000, embed_dim=128, hidden_dim=256):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.encoder = nn.LSTM(embed_dim, hidden_dim, num_layers=2, 
                              batch_first=True, dropout=0.3, bidirectional=True)
        self.decoder = nn.LSTM(embed_dim, hidden_dim, num_layers=2,
                              batch_first=True, dropout=0.3)
        self.attention = nn.MultiheadAttention(hidden_dim, num_heads=4)
        self.fc = nn.Linear(hidden_dim * 2, vocab_size)
        
    def forward(self, x, target=None):
        # Encoder
        embedded = self.embedding(x)
        encoder_out, (hidden, cell) = self.encoder(embedded)
        
        # Decoder (si hay target, training mode)
        if target is not None:
            target_emb = self.embedding(target)
            decoder_out, _ = self.decoder(target_emb, (hidden, cell))
            # Attention
            attn_out, _ = self.attention(decoder_out, encoder_out, encoder_out)
            output = self.fc(attn_out)
            return output
        else:
            return encoder_out

# ============ TOKENIZADOR INTELIGENTE ============
class AdvancedTokenizer:
    def __init__(self):
        self.word2idx = {'<pad>': 0, '<unk>': 1, '<sos>': 2, '<eos>': 3, 
                        '<num>': 4, '<url>': 5, '<name>': 6}
        self.idx2word = {v: k for k, v in self.word2idx.items()}
        self.word_freq = defaultdict(int)
        
    def fit(self, texts):
        for text in texts:
            words = self._tokenize(text)
            for w in words:
                self.word_freq[w] += 1
        
        # Agregar palabras más frecuentes
        for word, freq in sorted(self.word_freq.items(), 
                                key=lambda x: x[1], reverse=True)[:900]:
            if word not in self.word2idx:
                self.word2idx[word] = len(self.word2idx)
        self.idx2word = {v: k for k, v in self.word2idx.items()}
        return self
    
    def _tokenize(self, text):
        """Tokenización avanzada"""
        # Detectar números
        text = re.sub(r'\d+', ' <num> ', text)
        # Detectar URLs
        text = re.sub(r'http\S+', ' <url> ', text)
        # Detectar nombres propios (simplificado)
        words = re.findall(r'\b[a-záéíóúñ]+\b', text.lower())
        return words
    
    def encode(self, text):
        words = self._tokenize(text)
        tokens = [self.word2idx.get(w, 1) for w in words]
        return [2] + tokens + [3]
    
    def decode(self, tokens, skip_special=True):
        words = []
        for t in tokens:
            if t <= 3 and skip_special:
                continue
            word = self.idx2word.get(t, '')
            if word:
                words.append(word)
        text = ' '.join(words)
        # Restaurar tokens especiales
        text = text.replace('<num>', '[número]')
        text = text.replace('<url>', '[enlace]')
        return text

# ============ SERVICIOS EXTERNOS ============
class ExternalServices:
    @staticmethod
    def get_weather(city="Santiago"):
        """Obtener clima real (simulado si no hay API key)"""
        if not Config.OPENWEATHER_API:
            # Simulación educativa
            conditions = [
                ("soleado", "25°C", "☀️"),
                ("nublado", "18°C", "☁️"),
                ("lluvioso", "15°C", "🌧️"),
                ("despejado", "22°C", "✨")
            ]
            cond, temp, icon = random.choice(conditions)
            return f"{icon} En {city} está {cond} con {temp}"
        
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={Config.OPENWEATHER_API}&units=metric&lang=es"
            r = requests.get(url, timeout=5)
            data = r.json()
            temp = data['main']['temp']
            desc = data['weather'][0]['description']
            return f"🌡️ {temp}°C, {desc} en {city}"
        except:
            return "No pude obtener el clima ahora 😅"
    
    @staticmethod
    def get_news():
        """Obtener noticias (simulado si no hay API key)"""
        if not Config.NEWS_API:
            topics = [
                "🤖 La IA está revolucionando la educación",
                "🌍 Nuevos avances en energía renovable",
                "🚀 SpaceX planea nuevas misiones a Marte",
                "💊 Descubrimiento médico importante",
                "📱 Nuevo smartphone con IA integrada"
            ]
            return random.choice(topics)
        
        try:
            url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={Config.NEWS_API}"
            r = requests.get(url, timeout=5)
            articles = r.json().get('articles', [])
            if articles:
                return f"📰 {articles[0]['title']}"
        except:
            pass
        return "No hay noticias disponibles ahora"
    
    @staticmethod
    def search_wikipedia(query):
        """Búsqueda simple de conocimiento"""
        knowledge = {
            'python': "Python es un lenguaje de programación versátil creado por Guido van Rossum en 1991 🐍",
            'ia': "La Inteligencia Artificial es la simulación de procesos humanos por máquinas 🤖",
            'machine learning': "Machine Learning permite a las máquinas aprender de datos sin programación explícita 📊",
            'neurona': "Las neuronas artificiales son unidades de procesamiento inspiradas en el cerebro biológico 🧠",
            'internet': "Internet es una red global de computadoras interconectadas 🌐",
        }
        query_lower = query.lower()
        for key, value in knowledge.items():
            if key in query_lower:
                return value
        return None

# ============ SISTEMA DE APRENDIZAJE ============
class LearningSystem:
    def __init__(self):
        self.patterns = defaultdict(list)  # Patrones de conversación
        self.user_preferences = defaultdict(dict)
        self.corrections = []  # Correcciones del usuario
        self.load_learning()
    
    def add_pattern(self, input_pattern, output_pattern):
        """Agregar patrón de conversación"""
        self.patterns[input_pattern].append({
            'output': output_pattern,
            'count': 1,
            'timestamp': datetime.now().isoformat()
        })
    
    def learn_from_correction(self, wrong, correct):
        """Aprender de correcciones explícitas"""
        self.corrections.append({
            'wrong': wrong,
            'correct': correct,
            'timestamp': datetime.now().isoformat()
        })
        self.save_learning()
    
    def get_best_response(self, user_input):
        """Buscar mejor respuesta basada en patrones aprendidos"""
        # Buscar coincidencias exactas primero
        if user_input in self.patterns:
            responses = self.patterns[user_input]
            # Devolver la más usada
            best = max(responses, key=lambda x: x['count'])
            best['count'] += 1
            return best['output']
        return None
    
    def save_learning(self):
        data = {
            'patterns': dict(self.patterns),
            'corrections': self.corrections,
            'preferences': dict(self.user_preferences)
        }
        with open(Config.LEARNING_FILE, 'w') as f:
            json.dump(data, f)
    
    def load_learning(self):
        if os.path.exists(Config.LEARNING_FILE):
            try:
                with open(Config.LEARNING_FILE, 'r') as f:
                    data = json.load(f)
                    self.patterns = defaultdict(list, data.get('patterns', {}))
                    self.corrections = data.get('corrections', [])
                    self.user_preferences = defaultdict(dict, data.get('preferences', {}))
            except:
                pass

# ============ BEbÉ IA PRO ============
class BebeIAPro:
    def __init__(self):
        self.memory_file = Config.MEMORY_FILE
        self.conversations = self._load_memory()
        self.learning = LearningSystem()
        self.services = ExternalServices()
        
        # Base de conocimiento inicial
        self.knowledge = {
            'intents': {
                'greeting': {
                    'patterns': ['hola', 'hey', 'buenas', 'saludos', 'qué tal', 'como estas'],
                    'responses': [
                        '¡Hola! ¿En qué puedo ayudarte hoy? 😊',
                        '¡Hola! Me alegra verte. ¿Qué necesitas?',
                        '¡Hey! ¿Cómo va tu día?'
                    ]
                },
                'weather': {
                    'patterns': ['clima', 'tiempo', 'temperatura', 'hace calor', 'hace frío', 'llueve'],
                    'action': 'get_weather'
                },
                'news': {
                    'patterns': ['noticias', 'novedades', 'qué pasa', 'actualidad'],
                    'action': 'get_news'
                },
                'search': {
                    'patterns': ['qué es', 'quién es', 'definición', 'significa', 'explica'],
                    'action': 'search_knowledge'
                },
                'name': {
                    'patterns': ['nombre', 'llamas', 'quién eres'],
                    'responses': ['Soy Bebé IA Pro, tu asistente funcional 🍼🚀']
                },
                'help': {
                    'patterns': ['ayuda', 'puedes hacer', 'funciones', 'capacidades'],
                    'responses': [
                        'Puedo: 1) Decirte el clima 🌤️ 2) Dar noticias 📰 3) Buscar información 📚 4) Aprender de ti 🧠 ¿Qué necesitas?'
                    ]
                },
                'thanks': {
                    'patterns': ['gracias', 'ty', 'thank you', 'agradecido'],
                    'responses': ['¡De nada! 😊', 'Para eso estoy', '¡Con gusto! 🌟']
                },
                'goodbye': {
                    'patterns': ['adiós', 'adios', 'bye', 'hasta luego', 'nos vemos'],
                    'responses': ['¡Hasta luego! 👋', 'Vuelve pronto', '¡Cuídate!']
                }
            }
        }
        
        self.current_context = {}
        self.user_name = None
    
    def chat(self, user_input):
        """Procesar entrada del usuario"""
        user_lower = user_input.lower()
        
        # 1. Verificar si hay corrección previa aprendida
        learned = self.learning.get_best_response(user_lower)
        if learned:
            return self._format_response(learned, 'aprendido')
        
        # 2. Detectar intención
        intent = self._detect_intent(user_lower)
        
        # 3. Ejecutar acción según intención
        if intent == 'weather':
            response = self.services.get_weather()
        elif intent == 'news':
            response = self.services.get_news()
        elif intent == 'search':
            # Extraer término de búsqueda
            search_term = self._extract_search_term(user_input)
            result = self.services.search_wikipedia(search_term)
            if result:
                response = result
            else:
                response = f"No tengo información sobre '{search_term}' en mi base de datos, pero puedo aprenderlo 📚"
        elif intent in self.knowledge['intents']:
            response = random.choice(self.knowledge['intents'][intent]['responses'])
        else:
            # Respuesta contextual inteligente
            response = self._generate_contextual_response(user_input)
        
        # 4. Guardar y aprender
        self._save_conversation(user_input, response)
        self.learning.add_pattern(user_lower, response.lower())
        
        return self._format_response(response, intent or 'conversación')
    
    def _detect_intent(self, text):
        """Detectar la intención del usuario"""
        for intent, data in self.knowledge['intents'].items():
            for pattern in data['patterns']:
                if pattern in text:
                    return intent
        return None
    
    def _extract_search_term(self, text):
        """Extraer término de búsqueda"""
        # Eliminar palabras comunes
        common = ['qué', 'que', 'es', 'un', 'una', 'el', 'la', 'los', 'las', 
                 'dime', 'sobre', 'acerca', 'de', 'explica']
        words = [w for w in text.lower().split() if w not in common]
        return ' '.join(words[:3]) if words else text
    
    def _generate_contextual_response(self, user_input):
        """Generar respuesta basada en contexto"""
        # Recordar contexto previo
        if self.conversations:
            last = self.conversations[-1]
            if 'porque' in user_input.lower() and 'porque' in last['user']:
                return "Entiendo tu curiosidad. ¿Qué más te gustaría saber?"
        
        # Respuestas contextuales
        if '?' in user_input:
            responses = [
                "Buena pregunta. Déjame pensar... 🤔",
                "Interesante interrogante. ¿Qué opinas tú?",
                "Eso es algo que estoy aprendiendo. ¿Tienes alguna teoría?",
            ]
        else:
            responses = [
                "Cuéntame más sobre eso 📝",
                "¿Por qué te interesa ese tema?",
                "Eso suena interesante. ¿Puedes profundizar?",
                "Estoy procesando esa información... 💭",
            ]
        
        return random.choice(responses)
    
    def teach(self, correct_response):
        """Enseñar al bebé una corrección"""
        if self.conversations:
            last = self.conversations[-1]
            old_response = last['bot']
            
            # Guardar corrección
            self.learning.learn_from_correction(last['user'], correct_response)
            
            # Actualizar última respuesta
            last['bot'] = correct_response
            self._save_memory()
            
            return f"¡Gracias! Aprendí que debería decir: '{correct_response}' 🎓"
        return "No hay conversación previa para corregir"
    
    def _format_response(self, text, intent_type):
        """Formatear respuesta con metadatos"""
        # Detectar emoción
        emotion = self._detect_emotion(text, intent_type)
        
        return {
            'response': text,
            'emotion': emotion,
            'stage': self._get_stage(),
            'memories': len(self.conversations),
            'intent': intent_type
        }
    
    def _detect_emotion(self, text, intent):
        """Detectar emoción de la respuesta"""
        if intent == 'greeting':
            return 'alegre'
        elif intent == 'weather' or intent == 'news':
            return 'informativo'
        elif 'triste' in text or 'lo siento' in text:
            return 'empático'
        elif '?' in text:
            return 'curioso'
        elif 'gracias' in text or 'gusto' in text:
            return 'agradecido'
        else:
            return 'amigable'
    
    def _get_stage(self):
        """Determinar etapa de desarrollo"""
        count = len(self.conversations)
        if count < 20:
            return 'recién nacido 🍼'
        elif count < 50:
            return 'infante 👶'
        elif count < 100:
            return 'niño curioso 🧒'
        elif count < 200:
            return 'estudiante 📚'
        else:
            return 'experto 🎓'
    
    def _save_conversation(self, user_msg, bot_msg):
        """Guardar conversación en memoria"""
        self.conversations.append({
            'user': user_msg,
            'bot': bot_msg,
            'timestamp': datetime.now().isoformat(),
            'context': self.current_context
        })
        self._save_memory()
    
    def _load_memory(self):
        """Cargar memoria desde archivo"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_memory(self):
        """Guardar memoria en archivo"""
        with open(self.memory_file, 'w') as f:
            json.dump(self.conversations[-500:], f)  # Últimas 500 conversaciones

# ============ INICIALIZACIÓN ============
print("🚀 Inicializando Bebé IA Pro...")
bebe = BebeIAPro()
print(f"✅ Listo! {len(bebe.conversations)} conversaciones en memoria")

# ============ RUTAS FLASK ============
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')
    result = bebe.chat(message)
    return jsonify(result)

@app.route('/teach', methods=['POST'])
def teach():
    data = request.json
    correct = data.get('correct', '')
    result = bebe.teach(correct)
    return jsonify({'status': 'ok', 'message': result})

@app.route('/sleep', methods=['POST'])
def sleep():
    """Guardar todo el estado"""
    bebe._save_memory()
    bebe.learning.save_learning()
    return jsonify({
        'status': 'ok', 
        'message': f'💤 Dormí y guardé {len(bebe.conversations)} recuerdos y {len(bebe.learning.patterns)} patrones aprendidos'
    })

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'stage': bebe._get_stage(),
        'interactions': len(bebe.conversations),
        'patterns_learned': len(bebe.learning.patterns),
        'emotion': 'funcional',
        'memories': len(bebe.conversations)
    })

@app.route('/stats', methods=['GET'])
def stats():
    """Estadísticas detalladas"""
    return jsonify({
        'total_conversations': len(bebe.conversations),
        'patterns_learned': len(bebe.learning.patterns),
        'corrections_received': len(bebe.learning.corrections),
        'intents_recognized': list(bebe.knowledge['intents'].keys()),
        'last_conversation': bebe.conversations[-1] if bebe.conversations else None
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
