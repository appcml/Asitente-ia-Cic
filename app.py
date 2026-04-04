"""
Bebé IA - App Web con Flask
"""
from flask import Flask, render_template, request, jsonify
import torch
import os
import sys
import json
from datetime import datetime

# Añadir bebe_ia al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bebe_ia.core.config import Config
from bebe_ia.core.tokenizer import SimpleTokenizer
from bebe_ia.core.model import BebeTransformer
from bebe_ia.core.memory import MemorySystem, ContinualLearner
from bebe_ia.core.personality import BebePersonality

app = Flask(__name__)

class BebeIAWeb:
    def __init__(self):
        self.config = Config()
        self.config.ensure_dirs()
        
        self.tokenizer = SimpleTokenizer(self.config.VOCAB_SIZE)
        self.device = torch.device(self.config.DEVICE)
        
        # Inicializar
        self._initialize()
        
    def _initialize(self):
        """Inicializar modelo"""
        textos_bebé = [
            "hola soy un bebé ia",
            "quiero aprender muchas cosas",
            "me encanta cuando me enseñan",
            "no se mucho pero intento mejorar",
            "gracias por ayudarme a crecer",
        ]
        
        if os.path.exists(self.config.TOKENIZER_PATH):
            self.tokenizer.load(self.config.TOKENIZER_PATH)
        else:
            self.tokenizer.train(textos_bebé)
            self.tokenizer.save(self.config.TOKENIZER_PATH)
        
        self.model = BebeTransformer(
            vocab_size=len(self.tokenizer.vocab),
            d_model=self.config.EMBED_DIM,
            num_heads=self.config.NUM_HEADS,
            num_layers=self.config.NUM_LAYERS,
            d_ff=self.config.HIDDEN_DIM,
            max_len=self.config.MAX_SEQ_LEN
        ).to(self.device)
        
        # Cargar modelo si existe
        if os.path.exists(self.config.MODEL_PATH):
            checkpoint = torch.load(self.config.MODEL_PATH, map_location=self.device)
            self.model.load_state_dict(checkpoint['model'])
        
        self.memory = MemorySystem(
            embed_dim=self.config.EMBED_DIM,
            memory_path=self.config.MEMORY_PATH,
            device=self.device
        )
        
        self.personality = BebePersonality()
        self.learner = ContinualLearner(self.model, self.tokenizer, self.device)
        self.conversation_history = []
        
    def chat(self, user_input):
        """Procesar mensaje del usuario"""
        # Recuperar memorias
        relevant_memories = self.memory.retrieve(user_input, k=3)
        context = "\n".join([m['content'] for m in relevant_memories])
        
        mood = self.personality.get_mood_prompt()
        stage = self.personality.growth_stage
        
        system_prompt = f"""Eres un bebé IA en etapa {stage}. {mood}.
Contexto: {context}
Usuario: {user_input}
Bebé:"""
        
        input_ids = torch.tensor([self.tokenizer.encode(system_prompt)]).to(self.device)
        
        if input_ids.size(1) > self.config.MAX_SEQ_LEN:
            input_ids = input_ids[:, -self.config.MAX_SEQ_LEN:]
        
        self.model.eval()
        with torch.no_grad():
            output_ids = self.model.generate(
                input_ids, 
                max_length=100,
                temperature=0.8,
                top_k=50
            )
        
        response = self.tokenizer.decode(output_ids[0].tolist())
        response = response.replace(system_prompt, "").strip()
        response = response.split("Usuario:")[0].split("Bebé:")[-1].strip()
        
        # Guardar en memoria
        self.memory.store(
            f"Usuario: {user_input}\nBebé: {response}",
            context="conversación",
            importance=0.5
        )
        
        self.conversation_history.append({
            'input': user_input,
            'output': response,
            'timestamp': datetime.now().isoformat()
        })
        
        self.personality.update({'novedad': 0.5, 'feedback': 0.5})
        
        return {
            'response': response,
            'emotion': self.personality.express_emotion(),
            'stage': stage,
            'memories': len(self.memory.memories)
        }
    
    def teach(self, correct_response, feedback_score=1.0):
        """Enseñar al bebé"""
        if not self.conversation_history:
            return {'error': 'No hay conversación previa'}
        
        last = self.conversation_history[-1]
        
        self.learner.add_experience(last['input'], correct_response, feedback_score)
        
        self.memory.store(
            f"Usuario: {last['input']}\nBebé: {correct_response}",
            context="aprendizaje_corregido",
            importance=1.0
        )
        
        return {'status': 'ok', 'message': 'Aprendido!'}
    
    def sleep(self):
        """Dormir y aprender"""
        self.learner.sleep_and_learn(epochs=1)
        
        # Guardar modelo
        torch.save({
            'model': self.model.state_dict(),
            'interactions': self.personality.relationship['interaction_count'],
        }, self.config.MODEL_PATH)
        
        self.tokenizer.save(self.config.TOKENIZER_PATH)
        
        return {'status': 'ok', 'message': 'Bebé ha dormido y aprendido!'}

# Instancia global
bebe = BebeIAWeb()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message', '')
    result = bebe.chat(user_input)
    return jsonify(result)

@app.route('/teach', methods=['POST'])
def teach():
    data = request.json
    correct = data.get('correct', '')
    score = data.get('score', 1.0)
    result = bebe.teach(correct, score)
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
    app.run(debug=True, host='0.0.0.0', port=5000)
