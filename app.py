"""
Bebé IA Pro - API HuggingFace + Aprendizaje Automático
Funciona en Render gratuito (512MB RAM) - Sin modelos locales
"""
from flask import Flask, render_template, request, jsonify
import os
import json
import random
import re
import threading
import time
from datetime import datetime
from typing import List, Dict
import requests
import urllib.request

app = Flask(__name__)

# ============ CONFIGURACIÓN ============
class Config:
    # API de HuggingFace (gratuita, no requiere token para modelos públicos)
    # Si tienes token, ponlo aquí para más rate limit
    HF_API_TOKEN = os.environ.get('HF_API_TOKEN', '')
    
    # Modelos disponibles en API gratuita
    DEFAULT_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"
    FALLBACK_MODEL = "HuggingFaceH4/zephyr-7b-beta"
    FAST_MODEL = "google/gemma-2b-it"
    
    # Base de datos vectorial (usaremos JSON simple para Render)
    KNOWLEDGE_FILE = 'knowledge_base.json'
    MEMORY_FILE = 'conversation_memory.json'
    
    # Aprendizaje automático
    AUTO_LEARN_INTERVAL = 1800  # 30 minutos
    MAX_DAILY_ARTICLES = 15

# ============ CLIENTE API HUGGINGFACE ============
class HuggingFaceAPI:
    """Cliente para API de HuggingFace (gratuita)"""
    
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {Config.HF_API_TOKEN}" if Config.HF_API_TOKEN else "",
            "Content-Type": "application/json"
        }
        self.current_model = Config.DEFAULT_MODEL
        self.api_url = f"https://api-inference.huggingface.co/models/{self.current_model}"
        
        print(f"🤖 Usando API HuggingFace: {self.current_model}")
        if not Config.HF_API_TOKEN:
            print("   ⚠️ Sin token (rate limit más bajo)")
        else:
            print("   ✅ Con token de autenticación")
    
    def generate(self, prompt: str, system_prompt: str = None, max_tokens: int = 512) -> str:
        """Generar texto usando la API"""
        
        # Formato de chat para Mistral/Zephyr
        if system_prompt:
            full_prompt = f"<s>[INST] {system_prompt}\n\n{prompt} [/INST]"
        else:
            full_prompt = f"<s>[INST] {prompt} [/INST]"
        
        payload = {
            "inputs": full_prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": 0.7,
                "top_p": 0.95,
                "return_full_text": False
            }
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    text = result[0].get('generated_text', '')
                    # Limpiar
                    text = text.split('[/INST]')[-1].strip()
                    return text
                return str(result)
            
            elif response.status_code == 503:
                # Modelo cargándose, esperar y reintentar
                print("   ⏳ Modelo cargándose, esperando...")
                time.sleep(10)
                return self.generate(prompt, system_prompt, max_tokens)
            
            else:
                print(f"   ❌ Error API: {response.status_code}")
                # Fallback a modelo más simple
                if self.current_model != Config.FAST_MODEL:
                    print("   🔄 Cambiando a modelo más rápido...")
                    self.current_model = Config.FAST_MODEL
                    self.api_url = f"https://api-inference.huggingface.co/models/{self.current_model}"
                    return self.generate(prompt, system_prompt, max_tokens)
                return "Lo siento, estoy teniendo problemas técnicos. ¿Puedes intentar de nuevo?"
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return "Error de conexión. Intentando reconectar..."
    
    def switch_model(self, model_name: str):
        """Cambiar de modelo"""
        self.current_model = model_name
        self.api_url = f"https://api-inference.huggingface.co/models/{model_name}"
        return f"Modelo cambiado a: {model_name}"

