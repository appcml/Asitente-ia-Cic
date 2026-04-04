"""
Bebé IA - App completa todo-en-uno (sin dependencias externas)
"""
from flask import Flask, render_template, request, jsonify
import torch
import torch.nn as nn
import os
import json
import random
import numpy as np
from datetime import datetime

app = Flask(__name__)

# ============ CONFIGURACIÓN ============
class Config:
    VOCAB_SIZE = 1000
    EMBED_DIM = 64
    NUM_HEADS = 2
    NUM_LAYERS = 2
    HIDDEN_DIM = 128
    MAX_SEQ_LEN = 128
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")
    MEMORY_PATH = os.path.join(BASE_DIR, "memory.json")
    
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

# ============ TOKENIZADOR ============
class SimpleTokenizer:
    def __init__(self, vocab_size=1000):
        self.vocab = {'<pad>': 0, '<unk>': 1, '<sos>': 2, '<eos>': 3}
        self.reverse_vocab = {v: k for k, v in self.vocab.items()}
        self.vocab_size = vocab_size
    
    def train(self, texts):
        words = set()
        for text in texts:
            words.update(text.lower().split())
        for word in sorted(words)[:self.vocab_size - 4]:
            if word not in self.vocab:
                self.vocab[word] = len(self.vocab)
        self.reverse_vocab = {v: k for k, v in self.vocab.items()}
    
    def encode(self, text):
        tokens = [self.vocab.get(word.lower(), self.vocab['<unk>']) 
                  for word in text.split()]
        return [self.vocab['<sos>']] + tokens + [self.vocab['<eos>']]
    
    def decode(self, tokens):
        words = []
        for t in tokens:
            word = self.reverse_vocab.get(t, '')
            if word not in ['<pad>', '<sos>', '<eos>', '<unk>']:
                words.append(word)
        return ' '.join(words) if words else "No entiendo bien 🤔"
    
    def save(self, path):
        with open(path, 'w') as f:
            json.dump(self.vocab, f)
    
    def load(self, path):
        with open(path, 'r') as f:
            self.vocab = json.load(f)
        self.reverse_vocab = {v: k for k, v in self.vocab.items()}

# ============ MODELO ============
class BabyTransformer(nn.Module):
    def __init__(self, vocab_size, d_model=64, num_heads=2, num_layers=2):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.pos_emb = nn.Parameter(torch.randn(1, 128, d_model))
        
        layer = nn.TransformerEncoderLayer(d_model, num_heads, d_model*2, batch_first=True)
        self.transformer = nn.TransformerEncoder(layer, num_layers)
        self.fc = nn.Linear(d_model, vocab_size)
        
    def forward(self, x):
        seq_len = x.size(1)
        x = self.embedding(x) + self.pos_emb[:, :seq_len, :]
        x = self.transformer(x)
        return self.fc(x)
    
    def generate(self, input_ids, max_length=30, temperature=0.8):
        self.eval()
        generated = input_ids.clone()
        
        with torch.no_grad():
            for _ in range(max_length):
                output = self(generated)
                logits = output[:, -1, :] / temperature
                probs = torch.softmax(logits, dim=-1)
                next_token = torch.multinomial(probs, 1)
                generated = torch.cat([generated, next_token], dim=1)
                
                if next_token.item() == 3:  # <eos>
                    break
        return generated

# ============ MEMORIA ============
class Memory:
    def __init__(self, path):
        self.path = path
        self.memories = []
        self.load()
    
    def add(self, user_msg, bot_msg):
        self.memories.append({
            'user': user_msg,
            'bot': bot_msg,
            'time': datetime.now().isoformat()
        })
        if len(self.memories) > 100:
            self.memories = self.memories[-50:]
        self.save()
    
    def get_context(self, query, k=2):
        if not self.memories:
            return ""
        # Simple matching
        matches = []
        for m in self.memories[-10:]:
            matches.append(f"Usuario: {m['user']} | Bebé: {m['bot']}")
        return " | ".join(matches[-k:])
    
    def save(self):
        try:
            with open(self.path, 'w') as f:
                json.dump(self.memories, f)
        except:
            pass
    
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    self.memories = json.load(f)
            except:
                self.memories = []

# ============ PERSONALIDAD ============
class Personality:
    def __init__(self):
        self.stage = "recién nacido"
        self.emotion = "curioso"
        self.interactions = 0
    
    def update(self):
        self.interactions += 1
        if self.interactions > 20:
            self.stage = "infante"
        if self.interactions > 50:
            self.stage = "niño"
    
    def get_emotion(self):
        emotions = ["curioso", "feliz", "emocionado", "tranquilo"]
        return random.choice(emotions)

