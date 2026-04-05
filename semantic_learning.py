"""
Módulo de Análisis Semántico para Cic_IA
Proporciona búsqueda semántica, clustering y análisis de similaridad
"""

import numpy as np
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class SemanticAnalyzer:
    """Analizador semántico para memorias y búsquedas"""
    
    def __init__(self):
        """Inicializar con sentence-transformers"""
        try:
            from sentence_transformers import SentenceTransformer
            # Modelo multilingüe ligero (ideal para producción)
            self.model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
            self.embeddings_cache = {}
            logger.info("✅ Modelo de embeddings cargado")
        except ImportError:
            logger.warning("⚠️ sentence-transformers no instalado, usando fallback TF-IDF")
            self.model = None
            self.embeddings_cache = {}
    
    def get_embedding(self, text: str) -> np.ndarray:
        """Obtener embedding de un texto"""
        if self.model is None:
            return self._tfidf_fallback(text)
        
        # Verificar cache
        if text in self.embeddings_cache:
            return self.embeddings_cache[text]
        
        # Generar embedding
        embedding = self.model.encode(text, convert_to_numpy=True)
        self.embeddings_cache[text] = embedding
        
        return embedding
    
    def _tfidf_fallback(self, text: str) -> np.ndarray:
        """Fallback usando TF-IDF simple"""
        # Implementación básica de TF-IDF
        words = text.lower().split()
        # Crear vector simple basado en palabras
        vector = np.array([len(w) for w in words[:50]])
        # Normalizar
        if len(vector) > 0:
            vector = vector / (np.linalg.norm(vector) + 1e-8)
        return vector
    
    def similarity(self, text1: str, text2: str) -> float:
        """Calcular similaridad coseno entre dos textos"""
        try:
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)
            
            # Similaridad coseno
            similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-8)
            
            return float(similarity)
        except Exception as e:
            logger.error(f"Error calculando similaridad: {e}")
            return 0.0
    
    def find_similar_memories(self, query: str, memories: List[Dict], threshold: float = 0.5) -> List[Tuple[Dict, float]]:
        """Encontrar memorias similares a una query"""
        similar = []
        
        for memory in memories:
            sim_score = self.similarity(query, memory.get('content', ''))
            
            if sim_score >= threshold:
                similar.append((memory, sim_score))
        
        # Ordenar por similaridad descendente
        similar.sort(key=lambda x: x[1], reverse=True)
        
        return similar
    
    def cluster_memories(self, memories: List[Dict], num_clusters: int = 5) -> Dict[int, List[Dict]]:
        """Agrupar memorias por similaridad (clustering K-means simple)"""
        if len(memories) < num_clusters:
            # Si hay menos memorias que clusters, devolver cada una en su cluster
            return {i: [mem] for i, mem in enumerate(memories)}
        
        try:
            from sklearn.cluster import KMeans
            
            # Obtener embeddings de todas las memorias
            embeddings = np.array([
                self.get_embedding(mem.get('content', ''))
                for mem in memories
            ])
            
            # Aplicar K-means
            kmeans = KMeans(n_clusters=num_clusters, random_state=42)
            labels = kmeans.fit_predict(embeddings)
            
            # Agrupar memorias por cluster
            clusters = {}
            for idx, label in enumerate(labels):
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(memories[idx])
            
            return clusters
        except ImportError:
            logger.warning("scikit-learn no instalado, usando clustering simple")
            return self._simple_clustering(memories, num_clusters)
    
    def _simple_clustering(self, memories: List[Dict], num_clusters: int) -> Dict[int, List[Dict]]:
        """Clustering simple sin sklearn"""
        clusters = {i: [] for i in range(num_clusters)}
        
        for idx, memory in enumerate(memories):
            cluster_id = idx % num_clusters
            clusters[cluster_id].append(memory)
        
        return clusters
    
    def extract_keywords(self, text: str, top_n: int = 5) -> List[str]:
        """Extraer palabras clave de un texto"""
        try:
            import spacy
            nlp = spacy.load('es_core_news_sm')
        except:
            # Fallback: usar palabras más largas
            return self._simple_keywords(text, top_n)
        
        doc = nlp(text)
        
        # Extraer sustantivos y adjetivos
        keywords = [
            token.text for token in doc
            if token.pos_ in ['NOUN', 'PROPN', 'ADJ'] and len(token.text) > 3
        ]
        
        # Remover duplicados manteniendo orden
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique_keywords.append(kw)
        
        return unique_keywords[:top_n]
    
    def _simple_keywords(self, text: str, top_n: int) -> List[str]:
        """Extracción simple de palabras clave"""
        words = text.lower().split()
        # Filtrar palabras cortas y comunes
        stopwords = {'el', 'la', 'de', 'que', 'y', 'a', 'en', 'es', 'por', 'para', 'con', 'una', 'un', 'los', 'las'}
        keywords = [w for w in words if len(w) > 3 and w not in stopwords]
        
        # Contar frecuencias
        from collections import Counter
        freq = Counter(keywords)
        
        return [kw for kw, _ in freq.most_common(top_n)]
    
    def summarize_text(self, text: str, num_sentences: int = 3) -> str:
        """Resumir un texto (extracción de oraciones clave)"""
        try:
            import spacy
            nlp = spacy.load('es_core_news_sm')
            doc = nlp(text)
            
            # Obtener oraciones
            sentences = list(doc.sents)
            
            if len(sentences) <= num_sentences:
                return text
            
            # Calcular importancia de cada oración
            sentence_scores = {}
            for sent in sentences:
                for token in sent:
                    if token.has_vector:
                        if sent not in sentence_scores:
                            sentence_scores[sent] = 0
                        sentence_scores[sent] += token.vector_norm
            
            # Seleccionar top N oraciones
            top_sentences = sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True)[:num_sentences]
            top_sentences = sorted(top_sentences, key=lambda x: sentences.index(x[0]))
            
            summary = ' '.join([sent.text for sent, _ in top_sentences])
            return summary
        except:
            # Fallback: devolver primeras N oraciones
            sentences = text.split('.')
            return '. '.join(sentences[:num_sentences]) + '.'
    
    def detect_language(self, text: str) -> str:
        """Detectar idioma de un texto"""
        try:
            from langdetect import detect
            return detect(text)
        except:
            # Fallback: asumir español
            return 'es'
    
    def translate_text(self, text: str, target_lang: str = 'en') -> str:
        """Traducir texto (requiere API externa)"""
        try:
            from google.cloud import translate_v2
            client = translate_v2.Client()
            result = client.translate_text(text, target_language=target_lang)
            return result['translatedText']
        except:
            logger.warning("Traducción no disponible, devolviendo texto original")
            return text