# ============ RECOLECTORES DE CONOCIMIENTO ============
class WikipediaCollector:
    """Recolector de Wikipedia (sin API key)"""
    
    def search(self, query: str, lang: str = "es") -> List[Dict]:
        try:
            search_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&srlimit=2"
            
            with urllib.request.urlopen(search_url, timeout=10) as response:
                data = json.loads(response.read())
            
            results = []
            for item in data['query']['search']:
                content = self._get_article_content(item['title'], lang)
                if content:
                    results.append({
                        'title': item['title'],
                        'content': content[:1500],
                        'source': 'wikipedia',
                        'url': f'https://{lang}.wikipedia.org/wiki/{item["title"].replace(" ", "_")}'
                    })
            return results
        except Exception as e:
            print(f"Error Wikipedia: {e}")
            return []
    
    def _get_article_content(self, title: str, lang: str) -> str:
        try:
            url = f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&exchars=2000&titles={urllib.parse.quote(title)}&format=json"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read())
            pages = data['query']['pages']
            page = list(pages.values())[0]
            return page.get('extract', '')
        except:
            return ""

class ArxivCollector:
    """Recolector de arXiv"""
    
    def search(self, query: str, max_results: int = 2) -> List[Dict]:
        try:
            url = f"http://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query)}&start=0&max_results={max_results}"
            response = requests.get(url, timeout=15)
            content = response.text
            
            entries = re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL)
            results = []
            
            for entry in entries:
                title = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                summary = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                
                if title and summary:
                    results.append({
                        'title': self._clean_xml(title.group(1)),
                        'content': self._clean_xml(summary.group(1)),
                        'source': 'arxiv'
                    })
            return results
        except Exception as e:
            print(f"Error arXiv: {e}")
            return []
    
    def _clean_xml(self, text: str) -> str:
        return re.sub(r'<[^>]+>', '', text).strip()

