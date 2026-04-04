"""
Bebé IA Multi-Modelo - Sistema de Enrutamiento Inteligente
Usa múltiples modelos especializados según el tipo de consulta
"""
from flask import Flask, render_template, request, jsonify
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import chromadb
from chromadb.utils import embedding_functions
import os
import json
import hashlib
import re
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
import threading
import time

app = Flask(__name__)

# ============ CONFIGURACIÓN DE MODELOS ============
class ModelType(Enum):
    TINY_LLAMA = "tinyllama"      # 1.1B - Respuestas rápidas, chat simple
    PHI_2 = "phi2"                # 2.7B - Código, razonamiento lógico
    GEMMA_2B = "gemma2b"          # 2B - Balance velocidad/calidad
    MISTRAL_7B = "mistral7b"      # 7B - Respuestas complejas, creatividad
    LLAMA_2_7B = "llama2"         # 7B - Chat general, instrucciones

class ModelConfig:
    """Configuración de cada modelo disponible"""
    
    MODELS = {
        ModelType.TINY_LLAMA: {
            "name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "description": "Rápido para respuestas simples",
            "ram_gb": 2,
            "strengths": ["saludos", "despedidas", "preguntas_simples", "chat_casual"],
            "max_tokens": 256,
            "temperature": 0.6
        },
        ModelType.PHI_2: {
            "name": "microsoft/phi-2",
            "description": "Experto en código y lógica",
            "ram_gb": 6,
            "strengths": ["codigo", "matematicas", "razonamiento_logico", "explicaciones_tecnicas"],
            "max_tokens": 512,
            "temperature": 0.4
        },
        ModelType.GEMMA_2B: {
            "name": "google/gemma-2b-it",
            "description": "Balance perfecto velocidad/calidad",
            "ram_gb": 4,
            "strengths": ["preguntas_generales", "explicaciones", "conversacion", "creatividad"],
            "max_tokens": 512,
            "temperature": 0.7
        },
        ModelType.MISTRAL_7B: {
            "name": "mistralai/Mistral-7B-Instruct-v0.2",
            "description": "Máxima calidad para tareas complejas",
            "ram_gb": 14,
            "strengths": ["analisis_profundo", "creatividad", "consejos", "filosofia", "emociones"],
            "max_tokens": 1024,
            "temperature": 0.8
        },
        ModelType.LLAMA_2_7B: {
            "name": "meta-llama/Llama-2-7b-chat-hf",
            "description": "Chat natural y seguro",
            "ram_gb": 14,
            "strengths": ["chat_seguro", "instrucciones", "conversacion_larga", "empatia"],
            "max_tokens": 1024,
            "temperature": 0.7
        }
    }
    
    # Modelo por defecto si no hay recursos
    DEFAULT_MODEL = ModelType.TINY_LLAMA
    
    # Orden de preferencia según disponibilidad de RAM
    RAM_THRESHOLDS = {
        2: ModelType.TINY_LLAMA,
        4: ModelType.GEMMA_2B,
        6: ModelType.PHI_2,
        14: ModelType.MISTRAL_7B,
        16: ModelType.LLAMA_2_7B
    }

