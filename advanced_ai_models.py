"""
Módulo de Modelos IA Avanzados para Cic_IA
Integración con APIs de IA más potentes (OpenAI, Anthropic, Hugging Face, etc.)
"""

import os
import logging
from typing import Dict, List, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class AIModelBase(ABC):
    \"\"\"Clase base para modelos de IA\"\"\"
    
    @abstractmethod
    def generate_response(self, prompt: str, context: Optional[List[str]] = None) -> str:
        \"\"\"Generar respuesta del modelo\"\"\"
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict:
        \"\"\"Obtener información del modelo\"\"\"
        pass


class OpenAIModel(AIModelBase):
    \"\"\"Integración con OpenAI GPT\"\"\"
    
    def __init__(self, api_key: Optional[str] = None, model: str = \"gpt-3.5-turbo\"):
        \"\"\"
        Inicializar cliente de OpenAI
        
        Args:
            api_key: Clave API de OpenAI
            model: Modelo a usar (gpt-3.5-turbo, gpt-4, etc.)
        \"\"\"
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.model = model
        self.client = None
        
        if self.api_key:
            try:
                import openai
                openai.api_key = self.api_key
                self.client = openai
                logger.info(f\"✅ OpenAI modelo {model} inicializado\")
            except ImportError:
                logger.warning(\"openai no instalado\")
    
    def generate_response(self, prompt: str, context: Optional[List[str]] = None) -> str:
        \"\"\"Generar respuesta usando OpenAI\"\"\"
        if not self.client:
            return \"OpenAI no configurado\"
        
        try:
            messages = []
            
            # Agregar contexto si existe
            if context:
                for ctx in context:
                    messages.append({\"role\": \"system\", \"content\": ctx})
            
            # Agregar prompt del usuario
            messages.append({\"role\": \"user\", \"content\": prompt})
            
            # Llamar API
            response = self.client.ChatCompletion.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f\"Error con OpenAI: {e}\")
            return f\"Error: {str(e)}\"
    
    def get_model_info(self) -> Dict:
        return {
            'provider': 'OpenAI',
            'model': self.model,
            'available': bool(self.client)
        }


class AnthropicModel(AIModelBase):
    \"\"\"Integración con Anthropic Claude\"\"\"
    
    def __init__(self, api_key: Optional[str] = None, model: str = \"claude-3-sonnet-20240229\"):
        \"\"\"
        Inicializar cliente de Anthropic
        
        Args:
            api_key: Clave API de Anthropic
            model: Modelo a usar
        \"\"\"
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        self.model = model
        self.client = None
        
        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info(f\"✅ Anthropic modelo {model} inicializado\")
            except ImportError:
                logger.warning(\"anthropic no instalado\")
    
    def generate_response(self, prompt: str, context: Optional[List[str]] = None) -> str:
        \"\"\"Generar respuesta usando Claude\"\"\"
        if not self.client:
            return \"Anthropic no configurado\"
        
        try:
            # Construir contexto
            full_prompt = \"\"
            if context:
                full_prompt = \"\\n\".join(context) + \"\\n\\n\"
            full_prompt += prompt
            
            # Llamar API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {\"role\": \"user\", \"content\": full_prompt}
                ]
            )
            
            return message.content[0].text
        except Exception as e:
            logger.error(f\"Error con Anthropic: {e}\")
            return f\"Error: {str(e)}\"
    
    def get_model_info(self) -> Dict:
        return {
            'provider': 'Anthropic',
            'model': self.model,
            'available': bool(self.client)
        }


class HuggingFaceModel(AIModelBase):
    \"\"\"Integración con Hugging Face\"\"\"
    
    def __init__(self, api_key: Optional[str] = None, model: str = \"meta-llama/Llama-2-7b-chat-hf\"):
        \"\"\"
        Inicializar cliente de Hugging Face
        
        Args:
            api_key: Clave API de Hugging Face
            model: Modelo a usar
        \"\"\"
        self.api_key = api_key or os.getenv('HUGGINGFACE_API_KEY')
        self.model = model
        self.client = None
        
        if self.api_key:
            try:
                from huggingface_hub import InferenceClient
                self.client = InferenceClient(api_key=self.api_key)
                logger.info(f\"✅ Hugging Face modelo {model} inicializado\")
            except ImportError:
                logger.warning(\"huggingface_hub no instalado\")
    
    def generate_response(self, prompt: str, context: Optional[List[str]] = None) -> str:
        \"\"\"Generar respuesta usando Hugging Face\"\"\"
        if not self.client:
            return \"Hugging Face no configurado\"
        
        try:
            # Construir contexto
            full_prompt = \"\"
            if context:
                full_prompt = \"\\n\".join(context) + \"\\n\\n\"
            full_prompt += prompt
            
            # Llamar API
            response = self.client.text_generation(
                full_prompt,
                model=self.model,
                max_new_tokens=500
            )
            
            return response
        except Exception as e:
            logger.error(f\"Error con Hugging Face: {e}\")
            return f\"Error: {str(e)}\"
    
    def get_model_info(self) -> Dict:
        return {
            'provider': 'Hugging Face',
            'model': self.model,
            'available': bool(self.client)
        }


class LocalLLMModel(AIModelBase):
    \"\"\"Integración con LLMs locales (Ollama, LM Studio, etc.)\"\"\"
    
    def __init__(self, api_url: str = \"http://localhost:11434\", model: str = \"llama2\"):
        \"\"\"
        Inicializar cliente de LLM local
        
        Args:
            api_url: URL del servidor LLM
            model: Modelo a usar
        \"\"\"
        self.api_url = api_url
        self.model = model
        self.available = self._check_availability()
        
        if self.available:
            logger.info(f\"✅ LLM local {model} disponible en {api_url}\")
    
    def _check_availability(self) -> bool:
        \"\"\"Verificar si el servidor LLM está disponible\"\"\"
        try:
            import requests
            response = requests.get(f\"{self.api_url}/api/tags\", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def generate_response(self, prompt: str, context: Optional[List[str]] = None) -> str:
        \"\"\"Generar respuesta usando LLM local\"\"\"
        if not self.available:
            return \"LLM local no disponible\"
        
        try:
            import requests
            
            # Construir contexto
            full_prompt = \"\"
            if context:
                full_prompt = \"\\n\".join(context) + \"\\n\\n\"
            full_prompt += prompt
            
            # Llamar API
            response = requests.post(
                f\"{self.api_url}/api/generate\",
                json={
                    \"model\": self.model,
                    \"prompt\": full_prompt,
                    \"stream\": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get('response', 'Sin respuesta')
            else:
                return f\"Error: {response.status_code}\"
        except Exception as e:
            logger.error(f\"Error con LLM local: {e}\")
            return f\"Error: {str(e)}\"
    
    def get_model_info(self) -> Dict:
        return {
            'provider': 'Local LLM',
            'model': self.model,
            'url': self.api_url,
            'available': self.available
        }


class AIModelSelector:
    \"\"\"Selector inteligente de modelos IA\"\"\"
    
    def __init__(self):
        \"\"\"Inicializar selector con todos los modelos disponibles\"\"\"
        self.models = {}
        self._initialize_models()
    
    def _initialize_models(self):
        \"\"\"Inicializar todos los modelos disponibles\"\"\"
        # OpenAI
        self.models['openai'] = OpenAIModel()
        
        # Anthropic
        self.models['anthropic'] = AnthropicModel()
        
        # Hugging Face
        self.models['huggingface'] = HuggingFaceModel()
        
        # LLM Local
        self.models['local'] = LocalLLMModel()
        
        logger.info(f\"Modelos inicializados: {list(self.models.keys())}\")
    
    def get_available_models(self) -> List[Dict]:
        \"\"\"Obtener lista de modelos disponibles\"\"\"
        available = []
        for name, model in self.models.items():
            info = model.get_model_info()
            if info.get('available', False):
                available.append({**info, 'name': name})
        return available
    
    def select_best_model(self, priority: Optional[List[str]] = None) -> Optional[AIModelBase]:
        \"\"\"
        Seleccionar el mejor modelo disponible
        
        Args:
            priority: Lista de modelos en orden de preferencia
        
        Returns:
            Modelo seleccionado o None si no hay disponible
        \"\"\"
        if priority:
            for model_name in priority:
                if model_name in self.models:
                    model = self.models[model_name]
                    info = model.get_model_info()
                    if info.get('available', False):
                        return model
        
        # Fallback: devolver el primer modelo disponible
        for model in self.models.values():
            info = model.get_model_info()
            if info.get('available', False):
                return model
        
        return None
    
    def generate_response(self, prompt: str, context: Optional[List[str]] = None,
                         priority: Optional[List[str]] = None) -> Dict:
        \"\"\"
        Generar respuesta usando el mejor modelo disponible
        
        Args:
            prompt: Texto del prompt
            context: Contexto adicional
            priority: Modelos preferidos
        
        Returns:
            Diccionario con respuesta y metadata
        \"\"\"
        model = self.select_best_model(priority)
        
        if not model:
            return {
                'success': False,
                'error': 'No hay modelos IA disponibles',
                'response': 'Lo siento, no puedo generar una respuesta en este momento.'
            }
        
        try:
            response = model.generate_response(prompt, context)
            model_info = model.get_model_info()
            
            return {
                'success': True,
                'response': response,
                'model': model_info.get('provider'),
                'model_name': model_info.get('model')
            }
        except Exception as e:
            logger.error(f\"Error generando respuesta: {e}\")
            return {
                'success': False,
                'error': str(e),
                'response': 'Error al generar respuesta'
            }


class ResponseEnhancer:
    \"\"\"Mejorador de respuestas usando IA\"\"\"
    
    def __init__(self, model_selector: AIModelSelector):
        self.selector = model_selector
    
    def enhance_response(self, original_response: str, user_input: str) -> str:
        \"\"\"
        Mejorar una respuesta existente
        
        Args:
            original_response: Respuesta original
            user_input: Entrada del usuario
        
        Returns:
            Respuesta mejorada
        \"\"\"
        prompt = f\"\"\"Mejora la siguiente respuesta para que sea más clara, completa y útil.
        
Pregunta del usuario: {user_input}

Respuesta original: {original_response}

Por favor, proporciona una versión mejorada de la respuesta.\"\"\"
        
        result = self.selector.generate_response(prompt)
        
        if result['success']:
            return result['response']
        else:
            return original_response
    
    def generate_summary(self, text: str, max_length: int = 200) -> str:
        \"\"\"
        Generar resumen de un texto
        
        Args:
            text: Texto a resumir
            max_length: Longitud máxima del resumen
        
        Returns:
            Resumen del texto
        \"\"\"
        prompt = f\"\"\"Resume el siguiente texto en máximo {max_length} caracteres:
        
{text}\"\"\"
        
        result = self.selector.generate_response(prompt)
        
        if result['success']:
            return result['response'][:max_length]
        else:
            return text[:max_length]
    
    def translate_response(self, text: str, target_language: str = \"English\") -> str:
        \"\"\"
        Traducir respuesta a otro idioma
        
        Args:
            text: Texto a traducir
            target_language: Idioma objetivo
        
        Returns:
            Texto traducido
        \"\"\"
        prompt = f\"\"\"Traduce el siguiente texto al {target_language}:
        
{text}\"\"\"
        
        result = self.selector.generate_response(prompt)
        
        if result['success']:
            return result['response']
        else:
            return text


# Ejemplo de uso
if __name__ == \"__main__\":
    # Inicializar selector
    selector = AIModelSelector()
    
    # Ver modelos disponibles
    available = selector.get_available_models()
    print(\"Modelos disponibles:\")
    for model in available:
        print(f\"  - {model['name']}: {model['provider']} ({model['model']})\")
    
    # Generar respuesta
    prompt = \"¿Qué es machine learning?\"
    result = selector.generate_response(prompt)
    
    if result['success']:
        print(f\"\\nRespuesta ({result['model']}):\")
        print(result['response'])
    else:
        print(f\"Error: {result['error']}\")
