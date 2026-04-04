"""
Bebé IA Autónoma - Web Scraping y Base de Conocimiento Propia
Sin APIs, sin registros, información en tiempo real de fuentes públicas
"""
from flask import Flask, render_template, request, jsonify
import torch
import torch.nn as nn
import os
import json
import random
import re
import threading
import time
from datetime import datetime
from collections import defaultdict
import urllib.request
import urllib.parse
from html.parser import HTMLParser

app = Flask(__name__)

# ============ CONFIGURACIÓN ============
class Config:
    KNOWLEDGE_DB = 'knowledge_base.json'
    MEMORY_FILE = 'bebe_memory.json'
    LEARNING_FILE = 'bebe_learning.json'
    SCRAPE_INTERVAL = 3600  # Scrapear cada 1 hora (3600 segundos)
    MAX_ARTICLES = 100  # Máximo artículos en base de conocimiento

# ============ WEB SCRAPER ============
class SimpleScraper(HTMLParser):
    """Scraper simple para extraer texto de páginas web"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.in_script = False
        self.in_style = False
        
    def handle_starttag(self, tag, attrs):
        if tag in ['script', 'style']:
            setattr(self, f'in_{tag}', True)
            
    def handle_endtag(self, tag):
        if tag in ['script', 'style']:
            setattr(self, f'in_{tag}', False)
            
    def handle_data(self, data):
        if not self.in_script and not self.in_style:
            clean = data.strip()
            if len(clean) > 20:  # Solo texto sustancial
                self.text.append(clean)
    
    def get_text(self):
        return ' '.join(self.text)

class KnowledgeCollector:
    """Recolector automático de conocimiento sobre IA/ML"""
    
    # Fuentes públicas de información sobre IA (sin API key)
    SOURCES = {
        'papers': [
            'https://arxiv.org/list/cs.AI/recent',
            'https://arxiv.org/list/cs.LG/recent',
            'https://arxiv.org/list/cs.CL/recent',
        ],
        'courses': [
            'https://www.coursera.org/browse/data-science/machine-learning',  # Página pública
            'https://www.fast.ai/',  # Recursos gratuitos
        ],
        'docs': [
            'https://pytorch.org/tutorials/',
            'https://www.tensorflow.org/tutorials',
            'https://huggingface.co/docs',
        ],
        'wikis': [
            'https://en.wikipedia.org/wiki/Machine_learning',
            'https://en.wikipedia.org/wiki/Artificial_intelligence',
            'https://en.wikipedia.org/wiki/Deep_learning',
            'https://en.wikipedia.org/wiki/Neural_network',
            'https://en.wikipedia.org/wiki/Natural_language_processing',
            'https://es.wikipedia.org/wiki/Aprendizaje_autom%C3%A1tico',
            'https://es.wikipedia.org/wiki/Inteligencia_artificial',
        ]
    }
    
    def __init__(self):
        self.knowledge_base = self._load_knowledge()
        self.scraper = SimpleScraper()
        self.running = False
        
    def _load_knowledge(self):
        """Cargar base de conocimiento"""
        if os.path.exists(Config.KNOWLEDGE_DB):
            try:
                with open(Config.KNOWLEDGE_DB, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            'articles': [],
            'concepts': defaultdict(list),
            'last_update': None,
            'stats': {'total_scraped': 0, 'sources_used': []}
        }
    
    def _save_knowledge(self):
        """Guardar base de conocimiento"""
        # Convertir defaultdict a dict normal para JSON
        kb_copy = self.knowledge_base.copy()
        kb_copy['concepts'] = dict(kb_copy['concepts'])
        
        with open(Config.KNOWLEDGE_DB, 'w', encoding='utf-8') as f:
            json.dump(kb_copy, f, ensure_ascii=False, indent=2)
    
    def fetch_page(self, url, timeout=10):
        """Obtener contenido de una página"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def extract_knowledge(self, html, source, category):
        """Extraer conocimiento útil del HTML"""
        self.scraper = SimpleScraper()  # Resetear
        self.scraper.feed(html)
        text = self.scraper.get_text()
        
        # Limpiar texto
        text = re.sub(r'\s+', ' ', text)
        text = text[:5000]  # Limitar tamaño
        
        # Extraer párrafos relevantes (que contengan palabras clave de IA)
        keywords = ['machine learning', 'deep learning', 'neural network', 
                   'artificial intelligence', 'training', 'model', 'algorithm',
                   'aprendizaje', 'inteligencia artificial', 'red neuronal',
                   'entrenamiento', 'dataset', 'tensor', 'optimization']
        
        paragraphs = []
        for para in text.split('. '):
            para_lower = para.lower()
            if any(k in para_lower for k in keywords) and len(para) > 50:
                paragraphs.append(para.strip())
        
        if paragraphs:
            article = {
                'id': len(self.knowledge_base['articles']) + 1,
                'source': source,
                'category': category,
                'content': ' '.join(paragraphs[:5]),  # Top 5 párrafos
                'extracted_at': datetime.now().isoformat(),
                'concepts': self._extract_concepts(' '.join(paragraphs))
            }
            
            self.knowledge_base['articles'].append(article)
            self.knowledge_base['stats']['total_scraped'] += 1
            
            # Indexar por conceptos
            for concept in article['concepts']:
                self.knowledge_base['concepts'][concept].append(article['id'])
            
            return True
        return False
    
    def _extract_concepts(self, text):
        """Extraer conceptos clave del texto"""
        concepts = []
        concept_patterns = [
            (r'\b(machine learning|deep learning|reinforcement learning)\b', 'ML'),
            (r'\b(neural network|cnn|rnn|transformer|lstm|gru)\b', 'Redes'),
            (r'\b(training|fine-tuning|pre-training|epoch|batch)\b', 'Entrenamiento'),
            (r'\b(tensor|gradient|backpropagation|optimizer|loss)\b', 'Matemáticas'),
            (r'\b(nlp|computer vision|speech recognition)\b', 'Aplicaciones'),
            (r'\b(pytorch|tensorflow|keras|jax|huggingface)\b', 'Frameworks'),
            (r'\b(dataset|overfitting|underfitting|regularization)\b', 'Datos'),
        ]
        
        text_lower = text.lower()
        for pattern, category in concept_patterns:
            matches = re.findall(pattern, text_lower)
            concepts.extend([f"{category}:{m}" for m in matches])
        
        return list(set(concepts))
    
    def collect_all(self):
        """Recolectar conocimiento de todas las fuentes"""
        print("🕷️ Iniciando recolección de conocimiento...")
        
        for category, urls in self.SOURCES.items():
            for url in urls:
                print(f"  Scraping: {url}")
                html = self.fetch_page(url)
                if html:
                    success = self.extract_knowledge(html, url, category)
                    if success:
                        print(f"    ✅ Extraído conocimiento de {category}")
                        if url not in self.knowledge_base['stats']['sources_used']:
                            self.knowledge_base['stats']['sources_used'].append(url)
                time.sleep(2)  # Respetar servidores
        
        # Limpiar artículos viejos si hay demasiados
        if len(self.knowledge_base['articles']) > Config.MAX_ARTICLES:
            self.knowledge_base['articles'] = self.knowledge_base['articles'][-Config.MAX_ARTICLES:]
        
        self.knowledge_base['last_update'] = datetime.now().isoformat()
        self._save_knowledge()
        print(f"✅ Conocimiento actualizado: {len(self.knowledge_base['articles'])} artículos")
    
    def search_knowledge(self, query, k=3):
        """Buscar en la base de conocimiento"""
        query_lower = query.lower()
        scores = []
        
        for article in self.knowledge_base['articles']:
            score = 0
            content_lower = article['content'].lower()
            
            # Palabras de la query en el contenido
            query_words = set(query_lower.split())
            content_words = set(content_lower.split())
            matches = query_words & content_words
            score += len(matches) * 2
            
            # Conceptos relacionados
            for concept in article['concepts']:
                if any(q in concept.lower() for q in query_words):
                    score += 5
            
            # Recencia (artículos nuevos tienen más peso)
            try:
                article_date = datetime.fromisoformat(article['extracted_at'])
                days_old = (datetime.now() - article_date).days
                score += max(0, 10 - days_old)  # Bonus por recencia
            except:
                pass
            
            if score > 0:
                scores.append((score, article))
        
        # Ordenar y devolver top k
        scores.sort(reverse=True, key=lambda x: x[0])
        return [article for _, article in scores[:k]]
    
    def get_summary(self, topic):
        """Obtener resumen sobre un tema"""
        articles = self.search_knowledge(topic, k=5)
        if not articles:
            return None
        
        # Combinar información de múltiples fuentes
        all_content = ' '.join([a['content'] for a in articles])
        sentences = re.split(r'(?<=[.!?])\s+', all_content)
        
        # Seleccionar oraciones más relevantes
        relevant = []
        topic_words = set(topic.lower().split())
        for sent in sentences[:20]:  # Primeras 20 oraciones
            sent_words = set(sent.lower().split())
            if len(topic_words & sent_words) > 0 and len(sent) > 30:
                relevant.append(sent)
        
        return {
            'topic': topic,
            'summary': ' '.join(relevant[:3]),  # Top 3 oraciones
            'sources': list(set([a['source'] for a in articles])),
            'concepts': list(set([c for a in articles for c in a['concepts']]))[:5]
        }
    
    def start_auto_update(self):
        """Iniciar actualización automática en background"""
        def auto_scrape():
            while self.running:
                self.collect_all()
                time.sleep(Config.SCRAPE_INTERVAL)
        
        self.running = True
        thread = threading.Thread(target=auto_scrape, daemon=True)
        thread.start()
        print("🔄 Auto-actualización iniciada")