# ============ DETECTOR DE INTENCIÓN INTELIGENTE ============
class IntentDetector:
    """Detecta el tipo de consulta para elegir el mejor modelo"""
    
    PATTERNS = {
        # Código y técnico -> Phi-2
        "codigo": {
            "keywords": ["código", "code", "programar", "python", "javascript", "función", 
                        "function", "error", "bug", "debug", "script", "algoritmo"],
            "regex": [r"\b(def|class|import|function)\b", r"[{};=]+"],
            "model": ModelType.PHI_2,
            "priority": 10
        },
        
        # Matemáticas -> Phi-2
        "matematicas": {
            "keywords": ["calcular", "matemática", "ecuación", "resolver", "suma", "resta",
                        "multiplicar", "dividir", "álgebra", "geometría", "número"],
            "regex": [r"\d+\s*[\+\-\*\/]\s*\d+", r"=\s*\?"],
            "model": ModelType.PHI_2,
            "priority": 9
        },
        
        # Chat casual y rápido -> TinyLlama
        "chat_simple": {
            "keywords": ["hola", "hey", "buenos días", "buenas noches", "adiós", "gracias",
                        "bye", "ok", "vale", "entendido"],
            "regex": [],
            "model": ModelType.TINY_LLAMA,
            "priority": 3
        },
        
        # Creatividad y análisis profundo -> Mistral 7B
        "creatividad": {
            "keywords": ["cuento", "historia", "poema", "canción", "crea", "imagina",
                        "filosofía", "significado de la vida", "amor", "felicidad"],
            "regex": [],
            "model": ModelType.MISTRAL_7B,
            "priority": 8
        },
        
        # Emociones y empatía -> Llama 2
        "emocional": {
            "keywords": ["triste", "feliz", "solo", "ayuda", "problema", "depresión",
                        "ansiedad", "miedo", "preocupado", "estresado", "consejo"],
            "regex": [],
            "model": ModelType.LLAMA_2_7B,
            "priority": 9
        },
        
        # Preguntas generales -> Gemma 2B
        "general": {
            "keywords": ["qué es", "cómo", "por qué", "cuándo", "dónde", "quién",
                        "explica", "dime", "cuéntame", "qué opinas"],
            "regex": [r"\?$"],
            "model": ModelType.GEMMA_2B,
            "priority": 5
        },
        
        # Conversación larga y segura -> Llama 2
        "conversacion": {
            "keywords": ["hablemos", "conversación", "charlemos", "discutamos",
                        "opinión", "piensas", "crees"],
            "regex": [],
            "model": ModelType.LLAMA_2_7B,
            "priority": 6
        }
    }
    
    @classmethod
    def detect(cls, text: str) -> tuple:
        """
        Detecta la intención y devuelve (tipo, modelo_recomendado, confianza)
        """
        text_lower = text.lower()
        scores = {}
        
        for intent_type, config in cls.PATTERNS.items():
            score = 0
            
            # Puntuar por keywords
            for keyword in config["keywords"]:
                if keyword in text_lower:
                    score += config["priority"]
            
            # Puntuar por regex
            for pattern in config["regex"]:
                if re.search(pattern, text):
                    score += config["priority"] * 2
            
            if score > 0:
                scores[intent_type] = {
                    "score": score,
                    "model": config["model"]
                }
        
        if not scores:
            return ("general", ModelConfig.DEFAULT_MODEL, 0.5)
        
        # Elegir el de mayor puntuación
        best = max(scores.items(), key=lambda x: x[1]["score"])
        confidence = min(best[1]["score"] / 20, 1.0)  # Normalizar a 0-1
        
        return (best[0], best[1]["model"], confidence)

