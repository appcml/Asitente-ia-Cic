"""
Bebé IA - App Web Completa (Todo en uno)
Funciona sin dependencias externas, modelo ligero integrado
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

# ============ MODELO SIMPLE ============
class BabyBrain(nn.Module):
    def __init__(self, vocab_size=500, embed_dim=32, hidden_dim=64):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)
        
    def forward(self, x):
        x = self.embedding(x)
        lstm_out, _ = self.lstm(x)
        return self.fc(lstm_out)
    
    def generate(self, input_ids, max_length=20, temperature=0.8):
        self.eval()
        generated = input_ids.clone()
        
        with torch.no_grad():
            for _ in range(max_length):
                output = self(generated)
                logits = output[:, -1, :] / temperature
                probs = torch.softmax(logits, dim=-1)
                next_token = torch.multinomial(probs, 1)
                generated = torch.cat([generated, next_token], dim=1)
        return generated

# ============ TOKENIZADOR ============
class SimpleTokenizer:
    def __init__(self):
        self.word2idx = {'<pad>': 0, '<unk>': 1, '<sos>': 2, '<eos>': 3}
        self.idx2word = {v: k for k, v in self.word2idx.items()}
        
    def fit(self, texts):
        words = set()
        for text in texts:
            words.update(text.lower().split())
        for word in sorted(words):
            if word not in self.word2idx:
                self.word2idx[word] = len(self.word2idx)
        self.idx2word = {v: k for k, v in self.word2idx.items()}
        return self
    
    def encode(self, text):
        tokens = [self.word2idx.get(w.lower(), 1) for w in text.split()]
        return [2] + tokens + [3]  # <sos> + tokens + <eos>
    
    def decode(self, tokens):
        words = [self.idx2word.get(t, '') for t in tokens if t > 3]
        return ' '.join(words) if words else "..."
    
    def vocab_size(self):
        return len(self.word2idx)

# ============ BEbÉ IA ============
class BebeIA:
    def __init__(self):
        self.memory_file = 'chat_memory.json'
        self.conversations = self._load_memory()
        
        # Datos de entrenamiento básicos
        self.training_data = [
            ("hola", "¡Hola! ¿Cómo estás? 😊"),
            ("cómo te llamas", "Me llamo Bebé IA 🍼"),
            ("qué puedes hacer", "Puedo conversar contigo y aprender de lo que me dices"),
            ("cuéntame algo", "Estoy aprendiendo cosas nuevas cada día. ¿Tú qué me cuentas?"),
            ("gracias", "¡De nada! Me gusta ayudarte 🌟"),
            ("adiós", "¡Hasta luego! Vuelve pronto 👋"),
            ("bien", "¡Me alegro! ¿Qué has hecho hoy?"),
            ("mal", "Lo siento 😢 ¿Quieres hablar de ello?"),
            ("qué es", "Estoy aprendiendo sobre eso. ¿Me lo explicas?"),
            ("por qué", "Buena pregunta 🤔 Estoy tratando de entenderlo"),
        ]
        
        self.tokenizer = SimpleTokenizer()
        self.model = None
        self._init_model()
        
    def _init_model(self):
        # Entrenar tokenizador
        all_texts = [q for q, a in self.training_data] + [a for q, a in self.training_data]
        self.tokenizer.fit(all_texts)
        
        # Crear modelo
        self.model = BabyBrain(self.tokenizer.vocab_size())
        
        # Entrenar modelo básico (solo unas épocas rápidas)
        self._quick_train()
        
    def _quick_train(self):
        """Entrenamiento rápido del modelo"""
        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.01)
        criterion = nn.CrossEntropyLoss()
        
        for epoch in range(50):  # Solo 50 épocas rápidas
            total_loss = 0
            for question, answer in self.training_data:
                # Preparar datos
                q_tokens = torch.tensor([self.tokenizer.encode(question)])
                a_tokens = torch.tensor([self.tokenizer.encode(answer)])
                
                # Input: pregunta, Target: respuesta
                input_seq = torch.cat([q_tokens, a_tokens[:, :-1]], dim=1)
                target_seq = torch.cat([q_tokens[:, 1:], a_tokens], dim=1)
                
                optimizer.zero_grad()
                output = self.model(input_seq)
                loss = criterion(output.view(-1, self.tokenizer.vocab_size()), 
                               target_seq.view(-1))
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            
            if epoch % 10 == 0:
                print(f"Epoch {epoch}, Loss: {total_loss/len(self.training_data):.4f}")
    
    def chat(self, user_input):
        try:
            # Buscar respuesta exacta primero
            for q, a in self.training_data:
                if q.lower() in user_input.lower() or user_input.lower() in q.lower():
                    self._save_to_memory(user_input, a)
                    return self._format_response(a)
            
            # Si no hay coincidencia, usar el modelo
            input_ids = torch.tensor([self.tokenizer.encode(user_input)])
            output_ids = self.model.generate(input_ids, max_length=15)
            response = self.tokenizer.decode(output_ids[0].tolist())
            
            # Si la respuesta del modelo es mala, usar respuesta genérica
            if len(response) < 3 or response == "...":
                generic_responses = [
                    "Interesante, cuéntame más 🍼",
                    "Estoy aprendiendo sobre eso. ¿Puedes explicarme mejor?",
                    "No entiendo bien aún, pero quiero aprender 🤔",
                    "¡Eso suena emocionante! ¿Qué más sabes de eso?",
                    "Me gusta cuando hablamos de eso 😊",
                    "¿Puedes darme un ejemplo? Estoy tratando de entender",
                ]
                response = random.choice(generic_responses)
            
            self._save_to_memory(user_input, response)
            return self._format_response(response)
            
        except Exception as e:
            print(f"Error: {e}")
            return {
                'response': "Ups, me confundí un poco... ¿Me repites? 😅",
                'emotion': 'confundido',
                'stage': 'aprendiendo',
                'memories': len(self.conversations)
            }
    
    def _format_response(self, text):
        self.conversations.append({
            'user': 'last',
            'bot': text,
            'time': datetime.now().isoformat()
        })
        
        emotions = ['feliz', 'curioso', 'emocionado', 'tranquilo']
        stages = ['recién nacido', 'infante', 'niño']
        
        return {
            'response': text,
            'emotion': random.choice(emotions),
            'stage': stages[min(len(self.conversations)//20, 2)],
            'memories': len(self.conversations)
        }
    
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
            json.dump(self.conversations[-100:], f)  # Guardar últimas 100

# Instancia global
print("🍼 Inicializando Bebé IA...")
bebe = BebeIA()
print("✅ Bebé IA listo!")

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
    # Guardar corrección en memoria
    if bebe.conversations:
        bebe.conversations[-1]['bot'] = correct
        bebe._save_memory()
    return jsonify({'status': 'ok', 'message': '¡Aprendido! 🎓'})

@app.route('/sleep', methods=['POST'])
def sleep():
    # Simular que "duerme" guardando memoria
    bebe._save_memory()
    return jsonify({'status': 'ok', 'message': '💤 He dormido y soñado con lo que aprendí'})

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'stage': 'recién nacido' if len(bebe.conversations) < 20 else 'infante',
        'interactions': len(bebe.conversations),
        'emotion': 'curioso',
        'memories': len(bebe.conversations)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