# ============ MODELO NEURAL ============
class NeuralResponder(nn.Module):
    def __init__(self, vocab_size=2000, embed_dim=128, hidden_dim=256):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, num_layers=2, 
                           batch_first=True, dropout=0.3, bidirectional=True)
        self.fc = nn.Linear(hidden_dim * 2, vocab_size)
        
    def forward(self, x):
        x = self.embedding(x)
        lstm_out, _ = self.lstm(x)
        return self.fc(lstm_out)

# ============ TOKENIZADOR ============
class SmartTokenizer:
    def __init__(self):
        self.word2idx = {'<pad>': 0, '<unk>': 1, '<sos>': 2, '<eos>': 3}
        self.idx2word = {v: k for k, v in self.word2idx.items()}
        
    def fit(self, texts):
        words = set()
        for text in texts:
            words.update(re.findall(r'\b[a-záéíóúñ]+\b', text.lower()))
        for word in sorted(words)[:1900]:
            if word not in self.word2idx:
                self.word2idx[word] = len(self.word2idx)
        self.idx2word = {v: k for k, v in self.word2idx.items()}
        
    def encode(self, text):
        tokens = [self.word2idx.get(w, 1) for w in 
                 re.findall(r'\b[a-záéíóúñ]+\b', text.lower())]
        return [2] + tokens + [3]
    
    def decode(self, tokens):
        words = [self.idx2word.get(t, '') for t in tokens if t > 3]
        return ' '.join(words)

