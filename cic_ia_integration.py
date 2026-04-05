"""
Módulo de Integración para Cic_IA
Combina búsqueda web, análisis semántico y procesamiento de documentos
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CicIAAdvanced:
    \"\"\"Versión avanzada de Cic_IA con todas las mejoras integradas\"\"\"
    
    def __init__(self, db_session, semantic_analyzer, document_processor):
        \"\"\"
        Inicializar Cic_IA Advanced
        
        Args:
            db_session: Sesión de SQLAlchemy
            semantic_analyzer: Instancia de SemanticAnalyzer
            document_processor: Instancia de DocumentProcessor
        \"\"\"
        self.db = db_session
        self.semantic = semantic_analyzer
        self.doc_processor = document_processor
        self.conversation_context = []
        self.learning_enabled = True
        
        logger.info("🚀 Cic_IA Advanced inicializada")
    
    def process_user_input(self, user_input: str, attachments: Optional[List] = None) -> Dict:
        \"\"\"
        Procesar entrada del usuario con análisis completo
        
        Args:
            user_input: Mensaje del usuario
            attachments: Lista de archivos adjuntos
        
        Returns:
            Respuesta procesada con contexto y fuentes
        \"\"\"
        
        # Paso 1: Procesar adjuntos si existen
        attachment_data = []
        if attachments:
            for attachment in attachments:
                processed = self._process_attachment(attachment)
                if processed['success']:
                    attachment_data.append(processed)
        
        # Paso 2: Extraer palabras clave y contexto
        keywords = self.semantic.extract_keywords(user_input, top_n=5)
        
        # Paso 3: Buscar en memorias locales
        local_results = self._search_local_memory(user_input, keywords)
        
        # Paso 4: Buscar en web si no hay resultados locales
        web_results = []
        if not local_results or len(local_results) < 2:
            web_results = self._search_web(user_input, keywords)
        
        # Paso 5: Combinar resultados
        all_results = local_results + web_results
        
        # Paso 6: Generar respuesta
        response = self._generate_response(
            user_input,
            all_results,
            attachment_data,
            keywords
        )
        
        # Paso 7: Guardar en memoria
        self._save_interaction(user_input, response, all_results)
        
        return response
    
    def _process_attachment(self, attachment: Dict) -> Dict:
        \"\"\"Procesar un archivo adjunto\"\"\"
        try:
            file_path = attachment.get('path')
            
            # Extraer contenido
            result = self.doc_processor.extract_from_file(file_path)
            
            if not result['success']:
                return {'success': False, 'error': result['error']}
            
            # Analizar contenido
            content = result['content']
            summary = self.doc_processor.ContentAnalyzer.extract_summary(content)
            keywords = self.doc_processor.ContentAnalyzer.extract_keywords(content)
            entities = self.doc_processor.ContentAnalyzer.extract_entities(content)
            
            return {
                'success': True,
                'file_path': file_path,
                'file_type': result['source'],
                'content': content[:1000],  # Limitar
                'summary': summary,
                'keywords': keywords,
                'entities': entities,
                'metadata': result['metadata']
            }
        except Exception as e:
            logger.error(f\"Error procesando adjunto: {e}\")
            return {'success': False, 'error': str(e)}
    
    def _search_local_memory(self, query: str, keywords: List[str]) -> List[Dict]:
        \"\"\"Buscar en memorias locales usando análisis semántico\"\"\"
        try:
            from semantic_learning import SemanticAnalyzer
            
            # Obtener todas las memorias
            memories = self._get_all_memories()
            
            if not memories:
                return []
            
            # Buscar por similaridad semántica
            similar = self.semantic.find_similar_memories(query, memories, threshold=0.4)
            
            # Rankear por relevancia
            ranked = self._rank_results(similar, keywords)
            
            return ranked[:5]  # Top 5
        except Exception as e:
            logger.error(f\"Error buscando en memoria local: {e}\")
            return []
    
    def _search_web(self, query: str, keywords: List[str]) -> List[Dict]:
        \"\"\"Buscar en web y aprender automáticamente\"\"\"
        try:
            from cic_ia_mejorado import WebSearchEngine
            
            engine = WebSearchEngine()
            results = engine.search_duckduckgo(query, max_results=3)
            
            # Guardar en memoria
            for result in results:
                self._save_memory(
                    content=result['snippet'],
                    source='web_search',
                    topic=query,
                    relevance=0.7
                )
            
            return results
        except Exception as e:
            logger.error(f\"Error buscando en web: {e}\")
            return []
    
    def _generate_response(self, user_input: str, results: List[Dict], 
                          attachments: List[Dict], keywords: List[str]) -> Dict:
        \"\"\"Generar respuesta contextualizada\"\"\"
        
        response_text = \"\"
        sources = []
        
        # Agregar información de adjuntos
        if attachments:
            response_text += \"**Análisis de documentos adjuntos:**\\n\"
            for att in attachments:
                response_text += f\"- {att['file_type']}: {att['summary']}\\n\"
            response_text += \"\\n\"
            sources.append('attachments')
        
        # Agregar resultados de búsqueda
        if results:
            response_text += \"**Información encontrada:**\\n\"
            for i, result in enumerate(results[:3], 1):
                if isinstance(result, tuple):
                    mem, score = result
                    response_text += f\"{i}. {mem.get('content', '')[:200]}...\\n\"
                else:
                    response_text += f\"{i}. {result.get('snippet', result.get('content', ''))}\\n\"
            
            sources.append('search_results')
        
        # Agregar palabras clave
        if keywords:
            response_text += f\"\\n**Palabras clave:** {', '.join(keywords)}\"
        
        return {
            'response': response_text or \"No encontré información al respecto, pero estoy aprendiendo.\",
            'sources': sources,
            'keywords': keywords,
            'confidence': min(len(results) * 0.2, 1.0),
            'timestamp': datetime.now().isoformat()
        }
    
    def _rank_results(self, results: List[tuple], keywords: List[str]) -> List[Dict]:
        \"\"\"Rankear resultados por relevancia\"\"\"
        ranked = []
        
        for mem, similarity in results:
            # Calcular puntuación combinada
            keyword_match = sum(1 for kw in keywords if kw.lower() in mem.get('content', '').lower())
            combined_score = (similarity * 0.6) + (keyword_match * 0.1) + (mem.get('relevance', 0.5) * 0.3)
            
            ranked.append({
                **mem,
                'score': combined_score
            })
        
        ranked.sort(key=lambda x: x['score'], reverse=True)
        return ranked
    
    def _save_interaction(self, user_input: str, response: Dict, results: List[Dict]):
        \"\"\"Guardar interacción en base de datos\"\"\"
        try:
            # Guardar en tabla de conversaciones
            # (Implementación específica según tu BD)
            logger.info(f\"Interacción guardada: {user_input[:50]}...\")
        except Exception as e:
            logger.error(f\"Error guardando interacción: {e}\")
    
    def _save_memory(self, content: str, source: str, topic: str, relevance: float):
        \"\"\"Guardar información en memoria\"\"\"
        try:
            # Guardar en tabla Memory
            # (Implementación específica según tu BD)
            logger.info(f\"Memoria guardada: {topic}\")
        except Exception as e:
            logger.error(f\"Error guardando memoria: {e}\")
    
    def _get_all_memories(self) -> List[Dict]:
        \"\"\"Obtener todas las memorias\"\"\"
        try:
            # Consultar tabla Memory
            # (Implementación específica según tu BD)
            return []
        except Exception as e:
            logger.error(f\"Error obteniendo memorias: {e}\")
            return []
    
    def enable_continuous_learning(self):
        \"\"\"Habilitar aprendizaje continuo\"\"\"
        self.learning_enabled = True
        logger.info(\"✅ Aprendizaje continuo habilitado\")
    
    def disable_continuous_learning(self):
        \"\"\"Deshabilitar aprendizaje continuo\"\"\"
        self.learning_enabled = False
        logger.info(\"❌ Aprendizaje continuo deshabilitado\")
    
    def get_statistics(self) -> Dict:
        \"\"\"Obtener estadísticas del sistema\"\"\"
        return {
            'learning_enabled': self.learning_enabled,
            'conversation_history': len(self.conversation_context),
            'timestamp': datetime.now().isoformat()
        }


class PerformanceOptimizer:
    \"\"\"Optimizador de rendimiento para Cic_IA\"\"\"
    
    @staticmethod
    def optimize_memory_usage(memories: List[Dict], max_memories: int = 10000) -> List[Dict]:
        \"\"\"Optimizar uso de memoria\"\"\"
        if len(memories) <= max_memories:
            return memories
        
        # Eliminar memorias de baja relevancia
        sorted_mem = sorted(memories, key=lambda x: x.get('relevance', 0.5), reverse=True)
        return sorted_mem[:max_memories]
    
    @staticmethod
    def cache_frequent_queries(query_history: List[str], cache_size: int = 100) -> Dict:
        \"\"\"Cachear consultas frecuentes\"\"\"
        from collections import Counter
        
        query_freq = Counter(query_history)
        cached = {}
        
        for query, count in query_freq.most_common(cache_size):
            if count > 2:  # Solo cachear si se repite más de 2 veces
                cached[query] = {
                    'frequency': count,
                    'cached_at': datetime.now().isoformat()
                }
        
        return cached
    
    @staticmethod
    def profile_performance(start_time: float, end_time: float) -> Dict:
        \"\"\"Perfilar rendimiento de una operación\"\"\"
        duration = end_time - start_time
        
        return {
            'duration_ms': duration * 1000,
            'performance_rating': 'excellent' if duration < 0.1 else 'good' if duration < 0.5 else 'slow'
        }


# Ejemplo de integración en Flask
def create_advanced_cic_ia(app, db):
    \"\"\"Factory function para crear instancia de Cic_IA Advanced\"\"\"
    from semantic_learning import SemanticAnalyzer
    from document_processor import DocumentProcessor
    
    semantic = SemanticAnalyzer()
    doc_proc = DocumentProcessor()
    
    return CicIAAdvanced(db.session, semantic, doc_proc)


if __name__ == \"__main__\":
    # Ejemplo de uso
    print(\"🚀 Cic_IA Advanced - Sistema Integrado\")
    print(\"\\nMódulos disponibles:\")
    print(\"- Búsqueda Web Autónoma\")
    print(\"- Análisis Semántico\")
    print(\"- Procesamiento de Documentos\")
    print(\"- Aprendizaje Continuo\")
    print(\"- Optimización de Rendimiento\")
