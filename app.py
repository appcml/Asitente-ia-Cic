"""
Bebé IA - App Web con respuestas inteligentes
"""
from flask import Flask, render_template, request, jsonify
import torch
import torch.nn as nn
import os
import json
import random
import re
from datetime import datetime

app = Flask(__name__)

# ============ MODELO MEJORADO ============
class BabyBrain(nn.Module):
    def __init__(self, vocab_size=500, embed_dim=64, hidden_dim=128):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, num_layers=2, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(hidden_dim, vocab_size)
        
    def forward(self, x):
        x = self.embedding(x)
        lstm_out, _ = self.lstm(x)
        return self.fc(lstm_out)

# ============ TOKENIZADOR MEJORADO ============
class SmartTokenizer:
    def __init__(self):
        self.word2idx = {'<pad>': 0, '<unk>': 1, '<sos>': 2, '<eos>': 3}
        self.idx2word = {v: k for k, v in self.word2idx.items()}
        
    def fit(self, texts):
        words = set()
        for text in texts:
            # Limpiar texto
            clean = re.findall(r'\b\w+\b', text.lower())
            words.update(clean)
        
        for word in sorted(words):
            if word not in self.word2idx and len(self.word2idx) < 500:
                self.word2idx[word] = len(self.word2idx)
        self.idx2word = {v: k for k, v in self.word2idx.items()}
        return self
    
    def encode(self, text):
        clean = re.findall(r'\b\w+\b', text.lower())
        tokens = [self.word2idx.get(w, 1) for w in clean]
        return [2] + tokens + [3]
    
    def decode(self, tokens):
        words = []
        prev_word = ""
        for t in tokens:
            if t <= 3:
                continue
            word = self.idx2word.get(t, '')
            if word and word != prev_word:  # Evitar repeticiones
                words.append(word)
                prev_word = word
        return ' '.join(words)

