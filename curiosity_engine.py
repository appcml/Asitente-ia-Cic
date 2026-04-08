"""
Motor de Curiosidad Artificial para Cic_IA v7.0
"""

import re
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta

logger = logging.getLogger('cic_curiosity')

class ConceptExtractor:
    PATTERNS = {
        'quoted': r'"([^"]{3,50})"',
        'capitalized': r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b',
        'technical': r'\b([a-z]+_[a-z]+|[a-z]+[A-Z][a-z]+)\b',
    }
    
    STOP_WORDS = {'el', 'la', 'los', 'las', 'un', 'una', 'y', 'o', 'pero', 'de', 'que'}
    
    def extract(self, text: str) -> Set[str]:
        concepts = set()
        
        for pattern_name, pattern in self.PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                clean = match.strip().lower()
                if len(clean) > 2 and clean not in self.STOP_WORDS:
                    concepts.add(clean)
        
        return concepts

class CuriosityEngine:
    def __init__(self, db_session, web_search_engine):
        self.db = db_session
        self.search_engine = web_search_engine
        self.extractor = ConceptExtractor()
        self.MENTION_THRESHOLD = 2
    
    def process_conversation(self, user_message: str, bot_response: str) -> List[Dict]:
        concepts = self.extractor.extract(user_message)
        concepts.update(self.extractor.extract(bot_response))
        
        actions = []
        for concept in concepts:
            action = self._process_concept(concept, user_message)
            if action:
                actions.append(action)
        
        return actions
    
    def _process_concept(self, concept: str, context: str) -> Optional[Dict]:
        from models import CuriosityGap, Memory
        
        existing = self.db.query(Memory).filter(
            Memory.topic.ilike(f'%{concept}%') |
            Memory.content.ilike(f'%{concept}%')
        ).filter(Memory.confidence_score > 0.7).first()
        
        if existing:
            return None
        
        gap = self.db.query(CuriosityGap).filter_by(concept=concept).first()
        
        if gap:
            gap.mention_count += 1
            gap.last_mentioned = datetime.utcnow()
            self.db.commit()
            
            if gap.mention_count >= self.MENTION_THRESHOLD:
                return self._investigate_concept(gap)
            
            return {'action': 'updated_gap', 'concept': concept, 'mentions': gap.mention_count}
        else:
            new_gap = CuriosityGap(
                concept=concept,
                mention_count=1,
                context_examples=[{'text': context[:100], 'timestamp': datetime.utcnow().isoformat()}]
            )
            new_gap.calculate_priority()
            self.db.add(new_gap)
            self.db.commit()
            
            logger.info(f"🤔 Nueva curiosidad: '{concept}'")
            return {'action': 'new_gap', 'concept': concept, 'priority': new_gap.priority}
    
    def _investigate_concept(self, gap) -> Dict:
        from models import Memory, KnowledgeEvolution
        
        gap.status = 'investigating'
        self.db.commit()
        
        logger.info(f"🔍 Investigando: '{gap.concept}'")
        
        try:
            results = self.search_engine.search_duckduckgo(gap.concept, max_results=3)
            
            if not results:
                gap.status = 'failed'
                self.db.commit()
                return {'action': 'failed', 'concept': gap.concept}
            
            for result in results:
                memory = Memory(
                    content=f"{result['title']}\n\n{result['snippet']}\n\nFuente: {result['url']}",
                    source='curiosity',
                    topic=gap.concept,
                    relevance_score=0.7,
                    confidence_score=0.6
                )
                self.db.add(memory)
            
            evolution = KnowledgeEvolution(
                topic=gap.concept,
                action='learned',
                new_content=results[0]['snippet'][:200] if results else '',
                source='curiosity',
                triggered_by='curiosity'
            )
            self.db.add(evolution)
            
            gap.status = 'learned'
            self.db.commit()
            
            logger.info(f"✅ Aprendido por curiosidad: '{gap.concept}'")
            return {'action': 'investigation_complete', 'concept': gap.concept, 'memories': len(results)}
            
        except Exception as e:
            logger.error(f"Error: {e}")
            gap.status = 'failed'
            self.db.commit()
            return {'action': 'error', 'concept': gap.concept, 'error': str(e)}
