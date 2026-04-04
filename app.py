"""
Bebé IA Pro - Modelo Grande (Mistral/Llama) + Aprendizaje Automático Multi-Fuente
Aprende sola de Wikipedia, arXiv, GitHub, y conversaciones con otros bots
"""
from flask import Flask, render_template, request, jsonify
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import chromadb
from chromadb.utils import embedding_functions
import os
import json
import random
import re
import threading
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional
import urllib.request
from html.parser import HTMLParser

app = Flask(__name__)

# ============ CONFIGURACIÓN ============
class Config:
    # Modelo principal (cambia según tu RAM)
    # Opciones de modelo GRATIS (descarga desde HuggingFace)
    MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"  # 14GB RAM
    # Alternativas más ligeras:
    # MODEL_NAME = "microsoft/phi-2"  # 6GB RAM
    # MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # 2GB RAM
    # MODEL_NAME = "google/gemma-2b-it"  # 4GB RAM
    
    MAX_NEW_TOKENS = 512
    TEMPERATURE = 0.7
    
    # Base de datos vectorial
    CHROMA_PATH = "./chroma_knowledge"
    COLLECTION_NAME = "bebe_knowledge"
    
    # Fuentes de aprendizaje automático
    AUTO_LEARN_INTERVAL = 1800  # 30 minutos entre aprendizajes automáticos
    MAX_DAILY_ARTICLES = 20     # Límite de artículos por día

# ============ RECOLECTORES DE CONOCIMIENTO ============
class WikipediaCollector:
    """Recolector de Wikipedia (sin API)"""
    
    def search(self, query: str, lang: str = "es") -> List[Dict]:
        """Buscar artículos de Wikipedia"""
        try:
            # Usar la API de búsqueda de Wikipedia (pública, no requiere key)
            search_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&srlimit=3"
            
            with urllib.request.urlopen(search_url, timeout=10) as response:
                data = json.loads(response.read())
            
            results = []
            for item in data['query']['search']:
                # Obtener contenido del artículo
                content = self._get_article_content(item['title'], lang)
                if content:
                    results.append({
                        'title': item['title'],
                        'content': content[:2000],  # Primeros 2000 chars
                        'source': f'https://{lang}.wikipedia.org/wiki/{item["title"].replace(" ", "_")}',
                        'type': 'wikipedia'
                    })
            return results
        except Exception as e:
            print(f"Error Wikipedia: {e}")
            return []
    
    def _get_article_content(self, title: str, lang: str) -> str:
        """Obtener contenido de un artículo específico"""
        try:
            url = f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&exlimit=1&exchars=3000&titles={urllib.parse.quote(title)}&format=json"
            
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read())
            
            pages = data['query']['pages']
            page = list(pages.values())[0]
            return page.get('extract', '')
        except:
            return ""

class ArxivCollector:
    """Recolector de papers de arXiv (API pública)"""
    
    def search(self, query: str, max_results: int = 3) -> List[Dict]:
        """Buscar papers científicos"""
        try:
            # API pública de arXiv
            url = f"http://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query)}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"
            
            response = requests.get(url, timeout=15)
            content = response.text
            
            # Parsear XML (simplificado)
            entries = re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL)
            
            results = []
            for entry in entries[:max_results]:
                title = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                summary = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                
                if title and summary:
                    results.append({
                        'title': self._clean_xml(title.group(1)),
                        'content': self._clean_xml(summary.group(1)),
                        'source': 'arXiv',
                        'type': 'scientific_paper'
                    })
            return results
        except Exception as e:
            print(f"Error arXiv: {e}")
            return []
    
    def _clean_xml(self, text: str) -> str:
        """Limpiar texto XML"""
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()