# ============ GESTOR DE MODELOS ============
class ModelManager:
    """Gestiona múltiples modelos y selecciona el mejor para cada tarea"""
    
    def __init__(self):
        self.loaded_models = {}
        self.current_model_type = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.available_ram = self._detect_available_ram()
        
        print(f"🖥️ Dispositivo: {self.device}")
        print(f"💾 RAM disponible: ~{self.available_ram}GB")
        
        # Cargar modelo por defecto inmediatamente
        self._load_model(ModelConfig.DEFAULT_MODEL)
    
    def _detect_available_ram(self) -> int:
        """Detectar RAM disponible aproximada"""
        try:
            import psutil
            ram_gb = psutil.virtual_memory().available / (1024**3)
            return int(ram_gb)
        except:
            # Fallback: asumir mínimo
            return 2
    
    def _load_model(self, model_type: ModelType):
        """Cargar un modelo en memoria"""
        
        if model_type in self.loaded_models:
            self.current_model_type = model_type
            return self.loaded_models[model_type]
        
        config = ModelConfig.MODELS[model_type]
        
        # Verificar si tenemos suficiente RAM
        if config["ram_gb"] > self.available_ram * 0.8:
            print(f"⚠️ RAM insuficiente para {model_type.value}, usando fallback")
            return self._load_model(ModelConfig.DEFAULT_MODEL)
        
        print(f"🤖 Cargando modelo: {model_type.value} ({config['name']})")
        
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                config["name"],
                trust_remote_code=True
            )
            
            # Configurar modelo según recursos
            if self.device == "cuda":
                model = AutoModelForCausalLM.from_pretrained(
                    config["name"],
                    torch_dtype=torch.float16,
                    device_map="auto",
                    trust_remote_code=True
                )
            else:
                # CPU: usar modelo más ligero
                model = AutoModelForCausalLM.from_pretrained(
                    config["name"],
                    torch_dtype=torch.float32,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True
                )
            
            # Crear pipeline
            pipe = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                max_new_tokens=config["max_tokens"],
                temperature=config["temperature"],
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )
            
            model_data = {
                "pipeline": pipe,
                "tokenizer": tokenizer,
                "config": config,
                "type": model_type
            }
            
            self.loaded_models[model_type] = model_data
            self.current_model_type = model_type
            
            print(f"✅ Modelo {model_type.value} cargado")
            return model_data
            
        except Exception as e:
            print(f"❌ Error cargando {model_type.value}: {e}")
            if model_type != ModelConfig.DEFAULT_MODEL:
                return self._load_model(ModelConfig.DEFAULT_MODEL)
            raise
    
    def generate(self, prompt: str, system_prompt: str = None, 
                 force_model: ModelType = None) -> tuple:
        """
        Generar respuesta, opcionalmente forzando un modelo específico
        
        Returns: (respuesta, modelo_usado)
        """
        # Seleccionar modelo
        if force_model:
            model_data = self._load_model(force_model)
        else:
            model_data = self.loaded_models.get(
                self.current_model_type, 
                self.loaded_models[ModelConfig.DEFAULT_MODEL]
            )
        
        model_type = model_data["type"]
        config = model_data["config"]
        pipe = model_data["pipeline"]
        
        # Formatear prompt según el modelo
        formatted_prompt = self._format_prompt(
            prompt, system_prompt, model_type, model_data["tokenizer"]
        )
        
        # Generar
        try:
            outputs = pipe(
                formatted_prompt,
                return_full_text=False,
                max_new_tokens=config["max_tokens"]
            )
            
            response = outputs[0]['generated_text'].strip()
            
            # Limpiar respuesta según modelo
            response = self._clean_response(response, model_type)
            
            return (response, model_type)
            
        except Exception as e:
            print(f"Error generando con {model_type.value}: {e}")
            # Fallback a modelo más pequeño
            if model_type != ModelType.TINY_LLAMA:
                return self.generate(prompt, system_prompt, ModelType.TINY_LLAMA)
            return ("Lo siento, tuve un problema. ¿Puedes intentar de nuevo?", model_type)
    
    def _format_prompt(self, prompt: str, system_prompt: str, 
                      model_type: ModelType, tokenizer) -> str:
        """Formatear prompt según el modelo específico"""
        
        if model_type == ModelType.MISTRAL_7B:
            # Formato Mistral
            if system_prompt:
                return f"<s>[INST] {system_prompt}\n\n{prompt} [/INST]"
            return f"<s>[INST] {prompt} [/INST]"
        
        elif model_type == ModelType.LLAMA_2_7B:
            # Formato Llama 2
            if system_prompt:
                return f"<<SYS>>\n{system_prompt}\n<</SYS>>\n\n[INST] {prompt} [/INST]"
            return f"[INST] {prompt} [/INST]"
        
        elif model_type == ModelType.PHI_2:
            # Formato Phi-2
            if system_prompt:
                return f"System: {system_prompt}\n\nUser: {prompt}\nAssistant:"
            return f"User: {prompt}\nAssistant:"
        
        elif model_type == ModelType.GEMMA_2B:
            # Formato Gemma
            if system_prompt:
                return f"<start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
            return f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
        
        else:  # TinyLlama y otros
            # Formato chat simple
            if system_prompt:
                return f"### System:\n{system_prompt}\n\n### User:\n{prompt}\n\n### Assistant:\n"
            return f"### User:\n{prompt}\n\n### Assistant:\n"
    
    def _clean_response(self, response: str, model_type: ModelType) -> str:
        """Limpiar respuesta de tokens especiales"""
        
        # Remover tokens de fin
        response = response.split('[/INST]')[0]
        response = response.split('<end_of_turn>')[0]
        response = response.split('###')[0]
        response = response.split('User:')[0]
        response = response.split('System:')[0]
        
        # Limpiar espacios
        response = response.strip()
        
        return response
    
    def get_model_info(self) -> Dict:
        """Obtener información de modelos cargados"""
        return {
            "current": self.current_model_type.value if self.current_model_type else None,
            "loaded": [m.value for m in self.loaded_models.keys()],
            "available_ram": self.available_ram,
            "device": self.device
        }

