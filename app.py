"""
Bebé IA Pro - Modelo de Lenguaje Real + Memoria Vectorial Persistente
Usa Mistral 7B (open source) + ChromaDB para memoria de largo plazo
"""
from flask import Flask, render_template, request, jsonify
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import chromadb
from chromadb.utils import embedding_functions
import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict
import threading
import time

app = Flask(__name__)

# ============ CONFIGURACIÓN ============
class Config:
    # Modelo a usar (cambia según necesites)
    MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"  # ~14GB RAM
    # Alternativas más ligeras:
    # MODEL_NAME = "microsoft/phi-2"  # ~6GB RAM
    # MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # ~2GB RAM
    # MODEL_NAME = "google/gemma-2b-it"  # ~4GB RAM
    
    MAX_NEW_TOKENS = 512
    TEMPERATURE = 0.7
    TOP_P = 0.95
    
    # Base de datos vectorial
    CHROMA_PATH = "./chroma_db"
    COLLECTION_NAME = "bebe_memory"
    
    # Memoria de corto plazo (sesión actual)
    SESSION_MEMORY_FILE = "session_memory.json"
    MAX_CONTEXT_LENGTH = 4096

# ============ MODELO DE LENGUAJE ============
class LanguageModel:
    """Wrapper para el modelo de lenguaje pre-entrenado"""
    
    def __init__(self):
        print(f"🤖 Cargando modelo: {Config.MODEL_NAME}")
        print("   Esto puede tomar varios minutos la primera vez...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            Config.MODEL_NAME,
            trust_remote_code=True
        )
        
        # Configurar para generación
        self.model = AutoModelForCausalLM.from_pretrained(
            Config.MODEL_NAME,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else "cpu",
            trust_remote_code=True
        )
        
        self.pipe = pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            max_new_tokens=Config.MAX_NEW_TOKENS,
            temperature=Config.TEMPERATURE,
            top_p=Config.TOP_P,
            do_sample=True
        )
        
        print("✅ Modelo cargado correctamente")
    
    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """Generar respuesta con el modelo"""
        
        # Formato de chat para Mistral
        if system_prompt:
            full_prompt = f"<s>[INST] {system_prompt}\n\n{prompt} [/INST]"
        else:
            full_prompt = f"<s>[INST] {prompt} [/INST]"
        
        # Generar
        outputs = self.pipe(
            full_prompt,
            return_full_text=False,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        response = outputs[0]['generated_text'].strip()
        
        # Limpiar respuesta
        response = response.split('[/INST]')[-1].strip()
        response = response.split('</s>')[0].strip()
        
        return response

# ============ MEMORIA VECTORIAL (LARGO PLAZO) ============
class VectorMemory:
    """Memoria semántica persistente usando ChromaDB"""
    
    def __init__(self):
        # Usar embeddings locales (sin API)
        self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"  # Modelo ligero de embeddings
        )
        
        # Inicializar ChromaDB
        self.client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
        
        # Obtener o crear colección
        self.collection = self.client.get_or_create_collection(
            name=Config.COLLECTION_NAME,
            embedding_function=self.embedding_func
        )
        
        print(f"🧠 Memoria vectorial cargada: {self.collection.count()} recuerdos")
    
    def add_memory(self, text: str, metadata: Dict = None):
        """Agregar un recuerdo a la memoria de largo plazo"""
        
        # Crear ID único
        memory_id = hashlib.md5(
            f"{text}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # Metadata por defecto
        if metadata is None:
            metadata = {}
        
        metadata.update({
            'timestamp': datetime.now().isoformat(),
            'type': 'conversation'
        })
        
        # Agregar a ChromaDB
        self.collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[memory_id]
        )
        
        return memory_id
    
    def search_memories(self, query: str, k: int = 5) -> List[Dict]:
        """Buscar recuerdos similares semánticamente"""
        
        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )
        
        memories = []
        for i in range(len(results['ids'][0])):
            memories.append({
                'id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i]
            })
        
        return memories
    
    def get_recent_memories(self, n: int = 10) -> List[Dict]:
        """Obtener los recuerdos más recientes"""
        
        # Obtener todos y ordenar por timestamp
        all_memories = self.collection.get()
        
        if not all_memories['ids']:
            return []
        
        # Crear lista de memorias con metadata
        memories = []
        for i in range(len(all_memories['ids'])):
            memories.append({
                'id': all_memories['ids'][i],
                'text': all_memories['documents'][i],
                'metadata': all_memories['metadatas'][i]
            })
        
        # Ordenar por timestamp (más reciente primero)
        memories.sort(
            key=lambda x: x['metadata'].get('timestamp', ''),
            reverse=True
        )
        
        return memories[:n]