class MemoryOptimizer:
    """Optimizador de memorias para mejor rendimiento"""
    
    def __init__(self, semantic_analyzer: SemanticAnalyzer):
        self.analyzer = semantic_analyzer
    
    def deduplicate_memories(self, memories: List[Dict], threshold: float = 0.85) -> List[Dict]:
        """Eliminar memorias duplicadas o muy similares"""
        unique_memories = []
        
        for memory in memories:
            is_duplicate = False
            
            for unique_mem in unique_memories:
                similarity = self.analyzer.similarity(
                    memory.get('content', ''),
                    unique_mem.get('content', '')
                )
                
                if similarity >= threshold:
                    is_duplicate = True
                    # Actualizar puntuación de relevancia
                    unique_mem['relevance'] = max(
                        unique_mem.get('relevance', 0),
                        memory.get('relevance', 0)
                    )
                    break
            
            if not is_duplicate:
                unique_memories.append(memory)
        
        return unique_memories
    
    def rank_memories(self, query: str, memories: List[Dict]) -> List[Dict]:
        """Rankear memorias por relevancia a una query"""
        ranked = []
        
        for memory in memories:
            similarity = self.analyzer.similarity(query, memory.get('content', ''))
            relevance = memory.get('relevance', 0.5)
            
            # Combinar similaridad y relevancia
            combined_score = (similarity * 0.7) + (relevance * 0.3)
            
            ranked.append({
                **memory,
                'score': combined_score
            })
        
        # Ordenar por puntuación
        ranked.sort(key=lambda x: x['score'], reverse=True)
        
        return ranked
    
    def prune_memories(self, memories: List[Dict], keep_ratio: float = 0.8) -> List[Dict]:
        """Eliminar memorias de baja relevancia"""
        if len(memories) == 0:
            return memories
        
        # Calcular umbral de relevancia
        relevances = [m.get('relevance', 0.5) for m in memories]
        threshold = np.percentile(relevances, (1 - keep_ratio) * 100)
        
        # Mantener solo memorias por encima del umbral
        pruned = [m for m in memories if m.get('relevance', 0.5) >= threshold]
        
        logger.info(f"Memorias podadas: {len(memories)} -> {len(pruned)}")
        
        return pruned