# ============ BEbÉ IA ============
class BebeIA:
    def __init__(self):
        self.config = Config()
        self.tokenizer = SimpleTokenizer()
        self.memory = Memory(self.config.MEMORY_PATH)
        self.personality = Personality()
        self.model = None
        self._init_model()
    
    def _init_model(self):
        # Textos de entrenamiento básicos
        textos = [
            "hola soy un bebé", "quiero aprender cosas nuevas",
            "me gusta cuando me hablas", "no sé mucho pero intento",
            "eso es interesante cuéntame más", "gracias por enseñarme",
            "no entiendo bien puedes explicarme", "me encanta aprender contigo",
            "qué significa eso", "wow eso es nuevo para mí",
            "hola cómo estás", "me llamo bebé ia",
            "tengo muchas ganas de aprender", "eres muy amable",
            "cuéntame un cuento", "por qué pasa eso"
        ]
        
        # Entrenar tokenizador
        self.tokenizer.train(textos)
        
        # Crear modelo
        self.model = BabyTransformer(
            vocab_size=len(self.tokenizer.vocab),
            d_model=self.config.EMBED_DIM,
            num_heads=self.config.NUM_HEADS,
            num_layers=self.config.NUM_LAYERS
        )
        
        # Intentar cargar pesos si existen
        model_path = os.path.join(self.config.CHECKPOINT_DIR, "model.pt")
        if os.path.exists(model_path):
            try:
                self.model.load_state_dict(torch.load(model_path, map_location='cpu'))
            except:
                pass
    
    def chat(self, user_input):
        try:
            # Contexto de memoria
            context = self.memory.get_context(user_input)
            
            # Preparar input
            prompt = f"{context} Usuario: {user_input} Bebé:"
            input_ids = torch.tensor([self.tokenizer.encode(prompt)])
            
            if input_ids.size(1) > self.config.MAX_SEQ_LEN:
                input_ids = input_ids[:, -self.config.MAX_SEQ_LEN:]
            
            # Generar respuesta
            output_ids = self.model.generate(input_ids, max_length=25, temperature=0.9)
            response = self.tokenizer.decode(output_ids[0].tolist())
            
            # Limpiar respuesta
            response = response.replace(prompt, "").strip()
            response = response.split("Usuario:")[0].strip()
            
            # Si está vacía o muy corta, usar respuesta por defecto
            if len(response) < 3:
                responses = [
                    "¡Qué interesante! Cuéntame más 🍼",
                    "Estoy aprendiendo eso, ¿puedes explicarme mejor?",
                    "Me gusta cuando hablamos de eso 😊",
                    "¿Eso qué significa? Estoy curioso 🤔",
                    "Wow, eso es nuevo para mí, gracias por enseñarme ✨",
                    "No entiendo bien aún, pero quiero aprender 💪"
                ]
                response = random.choice(responses)
            
            # Guardar en memoria
            self.memory.add(user_input, response)
            self.personality.update()
            
            return {
                'response': response,
                'emotion': self.personality.get_emotion(),
                'stage': self.personality.stage,
                'memories': len(self.memory.memories)
            }
            
        except Exception as e:
            print(f"Error: {e}")
            return {
                'response': "Ups, me dormí un poco... 😴 ¿Me repites?",
                'emotion': 'confundido',
                'stage': self.personality.stage,
                'memories': len(self.memory.memories)
            }
    
    def sleep(self):
        # Guardar modelo
        model_path = os.path.join(self.config.CHECKPOINT_DIR, "model.pt")
        torch.save(self.model.state_dict(), model_path)
        return {'status': 'ok', 'message': 'He dormido y guardado mis recuerdos 💤'}
    
    def teach(self, correct):
        if self.memory.memories:
            last = self.memory.memories[-1]
            last['bot'] = correct
            self.memory.save()
        return {'status': 'ok'}

# Instancia global
bebe = BebeIA()

# ============ RUTAS ============
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    result = bebe.chat(data.get('message', ''))
    return jsonify(result)

@app.route('/teach', methods=['POST'])
def teach():
    data = request.json
    result = bebe.teach(data.get('correct', ''))
    return jsonify(result)

@app.route('/sleep', methods=['POST'])
def sleep():
    result = bebe.sleep()
    return jsonify(result)

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'stage': bebe.personality.stage,
        'interactions': bebe.personality.interactions,
        'emotion': bebe.personality.get_emotion(),
        'memories': len(bebe.memory.memories)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