class GitHubCollector:
    """Recolector de READMEs y documentación de GitHub"""
    
    def search_repos(self, query: str, language: str = "python") -> List[Dict]:
        """Buscar repositorios populares (API pública, sin auth para búsqueda básica)"""
        try:
            # GitHub API pública tiene límite, usamos búsqueda web simple
            search_url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}+language:{language}&sort=stars&order=desc"
            
            # Sin API key, limitado pero funciona
            headers = {'Accept': 'application/vnd.github.v3+json'}
            response = requests.get(search_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                for repo in data.get('items', [])[:3]:
                    # Intentar obtener README
                    readme = self._get_readme(repo['full_name'])
                    results.append({
                        'title': repo['name'],
                        'description': repo['description'] or '',
                        'readme': readme[:1500] if readme else '',
                        'source': repo['html_url'],
                        'type': 'github_repo',
                        'stars': repo['stargazers_count']
                    })
                return results
            return []
        except Exception as e:
            print(f"Error GitHub: {e}")
            return []
    
    def _get_readme(self, repo_full_name: str) -> str:
        """Obtener README de un repo"""
        try:
            url = f"https://raw.githubusercontent.com/{repo_full_name}/main/README.md"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.text
            # Intentar con master
            url = f"https://raw.githubusercontent.com/{repo_full_name}/master/README.md"
            response = requests.get(url, timeout=10)
            return response.text if response.status_code == 200 else ""
        except:
            return ""

class BotConversationSimulator:
    """Simula conversaciones con otros bots para aprender"""
    
    PERSONALITIES = [
        {"name": "Profesor", "style": "explicativo, paciente, usa ejemplos"},
        {"name": "Programador", "style": "técnico, directo, usa código"},
        {"name": "Filósofo", "style": "profundo, cuestiona, reflexivo"},
        {"name": "Niño", "style": "curioso, simple, muchas preguntas"},
        {"name": "Experto", "style": "preciso, detallado, formal"}
    ]
    
    def __init__(self, main_bot):
        self.main_bot = main_bot
    
    def simulate_conversation(self, topic: str, rounds: int = 3) -> List[Dict]:
        """Simular conversación entre bots sobre un tema"""
        conversation = []
        personas = random.sample(self.PERSONALITIES, 2)
        
        bot_a, bot_b = personas[0], personas[1]
        current_topic = topic
        
        for i in range(rounds):
            # Bot A pregunta/responde
            prompt_a = f"Eres {bot_a['name']}, un asistente {bot_a['style']}. "
            prompt_a += f"Habla sobre: {current_topic}"
            
            response_a = self.main_bot.generate_raw(prompt_a)
            
            conversation.append({
                'speaker': bot_a['name'],
                'message': response_a,
                'topic': current_topic
            })
            
            # Bot B responde
            prompt_b = f"Eres {bot_b['name']}, un asistente {bot_b['style']}. "
            prompt_b += f"Responde a esto sobre {current_topic}: {response_a[:200]}"
            
            response_b = self.main_bot.generate_raw(prompt_b)
            
            conversation.append({
                'speaker': bot_b['name'],
                'message': response_b,
                'topic': current_topic
            })
            
            # Evolucionar tema
            current_topic += " " + response_b[:50]
        
        return conversation

# ============ MODELO DE LENGUAJE GRANDE ============
class LargeLanguageModel:
    """Wrapper para modelos grandes (Mistral, Llama, etc.)"""
    
    def __init__(self):
        print(f"🤖 Cargando modelo grande: {Config.MODEL_NAME}")
        print("   Esto puede tomar 5-10 minutos la primera vez...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            Config.MODEL_NAME,
            trust_remote_code=True
        )
        
        # Configurar modelo según hardware disponible
        if torch.cuda.is_available():
            print("   ✅ Usando GPU")
            self.model = AutoModelForCausalLM.from_pretrained(
                Config.MODEL_NAME,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True
            )
        else:
            print("   ⚠️ Usando CPU (más lento)")
            self.model = AutoModelForCausalLM.from_pretrained(
                Config.MODEL_NAME,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True,
                trust_remote_code=True
            )
        
        self.pipe = pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            max_new_tokens=Config.MAX_NEW_TOKENS,
            temperature=Config.TEMPERATURE,
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        print("✅ Modelo cargado correctamente")
    
    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """Generar respuesta con formato de chat"""
        
        # Formato Mistral/Llama
        if system_prompt:
            full_prompt = f"<s>[INST] {system_prompt}\n\n{prompt} [/INST]"
        else:
            full_prompt = f"<s>[INST] {prompt} [/INST]"
        
        outputs = self.pipe(
            full_prompt,
            return_full_text=False
        )
        
        response = outputs[0]['generated_text'].strip()
        # Limpiar
        response = response.split('[/INST]')[0].strip()
        return response
    
    def generate_raw(self, prompt: str) -> str:
        """Generación sin formato (para simulaciones)"""
        outputs = self.pipe(prompt, return_full_text=False, max_new_tokens=256)
        return outputs[0]['generated_text'].strip()

# ============ MEMORIA VECTORIAL INTELIGENTE ============
class SmartMemory:
    """Memoria con embeddings semánticos"""
    
    def __init__(self):
        self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(
            name=Config.COLLECTION_NAME,
            embedding_function=self.embedding_func
        )
        
        print(f"🧠 Memoria: {self.collection.count()} documentos")
    
    def add(self, text: str, metadata: Dict, source: str = "user"):
        """Agregar conocimiento a la memoria"""
        
        doc_id = f"{source}_{datetime.now().timestamp()}"
        
        self.collection.add(
            documents=[text],
            metadatas=[{
                **metadata,
                'source': source,
                'timestamp': datetime.now().isoformat(),
                'length': len(text)
            }],
            ids=[doc_id]
        )
        return doc_id
    
    def search(self, query: str, k: int = 5, source_filter: str = None) -> List[Dict]:
        """Búsqueda semántica con filtros opcionales"""
        
        where_filter = {"source": source_filter} if source_filter else None
        
        results = self.collection.query(
            query_texts=[query],
            n_results=k,
            where=where_filter
        )
        
        documents = []
        for i in range(len(results['ids'][0])):
            documents.append({
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i]
            })
        
        return documents
    
    def get_stats(self) -> Dict:
        """Estadísticas de la memoria"""
        all_data = self.collection.get()
        
        sources = {}
        for meta in all_data.get('metadatas', []):
            src = meta.get('source', 'unknown')
            sources[src] = sources.get(src, 0) + 1
        
        return {
            'total_documents': self.collection.count(),
            'sources': sources
        }

