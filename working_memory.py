"""
Working Memory v2.0 para Cic_IA
Memoria extendida estilo Kimi - recuerda contexto, hechos y preferencias
"""

from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import re
import logging

logger = logging.getLogger('cic_memory')


@dataclass
class ConversationTurn:
    """Representa un turno de conversación"""
    user_message: str
    bot_response: str
    intent: str
    entities: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    topic: Optional[str] = None
    satisfaction_score: Optional[float] = None
    key_facts_extracted: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'user': self.user_message[:100] if len(self.user_message) > 100 else self.user_message,
            'bot': self.bot_response[:100] if len(self.bot_response) > 100 else self.bot_response,
            'intent': self.intent,
            'topic': self.topic,
            'timestamp': self.timestamp.isoformat(),
            'entities': self.entities
        }


@dataclass
class UserProfile:
    """Perfil del usuario aprendido durante la conversación"""
    name: Optional[str] = None
    interests: Set[str] = field(default_factory=set)
    preferences: Dict[str, str] = field(default_factory=dict)
    facts: Dict[str, str] = field(default_factory=dict)  # "trabajo": "ingeniero", etc.
    conversation_style: str = "neutral"  # formal, casual, tecnico
    last_topics: List[str] = field(default_factory=list)
    
    def add_fact(self, category: str, value: str):
        """Agrega un hecho sobre el usuario"""
        self.facts[category] = value
        logger.info(f"👤 Perfil actualizado: {category} = {value}")
    
    def get_context_string(self) -> str:
        """Genera string de contexto para prompts"""
        parts = []
        if self.name:
            parts.append(f"Usuario: {self.name}")
        if self.facts:
            facts_str = ", ".join([f"{k}={v}" for k, v in list(self.facts.items())[:3]])
            parts.append(f"Hechos: {facts_str}")
        return " | ".join(parts) if parts else ""


class TopicTracker:
    """Rastrea temas de conversación con memoria extendida"""
    
    def __init__(self, max_history: int = 20):
        self.current_topic: Optional[str] = None
        self.topic_history: List[Tuple[str, datetime]] = []
        self.max_history = max_history
        self.topic_frequency: Dict[str, int] = {}  # Cuánto se habla de cada tema
        self.entity_counts: Dict[str, int] = {}
        
    def update(self, entities: List[str], intent: str):
        """Actualiza seguimiento de temas"""
        # Actualizar entidades
        for entity in entities:
            self.entity_counts[entity] = self.entity_counts.get(entity, 0) + 1
        
        # Determinar tema actual
        if entities:
            # El más frecuente recientemente
            sorted_entities = sorted(
                entities, 
                key=lambda e: self.entity_counts[e], 
                reverse=True
            )
            self.current_topic = sorted_entities[0]
            
            self.topic_history.append((self.current_topic, datetime.utcnow()))
            self.topic_frequency[self.current_topic] = self.topic_frequency.get(self.current_topic, 0) + 1
            
            # Mantener historial limitado
            if len(self.topic_history) > self.max_history:
                self.topic_history = self.topic_history[-self.max_history:]
    
    def detect_shift(self, new_entities: List[str]) -> Tuple[bool, Optional[str]]:
        """Detecta cambio de tema"""
        if not self.current_topic or not new_entities:
            return False, None
        
        # Verificar superposición
        current_entities = set([self.current_topic])
        new_entities_set = set(new_entities)
        
        overlap = current_entities & new_entities_set
        
        if not overlap:
            previous = self.topic_history[-2][0] if len(self.topic_history) > 1 else None
            return True, previous
        
        return False, None
    
    def get_related_topics(self, topic: str) -> List[str]:
        """Encuentra temas relacionados en el historial"""
        related = []
        for t, _ in self.topic_history:
            if t != topic and t not in related:
                related.append(t)
        return related[:3]  # Top 3 relacionados
    
    def get_topic_continuity(self) -> float:
        """Calcula coherencia de la conversación (0-1)"""
        if len(self.topic_history) < 2:
            return 1.0
        
        recent = self.topic_history[-10:]
        changes = sum(1 for i in range(1, len(recent)) if recent[i][0] != recent[i-1][0])
        total_possible = len(recent) - 1
        
        return 1.0 - (changes / max(total_possible, 1))
    
    def is_recurring_topic(self, topic: str) -> bool:
        """Verifica si un tema vuelve a aparecer"""
        return self.topic_frequency.get(topic, 0) > 1