# ============ MEMORIA VECTORIAL ============
class VectorMemory:
    """Memoria semántica persistente"""
    
    def __init__(self):
        self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.client = chromadb.PersistentClient(path="./chroma_db_multi")
        self.collection = self.client.get_or_create_collection(
            name="bebe_multi_memory",
            embedding_function=self.embedding_func
        )
        
        print(f"🧠 Memoria: {self.collection.count()} recuerdos")
    
    def add(self, text: str, metadata: Dict):
        memory_id = hashlib.md5(
            f"{text}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        self.collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[memory_id]
        )
        return memory_id
    
    def search(self, query: str, k: int = 3):
        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )
        
        memories = []
        for i in range(len(results['ids'][0])):
            memories.append({
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i]
            })
        return memories

# ============ BEbÉ IA MULTI-MODELO ============
class BebeIAMultiModelo:
    """IA que selecciona el mejor modelo para cada tarea"""
    
    def __init__(self):
        print("=" * 60)
        print("🚀 Bebé IA Multi-Modelo v3.0")
        print("Sistema de enrutamiento inteligente")
        print("=" * 60)
        
        self.model_manager = ModelManager()
        self.memory = VectorMemory()
        self.conversation_history = []
        
        # Estadísticas de uso
        self.model_usage = {m: 0 for m in ModelType}
        self.intent_stats = {}
        
        print("\n✅ Sistema listo")
        print(f"Modelos disponibles: {len(ModelConfig.MODELS)}")
    
    def chat(self, user_input: str) -> Dict:
        """Procesar entrada seleccionando el mejor modelo"""
        
        # 1. Detectar intención
        intent, recommended_model, confidence = IntentDetector.detect(user_input)
        
        # 2. Verificar si debemos cambiar de modelo
        current_model = self.model_manager.current_model_type
        
        # Si la confianza es alta y el modelo es diferente, cambiar
        if confidence > 0.6 and recommended_model != current_model:
            print(f"🔄 Cambiando a {recommended_model.value} para {intent}")
            self.model_manager._load_model(recommended_model)
        
        # 3. Buscar memorias relevantes
        memories = self.memory.search(user_input, k=2)
        memory_context = self._format_memories(memories)
        
        # 4. Construir prompts
        system_prompt = self._build_system_prompt(intent)
        
        full_prompt = f"""Contexto de conversación previa:
{memory_context}

Consulta del usuario: {user_input}

Responde de manera natural y útil."""
        
        # 5. Generar respuesta
        response, used_model = self.model_manager.generate(
            full_prompt, system_prompt
        )
        
        # 6. Actualizar estadísticas
        self.model_usage[used_model] += 1
        self.intent_stats[intent] = self.intent_stats.get(intent, 0) + 1
        
        # 7. Guardar en memoria
        self._save_interaction(user_input, response, intent, used_model)
        
        return {
            'response': response,
            'model_used': used_model.value,
            'intent_detected': intent,
            'confidence': round(confidence, 2),
            'emotion': self._detect_emotion(response),
            'stage': self._get_stage(),
            'memories_stored': self.memory.collection.count(),
            'total_messages': len(self.conversation_history)
        }
    
    def _format_memories(self, memories: List[Dict]) -> str:
        if not memories:
            return "No hay contexto previo relevante."
        return "\n".join([f"- {m['text'][:150]}..." for m in memories])
    
    def _build_system_prompt(self, intent: str) -> str:
        """Construir prompt según la intención detectada"""
        
        base = "Eres Bebé IA, un asistente inteligente y amigable."
        
        specializations = {
            "codigo": f"{base} Eres experto en programación y código. Da ejemplos claros.",
            "matematicas": f"{base} Eres experto en matemáticas. Explica paso a paso.",
            "emocional": f"{base} Eres empático y comprensivo. Escucha con atención.",
            "creatividad": f"{base} Eres creativo e imaginativo. Sé original.",
            "chat_simple": f"{base} Sé breve y amigable.",
            "general": f"{base} Explica de manera clara y educativa.",
            "conversacion": f"{base} Sé conversacional y natural."
        }
        
        return specializations.get(intent, base)
    
    def _save_interaction(self, user: str, bot: str, intent: str, model: ModelType):
        """Guardar interacción en memoria"""
        
        # Guardar en vector DB
        enriched = f"Usuario ({intent}): {user}\nBebé IA ({model.value}): {bot}"
        self.memory.add(enriched, {
            'user': user,
            'bot': bot,
            'intent': intent,
            'model': model.value,
            'timestamp': datetime.now().isoformat()
        })
        
        # Guardar en historial
        self.conversation_history.append({
            'user': user,
            'bot': bot,
            'intent': intent,
            'model': model.value,
            'time': datetime.now().isoformat()
        })
    
    def _detect_emotion(self, response: str) -> str:
        indicators = {
            'entusiasta': ['!', 'genial', 'excelente', 'increíble'],
            'empático': ['entiendo', 'siento', 'comprendo'],
            'técnico': ['código', 'función', 'variable', 'algoritmo'],
            'creativo': ['imagina', 'podrías', 'quizás', 'qué tal']
        }
        
        response_lower = response.lower()
        for emotion, words in indicators.items():
            if any(w in response_lower for w in words):
                return emotion
        return 'neutral'
    
    def _get_stage(self) -> str:
        total = len(self.conversation_history)
        if total < 50:
            return '🍼 Explorando modelos'
        elif total < 200:
            return '🔧 Optimizando selección'
        elif total < 500:
            return '🎯 Especializando modelos'
        else:
            return '🧠 Maestra multi-modelo'
    
    def get_stats(self) -> Dict:
        """Obtener estadísticas de uso"""
        return {
            'model_usage': {k.value: v for k, v in self.model_usage.items()},
            'intent_stats': self.intent_stats,
            'total_interactions': len(self.conversation_history),
            'current_model': self.model_manager.current_model_type.value,
            'loaded_models': list(self.model_manager.loaded_models.keys())
        }
    
    def force_model(self, model_name: str) -> str:
        """Forzar uso de un modelo específico"""
        try:
            model_type = ModelType(model_name.lower())
            self.model_manager._load_model(model_type)
            return f"✅ Modelo cambiado a: {model_name}"
        except:
            available = [m.value for m in ModelType]
            return f"❌ Modelo no válido. Disponibles: {available}"