# ============ MOTOR DE APRENDIZAJE AUTOMÁTICO ============
class AutoLearningEngine:
    """Motor que aprende automáticamente de múltiples fuentes"""
    
    def __init__(self, llm: LargeLanguageModel, memory: SmartMemory):
        self.llm = llm
        self.memory = memory
        
        # Inicializar recolectores
        self.wikipedia = WikipediaCollector()
        self.arxiv = ArxivCollector()
        self.github = GitHubCollector()
        self.bot_simulator = BotConversationSimulator(llm)
        
        # Estado de aprendizaje
        self.learning_queue = []
        self.daily_learned = 0
        self.last_learning = None
        
        # Iniciar hilo de aprendizaje automático
        self.running = True
        self.learning_thread = threading.Thread(target=self._auto_learning_loop, daemon=True)
        self.learning_thread.start()
        
        print("🔄 Motor de aprendizaje automático iniciado")
    
    def _auto_learning_loop(self):
        """Bucle de aprendizaje continuo en background"""
        while self.running:
            if self.daily_learned < Config.MAX_DAILY_ARTICLES:
                self._learn_something_new()
                self.daily_learned += 1
            
            # Reset diario
            if self.last_learning and (datetime.now() - self.last_learning).days >= 1:
                self.daily_learned = 0
            
            time.sleep(Config.AUTO_LEARN_INTERVAL)
    
    def _learn_something_new(self):
        """Aprender algo nuevo de una fuente aleatoria"""
        
        topics = [
            "inteligencia artificial", "machine learning", "python programming",
            "neural networks", "deep learning", "natural language processing",
            "computer vision", "reinforcement learning", "data science",
            "algorithm optimization", "quantum computing", "blockchain"
        ]
        
        topic = random.choice(topics)
        source = random.choice(['wikipedia', 'arxiv', 'github', 'bots'])
        
        print(f"🎓 Auto-aprendiendo: {topic} desde {source}")
        
        try:
            if source == 'wikipedia':
                self._learn_from_wikipedia(topic)
            elif source == 'arxiv':
                self._learn_from_arxiv(topic)
            elif source == 'github':
                self._learn_from_github(topic)
            elif source == 'bots':
                self._learn_from_bot_conversation(topic)
            
            self.last_learning = datetime.now()
            
        except Exception as e:
            print(f"   ❌ Error aprendiendo: {e}")
    
    def _learn_from_wikipedia(self, topic: str):
        """Aprender de Wikipedia"""
        articles = self.wikipedia.search(topic)
        for article in articles:
            # Resumir con el modelo grande
            summary = self._summarize(article['content'])
            self.memory.add(
                text=f"Wikipedia - {article['title']}: {summary}",
                metadata={
                    'original_title': article['title'],
                    'original_url': article['source'],
                    'topic': topic
                },
                source='wikipedia'
            )
            print(f"   ✅ Aprendido: {article['title']}")
    
    def _learn_from_arxiv(self, topic: str):
        """Aprender de papers científicos"""
        papers = self.arxiv.search(topic, max_results=2)
        for paper in papers:
            # Simplificar el paper
            simplified = self._simplify_scientific_text(paper['content'])
            self.memory.add(
                text=f"Paper - {paper['title']}: {simplified}",
                metadata={
                    'original_title': paper['title'],
                    'topic': topic
                },
                source='arxiv'
            )
            print(f"   ✅ Aprendido paper: {paper['title'][:60]}...")
    
    def _learn_from_github(self, topic: str):
        """Aprender de repositorios de código"""
        repos = self.github.search_repos(topic)
        for repo in repos:
            content = f"{repo['description']}\n\nREADME:\n{repo['readme']}"
            analyzed = self._analyze_code_repo(content)
            self.memory.add(
                text=f"GitHub - {repo['title']} ({repo['stars']}⭐): {analyzed}",
                metadata={
                    'repo_name': repo['title'],
                    'url': repo['source'],
                    'stars': repo['stars']
                },
                source='github'
            )
            print(f"   ✅ Aprendido repo: {repo['title']}")
    
    def _learn_from_bot_conversation(self, topic: str):
        """Aprender de conversación simulada entre bots"""
        conversation = self.bot_simulator.simulate_conversation(topic, rounds=2)
        
        # Analizar y extraer conocimiento
        full_convo = "\n".join([f"{c['speaker']}: {c['message']}" for c in conversation])
        insights = self._extract_insights(full_convo)
        
        self.memory.add(
            text=f"Simulación bots sobre {topic}: {insights}",
            metadata={
                'conversation': full_convo[:500],
                'topic': topic
            },
            source='bot_simulation'
        )
        print(f"   ✅ Aprendido de simulación sobre: {topic}")
    
    def _summarize(self, text: str) -> str:
        """Resumir texto usando el modelo"""
        prompt = f"Resume este texto en 3 oraciones clave:\n\n{text[:1500]}\n\nResumen:"
        return self.llm.generate_raw(prompt)[:500]
    
    def _simplify_scientific_text(self, text: str) -> str:
        """Simplificar texto científico"""
        prompt = f"Explica este concepto científico de forma simple para un estudiante:\n\n{text[:1000]}\n\nExplicación simple:"
        return self.llm.generate_raw(prompt)[:600]
    
    def _analyze_code_repo(self, content: str) -> str:
        """Analizar repositorio de código"""
        prompt = f"Analiza este README y explica qué hace el proyecto en 2 oraciones:\n\n{content[:1000]}\n\nAnálisis:"
        return self.llm.generate_raw(prompt)[:400]
    
    def _extract_insights(self, conversation: str) -> str:
        """Extraer insights de una conversación"""
        prompt = f"Extrae las 3 ideas más importantes de esta conversación:\n\n{conversation[:1500]}\n\nIdeas clave:"
        return self.llm.generate_raw(prompt)[:500]
    
    def force_learning(self, source: str, query: str) -> str:
        """Forzar aprendizaje de una fuente específica"""
        try:
            if source == 'wikipedia':
                self._learn_from_wikipedia(query)
            elif source == 'arxiv':
                self._learn_from_arxiv(query)
            elif source == 'github':
                self._learn_from_github(query)
            elif source == 'bots':
                self._learn_from_bot_conversation(query)
            return f"✅ Aprendido de {source} sobre: {query}"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def get_learning_stats(self) -> Dict:
        """Estadísticas de aprendizaje"""
        return {
            'daily_learned': self.daily_learned,
            'max_daily': Config.MAX_DAILY_ARTICLES,
            'last_learning': self.last_learning.isoformat() if self.last_learning else None,
            'queue_size': len(self.learning_queue),
            'sources': ['wikipedia', 'arxiv', 'github', 'bot_simulation']
        }