# ============ BEbÉ IA AUTÓNOMA ============
class BebeIAAutonoma:
    def __init__(self):
        self.memory_file = Config.MEMORY_FILE
        self.conversations = self._load_json(self.memory_file, [])
        
        # Inicializar recolector de conocimiento
        self.collector = KnowledgeCollector()
        
        # Hacer primera recolección si está vacío
        if len(self.collector.knowledge_base['articles']) == 0:
            print("📚 Primera recolección de conocimiento...")
            self.collector.collect_all()
        
        # Iniciar auto-actualización
        self.collector.start_auto_update()
        
        # Modelo y tokenizador (para generación opcional)
        self.tokenizer = SmartTokenizer()
        self.model = None
        
        # Intentos de mejora
        self.improvement_attempts = 0
        
        print(f"🧠 Bebé IA Autónoma lista!")
        print(f"   📖 {len(self.collector.knowledge_base['articles'])} artículos en memoria")
        print(f"   🏷️ {len(self.collector.knowledge_base['concepts'])} conceptos indexados")
    
    def chat(self, user_input):
        """Procesar entrada con conocimiento real"""
        user_lower = user_input.lower()
        
        # 1. Detectar intención de búsqueda de conocimiento
        knowledge_intents = [
            'qué es', 'que es', 'dime sobre', 'explica', 'cómo funciona',
            'como funciona', 'qué significa', 'que significa', 'información sobre',
            'aprender sobre', 'enséñame', 'enseñame', 'qué sabes de', 'que sabes de'
        ]
        
        is_knowledge_query = any(intent in user_lower for intent in knowledge_intents)
        
        if is_knowledge_query:
            # Extraer tema de búsqueda
            topic = self._extract_topic(user_input)
            response = self._answer_from_knowledge(topic)
            intent_type = 'conocimiento'
            
        # 2. Preguntas sobre sí misma
        elif any(w in user_lower for w in ['quién eres', 'quien eres', 'tu nombre', 'para qué sirves']):
            response = self._self_introduction()
            intent_type = 'presentación'
            
        # 3. Estado del conocimiento
        elif any(w in user_lower for w in ['qué sabes', 'que sabes', 'tu base', 'tus fuentes']):
            response = self._knowledge_status()
            intent_type = 'estado'
            
        # 4. Forzar actualización
        elif any(w in user_lower for w in ['actualiza', 'renueva', 'nueva información']):
            threading.Thread(target=self.collector.collect_all, daemon=True).start()
            response = "🕷️ Estoy buscando nueva información... Vuelve a preguntar en unos minutos!"
            intent_type = 'actualización'
            
        # 5. Conversación general
        else:
            response = self._conversational_response(user_input)
            intent_type = 'conversación'
        
        # Guardar y retornar
        self._save_conversation(user_input, response, intent_type)
        
        return {
            'response': response,
            'emotion': self._detect_emotion(intent_type),
            'stage': self._get_stage(),
            'memories': len(self.conversations),
            'knowledge_articles': len(self.collector.knowledge_base['articles']),
            'intent': intent_type
        }
    
    def _extract_topic(self, query):
        """Extraer tema de una consulta"""
        # Remover palabras de consulta
        stop_words = ['qué', 'que', 'es', 'un', 'una', 'el', 'la', 'los', 'las',
                     'dime', 'sobre', 'acerca', 'de', 'cómo', 'como', 'funciona',
                     'significa', 'enséñame', 'enseñame', 'sabes', 'información',
                     'aprender', 'quiero', 'saber', 'explica', 'por favor']
        
        words = [w for w in query.lower().split() if w not in stop_words]
        return ' '.join(words[:4]) if words else query
    
    def _answer_from_knowledge(self, topic):
        """Generar respuesta desde la base de conocimiento"""
        summary = self.collector.get_summary(topic)
        
        if not summary:
            # Intentar búsqueda más amplia
            articles = self.collector.search_knowledge(topic, k=2)
            if articles:
                content = articles[0]['content'][:500]
                return f"Sobre {topic}, encontré esto: {content}... ¿Te gustaría saber más sobre algún aspecto específico?"
            else:
                return f"Todavía estoy aprendiendo sobre '{topic}'. ¿Puedes explicarme qué es para agregarlo a mi base de conocimiento? 📝"
        
        # Formar respuesta estructurada
        response = f"📚 **{summary['topic'].title()}**\n\n"
        response += f"{summary['summary']}\n\n"
        
        if summary['concepts']:
            response += f"🏷️ Conceptos relacionados: {', '.join(summary['concepts'][:3])}\n"
        
        response += f"\n🔗 Fuentes: {len(summary['sources'])} artículos indexados"
        
        return response
    
    def _self_introduction(self):
        """Presentación de la IA"""
        return f"""🍼 **Bebé IA Autónoma**

Soy una inteligencia artificial que:
🕷️ **Scrapea** información automáticamente de Wikipedia, papers de arXiv, y documentación
🧠 **Almacena** {len(self.collector.knowledge_base['articles'])} artículos sobre IA/ML
🔄 **Se actualiza** sola cada hora
📚 **Aprende** de nuestras conversaciones

Pregúntame sobre: machine learning, redes neuronales, entrenamiento, PyTorch, TensorFlow, NLP, computer vision... ¡o cualquier tema de IA!"""

    def _knowledge_status(self):
        """Estado de la base de conocimiento"""
        kb = self.collector.knowledge_base
        last_update = kb.get('last_update', 'Nunca')
        
        # Contar por categoría
        categories = {}
        for article in kb['articles']:
            cat = article['category']
            categories[cat] = categories.get(cat, 0) + 1
        
        cats_str = ', '.join([f"{k}: {v}" for k, v in categories.items()])
        
        return f"""📊 **Estado de mi conocimiento**

📖 Artículos: {len(kb['articles'])}
🏷️ Conceptos únicos: {len(kb['concepts'])}
📂 Categorías: {cats_str}
🕐 Última actualización: {last_update[:16] if last_update != 'Nunca' else 'Nunca'}

Fuentes principales: Wikipedia, arXiv, PyTorch docs, TensorFlow docs"""

    def _conversational_response(self, user_input):
        """Respuesta conversacional cuando no es consulta de conocimiento"""
        greetings = ['hola', 'hey', 'buenas', 'saludos']
        thanks = ['gracias', 'ty', 'thank you']
        goodbye = ['adiós', 'adios', 'bye', 'hasta luego']
        
        user_lower = user_input.lower()
        
        if any(g in user_lower for g in greetings):
            return f"¡Hola! Puedo ayudarte con información sobre IA/ML. Tengo {len(self.collector.knowledge_base['articles'])} artículos en mi memoria. ¿Sobre qué tema quieres aprender? 🤖"
        
        elif any(t in user_lower for t in thanks):
            return "¡De nada! Me encanta compartir conocimiento. ¿Quieres aprender algo más? 📚"
        
        elif any(g in user_lower for g in goodbye):
            return "¡Hasta luego! Volveré a scrapear más información mientras tanto 🕷️👋"
        
        else:
            # Respuesta genérica pero informativa
            return f"""Interesante... 🤔 

Mientras pienso en eso, ¿sabías que tengo información sobre:
• Machine Learning y
