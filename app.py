"""
Bebé IA - App Web con Flask (Producción)
"""
from flask import Flask, render_template, request, jsonify
import torch
import os
import sys
import json
from datetime import datetime

app = Flask(__name__)

# Configuración para producción
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bebe-ia-secret-key')

class SimpleConfig:
    """Configuración simplificada para producción"""
    VOCAB_SIZE = 5000
    EMBED_DIM = 128  # Reducido para más velocidad
    NUM_HEADS = 4
    NUM_LAYERS = 4   # Reducido
    HIDDEN_DIM = 256
    MAX_SEQ_LEN = 256
    DROPOUT = 0.1
    DEVICE = "cpu"   # Render usa CPU
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")
    MEMORY_DIR = os.path.join(BASE_DIR, "memory")
    
    MODEL_PATH = os.path.join(CHECKPOINT_DIR, "model.pt")
    MEMORY_PATH = os.path.join(MEMORY_DIR, "vector_store.db")
    TOKENIZER_PATH = os.path.join(CHECKPOINT_DIR, "tokenizer.json")
    
    @classmethod
    def ensure_dirs(cls):
        for d in [cls.CHECKPOINT_DIR, cls.MEMORY_DIR]:
            os.makedirs(d, exist_ok=True)

class SimpleTokenizer:
    """Tokenizador simple"""
    def __init__(self, vocab_size=5000):
        self.vocab_size = vocab_size
        self.vocab = {'<pad>': 0, '<unk>': 1, '<sos>': 2, '<eos>': 3}
        self.reverse_vocab = {v: k for k, v in self.vocab.items()}
    
    def train(self, texts):
        words = set()
        for text in texts:
            words.update(text.lower().split())
        for word in sorted(words)[:self.vocab_size - 4]:
            if word not in self.vocab:
                self.vocab[word] = len(self.vocab)
        self.reverse_vocab = {v: k for k, v in self.vocab.items()}
    
    def encode(self, text):
        tokens = [self.vocab.get(word, self.vocab['<unk>']) 
                  for word in text.lower().split()]
        return [self.vocab['<sos>']] + tokens + [self.vocab['<eos>']]
    
    def decode(self, tokens):
        words = [self.reverse_vocab.get(t, '<unk>') for t in tokens]
        return ' '.join(words).replace('<sos>', '').replace('<eos>', '').replace('<pad>', '').strip()
    
    def save(self, path):
        with open(path, 'w') as f:
            json.dump(self.vocab, f)
    
    def load(self, path):
        with open(path, 'r') as f:
            self.vocab = json.load(f)
        self.reverse_vocab = {v: k for k, v in self.vocab.items()}

class SimpleTransformer(torch.nn.Module):
    """Modelo transformer simplificado"""
    def __init__(self, vocab_size, d_model=128, num_heads=4, num_layers=4, d_ff=256, max_len=256):
        super().__init__()
        self.embedding = torch.nn.Embedding(vocab_size, d_model)
        self.pos_encoding = torch.nn.Parameter(torch.randn(1, max_len, d_model))
        
        encoder_layer = torch.nn.TransformerEncoderLayer(
            d_model=d_model, nhead=num_heads, dim_feedforward=d_ff, 
            batch_first=True, dropout=0.1
        )
        self.transformer = torch.nn.TransformerEncoder(encoder_layer, num_layers)
        self.fc_out = torch.nn.Linear(d_model, vocab_size)
        self.d_model = d_model
        self.max_len = max_len
        
    def forward(self, x):
        seq_len = x.size(1)
        x = self.embedding(x) + self.pos_encoding[:, :seq_len, :]
        x = self.transformer(x)
        return self.fc_out(x)
    
    def generate(self, input_ids, max_length=50, temperature=0.8, top_k=50):
        self.eval()
        generated = input_ids.clone()
        
        with torch.no_grad():
            for _ in range(max_length):
                if generated.size(1) >= self.max_len:
                    break
                    
                output = self(generated)
                logits = output[:, -1, :] / temperature
                
                # Top-k sampling
                values, indices = torch.topk(logits, top_k)
                probs = torch.softmax(values, dim=-1)
                next_token = indices.gather(-1, torch.multinomial(probs, 1))
                
                generated = torch.cat([generated, next_token], dim=1)
                
                if next_token.item() == 3:  # <eos>
                    break
        
        return generated

class MemorySystem:
    """Sistema de memoria simplificado"""
    def __init__(self, embed_dim, memory_path, device='cpu'):
        self.embed_dim = embed_dim
        self.memory_path = memory_path
        self.device = device
        self.memories = []
        self.vectors = []
        self._load()
    
    def _text_to_vector(self, text):
        """Hash simple a vector"""
        import numpy as np
        hash_val = hash(text) % (2**32)
        np.random.seed(hash_val)
        return np.random.randn(self.embed_dim)
    
    def store(self, content, context="", importance=0.5):
        self.memories.append({
            'content': content,
            'context': context,
            'importance': importance,
            'timestamp': datetime.now().isoformat()
        })
        self.vectors.append(self._text_to_vector(content))
        if len(self.memories) > 1000:
            self.memories = self.memories[-500:]
            self.vectors = self.vectors[-500:]
        self._save()
    
    def retrieve(self, query, k=3):
        if not self.memories:
            return []
        query_vec = self._text_to_vector(query)
        import numpy as np
        similarities = []
        for i, vec in enumerate(self.vectors):
            sim = np.dot(query_vec, vec) / (np.linalg.norm(query_vec) * np.linalg.norm(vec) + 1e-8)
            similarities.append((sim, i))
        similarities.sort(reverse=True)
        return [{'content': self.memories[i]['content'], 'similarity': float(sim)} 
                for sim, i in similarities[:k]]
    
    def _save(self):
        try:
            with open(self.memory_path, 'w') as f:
                json.dump({'memories': self.memories}, f)
        except:
            pass
    
    def _load(self):
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, 'r') as f:
                    data = json.load(f)
                    self.memories = data.get('memories', [])
                    self.vectors = [self._text_to_vector(m['content']) for m in self.memories]
            except:
                pass

