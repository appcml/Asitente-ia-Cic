"""
Sistema de Feedback para Cic_IA v7.0
"""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger('cic_feedback')

class SatisfactionDetector:
    POSITIVE_SIGNALS = {
        'strong': [r'gracias', r'perfecto', r'excelente', r'genial', r'exacto', r'👍', r'🙏'],
        'moderate': [r'ok', r'bien', r'vale', r'entendido', r'claro', r'sí', r'ya veo'],
        'weak': [r'ah', r'ya', r'veo']
    }
    
    NEGATIVE_SIGNALS = {
        'strong': [r'no (?:es|fue|está|sirve)', r'está mal', r'incorrecto', r'repitelo', r'\?{2,}'],
        'moderate': [r'no', r'nop', r'confuso', r'perdido'],
        'weak': [r'espera', r'no sé']
    }
    
    def analyze_interaction(self, previous_bot_msg: str, current_user_msg: str, 
                          response_time_seconds: float = 0.0) -> Dict:
        user_msg_lower = current_user_msg.lower().strip()
        score = 0.0
        confidence = 0.5
        reasoning = []
        
        # Análisis de sentimiento
        sentiment_score, sentiment_conf, sentiment_reasons = self._analyze_sentiment(user_msg_lower)
        score += sentiment_score
        confidence += sentiment_conf * 0.3
        reasoning.extend(sentiment_reasons)
        
        # Tiempo de respuesta
        if response_time_seconds > 0:
            if response_time_seconds < 3:
                score += 0.2
                reasoning.append("Respuesta rápida")
            elif response_time_seconds > 30:
                score -= 0.2
                reasoning.append("Respuesta lenta")
        
        # Detección de repetición
        similarity = self._calculate_similarity(user_msg_lower, previous_bot_msg.lower())
        if similarity > 0.6:
            score -= 0.8
            reasoning.append("Repetición detectada")
        
        score = max(-1.0, min(1.0, score))
        confidence = max(0.0, min(1.0, confidence))
        
        category = self._categorize(score, confidence)
        
        return {
            'score': round(score, 3),
            'confidence': round(confidence, 3),
            'category': category,
            'reasoning': reasoning
        }
    
    def _analyze_sentiment(self, text: str) -> Tuple[float, float, List[str]]:
        score = 0.0
        confidence = 0.0
        reasons = []
        
        for pattern in self.POSITIVE_SIGNALS['strong']:
            if re.search(pattern, text):
                score += 0.6
                confidence += 0.3
                reasons.append(f"Positivo fuerte: {pattern}")
        
        for pattern in self.NEGATIVE_SIGNALS['strong']:
            if re.search(pattern, text):
                score -= 0.6
                confidence += 0.3
                reasons.append(f"Negativo fuerte: {pattern}")
        
        return score, min(confidence, 1.0), reasons
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)
    
    def _categorize(self, score: float, confidence: float) -> str:
        if confidence < 0.3:
            return 'uncertain'
        if score >= 0.6:
            return 'very_satisfied'
        elif score >= 0.2:
            return 'satisfied'
        elif score > -0.2:
            return 'neutral'
        elif score > -0.6:
            return 'dissatisfied'
        else:
            return 'very_dissatisfied'


class FeedbackCollector:
    def __init__(self, db_session):
        self.db = db_session
        self.detector = SatisfactionDetector()
    
    def collect_implicit_feedback(self, conversation_id: int, user_message: str, 
                                  bot_message: str, response_time: float = 0.0) -> Dict:
        from models import FeedbackLog
        
        analysis = self.detector.analyze_interaction(bot_message, user_message, response_time)
        
        feedback = FeedbackLog(
            conversation_id=conversation_id,
            feedback_type='implicit',
            score=analysis['score'],
            category=analysis['category'],
            reason='; '.join(analysis['reasoning'])
        )
        
        self.db.add(feedback)
        self.db.commit()
        
        return {
            'feedback_id': feedback.id,
            'analysis': analysis,
            'action_needed': analysis['score'] < -0.3
        }
    
    def get_feedback_for_training(self, min_samples: int = 5, unused_only: bool = True) -> List[Dict]:
        from models import FeedbackLog, Conversation
        
        query = self.db.query(FeedbackLog, Conversation).join(Conversation)
        
        if unused_only:
            query = query.filter(FeedbackLog.used_for_training == False)
        
        results = query.all()
        
        if len(results) < min_samples:
            return []
        
        return [{
            'feedback_id': fb.id,
            'user_message': conv.user_message,
            'intent': conv.intent_detected,
            'score': fb.score,
            'correction': fb.user_correction
        } for fb, conv in results]
    
    def mark_as_used_for_training(self, feedback_ids: List[int]):
        from models import FeedbackLog
        self.db.query(FeedbackLog).filter(FeedbackLog.id.in_(feedback_ids))\
            .update({'used_for_training': True}, synchronize_session=False)
        self.db.commit()
