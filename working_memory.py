"""
Memoria de Trabajo Mejorada para Cic_IA v7.1 - Estilo Kimi
Mantiene contexto prolongado y extrae hechos clave del usuario
"""

import re
import logging
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger('cic_memory')

@dataclass
class ConversationTurn:
    """Representa un turno de conversación"""
    user_message: str
    bot_response: str
    intent: str
    entities: List[str]
    timestamp: datetime
    topic: Optional[str] = None
    satisfaction_score: Optional[float] = None
    key_facts_extracted: List[str] = field(default_factory=list)
    
    def to_dict(self):
        return {
            'user': self.user_message[:150],
            'bot': self.bot_response[:150],
            'intent': self.intent,
            'entities': self.entities,
            'timestamp': self.timestamp.isoformat(),
            'topic': self.topic,
            'facts': self.key_facts_extracted
        }


class FactExtractor:
    """Extrae hechos importantes de las conversaciones (como Kimi hace)"""
    
    # Patrones para detectar información personal relevante
    PATTERNS = {
        'nombre': [
            r'mi nombre es (\w+)',
            r'me llamo (\w+)',
            r'soy (\w+) (?:y|de|en|trabajo|estudio)',
        ],
        'trabajo': [
            r'trabajo (?:como|de|en) ([\w\s]+?)(?:\s+(?:en|para|desde|hace)|$)',
            r'soy ([\w\s]+?)(?:\s+(?:en|de|trabajando))',
            r'mi trabajo es ([\w\s]+)',
        ],
        'estudio': [
            r'estudio ([\w\s]+?)(?:\s+(?:en|de|para)|$)',
            r'soy estudiante de ([\w\s]+)',
            r'cursando ([\w\s]+)',
        ],
        'gustos': [
            r'me gusta ([\w\s]+?)(?:\s+(?:mucho|bastante|más|menos)|$)',
            r'me encanta ([\w\s]+)',
            r'me apasiona ([\w\s]+)',
            r'mi favorito es ([\w\s]+)',
        ],
        'ubicacion': [
            r'vivo en ([\w\s]+?)(?:\s+(?:con|desde|hace)|$)',
            r'soy de ([\w\s]+)',
            r'estoy en ([\w\s]+)',
        ],
        'necesidades': [
            r'necesito ([\w\s]+?)(?:\s+(?:para|que|urgente)|$)',
            r'quiero ([\w\s]+?)(?:\s+(?:aprender|saber|hacer)|$)',
            r'mi objetivo es ([\w\s]+)',
        ],
        'proyectos': [
            r'estoy (?:haciendo|trabajando en|desarrollando) ([\w\s]+)',
            r'mi proyecto es ([\w\s]+)',
            r'estoy creando ([\w\s]+)',
        ]
    }
    
    def extract(self, message: str) -> Dict[str, str]:
        """Extrae todos los hechos relevantes de un mensaje"""
        facts = {}
        message_lower = message.lower()
        
        for fact_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, message_lower)
                if match:
                    value = match.group(1).strip()
                    # Limpiar valor
                    value = re.sub(r'\s+', ' ', value)
                    if len(value) > 2 and len(value) < 100:
                        facts[fact_type] = value
                        logger.info(f"💡 Hecho extraído: {fact_type} = {value}")
                        break  # Solo el primer match por tipo
        
        return facts
    
    def is_question_about_user(self, message: str, facts: Dict[str, str]) -> Optional[str]:
        """Detecta si el usuario pregunta sobre algo que ya mencionó"""
        message_lower = message.lower()
        
        # Preguntas sobre sí mismo
        if any(x in message_lower for x in ['cómo me llamo', 'como me llamo', 'mi nombre']):
            return facts.get('nombre')
        
        if any(x in message_lower for x in ['en qué trabajo', 'que trabajo', 'mi trabajo']):
            return facts.get('trabajo')
        
        if any(x in message_lower for x in ['qué estudio', 'que estudio', 'mi carrera']):
            return facts.get('estudio')
        
        if any(x in message_lower for x in ['dónde vivo', 'donde vivo', 'de dónde soy']):
            return facts.get('ubicacion')
        
        return None


