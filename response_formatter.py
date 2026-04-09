"""
Response Formatter para Cic_IA v7.1
Formatea respuestas al estilo Kimi: claras, estructuradas, útiles
"""

import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class ResponseFormatter:
    """
    Formatea respuestas para máxima claridad y utilidad
    """
    
    # Plantillas de respuesta por tipo
    TEMPLATES = {
        'definition': {
            'kimi': "**{concepto}** es {definicion}\n\nEn términos simples: {simple}",
            'formal': "{concepto}: {definicion}",
            'simple': "{concepto} = {simple}"
        },
        'comparison': {
            'kimi': "Aquí la comparación entre {items}:\n\n{tabla}\n\n**Conclusión**: {conclusion}",
            'formal': "Comparación:\n{tabla}",
            'simple': "{items}: {conclusion}"
        },
        'steps': {
            'kimi': "## Cómo {accion}\n\n{pasos}\n\n💡 **Tip**: {tip}",
            'formal': "Procedimiento para {accion}:\n{pasos}",
            'simple': "Pasos:\n{pasos}"
        },
        'uncertainty': {
            'kimi': "No tengo información suficiente sobre '{tema}' en mi base actual.\n\n🔍 *Buscando en fuentes externas...*\n\n{resultado}",
            'formal': "Información insuficiente sobre '{tema}'. {resultado}",
            'simple': "No sé mucho de '{tema}'. {resultado}"
        }
    }
    
    def __init__(self, style: str = 'kimi'):
        self.style = style
    
    def format_definition(self, concept: str, definition: str, 
                         simple_explanation: str = "") -> str:
        """Formatea definición de concepto"""
        template = self.TEMPLATES['definition'][self.style]
        
        return template.format(
            concepto=concept,
            definicion=definition,
            simple=simple_explanation or definition[:100] + "..."
        )
    
    def format_list(self, items: List[str], title: str = "", 
                   ordered: bool = False) -> str:
        """Formatea lista de items"""
        if not items:
            return ""
        
        result = f"**{title}**\n\n" if title else ""
        
        for i, item in enumerate(items, 1):
            if ordered:
                result += f"{i}. {item}\n"
            else:
                result += f"• {item}\n"
        
        return result
    
    def format_key_value(self, data: Dict[str, str], title: str = "") -> str:
        """Formatea pares clave-valor"""
        result = f"**{title}**\n\n" if title else ""
        
        for key, value in data.items():
            result += f"**{key}**: {value}\n"
        
        return result
    
    def format_code(self, code: str, language: str = "") -> str:
        """Formatea bloque de código"""
        if self.style == 'kimi':
            lang = language or "python"
            return f"```{lang}\n{code}\n```"
        return f"Código:\n{code}"
    
    def format_quote(self, text: str, author: str = "") -> str:
        """Formatea cita"""
        if self.style == 'kimi':
            result = f"> {text}\n"
            if author:
                result += f"> — *{author}*"
            return result
        return f'"{text}"' + (f" - {author}" if author else "")
    
    def format_warning(self, message: str) -> str:
        """Formatea advertencia"""
        warnings = {
            'kimi': f"⚠️ **Importante**: {message}",
            'formal': f"NOTA: {message}",
            'simple': f"Ojo: {message}"
        }
        return warnings.get(self.style, message)
    
    def format_success(self, message: str) -> str:
        """Formatea mensaje de éxito"""
        icons = {
            'kimi': "✅",
            'formal': "✓",
            'simple': "OK"
        }
        return f"{icons.get(self.style, '✓')} {message}"
    
    def format_search_result(self, query: str, results: List[Dict]) -> str:
        """Formatea resultados de búsqueda"""
        if self.style != 'kimi':
            # Versión simple
            text = f"Resultados para '{query}':\n\n"
            for i, r in enumerate(results[:3], 1):
                text += f"{i}. {r.get('title', 'Sin título')}\n"
            return text
        
        # Versión Kimi
        text = f"He investigado sobre **'{query}'**:\n\n"
        
        for i, result in enumerate(results[:3], 1):
            title = result.get('title', 'Sin título')
            snippet = result.get('snippet', '')[:150]
            url = result.get('url', '')
            
            text += f"{i}. **{title}**\n"
            text += f"   {snippet}...\n"
            if url:
                text += f"   [Fuente]({url})\n"
            text += "\n"
        
        return text
    
    def auto_format(self, content: str, content_type: str = "general") -> str:
        """
        Detecta automáticamente el mejor formato
        """
        # Detectar si es lista
        if '\n' in content and any(line.strip().startswith(('-', '*', '1.')) for line in content.split('\n')):
            return self._format_detected_list(content)
        
        # Detectar si es código
        if 'def ' in content or 'class ' in content or 'import ' in content:
            return self.format_code(content)
        
        # Detectar si es definición
        if ' es ' in content[:100] and len(content) < 500:
            parts = content.split(' es ', 1)
            if len(parts) == 2:
                return self.format_definition(parts[0], parts[1])
        
        # Por defecto, solo estructurar párrafos
        return self._structure_paragraphs(content)
    
    def _format_detected_list(self, content: str) -> str:
        """Formatea lista detectada automáticamente"""
        lines = content.split('\n')
        items = []
        
        for line in lines:
            stripped = line.strip()
            # Limpiar marcadores de lista
            cleaned = re.sub(r'^[\d]+\.\s*', '', stripped)
            cleaned = re.sub(r'^[-*•]\s*', '', cleaned)
            if cleaned:
                items.append(cleaned)
        
        return self.format_list(items)
    
    def _structure_paragraphs(self, text: str) -> str:
        """Estructura texto en párrafos legibles"""
        # Dividir en oraciones
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        paragraphs = []
        current_para = []
        
        for sentence in sentences:
            current_para.append(sentence)
            # Nueva cada 3-4 oraciones
            if len(current_para) >= 3:
                paragraphs.append(' '.join(current_para))
                current_para = []
        
        if current_para:
            paragraphs.append(' '.join(current_para))
        
        return '\n\n'.join(paragraphs)
    
    def add_timestamp(self, content: str) -> str:
        """Agrega timestamp a la respuesta"""
        if self.style == 'kimi':
            ts = datetime.now().strftime("%H:%M")
            return f"{content}\n\n---\n*Actualizado: {ts}*"
        return content
