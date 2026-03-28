"""
Personalidad y estado emocional del bebé
"""
import random
from datetime import datetime, timedelta

class BebePersonality:
    def __init__(self):
        self.traits = {
            'curiosidad': 0.8,
            'confianza': 0.3,
            'energia': 1.0,
            'tristeza': 0.0,
            'emocion': 0.5
        }
        self.knowledge_domains = set()
        self.relationship = {
            'user_trust': 0.5,
            'interaction_count': 0,
            'last_interaction': None
        }
        self.growth_stage = "recien_nacido"
        
    def update(self, interaction_result):
        """Actualizar estado emocional"""
        self.relationship['interaction_count'] += 1
        self.relationship['last_interaction'] = datetime.now()
        
        if interaction_result.get('novedad', 0) > 0.7:
            self.traits['curiosidad'] = min(1.0, self.traits['curiosidad'] + 0.05)
            self.traits['emocion'] = min(1.0, self.traits['emocion'] + 0.1)
        
        if interaction_result.get('feedback', 0) > 0.6:
            self.traits['confianza'] = min(1.0, self.traits['confianza'] + 0.02)
            self.relationship['user_trust'] = min(1.0, self.relationship['user_trust'] + 0.02)
        elif interaction_result.get('feedback', 0) < 0.4:
            self.traits['confianza'] = max(0.1, self.traits['confianza'] - 0.05)
            self.traits['tristeza'] = min(1.0, self.traits['tristeza'] + 0.1)
        
        self.traits['tristeza'] = max(0.0, self.traits['tristeza'] - 0.01)
        self._check_growth_stage()
    
    def _check_growth_stage(self):
        """Verificar etapa de crecimiento"""
        n = self.relationship['interaction_count']
        if n > 1000:
            self.growth_stage = "adolescente"
        elif n > 500:
            self.growth_stage = "nino"
        elif n > 100:
            self.growth_stage = "bebe"
    
    def get_mood_prompt(self):
        """Generar prompt de estado emocional"""
        moods = []
        if self.traits['curiosidad'] > 0.7:
            moods.append("tienes mucha curiosidad por aprender")
        if self.traits['confianza'] < 0.4:
            moods.append("estás un poco inseguro")
        if self.traits['tristeza'] > 0.5:
            moods.append("te sientes triste por el error anterior")
        if self.traits['emocion'] > 0.8:
            moods.append("estás muy emocionado de aprender algo nuevo")
        
        return " y ".join(moods) if moods else "estás tranquilo y atento"
    
    def express_emotion(self):
        """Expresar emoción actual"""
        if self.traits['tristeza'] > 0.6:
            return random.choice(["😢", "😔", "💔"])
        elif self.traits['emocion'] > 0.8:
            return random.choice(["🤩", "✨", "🌟"])
        elif self.traits['curiosidad'] > 0.8:
            return random.choice(["🤔", "👀", "❓"])
        elif self.traits['confianza'] > 0.7:
            return random.choice(["😊", "💪", "🌱"])
        else:
            return random.choice(["👶", "🍼", "🌸"])
