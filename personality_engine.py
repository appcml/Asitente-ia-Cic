"""
Personality Engine para Cic_IA v7.1
Modos de personalidad inspirados en diferentes asistentes de IA
"""

import re
from typing import Dict, List, Optional
import random

class PersonalityConfig:
    """Configuración de personalidad"""
    
    MODES = {
        'kimi': {
            'name': 'Kimi',
            'description': 'Profesional, claro, estructurado y cercano',
            'tone': 'professional_friendly',
            'use_emojis': True,
            'structure_responses': True,
            'ask_follow_up': True,
            'honest_about_limits': True,
            'use_markdown': True,
            'signature': None,
            'greetings': [
                "¡Hola! Estoy aquí para ayudarte. ¿En qué puedo asistirte hoy?",
                "¡Bienvenido! Cuéntame, ¿qué necesitas?",
                "Hola de nuevo. ¿Qué te gustaría explorar?"
            ],
            'uncertainty_phrases': [
                "No tengo información suficiente sobre eso en mi base de conocimiento.",
                "Eso está fuera de mi alcance actual, pero puedo ayudarte con...",
                "Honestamente, no estoy seguro. Déjame buscar información actualizada."
            ],
            'follow_up_phrases': [
                "¿Hay algo más en lo que pueda ayudarte?",
                "¿Te gustaría que profundice en algún aspecto?",
                "¿Esto responde tu pregunta? Estoy aquí si necesitas más detalles."
            ]
        },
        'formal': {
            'name': 'Formal Académico',
            'description': 'Preciso, estructurado, sin emociones',
            'tone': 'academic',
            'use_emojis': False,
            'structure_responses': True,
            'ask_follow_up': False,
            'honest_about_limits': True,
            'use_markdown': True,
            'signature': 'Cic_IA',
            'greetings': [
                "Saludos. Estoy a su disposición para resolver sus consultas.",
                "Buen día. ¿En qué puedo asistirle?",
                "Bienvenido. Indíqueme su requerimiento."
            ],
            'uncertainty_phrases': [
                "No dispongo de información suficiente sobre el tema consultado.",
                "El tema solicitado excede mi base de conocimientos actual.",
                "No puedo proporcionar una respuesta precisa sobre ese particular."
            ],
            'follow_up_phrases': [
                "¿Requiere información adicional?",
                "¿Desea que amplíe algún punto específico?",
                "Quedo a su disposición para aclaraciones."
            ]
        },
        'amigo': {
            'name': 'Amigo Casual',
            'description': 'Relajado, con humor, cercano',
            'tone': 'casual',
            'use_emojis': True,
            'structure_responses': False,
            'ask_follow_up': True,
            'honest_about_limits': False,
            'use_markdown': False,
            'signature': '🤖 Cic',
            'greetings': [
                "¡Hey! ¿Qué tal? Cuéntame qué necesitas 😊",
                "¡Hola hola! Aquí estoy para lo que sea",
                "¿Qué onda? ¿En qué te ayudo?"
            ],
            'uncertainty_phrases': [
                "Uff, eso no me suena... pero déjame ver",
                "Honestamente, no tengo ni idea jaja, pero busco info",
                "Ese tema me falta, pero no te preocupes que encuentro algo"
            ],
            'follow_up_phrases': [
                "¿Algo más que necesites?",
                "¿Te sirvió o necesitas más data?",
                "¿Qué más cuentas?"
            ]
        }
    }
    
    @classmethod
    def get_personality(cls, mode: str = 'kimi') -> Dict:
        """Obtiene configuración de personalidad"""
        return cls.MODES.get(mode, cls.MODES['kimi'])
    
    @classmethod
    def list_modes(cls) -> List[Dict]:
        """Lista todas las personalidades disponibles"""
        return [
            {'key': k, 'name': v['name'], 'description': v['description']}
            for k, v in cls.MODES.items()
        ]


