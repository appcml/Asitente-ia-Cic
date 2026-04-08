"""
Memoria de Trabajo para Cic_IA v7.0
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from collections import deque

@dataclass
class ConversationTurn:
    user_message: str
    bot_response: str
    intent: str
    entities: List[str]
    timestamp: datetime
    topic: Optional[str] = None
    satisfaction_score: Optional[float] = None
    
    def to_dict(self):
        return {
            'user': self.user_message[:100],
            'bot': self.bot_response[:100],
            'intent': self.intent,
            'entities': self.entities,
            'timestamp': self.timestamp.isoformat(),
            'topic': self.topic
        }

class WorkingMemory:
    def __init__(self, max_turns: int = 7):
        self.max_turns = max_turns
        self.turns: deque = deque(maxlen=max_turns)
        self.current_topic: Optional[str] = None
        self.topic_history: List[Tuple[str, datetime]] = []
        self.total_turns = 0
        self.satisfaction_history: List[float] = []
        self.session_start = datetime.utcnow()
    
    def add_turn(self, user_message: str, bot_response: str, intent: str,
                entities: List[str] = None, satisfaction: float = None) -> Dict:
        
        entities = entities or []
        
        # Determinar tema
        if entities:
            self.current_topic = max(entities, key=lambda e: len(e))
            self.topic_history.append((self.current_topic, datetime.utcnow()))
            self.topic_history = self.topic_history[-10:]
        
        turn = ConversationTurn(
            user_message=user_message,
            bot_response=bot_response,
            intent=intent,
            entities=entities,
            timestamp=datetime.utcnow(),
            topic=self.current_topic,
            satisfaction_score=satisfaction
        )
        
        self.turns.append(turn)
        self.total_turns += 1
        
        if satisfaction is not None:
            self.satisfaction_history.append(satisfaction)
        
        return self.get_context()
    
    def get_context(self) -> Dict:
        return {
            'current_topic': self.current_topic,
            'recent_turns': [t.to_dict() for t in list(self.turns)[-3:]],
            'conversation_stage': self._determine_stage(),
            'topic_continuity': self._get_topic_continuity(),
            'session_turns': self.total_turns
        }
    
    def should_ask_clarification(self) -> Tuple[bool, Optional[str]]:
        if len(self.turns) < 2:
            return False, None
        
        # Satisfacción decayendo
        if len(self.satisfaction_history) >= 3:
            recent = self.satisfaction_history[-3:]
            if recent[-1] < recent[0] - 0.3:
                return True, "Parece que no estoy entendiendo bien. ¿Podrías reformular?"
        
        # Muchos cambios de tema
        if self._get_topic_continuity() < 0.3:
            return True, "Detecto varios cambios de tema. ¿Podrías enfocarte en uno?"
        
        # Repetición
        if len(self.turns) >= 2:
            last_turns = list(self.turns)[-2:]
            similarity = self._text_similarity(
                last_turns[0].user_message.lower(),
                last_turns[1].user_message.lower()
            )
            if similarity > 0.7:
                return True, "Parece que repites lo mismo. ¿En qué puedo ayudarte exactamente?"
        
        return False, None
    
    def _determine_stage(self) -> str:
        if self.total_turns == 0:
            return 'greeting'
        elif self.total_turns < 3:
            return 'exploration'
        elif self._get_topic_continuity() > 0.7:
            return 'deep_dive'
        else:
            return 'wandering'
    
    def _get_topic_continuity(self) -> float:
        if len(self.topic_history) < 2:
            return 1.0
        
        recent = self.topic_history[-5:]
        changes = sum(1 for i in range(1, len(recent)) if recent[i][0] != recent[i-1][0])
        return 1.0 - (changes / max(len(recent) - 1, 1))
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)
    
    def save_snapshot(self, db_session, conversation_id: int):
        from models import WorkingMemorySnapshot
        
        snapshot = WorkingMemorySnapshot(
            conversation_id=conversation_id,
            turns_json=[t.to_dict() for t in self.turns],
            current_topic=self.current_topic,
            topic_shift_detected=self._get_topic_continuity() < 0.5
        )
        db.session.add(snapshot)
        db.session.commit()
    
    def clear(self):
        self.turns.clear()
        self.current_topic = None
        self.topic_history = []
        self.total_turns = 0
        self.satisfaction_history = []
        self.session_start = datetime.utcnow()
