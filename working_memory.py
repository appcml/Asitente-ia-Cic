# En working_memory.py - MEJORADO

class WorkingMemory:
    def __init__(self, max_turns=15):  # Aumentar de 7 a 15
        self.max_turns = max_turns
        self.turns = deque(maxlen=max_turns)
        self.key_facts = {}  # NUEVO: Hechos importantes mencionados
        self.user_preferences = {}  # NUEVO: Preferencias del usuario
        self.pending_questions = []  # NUEVO: Preguntas sin responder
        
    def extract_key_facts(self, message: str):
        """Extrae hechos clave para recordar (como yo hago)"""
        # Detectar: "me gusta X", "trabajo en Y", "estudio Z"
        patterns = [
            (r'me gusta (\w+)', 'gusto'),
            (r'trabajo (?:en|como) (\w+)', 'trabajo'),
            (r'estudio (\w+)', 'estudio'),
            (r'mi nombre es (\w+)', 'nombre'),
            (r'vivo en (\w+)', 'ubicacion'),
        ]
        
        for pattern, category in patterns:
            match = re.search(pattern, message.lower())
            if match:
                self.key_facts[category] = match.group(1)
                logger.info(f"💡 Hecho guardado: {category} = {match.group(1)}")
    
    def get_context_summary(self) -> str:
        """Genera resumen como yo hago para mantener contexto"""
        parts = []
        
        if self.key_facts.get('nombre'):
            parts.append(f"Usuario: {self.key_facts['nombre']}")
        if self.key_facts.get('gusto'):
            parts.append(f"Le gusta: {self.key_facts['gusto']}")
        
        # Temas recientes
        recent_topics = [t.topic for t in self.turns if t.topic]
        if recent_topics:
            parts.append(f"Temas: {', '.join(set(recent_topics[-3:]))}")
        
        return " | ".join(parts) if parts else "Nueva conversación"
    
    def recall_related(self, current_topic: str) -> str:
        """Recuerda información relacionada (como yo hago conexiones)"""
        related = []
        
        # Buscar en hechos clave relacionados
        for fact_type, value in self.key_facts.items():
            if self._is_related(current_topic, value):
                related.append(f"Anteriormente mencionaste que {fact_type}: {value}")
        
        return "\n".join(related) if related else ""