# ============ BEbÉ IA COMPLETA ============
class BebeIAPro:
    """Bebé IA con modelo grande y aprendizaje automático"""
    
    def __init__(self):
        print("=" * 70)
        print("🚀 INICIANDO BEbÉ IA PRO")
        print("Modelo Grande + Aprendizaje Automático Multi-Fuente")
        print("=" * 70)
        
        # Componentes principales
        self.llm = LargeLanguageModel()
        self.memory = SmartMemory()
        self.learner = AutoLearningEngine(self.llm, self.memory)
        
        # Historial de conversación
        self.conversation_history = []
        
        print("\n✅ Sistema listo")
        print(f"   📚 Aprendiendo automáticamente cada {Config.AUTO_LEARN_INTERVAL/60} minutos")
    
    def chat(self, user_input: str) -> Dict:
        """Procesar mensaje del usuario"""
        
        # 1. Buscar conocimiento relevante en memoria
        relevant = self.memory.search(user_input, k=3)
        knowledge_context = self._format_knowledge(relevant)
        
        # 2. Construir prompt enriquecido
        system_prompt = """Eres Bebé IA Pro, un asistente inteligente que:
- Ha aprendido de Wikipedia, papers científicos, GitHub y conversaciones
- Usa conocimiento real y actualizado
- Es conversacional, amigable y útil
- Cita sus fuentes cuando es relevante"""
        
        user_prompt = f"""Contexto de conocimiento almacenado:
{knowledge_context}

Pregunta del usuario: {user_input}

Responde usando el contexto si es relevante, o tu conocimiento general."""
        
        # 3. Generar respuesta
        response = self.llm.generate(user_prompt, system_prompt)
        
        # 4. Guardar conversación
        self._save_conversation(user_input, response)
        
        # 5. Detectar si debemos aprender más sobre este tema
        if self._should_learn_more(user_input):
            threading.Thread(
                target=self.learner.force_learning,
                args=('wikipedia', user_input),
                daemon=True
            ).start()
        
        return {
            'response': response,
            'sources_used': [r['metadata'].get('source', 'unknown') for r in relevant],
            'documents_found': len(relevant),
            'emotion': self._detect_emotion(response),
            'stage': self._get_stage(),
            'auto_learning': True
        }
    
    def _format_knowledge(self, documents: List[Dict]) -> str:
        """Formatear documentos para el contexto"""
        if not documents:
            return "No hay conocimiento específico en memoria aún."
        
        formatted = []
        for doc in documents:
            source = doc['metadata'].get('source', 'unknown')
            text = doc['text'][:300]
            formatted.append(f"[{source.upper()}] {text}...")
        
        return "\n\n".join(formatted)
    
    def _should_learn_more(self, query: str) -> bool:
        """Determinar si deberíamos aprender más sobre este tema"""
        # Si no encontramos mucho en memoria, aprender más
        results = self.memory.search(query, k=1)
        return len(results) == 0 or results[0]['distance'] > 0.5
    
    def _save_conversation(self, user: str, bot: str):
        """Guardar interacción"""
        self.conversation_history.append({
            'user': user,
            'bot': bot,
            'timestamp': datetime.now().isoformat()
        })
        
        # También guardar en memoria vectorial
        self.memory.add(
            text=f"User: {user}\nBot: {bot}",
            metadata={'type': 'conversation'},
            source='user_chat'
        )
    
    def _detect_emotion(self, text: str) -> str:
        indicators = {
            'entusiasta': ['!', 'excelente', 'genial', 'increíble'],
            'técnico': ['código', 'función', 'algoritmo', 'implementación'],
            'empático': ['entiendo', 'siento', 'comprendo tu situación']
        }
        text_lower = text.lower()
        for emotion, words in indicators.items():
            if any(w in text_lower for w in words):
                return emotion
        return 'neutral'
    
    def _get_stage(self) -> str:
        stats = self.memory.get_stats()
        total = stats['total_documents']
        
        if total < 50:
            return '🍼 Bebé aprendiz (poca experiencia)'
        elif total < 200:
            return '📚 Estudiante (acumulando conocimiento)'
        elif total < 500:
            return '🔬 Investigador (bases sólidas)'
        else:
            return '🧠 Experto (conocimiento amplio)'
    
    def teach(self, correction: str) -> str:
        """Enseñar manualmente"""
        self.memory.add(
            text=f"CORRECCIÓN MANUAL: {correction}",
            metadata={'type': 'explicit_knowledge'},
            source='user_teaching'
        )
        return "🎓 ¡Aprendido! He guardado tu corrección en mi memoria permanente."
    
    def get_status(self) -> Dict:
        """Estado completo del sistema"""
        return {
            'stage': self._get_stage(),
            'memory_stats': self.memory.get_stats(),
            'learning_stats': self.learner.get_learning_stats(),
            'total_conversations': len(self.conversation_history),
            'model': Config.MODEL_NAME
        }

# ============ INICIALIZACIÓN ============
bebe = BebeIAPro()

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
    return jsonify({'message': result})

@app.route('/learn', methods=['POST'])
def force_learn():
    """Forzar aprendizaje de una fuente específica"""
    data = request.json
    source = data.get('source', 'wikipedia')
    query = data.get('query', '')
    result = bebe.learner.force_learning(source, query)
    return jsonify({'message': result})

@app.route('/status', methods=['GET'])
def status():
    return jsonify(bebe.get_status())

@app.route('/search_memory', methods=['POST'])
def search_memory():
    """Buscar en la memoria de la IA"""
    data = request.json
    query = data.get('query', '')
    results = bebe.memory.search(query, k=5)
    return jsonify({'results': results})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
