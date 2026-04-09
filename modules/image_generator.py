"""
Módulo de Generación de Imágenes
Usa APIs de IA para crear imágenes desde descripciones
"""

import requests
import base64
import io
import os
from PIL import Image
import logging

logger = logging.getLogger('cic_ia.image_generator')

class ImageGeneratorModule:
    def __init__(self):
        # APIs disponibles (requieren API keys en variables de entorno)
        self.openai_api_key = os.environ.get('OPENAI_API_KEY')
        self.stability_api_key = os.environ.get('STABILITY_API_KEY')
        self.huggingface_token = os.environ.get('HUGGINGFACE_TOKEN')
        
        self.available_models = {
            'dalle': 'OpenAI DALL-E 3 (mejor calidad)',
            'sdxl': 'Stable Diffusion XL (open source)',
            'flux': 'FLUX.1 (alta calidad)',
            'basic': 'Generador básico (fallback)'
        }
    
    def generate(self, prompt, style='realistic', size='1024x1024', model='auto'):
        """
        Genera imagen desde descripción textual
        
        Args:
            prompt: Descripción de la imagen deseada
            style: realistic, anime, artistic, sketch, 3d
            size: 1024x1024, 512x512, etc.
            model: dalle, sdxl, flux, o auto para selección automática
        """
        
        # Mejorar el prompt según el estilo
        enhanced_prompt = self._enhance_prompt(prompt, style)
        
        # Seleccionar modelo
        if model == 'auto':
            model = self._select_best_model()
        
        try:
            if model == 'dalle' and self.openai_api_key:
                return self._generate_dalle(enhanced_prompt, size)
            elif model == 'sdxl' and self.huggingface_token:
                return self._generate_sdxl(enhanced_prompt)
            elif model == 'flux':
                return self._generate_flux(enhanced_prompt)
            else:
                # Fallback: crear imagen placeholder con instrucciones
                return self._generate_basic(enhanced_prompt, prompt)
                
        except Exception as e:
            logger.error(f"Error generando imagen: {e}")
            return {
                'success': False,
                'error': str(e),
                'fallback': self._generate_text_description(enhanced_prompt)
            }
    
    def _enhance_prompt(self, prompt, style):
        """Mejora el prompt con estilo y detalles"""
        style_modifiers = {
            'realistic': 'highly detailed, photorealistic, 8k, professional photography',
            'anime': 'anime style, manga art, vibrant colors, detailed illustration',
            'artistic': 'digital art, artistic composition, beautiful lighting, masterpiece',
            'sketch': 'pencil sketch, hand drawn, artistic sketch, detailed lines',
            '3d': '3D render, octane render, blender, cinematic lighting, detailed textures'
        }
        
        modifier = style_modifiers.get(style, style_modifiers['realistic'])
        return f"{prompt}, {modifier}"
    
    def _select_best_model(self):
        """Selecciona el mejor modelo disponible"""
        if self.openai_api_key:
            return 'dalle'
        elif self.huggingface_token:
            return 'sdxl'
        else:
            return 'basic'
    
    def _generate_dalle(self, prompt, size):
        """Genera usando OpenAI DALL-E"""
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "dall-e-3",
            "prompt": prompt,
            "size": size,
            "quality": "standard",
            "n": 1
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=60)
        result = response.json()
        
        if 'data' in result:
            image_url = result['data'][0]['url']
            # Descargar imagen
            img_response = requests.get(image_url)
            
            return {
                'success': True,
                'model': 'dalle',
                'image_data': base64.b64encode(img_response.content).decode(),
                'format': 'png',
                'prompt_used': prompt,
                'url': image_url
            }
        else:
            return {'success': False, 'error': result.get('error', 'Unknown error')}
    
    def _generate_sdxl(self, prompt):
        """Genera usando Stable Diffusion XL en HuggingFace"""
        API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
        headers = {"Authorization": f"Bearer {self.huggingface_token}"}
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "guidance_scale": 7.5,
                "num_inference_steps": 50
            }
        }
        
        response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        
        if response.status_code == 200:
            return {
                'success': True,
                'model': 'sdxl',
                'image_data': base64.b64encode(response.content).decode(),
                'format': 'png',
                'prompt_used': prompt
            }
        else:
            return {'success': False, 'error': f"HTTP {response.status_code}: {response.text}"}
    
    def _generate_flux(self, prompt):
        """Placeholder para FLUX.1"""
        # FLUX requiere API específica
        return {
            'success': False,
            'error': 'FLUX.1 requiere configuración adicional',
            'note': 'Usa DALL-E o SDXL por ahora'
        }
    
    def _generate_basic(self, enhanced_prompt, original_prompt):
        """
        Fallback básico: crea una imagen simple con PIL
        Útil cuando no hay APIs configuradas
        """
        try:
            # Crear imagen informativa
            from PIL import Image, ImageDraw, ImageFont
            
            # Imagen 512x512 con gradiente
            img = Image.new('RGB', (512, 512), color=(240, 240, 240))
            draw = ImageDraw.Draw(img)
            
            # Texto descriptivo
            text_lines = [
                "🎨 GENERADOR DE IMÁGENES",
                "",
                "Prompt recibido:",
                original_prompt[:50] + "..." if len(original_prompt) > 50 else original_prompt,
                "",
                "Para generar imágenes reales:",
                "1. Configura OPENAI_API_KEY o",
                "   HUGGINGFACE_TOKEN en Render",
                "",
                f"Estilo solicitado: {enhanced_prompt.split(',')[-1].strip() if ',' in enhanced_prompt else 'default'}"
            ]
            
            y = 50
            for line in text_lines:
                draw.text((20, y), line, fill=(50, 50, 50))
                y += 30
            
            # Guardar en buffer
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            return {
                'success': True,
                'model': 'basic_placeholder',
                'image_data': base64.b64encode(buffer.getvalue()).decode(),
                'format': 'png',
                'prompt_used': original_prompt,
                'note': 'Esta es una imagen placeholder. Configura una API key para generación real.'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'No se pudo generar ni siquiera placeholder: {str(e)}'
            }
    
    def _generate_text_description(self, prompt):
        """Genera descripción textual detallada cuando no hay imagen"""
        return {
            'type': 'text_description',
            'description': f"""
🎨 **Descripción de imagen solicitada:**

**Prompt:** {prompt}

**Elementos visuales sugeridos:**
- Composición centrada en el tema principal
- Iluminación natural y equilibrada
- Colores armónicos según el contexto
- Detalles de fondo que complementen la escena

**Nota:** Para ver la imagen generada, configura OPENAI_API_KEY o HUGGINGFACE_TOKEN en las variables de entorno de Render.
"""
        }
    
    def edit_image(self, image_data, edit_prompt):
        """Edita imagen existente (DALL-E 2)"""
        # Implementación futura
        return {'success': False, 'error': 'Edición de imágenes en desarrollo'}
    
    def create_variation(self, image_data, n=1):
        """Crea variaciones de imagen existente"""
        # Implementación futura
        return {'success': False, 'error': 'Variaciones en desarrollo'}