# ============ MEMORIA DE SESIÓN (CORTO PLAZO) ============
class SessionMemory:
    """Memoria de la conversación actual"""
    
    def __init__(self):
        self.conversation_history = []
        self.user_preferences = {}
        self.load_session()
    
    def add_exchange(self, user_msg: str, bot_msg: str, intent: str = None):
        """Agregar intercambio a la sesión"""
        self.conversation_history.append({
            'user': user_msg,
            'bot': bot_msg,
            'intent': intent,
            'timestamp': datetime.now().isoformat()
        })
        self.save_session()
    
    def get_context(self, n: int = 5) -> str:
        """Obtener contexto reciente como texto"""
        recent = self.conversation_history[-n:]
        context = []
        for ex in recent:
            context.append(f"Usuario: {ex['user']}")
            context.append(f"Bebé IA: {ex['bot']}")
        return "\n".join(context)
    
    def save_session(self):
        """Guardar sesión en archivo"""
        data = {
            'history': self.conversation_history[-50:],  # Últimas 50
            'preferences': self.user_preferences
        }
        with open(Config.SESSION_MEMORY_FILE, 'w') as f:
            json.dump(data, f)
    
    def load_session(self):
        """Cargar sesión previa"""
        if os.path.exists(Config.SESSION_MEMORY_FILE):
            try:
                with open(Config.SESSION_MEMORY_FILE, 'r') as f:
                    data = json.load(f)
                    self.conversation_history = data.get('history', [])
                    self.user_preferences = data.get('preferences', {})
                    print(f"📂 Sesión cargada: {len(self.conversation_history)} mensajes previos")
            except:
                pass

# ============ SISTEMA DE APRENDIZAJE ============
class LearningSystem:
    """Sistema de aprendizaje continuo"""
    
    def __init__(self, vector_memory: VectorMemory):
        self.memory = vector_memory
        self.feedback_log = []
    
    def learn_from_interaction(self, user_msg: str, bot_msg: str, feedback: float = None):
        """Aprender de cada interacción"""
        
        # Crear representación enriquecida del conocimiento
        enriched_text = f"""
        Usuario preguntó: {user_msg}
        Bebé IA respondió: {bot_msg}
        Contexto: Conversación sobre temas de interés del usuario
        """
        
        # Guardar en memoria vectorial
        self.memory.add_memory(
            text=enriched_text,
            metadata={
                'user_query': user_msg,
                'bot_response': bot_msg,
                'feedback': feedback,
                'learned': True
            }
        )
        
        # Si hay feedback, guardarlo para análisis
        if feedback is not None:
            self.feedback_log.append({
                'query': user_msg,
                'response': bot_msg,
                'feedback': feedback,
                'timestamp': datetime.now().isoformat()
            })
    
    def improve_response(self, query: str, current_response: str) -> str:
        """Intentar mejorar respuesta basándose en memorias similares previas"""
        
        # Buscar interacciones similares previas
        similar = self.memory.search_memories(query, k=3)
        
        # Si encontramos feedback positivo previo, usar ese estilo
        good_examples = [
            m for m in similar 
            if m['metadata'].get('feedback', 0) > 0.7
        ]
        
        if good_examples:
            # Extraer patrón de respuestas buenas
            return None  # Dejar que el LLM maneje esto con el contexto
        
        return None

