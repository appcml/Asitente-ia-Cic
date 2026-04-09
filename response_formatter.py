"""
ResponseFormatter - Formatea respuestas al estilo Kimi
"""

import re
import random
from typing import List, Dict, Optional


class ResponseFormatter:
    """
    Da formato a las respuestas como lo haría Kimi:
    - Estructura clara con markdown
    - Ejemplos prácticos
    - Honestidad sobre limitaciones
    - Tono profesional pero cercano
    """
    
    # Frases de transición estilo Kimi
    TRANSITIONS = {
        'explicacion': [
            "Entiendo tu pregunta. Déjame explicarte:",
            "Buena pregunta. Aquí te lo aclaro:",
            "Veo que te interesa este tema. Te explico:",
        ],
        'ejemplo': [
            "Para que quede más claro, imagina esto:",
            "Un ejemplo práctico sería:",
            "Pongámoslo en contexto:",
        ],
        'honestidad': [
            "Voy a ser honesto contigo:",
            "Para no confundirte, debo aclarar:",
            "Es importante que sepas:",
        ],
        'profundizar': [
            "¿Te gustaría que profundice en algún aspecto específico?",
            "¿Hay algo de lo que te gustaría saber más?",
            "¿Esto responde tu pregunta o necesitas más detalles?",
        ],
        'no_se': [
            "No tengo información suficiente sobre eso en mi base de conocimiento.",
            "Específicamente sobre ese punto, no tengo datos confirmados.",
            "Prefiero ser honesto: no tengo información precisa sobre eso.",
        ]
    }
    
    def __init__(self, mode='kimi'):
        self.mode = mode
    
    def format(self, content: str, context: Dict = None, 
               topic: str = None, confidence: float = 1.0) -> str:
        """
        Formatea una respuesta completa
        """
        if confidence < 0.3:
            return self._format_uncertain(content, topic)
        
        parts = []
        
        # 1. Transición inicial (si es inicio de tema)
        if context and context.get('conversation_stage') in ['exploracion_inicial', 'saludo']:
            parts.append(random.choice(self.TRANSITIONS['explicacion']))
        
        # 2. Contenido principal estructurado
        structured_content = self._structure_content(content)
        parts.append(structured_content)
        
        # 3. Ejemplo práctico (si el contenido es explicativo)
        if len(content) > 150 and self._needs_example(content):
            parts.append(f"\n**💡 {random.choice(self.TRANSITIONS['ejemplo'])}**")
            parts.append(self._generate_example(topic, content))
        
        # 4. Pregunta de seguimiento
        if context and len(self.TRANSITIONS['profundizar']) > 0:
            parts.append(f"\n\n{random.choice(self.TRANSITIONS['profundizar'])} 😊")
        
        return "\n\n".join(parts)
    
    def _structure_content(self, content: str) -> str:
        """Estructura el contenido con markdown"""
        
        # Si ya tiene estructura, respetarla
        if '##' in content or '**' in content:
            return content
        
        # Dividir en párrafos y estructurar
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        if len(paragraphs) == 1:
            return paragraphs[0]
        
        # Múltiples párrafos: estructurar con encabezados si es largo
        structured = []
        
        for i, para in enumerate(paragraphs):
            if i == 0:
                # Primer párrafo: introducción
                structured.append(para)
            elif len(para) > 100:
                # Párrafos largos: ver si tienen punto clave
                key_point = self._extract_key_point(para)
                if key_point:
                    structured.append(f"\n**{key_point}**\n\n{para}")
                else:
                    structured.append(para)
            else:
                structured.append(para)
        
        return "\n\n".join(structured)
    
    def _extract_key_point(self, paragraph: str) -> Optional[str]:
        """Extrae el punto clave de un párrafo"""
        # Buscar frases como "Lo importante es...", "La clave está en..."
        patterns = [
            r'(?:lo importante|la clave|el punto clave) es (que )?([^\.]+)',
            r'(?:en resumen|básicamente)([^\.]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, paragraph.lower())
            if match:
                return match.group(2).strip().capitalize()
        
        # Si no hay patrón, usar primera oración si es corta
        first_sentence = paragraph.split('.')[0]
        if 10 < len(first_sentence) < 60:
            return first_sentence
        
        return None
    
    def _needs_example(self, content: str) -> bool:
        """Determina si el contenido necesita un ejemplo"""
        # Conceptos abstractos suelen necesitar ejemplos
        abstract_terms = ['concepto', 'teoría', 'método', 'sistema', 'proceso', 'algoritmo']
        return any(term in content.lower() for term in abstract_terms)
    
    def _generate_example(self, topic: str, content: str) -> str:
        """Genera un ejemplo relacionado"""
        # Plantillas de ejemplos por tema
        examples = {
            'ia': "Imagina que le pides a una IA que reconozca gatos en fotos. No le dices 'busca orejas puntiagudas', sino que le muestras miles de fotos etiquetadas y ella misma descubre los patrones.",
            'python': "Es como aprender a cocinar siguiendo recetas. Al principio sigues paso a paso, pero con práctica puedes improvisar y crear tus propios platos.",
            'default': "Piensa en aprender a andar en bicicleta. No es solo saber la teoría, sino practicar hasta que el equilibrio se vuelva natural."
        }
        
        # Buscar ejemplo relevante
        for key, example in examples.items():
            if key in (topic or '').lower() or key in content.lower():
                return example
        
        return examples['default']
    
    def _format_uncertain(self, content: str, topic: str) -> str:
        """Formatea cuando no estamos seguros"""
        parts = [
            random.choice(self.TRANSITIONS['honestidad']),
            random.choice(self.TRANSITIONS['no_se']),
        ]
        
        if topic:
            parts.append(f"\nSobre '{topic[:50]}', te sugiero:")
            parts.append("1. Verificar en fuentes oficiales o documentación actualizada")
            parts.append("2. Consultar con expertos en el área")
            parts.append("3. ¿Podrías darme más contexto para ayudarte mejor?")
        
        return "\n\n".join(parts)
    
    def format_comparison(self, items: List[Dict], headers: List[str]) -> str:
        """Crea tabla comparativa markdown"""
        if not items or not headers:
            return ""
        
        # Crear tabla
        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("|" + "|".join(["---" for _ in headers]) + "|")
        
        for item in items:
            row = "| " + " | ".join(str(item.get(h.lower(), "-")) for h in headers) + " |"
            lines.append(row)
        
        return "\n".join(lines)
    
    def format_steps(self, steps: List[str], title: str = "Pasos a seguir") -> str:
        """Lista numerada