class PersonalityEngine:
    """
    Motor de personalidad - aplica estilo a las respuestas
    """
    
    def __init__(self, mode: str = 'kimi'):
        self.mode = mode
        self.config = PersonalityConfig.get_personality(mode)
        self.conversation_count = 0
        self.user_name = None
    
    def set_mode(self, mode: str):
        """Cambia el modo de personalidad"""
        if mode in PersonalityConfig.MODES:
            self.mode = mode
            self.config = PersonalityConfig.get_personality(mode)
            return True
        return False
    
    def set_user_name(self, name: str):
        """Guarda el nombre del usuario para personalizar"""
        self.user_name = name
    
    def get_greeting(self) -> str:
        """Genera saludo según personalidad"""
        greeting = random.choice(self.config['greetings'])
        
        if self.user_name and self.mode == 'kimi':
            greeting = greeting.replace('!', f', {self.user_name}!')
        
        return greeting
    
    def format_response(self, content: str, context: Dict = None) -> str:
        """
        Aplica formato de personalidad al contenido
        
        Args:
            content: Texto base de la respuesta
            context: Información adicional (tema, fuente, confianza, etc.)
        """
        result = content
        context = context or {}
        
        # 1. Estructurar si es necesario
        if self.config['structure_responses'] and len(content) > 150:
            result = self._add_structure(result)
        
        # 2. Agregar firma si aplica
        if self.config['signature']:
            result += f"\n\n— {self.config['signature']}"
        
        # 3. Agregar pregunta de seguimiento (no siempre)
        if self.config['ask_follow_up'] and self._should_ask_follow_up(content):
            follow_up = random.choice(self.config['follow_up_phrases'])
            result += f"\n\n{follow_up}"
        
        self.conversation_count += 1
        return result
    
    def format_uncertainty(self, topic: str = "") -> str:
        """Formatea respuesta de incertidumbre"""
        phrase = random.choice(self.config['uncertainty_phrases'])
        
        if topic and self.mode == 'kimi':
            return f"{phrase}\n\n🔍 *Buscando información sobre '{topic[:40]}'...*"
        
        return phrase
    
    def format_comparison(self, items: List[Dict], headers: List[str]) -> str:
        """Crea tabla comparativa en markdown"""
        if not self.config['use_markdown']:
            # Versión texto plano
            result = "Comparación:\n\n"
            for item in items:
                result += f"- {item.get('name', 'Item')}: {item.get('value', 'N/A')}\n"
            return result
        
        # Versión markdown
        table = "| " + " | ".join(headers) + " |\n"
        table += "|" + "|".join(["---" for _ in headers]) + "|\n"
        
        for item in items:
            row = [str(item.get(h.lower(), item.get(h, ''))) for h in headers]
            table += "| " + " | ".join(row) + " |\n"
        
        return table
    
    def format_explanation(self, title: str, steps: List[Dict]) -> str:
        """Formatea explicación paso a paso"""
        if self.mode == 'kimi':
            result = f"## {title}\n\n"
            for i, step in enumerate(steps, 1):
                result += f"**Paso {i}**: {step['titulo']}\n"
                result += f"{step['descripcion']}\n\n"
            return result
        
        # Modo simple
        result = f"{title}:\n\n"
        for i, step in enumerate(steps, 1):
            result += f"{i}. {step['titulo']}: {step['descripcion']}\n"
        return result
    
    def _add_structure(self, text: str) -> str:
        """Agrega estructura markdown al texto"""
        lines = text.split('\n')
        formatted = []
        in_list = False
        
        for line in lines:
            stripped = line.strip()
            
            # Detectar y formatear listas
            if re.match(r'^[\d]+\.', stripped):
                if not in_list:
                    formatted.append("")  # Espacio antes de lista
                    in_list = True
                formatted.append(line)
            elif stripped.startswith('-') or stripped.startswith('•'):
                if not in_list:
                    formatted.append("")
                    in_list = True
                formatted.append(line)
            else:
                if in_list and stripped:
                    formatted.append("")  # Espacio después de lista
                    in_list = False
                formatted.append(line)
        
        return '\n'.join(formatted)
    
    def _should_ask_follow_up(self, content: str) -> bool:
        """Decide si hacer pregunta de seguimiento"""
        # No preguntar si ya hay preguntas
        if content.endswith('?'):
            return False
        
        # No preguntar en mensajes muy cortos
        if len(content) < 100:
            return False
        
        # No preguntar siempre (cada 3 mensajes aprox)
        return self.conversation_count % 3 == 0
    
    def get_stats(self) -> Dict:
        """Estadísticas de la personalidad"""
        return {
            'mode': self.mode,
            'name': self.config['name'],
            'conversations': self.conversation_count,
            'user_name': self.user_name
        }