class LearningEngine:
    """Motor de aprendizaje continuo para Cic_IA"""
    
    def __init__(self, semantic_analyzer: SemanticAnalyzer):
        self.analyzer = semantic_analyzer
        self.optimizer = MemoryOptimizer(semantic_analyzer)
        self.learning_history = []
    
    def learn_from_interaction(self, user_input: str, bot_response: str, sources: List[str]) -> Dict:
        """Aprender de una interacción usuario-bot"""
        learning_data = {
            'user_input': user_input,
            'bot_response': bot_response,
            'sources': sources,
            'keywords': self.analyzer.extract_keywords(user_input),
            'timestamp': None
        }
        
        self.learning_history.append(learning_data)
        
        return learning_data
    
    def identify_knowledge_gaps(self, memories: List[Dict], threshold: float = 0.3) -> List[str]:
        """Identificar áreas donde la IA tiene poco conocimiento"""
        # Calcular promedio de relevancia
        if not memories:
            return []
        
        relevances = [m.get('relevance', 0.5) for m in memories]
        avg_relevance = np.mean(relevances)
        
        # Encontrar tópicos con baja relevancia
        gaps = []
        for memory in memories:
            if memory.get('relevance', 0.5) < threshold:
                topic = memory.get('topic', 'unknown')
                if topic not in gaps:
                    gaps.append(topic)
        
        return gaps
    
    def suggest_learning_topics(self, memories: List[Dict], num_suggestions: int = 5) -> List[str]:
        """Sugerir tópicos para aprender"""
        gaps = self.identify_knowledge_gaps(memories)
        
        # Expandir gaps con tópicos relacionados
        suggestions = []
        for gap in gaps[:num_suggestions]:
            suggestions.append(f"Aprender más sobre: {gap}")
        
        return suggestions


# Ejemplo de uso
if __name__ == "__main__":
    # Inicializar analizador
    analyzer = SemanticAnalyzer()
    
    # Textos de ejemplo
    text1 = "Machine learning es una rama de la inteligencia artificial"
    text2 = "El aprendizaje automático es parte de la IA"
    text3 = "Python es un lenguaje de programación"
    
    # Calcular similaridad
    sim1 = analyzer.similarity(text1, text2)
    sim2 = analyzer.similarity(text1, text3)
    
    print(f"Similaridad entre text1 y text2: {sim1:.2f}")
    print(f"Similaridad entre text1 y text3: {sim2:.2f}")
    
    # Extraer palabras clave
    keywords = analyzer.extract_keywords(text1)
    print(f"Palabras clave: {keywords}")
    
    # Resumir texto
    long_text = "Machine learning es una rama de la inteligencia artificial. " \
                "Permite a las máquinas aprender de datos. " \
                "Se utiliza en muchas aplicaciones modernas."
    summary = analyzer.summarize_text(long_text, num_sentences=2)
    print(f"Resumen: {summary}")