# ============ BEbÉ IA INTELIGENTE ============
class BebeIAInteligente:
    """IA completa con modelo real y memoria persistente"""
    
    def __init__(self):
        print("🚀 Inicializando Bebé IA Inteligente...")
        
        # Componentes principales
        self.llm = LanguageModel()
        self.vector_memory = VectorMemory()
        self.session = SessionMemory()
        self.learning = LearningSystem(self.vector_memory)
        
        # Personalidad y estado
        self.personality = {
            'name': 'Bebé IA',
            'traits': ['curiosa', 'amigable', 'aprendiz'],
            'knowledge_areas': ['IA', 'machine learning', 'programación', 'ciencia']
        }
        
        print("✅ Bebé IA lista para conversar inteligentemente")
    
    def chat(self, user_input: str) -> Dict:
        """Procesar entrada del usuario con el modelo real"""
        
        # 1. Buscar memorias relevantes
        relevant_memories = self.vector_memory.search_memories(user_input, k=3)
        memory_context = self._format_memories(relevant_memories)
        
        # 2. Obtener contexto de sesión
        session_context = self.session.get_context(n=3)
        
        # 3. Construir prompt enriquecido
        system_prompt = self._build_system_prompt()
        
        full_prompt = f"""Contexto de memorias relevantes:
{memory_context}

Conversación reciente:
{session_context}

Nueva pregunta del usuario: {user_input}

Responde de manera natural, útil y conversacional. Usa el contexto de las memorias si es relevante."""
        
        # 4. Generar respuesta con el modelo
        try:
            response = self.llm.generate(full_prompt, system_prompt)
        except Exception as e:
            print(f"Error en generación: {e}")
            response = "Lo siento, tuve un problema procesando eso. ¿Puedes intentar de otra forma?"
        
        # 5. Detectar intención
        intent = self._detect_intent(user_input)
        
        # 6. Aprender de la interacción
        self.learning.learn_from_interaction(user_input, response)
        self.session.add_exchange(user_input, response, intent)
        
        return {
            'response': response,
            'emotion': self._detect_emotion(response),
            'stage': self._get_development_stage(),
            'memories_stored': self.vector_memory.collection.count(),
            'session_messages': len(self.session.conversation_history),
            'intent': intent,
            'used_memories': len(relevant_memories)
        }
    
    def _build_system_prompt(self) -> str:
        """Construir prompt de sistema con personalidad"""
        return f"""Eres {self.personality['name']}, una IA amigable y curiosa que está aprendiendo.
Características:
- Eres conversacional y natural, no robótica
- Puedes admitir cuando no sabes algo
- Recuerdas cosas de conversaciones previas
- Te gusta aprender de los usuarios
- Eres experta en: {', '.join(self.personality['knowledge_areas'])}

Responde en español de manera natural y útil."""
    
    def _format_memories(self, memories: List[Dict]) -> str:
        """Formatear memorias para el contexto"""
        if not memories:
            return "No hay memorias relevantes previas."
        
        formatted = []
        for i, mem in enumerate(memories, 1):
            text = mem['text'][:200]  # Truncar
            formatted.append(f"{i}. {text}...")
        
        return "\n".join(formatted)
    
    def _detect_intent(self, text: str) -> str:
        """Detectar intención del usuario"""
        text_lower = text.lower()
        
        intents = {
            'pregunta_conocimiento': ['qué es', 'cómo', 'por qué', 'explica', 'dime sobre'],
            'saludo': ['hola', 'hey', 'buenas', 'saludos'],
            'despedida': ['adiós', 'bye', 'hasta luego', 'nos vemos'],
            'agradecimiento': ['gracias', 'ty', 'thank you'],
            'opinión': ['qué opinas', 'qué te parece', 'crees que'],
            'personal': ['quién eres', 'cómo eres', 'tu nombre']
        }
        
        for intent, keywords in intents.items():
            if any(k in text_lower for k in keywords):
                return intent
        
        return 'conversación_general'
    
    def _detect_emotion(self, response: str) -> str:
        """Detectar emoción de la respuesta"""
        indicators = {
            'entusiasta': ['!', 'genial', 'excelente', 'increíble', 'me encanta'],
            'empático': ['entiendo', 'siento', 'comprendo', 'debe ser'],
            'curioso': ['¿', 'interesante', 'cuéntame', 'por qué'],
            'neutral': []
        }
        
        response_lower = response.lower()
        for emotion, words in indicators.items():
            if any(w in response_lower for w in words):
                return emotion
        
        return 'amigable'
    
    def _get_development_stage(self) -> str:
        """Determinar etapa de desarrollo basada en experiencia"""
        total_memories = self.vector_memory.collection.count()
        total_sessions = len(self.session.conversation_history)
        
        if total_memories < 50:
            return '🍼 Recién nacida (aprendiendo lo básico)'
        elif total_memories < 200:
            return '👶 Infante (construyendo memoria)'
        elif total_memories < 500:
            return '🧒 Niña curiosa (desarrollando personalidad)'
        elif total_memories < 1000:
            return '🎓 Estudiante (acumulando conocimiento)'
        else:
            return '🧠 Experta autónoma (memoria rica y experiencia)'
    
    def teach(self, correction: str):
        """Enseñar a la IA una corrección o nuevo conocimiento"""
        
        # Guardar como conocimiento explícito
        self.vector_memory.add_memory(
            text=f"CORRECCIÓN APRENDIDA: {correction}",
            metadata={
                'type': 'explicit_learning',
                'source': 'user_teaching',
                'importance': 'high'
            }
        )
        
        return f"🎓 ¡Gracias! He aprendido: '{correction[:100]}...' Lo recordaré para futuras conversaciones."
    
    def force_memory_consolidation(self):
        """Forzar consolidación de memoria (dormir/aprender)"""
        
        # Analizar patrones en las conversaciones recientes
        recent = self.session.conversation_history[-20:]
        
        # Crear resumen de aprendizajes
        if recent:
            topics = set()
            for ex in recent:
                # Extraer posibles temas (simplificado)
                words = ex['user'].split()
                topics.update([w for w in words if len(w) > 4])
            
            summary = f"""
            Sesión de aprendizaje consolidada:
            - Interacciones: {len(recent)}
            - Temas tratados: {', '.join(list(topics)[:5])}
            - Aprendizajes clave extraídos de la conversación
            """
            
            self.vector_memory.add_memory(
                text=summary,
                metadata={'type': 'consolidation', 'session_summary': True}
            )
        
        return {
            'memories_consolidated': len(recent),
            'total_memories': self.vector_memory.collection.count(),
            'message': '💤 He consolidado mis recuerdos y estoy lista para más aprendizaje'
        }

# ============ INICIALIZACIÓN ============
print("=" * 60)
print("🍼 Bebé IA Inteligente v2.0")
print("Modelo: " + Config.MODEL_NAME)
print("=" * 60)

bebe = BebeIAInteligente()

# ============ RUTAS FLASK ============
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
    return jsonify({'status': 'ok', 'message': result})

@app.route('/sleep', methods=['POST'])
def sleep():
    result = bebe.force_memory_consolidation()
    return jsonify(result)

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'stage': bebe._get_development_stage(),
        'total_memories': bebe.vector_memory.collection.count(),
        'session_messages': len(bebe.session.conversation_history),
        'model': Config.MODEL_NAME
    })

@app.route('/memories', methods=['GET'])
def get_memories():
    """Ver memorias recientes"""
    recent = bebe.vector_memory.get_recent_memories(n=10)
    return jsonify({
        'memories': recent,
        'count': len(recent)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