# ============ BASE DE CONOCIMIENTO SIMPLE ============
class SimpleKnowledgeBase:
    """Base de conocimiento usando JSON (para Render)"""
    
    def __init__(self):
        self.knowledge_file = Config.KNOWLEDGE_FILE
        self.data = self._load()
        print(f"📚 Base de conocimiento: {len(self.data['documents'])} documentos")
    
    def _load(self) -> Dict:
        if os.path.exists(self.knowledge_file):
            try:
                with open(self.knowledge_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            'documents': [],
            'concepts': {},
            'last_update': None
        }
    
    def _save(self):
        with open(self.knowledge_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def add(self, text: str, metadata: Dict, source: str = "unknown"):
        """Agregar documento"""
        doc = {
            'id': f"{source}_{datetime.now().timestamp()}",
            'text': text,
            'metadata': metadata,
            'source': source,
            'timestamp': datetime.now().isoformat()
        }
        
        self.data['documents'].append(doc)
        
        # Limitar tamaño
        if len(self.data['documents']) > 500:
            self.data['documents'] = self.data['documents'][-400:]
        
        # Indexar conceptos simple
        words = set(re.findall(r'\b\w+\b', text.lower()))
        for word in words:
            if len(word) > 4:
                if word not in self.data['concepts']:
                    self.data['concepts'][word] = []
                self.data['concepts'][word].append(doc['id'])
        
        self.data['last_update'] = datetime.now().isoformat()
        self._save()
        return doc['id']
    
    def search(self, query: str, k: int = 3) -> List[Dict]:
        """Búsqueda simple por palabras clave"""
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        
        scores = []
        for doc in self.data['documents']:
            doc_words = set(re.findall(r'\b\w+\b', doc['text'].lower()))
            matches = len(query_words & doc_words)
            
            # Bonus por recencia
            try:
                doc_time = datetime.fromisoformat(doc['timestamp'])
                days_old = (datetime.now() - doc_time).days
                recency_bonus = max(0, 5 - days_old)
            except:
                recency_bonus = 0
            
            score = matches + recency_bonus
            if score > 0:
                scores.append((score, doc))
        
        scores.sort(reverse=True, key=lambda x: x[0])
        return [doc for _, doc in scores[:k]]
    
    def get_stats(self) -> Dict:
        sources = {}
        for doc in self.data['documents']:
            src = doc.get('source', 'unknown')
            sources[src] = sources.get(src, 0) + 1
        
        return {
            'total': len(self.data['documents']),
            'sources': sources,
            'concepts': len(self.data['concepts'])
        }

# ============ MOTOR DE APRENDIZAJE AUTOMÁTICO ============
class AutoLearningEngine:
    """Aprendizaje automático de múltiples fuentes"""
    
    def __init__(self, api: HuggingFaceAPI, knowledge: SimpleKnowledgeBase):
        self.api = api
        self.knowledge = knowledge
        
        self.wikipedia = WikipediaCollector()
        self.arxiv = ArxivCollector()
        
        self.running = True
        self.daily_count = 0
        self.last_reset = datetime.now()
        
        # Iniciar hilo de aprendizaje
        self.thread = threading.Thread(target=self._learning_loop, daemon=True)
        self.thread.start()
        
        print("🔄 Aprendizaje automático iniciado")
    
    def _learning_loop(self):
        """Bucle de aprendizaje continuo"""
        while self.running:
            # Reset diario
            if (datetime.now() - self.last_reset).days >= 1:
                self.daily_count = 0
                self.last_reset = datetime.now()
            
            if self.daily_count < Config.MAX_DAILY_ARTICLES:
                self._learn_something()
                self.daily_count += 1
            
            time.sleep(Config.AUTO_LEARN_INTERVAL)
    
    def _learn_something(self):
        """Aprender de una fuente aleatoria"""
        topics = [
            "inteligencia artificial", "machine learning", "python",
            "neural networks", "deep learning", "data science",
            "programación", "algoritmos", "matemáticas"
        ]
        
        topic = random.choice(topics)
        source = random.choice(['wikipedia', 'arxiv'])
        
        print(f"🎓 Auto-aprendiendo: {topic} desde {source}")
        
        try:
            if source == 'wikipedia':
                articles = self.wikipedia.search(topic)
                for art in articles:
                    summary = self._summarize(art['content'])
                    self.knowledge.add(
                        text=f"Wikipedia: {art['title']}\n{summary}",
                        metadata={'topic': topic, 'original': art['content'][:500]},
                        source='wikipedia'
                    )
                    print(f"   ✅ {art['title'][:50]}...")
            
            elif source == 'arxiv':
                papers = self.arxiv.search(topic, max_results=1)
                for paper in papers:
                    simplified = self._simplify(paper['content'])
                    self.knowledge.add(
                        text=f"Paper: {paper['title']}\n{simplified}",
                        metadata={'topic': topic},
                        source='arxiv'
                    )
                    print(f"   ✅ Paper: {paper['title'][:50]}...")
                    
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    def _summarize(self, text: str) -> str:
        """Resumir con la API"""
        prompt = f"Resume este texto en 2 oraciones:\n\n{text[:1000]}\n\nResumen:"
        return self.api.generate(prompt, max_tokens=150)
    
    def _simplify(self, text: str) -> str:
        """Simplificar texto científico"""
        prompt = f"Explica esto simplemente:\n\n{text[:800]}\n\nExplicación:"
        return self.api.generate(prompt, max_tokens=200)
    
    def force_learn(self, source: str, query: str) -> str:
        """Forzar aprendizaje manual"""
        try:
            if source == 'wikipedia':
                articles = self.wikipedia.search(query)
                for art in articles[:2]:
                    self.knowledge.add(
                        text=f"{art['title']}: {art['content'][:1000]}",
                        metadata={'query': query},
                        source='wikipedia'
                    )
                return f"✅ Aprendido {len(articles)} artículos de Wikipedia sobre '{query}'"
            
            elif source == 'arxiv':
                papers = self.arxiv.search(query, max_results=2)
                for paper in papers:
                    self.knowledge.add(
                        text=f"{paper['title']}: {paper['content'][:800]}",
                        metadata={'query': query},
                        source='arxiv'
                    )
                return f"✅ Aprendido {len(papers)} papers de arXiv sobre '{query}'"
            
            return "Fuente no válida"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def get_stats(self) -> Dict:
        return {
            'daily_learned': self.daily_count,
            'max_daily': Config.MAX_DAILY_ARTICLES,
            'next_in': Config.AUTO_LEARN_INTERVAL // 60,
            'sources': ['wikipedia', 'arxiv']
        }

# ============ BEbÉ IA COMPLETA ============
class BebeIAPro:
    """IA completa con API HuggingFace"""
    
    def __init__(self):
        print("=" * 60)
        print("🚀 BEbÉ IA PRO - API HuggingFace")
        print("Sin modelos locales - Funciona en Render gratuito")
        print("=" * 60)
        
        self.api = HuggingFaceAPI()
        self.knowledge = SimpleKnowledgeBase()
        self.learner = AutoLearningEngine(self.api, self.knowledge)
        
        self.conversations = []
        
        print("\n✅ Sistema listo")
        print(f"   📚 {self.knowledge.get_stats()['total']} documentos")
        print("   🔄 Auto-aprendizaje activo")
    
    def chat(self, user_input: str) -> Dict:
        """Procesar mensaje"""
        
        # Buscar conocimiento relevante
        relevant = self.knowledge.search(user_input, k=3)
        context = self._format_context(relevant)
        
        # Construir prompt
        system = """Eres Bebé IA Pro, un asistente inteligente que aprende continuamente de Wikipedia y papers científicos. Usa el contexto proporcionado si es relevante."""
        
        prompt = f"""Contexto de conocimiento:
{context}

Pregunta: {user_input}

Responde de manera útil y natural:"""
        
        # Generar respuesta
        response = self.api.generate(prompt, system, max_tokens=400)
        
        # Guardar
        self._save_conversation(user_input, response)
        
        # Verificar si necesitamos aprender más
        if len(relevant) == 0:
            threading.Thread(
                target=self.learner.force_learn,
                args=('wikipedia', user_input),
                daemon=True
            ).start()
        
        return {
            'response': response,
            'sources': [r['source'] for r in relevant],
            'documents_found': len(relevant),
            'model_used': self.api.current_model,
            'stage': self._get_stage()
        }
    
    def _format_context(self, docs: List[Dict]) -> str:
        if not docs:
            return "No hay contexto específico en mi base de datos."
        return "\n\n".join([f"[{d['source']}] {d['text'][:300]}..." for d in docs])
    
    def _save_conversation(self, user: str, bot: str):
        self.conversations.append({
            'user': user,
            'bot': bot,
            'time': datetime.now().isoformat()
        })
        self.knowledge.add(
            text=f"User: {user}\nBot: {bot}",
            metadata={'type': 'conversation'},
            source='chat'
        )
    
    def _get_stage(self) -> str:
        stats = self.knowledge.get_stats()
        total = stats['total']
        if total < 50:
            return '🍼 Aprendiz'
        elif total < 200:
            return '📚 Estudiante'
        elif total < 500:
            return '🔬 Investigador'
        return '🧠 Experto'
    
    def teach(self, text: str) -> str:
        self.knowledge.add(
            text=f"ENSEÑADO: {text}",
            metadata={'type': 'manual'},
            source='user'
        )
        return "🎓 ¡Aprendido! Guardado en mi base de conocimiento."
    
    def get_status(self) -> Dict:
        return {
            'stage': self._get_stage(),
            'knowledge': self.knowledge.get_stats(),
            'learning': self.learner.get_stats(),
            'model': self.api.current_model,
            'conversations': len(self.conversations)
        }

# ============ INICIALIZACIÓN ============
bebe = BebeIAPro()

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
    return jsonify({'message': result})

@app.route('/learn', methods=['POST'])
def learn():
    data = request.json
    result = bebe.learner.force_learn(
        data.get('source', 'wikipedia'),
        data.get('query', '')
    )
    return jsonify({'message': result})

@app.route('/status', methods=['GET'])
def status():
    return jsonify(bebe.get_status())

@app.route('/switch_model', methods=['POST'])
def switch_model():
    data = request.json
    result = bebe.api.switch_model(data.get('model', Config.FAST_MODEL))
    return jsonify({'message': result})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