class WorkingMemory:
    """
    Memoria de trabajo estilo Kimi:
    - 15 turnos de conversación
    - Extracción de hechos clave
    - Recuperación de contexto
    - Detección de preguntas sobre información previa
    """
    
    def __init__(self, max_turns: int = 15):
        self.max_turns = max_turns
        self.turns: deque = deque(maxlen=max_turns)
        self.current_topic: Optional[str] = None
        self.topic_history: List[Tuple[str, datetime]] = []
        
        # NUEVO: Base de conocimiento del usuario (persiste en sesión)
        self.user_profile: Dict[str, str] = {}
        self.fact_extractor = FactExtractor()
        
        # Estado de la conversación
        self.total_turns = 0
        self.satisfaction_history: List[float] = []
        self.session_start = datetime.utcnow()
        self.conversation_goals: List[str] = []  # Qué quiere lograr el usuario
        
        # Metadatos
        self.last_clarification_request: Optional[datetime] = None
        self.repeated_topics: Set[str] = set()
    
    def add_turn(self, user_message: str, bot_response: str, intent: str,
                entities: List[str] = None, satisfaction: float = None) -> Dict:
        """Agrega un turno y extrae información relevante"""
        
        entities = entities or []
        
        # Extraer hechos del mensaje del usuario
        extracted_facts = self.fact_extractor.extract(user_message)
        
        # Actualizar perfil del usuario con nuevos hechos
        for fact_type, value in extracted_facts.items():
            self.user_profile[fact_type] = {
                'value': value,
                'timestamp': datetime.utcnow().isoformat(),
                'turn': self.total_turns
            }
        
        # Detectar si pregunta sobre algo que ya dijo
        recalled_info = self.fact_extractor.is_question_about_user(
            user_message, {k: v['value'] for k, v in self.user_profile.items()}
        )
        
        # Determinar tema actual
        if entities:
            self.current_topic = max(entities, key=len)
            self.topic_history.append((self.current_topic, datetime.utcnow()))
            self.topic_history = self.topic_history[-10:]  # Mantener últimos 10
        
        # Crear turno
        turn = ConversationTurn(
            user_message=user_message,
            bot_response=bot_response,
            intent=intent,
            entities=entities,
            timestamp=datetime.utcnow(),
            topic=self.current_topic,
            satisfaction_score=satisfaction,
            key_facts_extracted=list(extracted_facts.keys())
        )
        
        self.turns.append(turn)
        self.total_turns += 1
        
        if satisfaction is not None:
            self.satisfaction_history.append(satisfaction)
        
        # Detectar objetivos de la conversación
        self._detect_goals(user_message)
        
        return self.get_context(recalled_info=recalled_info)
    
    def _detect_goals(self, message: str):
        """Detecta qué quiere lograr el usuario"""
        goal_patterns = [
            (r'quiero (aprender|saber|hacer|crear|desarrollar)', 'aprendizaje'),
            (r'necesito (resolver|solucionar|arreglar)', 'resolucion_problema'),
            (r'quiero entender|cómo funciona', 'comprension'),
            (r'comparar|diferencia entre|mejor opción', 'comparacion'),
            (r'ejemplo|cómo se hace|pasos para', 'ejemplo_practico'),
        ]
        
        for pattern, goal_type in goal_patterns:
            if re.search(pattern, message.lower()):
                if goal_type not in self.conversation_goals:
                    self.conversation_goals.append(goal_type)
                    logger.info(f"🎯 Objetivo detectado: {goal_type}")
    
    def get_context(self, recalled_info: Optional[str] = None) -> Dict:
        """Obtiene contexto completo para la IA"""
        
        context = {
            'current_topic': self.current_topic,
            'recent_turns': [t.to_dict() for t in list(self.turns)[-5:]],
            'conversation_stage': self._determine_stage(),
            'topic_continuity': self._get_topic_continuity(),
            'session_duration_minutes': (datetime.utcnow() - self.session_start).total_seconds() / 60,
            'total_turns': self.total_turns,
            'user_profile_summary': self._get_profile_summary(),
            'goals': self.conversation_goals[-3:],  # Últimos 3 objetivos
        }
        
        # Si recordamos algo que el usuario olvidó que dijo
        if recalled_info:
            context['recalled_user_info'] = recalled_info
            context['recall_message'] = f"El usuario preguntó sobre algo que ya mencionó: '{recalled_info}'"
        
        return context
    
    def _get_profile_summary(self) -> str:
        """Resume lo que sabemos del usuario"""
        if not self.user_profile:
            return "Nuevo usuario"
        
        parts = []
        priority_facts = ['nombre', 'trabajo', 'estudio', 'ubicacion']
        
        for fact in priority_facts:
            if fact in self.user_profile:
                parts.append(f"{fact}: {self.user_profile[fact]['value']}")
        
        return " | ".join(parts) if parts else "Usuario en conversación"
    
    def get_enhanced_prompt_context(self) -> str:
        """
        Genera contexto enriquecido para prompts (como Kimi usa internamente)
        """
        lines = []
        
        # Perfil del usuario
        if self.user_profile:
            lines.append("## Perfil del usuario")
            for fact_type, data in self.user_profile.items():
                lines.append(f"- {fact_type}: {data['value']}")
            lines.append("")
        
        # Contexto reciente
        lines.append("## Contexto reciente")
        for i, turn in enumerate(list(self.turns)[-3:], 1):
            lines.append(f"{i}. Usuario ({turn.intent}): {turn.user_message[:80]}...")
        lines.append("")
        
        # Tema actual
        if self.current_topic:
            lines.append(f"## Tema actual: {self.current_topic}")
        
        # Objetivos
        if self.conversation_goals:
            lines.append(f"## Objetivos detectados: {', '.join(self.conversation_goals[-2:])}")
        
        return "\n".join(lines)
    
    def should_ask_clarification(self) -> Tuple[bool, Optional[str]]:
        """Decide si necesitamos aclaración, estilo Kimi"""
        
        # No pedir aclaración muy seguido
        if self.last_clarification_request:
            time_since = datetime.utcnow() - self.last_clarification_request
            if time_since < timedelta(minutes=2):
                return False, None
        
        # Casos que requieren aclaración
        
        # 1. Satisfacción decayendo rápido
        if len(self.satisfaction_history) >= 3:
            recent = self.satisfaction_history[-3:]
            if recent[-1] < recent[0] - 0.4:
                self.last_clarification_request = datetime.utcnow()
                return True, "Perdón, parece que no estoy entendiendo bien lo que necesitas. ¿Podrías explicármelo de otra forma? 😊"
        
        # 2. Cambios de tema abruptos (posible confusión)
        if self._get_topic_continuity() < 0.2 and self.total_turns > 5:
            self.last_clarification_request = datetime.utcnow()
            return True, "Noto que hemos cambiado de tema varias veces. ¿Hay algo específico en lo que pueda enfocarme para ayudarte mejor?"
        
        # 3. Repetición del usuario (no entendió respuesta)
        if len(self.turns) >= 2:
            last_msgs = [t.user_message.lower() for t in list(self.turns)[-2:]]
            similarity = self._text_similarity(last_msgs[0], last_msgs[1])
            if similarity > 0.75:
                self.last_clarification_request = datetime.utcnow()
                return True, "Parece que mi respuesta anterior no fue clara. Voy a intentar explicarlo de forma diferente. ¿Qué parte específica te gustaría que profundice?"
        
        # 4. Mensaje muy corto después de respuesta larga
        if self.turns:
            last_turn = self.turns[-1]
            if len(last_turn.bot_response) > 300 and len(last_turn.user_message) < 10:
                self.last_clarification_request = datetime.utcnow()
                return True, "Dime si te gustaría que profundice en algún punto específico de mi explicación anterior."
        
        return False, None
    
    def get_suggested_follow_up(self) -> Optional[str]:
        """Sugiere temas relacionados para continuar la conversación"""
        
        if not self.current_topic:
            return None
        
        # Basado en el tema actual y perfil del usuario
        suggestions = {
            'ia': ['aplicaciones prácticas', 'herramientas para empezar', 'ética en IA'],
            'python': ['proyectos prácticos', 'librerías útiles', 'mejores prácticas'],
            'machine learning': ['datasets públicos', 'cursos recomendados', 'proyectos iniciales'],
        }
        
        for key, options in suggestions.items():
            if key in self.current_topic.lower():
                return f"¿Te interesaría saber más sobre {random.choice(options)}?"
        
        return None
    
    def _determine_stage(self) -> str:
        """Determina etapa de la conversación"""
        if self.total_turns == 0:
            return 'saludo'
        elif self.total_turns < 3:
            return 'exploracion_inicial'
        elif len(self.conversation_goals) > 0:
            return 'trabajando_objetivo'
        elif self._get_topic_continuity() > 0.7:
            return 'profundizando'
        else:
            return 'explorando_temas'
    
    def _get_topic_continuity(self) -> float:
        """Calcula continuidad temática"""
        if len(self.topic_history) < 2:
            return 1.0
        
        recent = self.topic_history[-5:]
        changes = sum(1 for i in range(1, len(recent)) if recent[i][0] != recent[i-1][0])
        return 1.0 - (changes / max(len(recent) - 1, 1))
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Similitud entre dos textos"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)
    
    def save_snapshot(self, db_session, conversation_id: int):
        """Guarda snapshot en base de datos"""
        from models import WorkingMemorySnapshot
        
        snapshot = WorkingMemorySnapshot(
            conversation_id=conversation_id,
            turns_json=[asdict(t) for t in self.turns],
            current_topic=self.current_topic,
            topic_shift_detected=self._get_topic_continuity() < 0.5,
            user_profile_snapshot=self.user_profile
        )
        db_session.add(snapshot)
        db_session.commit()
    
    def clear(self):
        """Limpia memoria (nueva conversación)"""
        self.turns.clear()
        self.current_topic = None
        self.topic_history = []
        # NO limpiar user_profile - queremos recordar al usuario
        self.total_turns = 0
        self.satisfaction_history = []
        self.session_start = datetime.utcnow()
        self.conversation_goals = []
        self.last_clarification_request = None