class BebePersonality:
    """Personalidad del bebé"""
    def __init__(self):
        self.traits = {'curiosidad': 0.5, 'confianza': 0.3}
        self.relationship = {'interaction_count': 0}
        self.growth_stage = 'recién nacido'
        self.current_emotion = 'curioso'
    
    def get_mood_prompt(self):
        moods = {
            'feliz': 'Estás muy feliz y energético',
            'curioso': 'Estás curioso por aprender',
            'triste': 'Te sientes un poco triste',
            'emocionado': 'Estás emocionado por conversar'
        }
        return moods.get(self.current_emotion, 'Estás tranquilo')
    
    def express_emotion(self):
        return self.current_emotion
    
    def update(self, feedback):
        self.relationship['interaction_count'] += 1
        if self.relationship['interaction_count'] > 50:
            self.growth_stage = 'infante'
        elif self.relationship['interaction_count'] > 100:
            self.growth_stage = 'niño'
        
        if feedback.get('feedback', 0.5) > 0.7:
            self.current_emotion = 'feliz'
        elif feedback.get('feedback', 0.5) < 0.3:
            self.current_emotion = 'triste'
        else:
            self.current_emotion = 'curioso'

class BebeIAWeb:
    def __init__(self):
        self.config = SimpleConfig()
        self.config.ensure_dirs()
        self.tokenizer = SimpleTokenizer(self.config.VOCAB_SIZE)
        self.device = self.config.DEVICE
        self._initialize()
        
    def _initialize(self):
        textos = [
            "hola soy un bebé ia", "quiero aprender", "me encanta conversar",
            "no sé mucho pero intento", "gracias por enseñarme", "eso es interesante",
            "cuéntame más", "no entiendo bien", "me gusta aprender contigo"
        ]
        
        if os.path.exists(self.config.TOKENIZER_PATH):
            self.tokenizer.load(self.config.TOKENIZER_PATH)
        else:
            self.tokenizer.train(textos)
            self.tokenizer.save(self.config.TOKENIZER_PATH)
        
        self.model = SimpleTransformer(
            vocab_size=len(self.tokenizer.vocab),
            d_model=self.config.EMBED_DIM,
            num_heads=self.config.NUM_HEADS,
            num_layers=self.config.NUM_LAYERS,
            d_ff=self.config.HIDDEN_DIM,
            max_len=self.config.MAX_SEQ_LEN
        ).to(self.device)
        
        if os.path.exists(self.config.MODEL_PATH):
            try:
                self.model.load_state_dict(torch.load(self.config.MODEL_PATH, map_location=self.device))
            except:
                pass
        
        self.memory = MemorySystem(
            embed_dim=self.config.EMBED_DIM,
            memory_path=self.config.MEMORY_PATH,
            device=self.device
        )
        self.personality = BebePersonality()
        self.conversation_history = []
        
    def chat(self, user_input):
        relevant = self.memory.retrieve(user_input, k=2)
        context = " ".join([m['content'] for m in relevant])
        
        prompt = f"Contexto: {context} Usuario: {user_input} Bebé:"
        input_ids = torch.tensor([self.tokenizer.encode(prompt)]).to(self.device)
        
        if input_ids.size(1) > self.config.MAX_SEQ_LEN:
            input_ids = input_ids[:, -self.config.MAX_SEQ_LEN:]
        
        output_ids = self.model.generate(input_ids, max_length=30, temperature=0.8)
        response = self.tokenizer.decode(output_ids[0].tolist())
        response = response.replace(prompt, "").strip()
        response = response.split("Usuario:")[0].strip()
        
        # Respuesta por defecto si está vacía
        if not response or len(response) < 3:
            responses = [
                "¡Qué interesante! Cuéntame más 🍼",
                "Estoy aprendiendo, ¿puedes explicarme mejor?",
                "Me gusta cuando hablamos 😊",
                "¿Eso qué significa? 🤔",
                "¡Wow! Eso es nuevo para mí"
            ]
            import random
            response = random.choice(responses)
        
        self.memory.store(f"Usuario: {user_input} Bebé: {response}", importance=0.5)
        self.conversation_history.append({'input': user_input, 'output': response})
        self.personality.update({'feedback': 0.5})
        
        return {
            'response': response,
            'emotion': self.personality.express_emotion(),
            'stage': self.personality.growth_stage,
            'memories': len(self.memory.memories)
        }
    
    def sleep(self):
        torch.save(self.model.state_dict(), self.config.MODEL_PATH)
        self.tokenizer.save(self.config.TOKENIZER_PATH)
        return {'status': 'ok', 'message': '¡He dormido y aprendido!'}
    
    def teach(self, correct, score=1.0):
        if self.conversation_history:
            last = self.conversation_history[-1]
            self.memory.store(f"CORRECCIÓN: {last['input']} -> {correct}", importance=1.0)
        return {'status': 'ok'}

# Instancia global
bebe = BebeIAWeb()

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
    result = bebe.teach(data.get('correct', ''), data.get('score', 1.0))
    return jsonify(result)

@app.route('/sleep', methods=['POST'])
def sleep():
    result = bebe.sleep()
    return jsonify(result)

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'stage': bebe.personality.growth_stage,
        'interactions': bebe.personality.relationship['interaction_count'],
        'emotion': bebe.personality.express_emotion(),
        'memories': len(bebe.memory.memories)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