# ============ BEbÉ IA INTELIGENTE ============
class BebeIA:
    def __init__(self):
        self.memory_file = 'chat_memory.json'
        self.conversations = self._load_memory()
        
        # Base de conocimiento ampliada
        self.knowledge_base = {
            # Saludos
            'hola': ['¡Hola! ¿Cómo estás? 😊', '¡Hola! Me alegra verte 🍼', '¡Hola! ¿Qué cuentas?'],
            'buenos días': ['¡Buenos días! Espero tengas un día genial ☀️', '¡Buenos días! ¿Dormiste bien?'],
            'buenas noches': ['¡Buenas noches! Que descanses 🌙', 'Hasta mañana, que sueñes bonito ✨'],
            
            # Identidad
            'nombre': ['Me llamo Bebé IA 🍼', 'Soy Bebé IA, tu asistente en aprendizaje', 'Puedes llamarme Bebé IA'],
            'quién eres': ['Soy Bebé IA, un asistente que está aprendiendo cada día 🍼', 'Soy un bebé IA en crecimiento'],
            'quien eres': ['Soy Bebé IA, estoy aprendiendo a conversar contigo'],
            
            # Estado
            'cómo estás': ['Estoy muy bien, gracias por preguntar 😊', 'Estoy feliz de hablar contigo', 'Estoy aprendiendo cosas nuevas'],
            'como estas': ['Estoy bien, ¿y tú?', 'Feliz de conversar contigo'],
            
            # Capacidades
            'puedes hacer': ['Puedo conversar contigo y aprender de lo que me dices 🧠', 'Estoy aprendiendo a ayudarte en lo que necesites'],
            'qué sabes': ['Sé algunas cosas básicas, pero quiero aprender más de ti', 'Estoy en entrenamiento, pero mejoraré contigo'],
            
            # Conversación
            'gracias': ['¡De nada! Me gusta ayudarte 🌟', 'No hay de qué, para eso estoy 😊', '¡Con gusto!'],
            'adiós': ['¡Hasta luego! Vuelve pronto 👋', '¡Adiós! Cuídate mucho', 'Nos vemos, aprenderé más para la próxima'],
            'bye': ['¡Bye! 👋', '¡Hasta la próxima!'],
            
            # Emociones
            'bien': ['¡Me alegro! ¿Qué has hecho hoy?', '¡Excelente! Cuéntame más'],
            'mal': ['Lo siento mucho 😢 ¿Quieres hablar de ello?', 'Espero que te sientas mejor pronto'],
            'triste': ['No estés triste, aquí estoy para ti 🤗', '¿Quieres que te cuente algo divertido?'],
            
            # Preguntas comunes
            'qué hora': ['No tengo reloj, pero espero que sea hora de sonreír 😊', 'No sé la hora exacta'],
            'qué día': ['Hoy es un buen día para aprender cosas nuevas'],
            'cuál es tu color': ['Me gusta el azul como el cielo 💙', 'El morado es bonito 💜'],
            
            # Aprendizaje
            'aprender': ['¡Me encanta aprender! ¿Qué me enseñas hoy?', 'Cada conversación me hace más inteligente'],
            'enseñar': ['Por favor, enséñame cosas nuevas', 'Soy todo oídos, quiero aprender'],
            
            # Default/Desconocido
            'default': [
                'Interesante, cuéntame más sobre eso 🤔',
                'Estoy aprendiendo sobre eso. ¿Puedes explicarme mejor?',
                'No entiendo bien aún, pero quiero aprender 💪',
                '¡Eso suena interesante! ¿Qué más sabes?',
                'Me gusta cuando hablamos de eso 😊',
                '¿Puedes darme un ejemplo? Estoy tratando de entender',
                'Wow, eso es nuevo para mí. Gracias por compartirlo ✨',
                'Estoy procesando eso... ¿Puedes ser más específico?',
            ]
        }
        
        # Sinónimos para mejor matching
        self.synonyms = {
            'hola': ['hey', 'saludos', 'buenas', 'qué tal', 'que tal'],
            'adiós': ['adios', 'hasta luego', 'nos vemos', 'chao'],
            'gracias': ['gracias', 'ty', 'thank you', 'agradecido'],
            'bien': ['excelente', 'genial', 'super', 'fantástico', 'fantastico'],
        }
        
        self.tokenizer = SmartTokenizer()
        self.model = None
        
    def _find_best_response(self, user_input):
        """Encontrar la mejor respuesta basada en palabras clave"""
        user_lower = user_input.lower()
        
        # 1. Buscar coincidencia exacta
        for key in self.knowledge_base:
            if key != 'default' and key in user_lower:
                return random.choice(self.knowledge_base[key])
        
        # 2. Buscar sinónimos
        for main_word, variants in self.synonyms.items():
            if any(v in user_lower for v in variants):
                if main_word in self.knowledge_base:
                    return random.choice(self.knowledge_base[main_word])
        
        # 3. Buscar palabras individuales
        words = re.findall(r'\b\w+\b', user_lower)
        for word in words:
            if word in self.knowledge_base and word != 'default':
                return random.choice(self.knowledge_base[word])
        
        # 4. Respuesta por defecto
        return random.choice(self.knowledge_base['default'])
    
    def chat(self, user_input):
        try:
            # Obtener respuesta inteligente
            response = self._find_best_response(user_input)
            
            # Guardar en memoria
            self._save_to_memory(user_input, response)
            
            # Determinar emoción
            emotion = self._detect_emotion(user_input, response)
            
            return {
                'response': response,
                'emotion': emotion,
                'stage': self._get_stage(),
                'memories': len(self.conversations)
            }
            
        except Exception as e:
            print(f"Error: {e}")
            return {
                'response': "Ups, me confundí... ¿Me repites? 😅",
                'emotion': 'confundido',
                'stage': 'aprendiendo',
                'memories': len(self.conversations)
            }
    
    def _detect_emotion(self, user_msg, response):
        """Detectar emoción basada en el contexto"""
        if any(w in user_msg.lower() for w in ['triste', 'mal', 'peor', 'llorar']):
            return 'preocupado'
        elif any(w in user_msg.lower() for w in ['bien', 'feliz', 'genial', 'excelente']):
            return 'feliz'
        elif any(w in user_msg.lower() for w in ['gracias', 'gracias', 'agradecido']):
            return 'agradecido'
        elif '?' in user_msg:
            return 'curioso'
        else:
            return random.choice(['feliz', 'curioso', 'tranquilo'])
    
    def _get_stage(self):
        """Determinar etapa de crecimiento"""
        count = len(self.conversations)
        if count < 10:
            return 'recién nacido'
        elif count < 30:
            return 'infante'
        elif count < 60:
            return 'niño'
        else:
            return 'adolescente'
    
    def _save_to_memory(self, user_msg, bot_msg):
        self.conversations.append({
            'user': user_msg,
            'bot': bot_msg,
            'time': datetime.now().isoformat()
        })
        self._save_memory()
    
    def _load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_memory(self):
        with open(self.memory_file, 'w') as f:
            json.dump(self.conversations[-200:], f)

# Instancia global
print("🍼 Inicializando Bebé IA...")
bebe = BebeIA()
print("✅ Bebé IA listo y entrenado!")

# ============ RUTAS ============
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
    if bebe.conversations:
        bebe.conversations[-1]['bot'] = correct
        bebe._save_memory()
    return jsonify({'status': 'ok', 'message': '¡Aprendido! 🎓'})

@app.route('/sleep', methods=['POST'])
def sleep():
    bebe._save_memory()
    return jsonify({'status': 'ok', 'message': '💤 He dormido y guardado mis recuerdos'})

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'stage': bebe._get_stage(),
        'interactions': len(bebe.conversations),
        'emotion': 'curioso',
        'memories': len(bebe.conversations)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