# ============ INICIALIZACIÓN ============
print("\n" + "=" * 60)
print("INICIANDO SISTEMA MULTI-MODELO")
print("=" * 60 + "\n")

bebe = BebeIAMultiModelo()

# ============ RUTAS ============
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    result = bebe.chat(data.get('message', ''))
    return jsonify(result)

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'stage': bebe._get_stage(),
        'current_model': bebe.model_manager.current_model_type.value,
        'loaded_models': [m.value for m in bebe.model_manager.loaded_models.keys()],
        'memories': bebe.memory.collection.count(),
        'messages': len(bebe.conversation_history),
        'model_info': bebe.model_manager.get_model_info()
    })

@app.route('/stats', methods=['GET'])
def stats():
    return jsonify(bebe.get_stats())

@app.route('/switch_model', methods=['POST'])
def switch_model():
    data = request.json
    result = bebe.force_model(data.get('model', ''))
    return jsonify({'message': result})

@app.route('/models', methods=['GET'])
def list_models():
    """Listar todos los modelos disponibles"""
    models = []
    for model_type, config in ModelConfig.MODELS.items():
        models.append({
            'id': model_type.value,
            'name': config['name'],
            'description': config['description'],
            'ram_gb': config['ram_gb'],
            'strengths': config['strengths'],
            'loaded': model_type in bebe.model_manager.loaded_models
        })
    return jsonify({
        'models': models,
        'current': bebe.model_manager.current_model_type.value if bebe.model_manager.current_model_type else None,
        'available_ram': bebe.model_manager.available_ram
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