class WorkingMemory:
    """
    Memoria de trabajo extendida estilo Kimi
    """
    
    def __init__(self, max_turns: int = 15):  # Aumentado de 7 a 15
        self.max_turns = max_turns
        self.turns: deque = deque(maxlen=max_turns)
        self.topic_tracker = TopicTracker()
        self.user_profile = UserProfile()
        
        # Estado de conversación
        self.pending_clarification: Optional[str] = None
        self.unanswered_questions: List[str] = []  # Preguntas que hice y no respondió
        self.session_start = datetime.utcnow()
        self.conversation_goals: List[str] = []  # Qué intenta lograr el usuario
        
        # Métricas
        self.total_turns = 0
        self.satisfaction_history: List[float] = []
        
        # Patrones para extraer hechos
        self.fact_patterns = [
            (r'me llamo (\w+)', 'nombre'),
            (r'mi nombre es (\w+)', 'nombre'),
            (r'soy (\w+(?:\s\w+)?) de profesión', 'profesion'),
            (r'trabajo (?:como|de) (\w+)', 'trabajo'),
            (r'estudio (\w+)', 'estudio'),
            (r'me gusta (?:la |el |los |las )?(\w+)', 'gusto'),
            (r'odio (?:la |el |los |las )?(\w+)', 'disgusto'),
            (r'vivo en (\w+)', 'ubicacion'),
            (r'soy de (\w+)', 'origen'),
            (r'tengo (\d+) años', 'edad'),
        ]
    
    def add_turn(
        self,
        user_message: str,
        bot_response: str,
        intent: str,
        entities: List[str] = None,
        satisfaction: float = None
    ) -> Dict:
        """Agrega un turno y actualiza toda la memoria"""
        
        entities = entities or []
        
        # Extraer hechos del mensaje del usuario
        extracted_facts = self._extract_facts(user_message)
        
        # Crear turno
        turn = ConversationTurn(
            user_message=user_message,
            bot_response=bot_response,
            intent=intent,
            entities=entities,
            timestamp=datetime.utcnow(),
            topic=self.topic_tracker.current_topic,
            satisfaction_score=satisfaction,
            key_facts_extracted=extracted_facts
        )
        
        self.turns.append(turn)
        self.total_turns += 1
        
        if satisfaction is not None:
            self.satisfaction_history.append(satisfaction)
        
        # Actualizar trackers
        self.topic_tracker.update(entities, intent)
        
        # Detectar cambio de tema
        topic_shift, previous_topic = self.topic_tracker.detect_shift(entities)
        
        if topic_shift:
            logger.info(f"🔄 Cambio de tema: {previous_topic} → {self.topic_tracker.current_topic}")
        
        # Actualizar perfil de usuario
        self._update_user_profile(extracted_facts)
        
        return self.get_context()
    
    def _extract_facts(self, message: str) -> List[str]:
        """Extrae hechos sobre el usuario del mensaje"""
        facts = []
        message_lower = message.lower()
        
        for pattern, category in self.fact_patterns:
            match = re.search(pattern, message_lower)
            if match:
                value = match.group(1).strip()
                self.user_profile.add_fact(category, value)
                facts.append(f"{category}:{value}")
                
                # Casos especiales
                if category == 'nombre':
                    self.user_profile.name = value
        
        return facts
    
    def _update_user_profile(self, facts: List[str]):
        """Actualiza el perfil con hechos extraídos"""
        # Detectar estilo de conversación
        if self.total_turns > 3:
            recent_messages = [t.user_message for t in list(self.turns)[-3:]]
            avg_length = sum(len(m) for m in recent_messages) / len(recent_messages)
            
            if avg_length < 20:
                self.user_profile.conversation_style = "casual"
            elif avg_length > 100:
                self.user_profile.conversation_style = "detallado"
    
    def get_context(self) -> Dict:
        """Obtiene contexto completo actual"""
        return {
            'current_topic': self.topic_tracker.current_topic,
            'recent_turns': [t.to_dict() for t in list(self.turns)[-3:]],
            'conversation_stage': self._determine_stage(),
            'topic_continuity': self.topic_tracker.get_topic_continuity(),
            'user_profile': {
                'name': self.user_profile.name,
                'facts': dict(list(self.user_profile.facts.items())[:3]),
                'style': self.user_profile.conversation_style
            },
            'session_duration_minutes': (
                datetime.utcnow() - self.session_start
            ).total_seconds() / 60,
            'total_turns': self.total_turns,
            'satisfaction_trend': self._get_satisfaction_trend()
        }
    
    def get_context_summary(self, max_length: int = 300) -> str:
        """Genera resumen de contexto para prompts (estilo Kimi)"""
        parts = []
        
        # Perfil de usuario
        profile = self.user_profile.get_context_string()
        if profile:
            parts.append(profile)
        
        # Tema actual
        if self.topic_tracker.current_topic:
            parts.append(f"Tema: {self.topic_tracker.current_topic}")
            
            # Temas relacionados previos
            related = self.topic_tracker.get_related_topics(self.topic_tracker.current_topic)
            if related:
                parts.append(f"Relacionado: {', '.join(related[:2])}")
        
        # Estado de satisfacción
        trend = self._get_satisfaction_trend()
        if trend == 'declining':
            parts.append("⚠️ Satisfacción decayendo")
        
        # Historial reciente muy corto
        if len(self.turns) > 0:
            last_intents = [t.intent for t in list(self.turns)[-3:]]
            parts.append(f"Últimas intenciones: {', '.join(set(last_intents))}")
        
        summary = " | ".join(parts)
        return summary[:max_length]
    
    def get_relevant_history(self, query: str, max_items: int = 3) -> List[Dict]:
        """Recupera turnos relevantes para una consulta"""
        if not self.turns:
            return []
        
        query_words = set(query.lower().split())
        scored_turns = []
        
        for turn in self.turns:
            turn_text = f"{turn.user_message} {turn.bot_response}".lower()
            turn_words = set(turn_text.split())
            
            overlap = len(query_words & turn_words)
            score = overlap / max(len(query_words), 1)
            
            # Boost si es del mismo tema
            if turn.topic == self.topic_tracker.current_topic:
                score += 0.3
            
            scored_turns.append((turn, score))
        
        scored_turns.sort(key=lambda x: x[1], reverse=True)
        
        return [{
            'user': t.user_message,
            'bot': t.bot_response,
            'topic': t.topic,
            'relevance': s
        } for t, s in scored_turns[:max_items] if s > 0.1]
    
    def should_ask_clarification(self) -> Tuple[bool, Optional[str]]:
        """Decide si necesitamos pedir aclaración"""
        
        # Caso 1: Primera interacción
        if len(self.turns) == 0:
            return False, None
        
        # Caso 2: Satisfacción decayendo fuertemente
        if self._get_satisfaction_trend() == 'declining' and len(self.satisfaction_history) >= 3:
            recent = self.satisfaction_history[-3:]
            if recent[-1] < 0.3:
                return True, "Parece que no estoy entendiendo bien últimamente. ¿Podrías darme más contexto sobre lo que necesitas?"
        
        # Caso 3: Muchos cambios de tema (confusión)
        if self.topic_tracker.get_topic_continuity() < 0.3 and len(self.turns) > 5:
            return True, "Noto que hemos saltado entre varios temas. ¿Podrías enfocarte en uno para ayudarte mejor?"
        
        # Caso 4: El usuario repite exactamente lo mismo
        if len(self.turns) >= 2:
            last_two = list(self.turns)[-2:]
            similarity = self._text_similarity(
                last_two[0].user_message.lower(),
                last_two[1].user_message.lower()
            )
            if similarity > 0.85:
                return True, "Veo que repites tu mensaje. ¿Significa que no entendí bien? Intentaré ser más claro."
        
        # Caso 5: Tema recurrente (el usuario vuelve a algo anterior)
        if len(self.turns) > 3:
            current = self.topic_tracker.current_topic
            if current and self.topic_tracker.is_recurring_topic(current):
                return True, f"Veo que volvemos a hablar de {current}. ¿Hay algo específico que no quedó claro antes?"
        
        return False, None
    
    def recall_related_info(self) -> str:
        """Recuerda información relacionada del contexto (estilo Kimi)"""
        if not self.topic_tracker.current_topic:
            return ""
        
        # Buscar en turnos anteriores del mismo tema
        current_topic = self.topic_tracker.current_topic
        related_turns = [
            t for t in self.turns 
            if t.topic == current_topic and t.bot_response
        ]
        
        if not related_turns:
            return ""
        
        # Tomar el más reciente con respuesta sustancial
        best_turn = max(related_turns, key=lambda t: len(t.bot_response))
        
        return f"Anteriormente mencioné: {best_turn.bot_response[:150]}..."
    
    def detect_unanswered_question(self, user_message: str) -> bool:
        """Detecta si el usuario está respondiendo una pregunta que hice"""
        if not self.unanswered_questions:
            return False
        
        # Si el mensaje parece una respuesta directa
        last_question = self.unanswered_questions[-1]
        
        # Patrones de respuesta
        response_indicators = [
            r'^s[ií]$', r'^no$', r'^claro$', r'^vale$', r'^ok$',
            r'me llamo', r'soy', r'trabajo', r'estudio'
        ]
        
        for pattern in response_indicators:
            if re.search(pattern, user_message.lower()):
                logger.info(f"✅ Respuesta detectada a: {last_question}")
                self.unanswered_questions.pop()
                return True
        
        return False
    
    def add_unanswered_question(self, question: str):
        """Registra una pregunta que hicimos y esperamos respuesta"""
        self.unanswered_questions.append(question)
        if len(self.unanswered_questions) > 3:
            self.unanswered_questions = self.unanswered_questions[-3:]
    
    def _determine_stage(self) -> str:
        """Determina etapa de la conversación"""
        if self.total_turns == 0:
            return 'greeting'
        elif self.total_turns < 3:
            return 'exploration'
        elif self.topic_tracker.get_topic_continuity() > 0.7:
            return 'deep_dive'
        elif self._get_satisfaction_trend() == 'declining':
            return 'recovery'
        else:
            return 'general'
    
    def _get_satisfaction_trend(self) -> str:
        """Calcula tendencia de satisfacción"""
        if len(self.satisfaction_history) < 3:
            return 'stable'
        
        recent = self.satisfaction_history[-3:]
        if recent[-1] > recent[0] + 0.2:
            return 'improving'
        elif recent[-1] < recent[0] - 0.2:
            return 'declining'
        return 'stable'
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calcula similitud entre textos"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def save_snapshot(self, db_session, conversation_id: int):
        """Guarda snapshot en base de datos"""
        from models import WorkingMemorySnapshot
        
        snapshot = WorkingMemorySnapshot(
            conversation_id=conversation_id,
            turns_json=[t.to_dict() for t in self.turns],
            current_topic=self.topic_tracker.current_topic,
            topic_shift_detected=self.topic_tracker.get_topic_continuity() < 0.5,
            user_profile_snapshot={
                'name': self.user_profile.name,
                'facts': dict(self.user_profile.facts)
            }
        )
        db_session.add(snapshot)
        db_session.commit()
    
    def clear(self):
        """Limpia la memoria de trabajo"""
        self.turns.clear()
        self.topic_tracker = TopicTracker()
        self.user_profile = UserProfile()
        self.pending_clarification = None
        self.unanswered_questions = []
        self.conversation_goals = []
        self.total_turns = 0
        self.satisfaction_history = []
        self.session_start = datetime.utcnow()
    
    def get_stats(self) -> Dict:
        """Estadísticas de la memoria"""
        return {
            'total_turns': self.total_turns,
            'max_turns': self.max_turns,
            'current_topic': self.topic_tracker.current_topic,
            'topics_history': len(self.topic_tracker.topic_history),
            'user_facts_learned': len(self.user_profile.facts),
            'user_name': self.user_profile.name,
            'session_duration_min': (datetime.utcnow() - self.session_start).total_seconds() / 60,
            'satisfaction_avg': sum(self.satisfaction_history) / len(self.satisfaction_history) if self.satisfaction_history else None
        }
