"""
modules/image_generator/cicdream/engine.py
==========================================
CicDream v1.0 — Motor Principal

Orquesta todos los componentes:
  embeddings.py → palette.py → diffusion.py → imagen final

Es el único punto de contacto con el exterior.
main.py solo llama: CicDreamEngine().generate(prompt, ...)
"""

import numpy as np
import io
import base64
import logging
import time
import json
import os
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger('cicdream.engine')

# ── Importar componentes propios ──────────────────────────────────────────
try:
    from .embeddings import CicDreamEmbeddings, get_embeddings
    from .palette    import CicDreamPalette,    get_palette
    from .diffusion  import CicDiffusion, DiffusionConfig, get_diffusion
    _imports_ok = True
except ImportError:
    try:
        from embeddings import CicDreamEmbeddings, get_embeddings
        from palette    import CicDreamPalette,    get_palette
        from diffusion  import CicDiffusion, DiffusionConfig, get_diffusion
        _imports_ok = True
    except ImportError as e:
        _imports_ok = False
        logger.error(f"[CicDream] Error importando componentes: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DEL MOTOR
# ═══════════════════════════════════════════════════════════════════════════

ENGINE_NAME    = "CicDream"
ENGINE_VERSION = "1.0.0"
ENGINE_AUTHOR  = "Cic_IA Dev"

# Tamaños de salida disponibles
OUTPUT_SIZES = {
    'square':    (512, 512),
    'landscape': (512, 288),
    'portrait':  (288, 512),
    '512':       (512, 512),
    'small':     (256, 256),
}

# Calidad → pasos de difusión
QUALITY_STEPS = {
    'standard': 20,
    'hd':       40,
}


# ═══════════════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class CicDreamEngine:
    """
    Motor principal de CicDream.

    Uso:
        engine = CicDreamEngine()
        result = engine.generate("un árbol en el bosque", style="realistic")
        # result['url'] = "data:image/png;base64,..."
    """

    def __init__(self):
        if not _imports_ok:
            raise ImportError("Componentes de CicDream no disponibles")

        # Inicializar componentes
        self.embeddings = CicDreamEmbeddings()
        self.palette    = CicDreamPalette()
        self.config     = DiffusionConfig()
        self.diffusion  = CicDiffusion(self.config)

        # Estado interno
        self._generation_count = 0
        self._feedback_count   = 0

        # Ruta de estado persistente
        self._state_path = '/tmp/cicdream_engine_state.json'
        self._load_state()

        logger.info(f"[{ENGINE_NAME}] v{ENGINE_VERSION} iniciado")

    # ── Generación principal ──────────────────────────────────────────────

    def generate(self, prompt: str,
                  style:   str = 'realistic',
                  size:    str = 'square',
                  quality: str = 'standard',
                  seed:    int = None,
                  count:   int = 1) -> list:
        """
        Genera imágenes desde un prompt de texto.

        Args:
            prompt:  Descripción de la imagen
            style:   Estilo visual (realistic, cyberpunk, fantasy, etc.)
            size:    Tamaño (square, landscape, portrait, 512)
            quality: Calidad (standard=20 pasos, hd=40 pasos)
            seed:    Semilla (None = aleatoria)
            count:   Cantidad de variantes (1-4)

        Returns:
            Lista de dicts con:
              url:      data:image/png;base64,...
              provider: "CicDream v1.0"
              engine:   "cicdream"
              seed:     semilla usada
              time_ms:  tiempo de generación
        """
        if not prompt or not prompt.strip():
            raise ValueError("El prompt no puede estar vacío")

        count = max(1, min(4, count))
        W, H  = OUTPUT_SIZES.get(size, (512, 512))

        # Ajustar pasos según calidad
        self.config.T = QUALITY_STEPS.get(quality, 20)

        # Prompt enriquecido con estilo
        enhanced = self._enhance_prompt(prompt, style)

        # Embedding del prompt
        t0 = time.time()
        embedding = self.embeddings.encode(enhanced)

        # Paleta de colores
        palette_arr = self.palette.build_gradient_fast(
            self.palette.get_palette(enhanced, embedding),
            W, H
        )

        results = []
        for i in range(count):
            img_seed = (seed + i * 1337) if seed is not None else (
                int(time.time() * 1000) % (2**31) + i * 1337
            )

            try:
                # Generar con motor de difusión
                img_array = self.diffusion.generate(
                    embedding   = embedding,
                    palette_arr = palette_arr,
                    width       = W,
                    height      = H,
                    seed        = img_seed,
                )

                # Post-proceso con PIL
                img_pil  = self._postprocess_pil(img_array, style, quality)

                # Convertir a base64
                b64 = self._to_base64(img_pil)

                t1 = time.time()
                results.append({
                    'url':      f"data:image/png;base64,{b64}",
                    'type':     'base64',
                    'provider': f"{ENGINE_NAME} v{ENGINE_VERSION}",
                    'engine':   'cicdream',
                    'seed':     img_seed,
                    'time_ms':  int((t1 - t0) * 1000),
                    'size':     f"{W}x{H}",
                    'steps':    self.config.T,
                    'guidance': self.config.guidance_scale,
                })

                logger.info(
                    f"[{ENGINE_NAME}] Imagen {i+1}/{count} generada "
                    f"en {int((t1-t0)*1000)}ms seed={img_seed}"
                )

            except Exception as e:
                logger.error(f"[{ENGINE_NAME}] Error generando imagen {i+1}: {e}",
                             exc_info=True)

        self._generation_count += len(results)
        self._save_state()

        return results

    # ── Mejora de prompt ──────────────────────────────────────────────────

    def _enhance_prompt(self, prompt: str, style: str) -> str:
        """Enriquece el prompt con descriptores de estilo."""
        style_hints = {
            'realistic':  'photorealistic, detailed, natural lighting',
            'artistic':   'digital painting, expressive brushstrokes',
            'anime':      'anime style, cel-shaded, vibrant',
            'cyberpunk':  'cyberpunk, neon lights, dark atmosphere',
            'fantasy':    'fantasy art, magical, epic lighting',
            'space':      'space, cosmic, nebula, stars, photorealistic',
            'sketch':     'pencil sketch, detailed linework',
            '3d':         '3D render, volumetric lighting, PBR',
            'abstract':   'abstract art, geometric, vivid colors',
            'minimalist': 'minimalist, clean, simple composition',
            'cartoon':    'cartoon style, vibrant, clean lines',
        }
        hint = style_hints.get(style, '')
        return f"{prompt}, {hint}" if hint else prompt

    # ── Post-proceso PIL ──────────────────────────────────────────────────

    def _postprocess_pil(self, img_array: np.ndarray,
                          style: str, quality: str) -> Image.Image:
        """
        Post-proceso final con PIL.
        Mejora la imagen del motor de difusión.
        """
        img = Image.fromarray(img_array.astype(np.uint8), 'RGB')

        # Nitidez según calidad
        if quality == 'hd':
            img = img.filter(ImageFilter.SHARPEN)
            img = ImageEnhance.Sharpness(img).enhance(1.4)

        # Contraste según estilo
        contrast_map = {
            'cyberpunk': 1.3,
            'fantasy':   1.2,
            'realistic': 1.1,
            'anime':     1.2,
            'space':     1.3,
            'sketch':    0.9,
        }
        contrast = contrast_map.get(style, 1.1)
        img = ImageEnhance.Contrast(img).enhance(contrast)

        # Saturación según estilo
        saturation_map = {
            'cyberpunk':  1.5,
            'anime':      1.4,
            'fantasy':    1.3,
            'realistic':  1.0,
            'minimalist': 0.7,
            'sketch':     0.3,
        }
        sat = saturation_map.get(style, 1.1)
        img = ImageEnhance.Color(img).enhance(sat)

        # Suavizado leve para coherencia visual
        img = img.filter(ImageFilter.SMOOTH_MORE)

        return img

    # ── Conversión a base64 ───────────────────────────────────────────────

    def _to_base64(self, img: Image.Image) -> str:
        """Convierte imagen PIL a base64 PNG."""
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    # ── Sistema de feedback ───────────────────────────────────────────────

    def apply_feedback(self, prompt: str,
                        rating: float,
                        details: str = '',
                        tags: list = None,
                        style: str = 'realistic') -> dict:
        """
        Aplica feedback del usuario para mejorar el motor en tiempo real.

        Args:
            prompt:  El prompt que generó la imagen
            rating:  1.0 (malo) a 5.0 (excelente)
            details: Texto libre del usuario ("más oscuro", "más detalle")
            tags:    Tags seleccionados por el usuario
            style:   Estilo que se usó

        Returns:
            dict con los ajustes aplicados
        """
        rating = float(np.clip(rating, 1.0, 5.0))
        tags   = tags or []

        # Combinar details + tags para más contexto
        full_details = details
        if tags:
            full_details += ' ' + ' '.join(tags)

        # Obtener embedding del prompt para ajuste direccional
        embedding = self.embeddings.encode(prompt)

        # 1. Ajustar embeddings (pesos del vocabulario)
        self.embeddings.adjust_from_feedback(prompt, rating, details, tags)

        # 2. Ajustar paleta (colores)
        self.palette.adjust_from_feedback(prompt, rating, full_details)

        # 3. Ajustar difusión (hiperparámetros)
        self.diffusion.adjust_from_feedback(rating, full_details, embedding)

        self._feedback_count += 1
        self._save_state()

        adjustments = {
            'rating':          rating,
            'guidance_scale':  round(self.config.guidance_scale, 2),
            'diffusion_steps': self.config.T,
            'detail_strength': round(self.config.detail_strength, 2),
            'feedback_count':  self._feedback_count,
            'palette_name':    self.palette.select_palette_name(prompt),
        }

        logger.info(
            f"[{ENGINE_NAME}] Feedback aplicado: rating={rating:.1f} "
            f"guidance={adjustments['guidance_scale']} "
            f"T={adjustments['diffusion_steps']}"
        )

        return adjustments

    # ── Información del motor ─────────────────────────────────────────────

    def status(self) -> dict:
        """Estado actual del motor."""
        return {
            'name':            ENGINE_NAME,
            'version':         ENGINE_VERSION,
            'ready':           _imports_ok,
            'generations':     self._generation_count,
            'feedbacks':       self._feedback_count,
            'config': {
                'T':             self.config.T,
                'guidance':      self.config.guidance_scale,
                'detail':        self.config.detail_strength,
                'schedule':      self.config.schedule,
                'latent_size':   self.config.latent_size,
            },
            'capabilities': {
                'sizes':         list(OUTPUT_SIZES.keys()),
                'quality':       list(QUALITY_STEPS.keys()),
                'feedback':      True,
                'learning':      True,
            }
        }

    def describe_prompt(self, prompt: str) -> dict:
        """Describe cómo el motor interpreta un prompt."""
        emb = self.embeddings.encode(prompt)
        pal = self.palette.describe(prompt)
        return {
            'prompt':    prompt,
            'embedding': self.embeddings.describe(prompt),
            'palette':   pal,
            'engine':    ENGINE_NAME,
        }

    # ── Persistencia de estado ────────────────────────────────────────────

    def _save_state(self):
        """Guarda el estado del motor."""
        try:
            state = {
                'generation_count': self._generation_count,
                'feedback_count':   self._feedback_count,
                'config':           self.config.to_dict(),
                'last_updated':     datetime.utcnow().isoformat(),
            }
            with open(self._state_path, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logger.warning(f"[{ENGINE_NAME}] No se pudo guardar estado: {e}")

    def _load_state(self):
        """Carga el estado previo del motor."""
        try:
            if os.path.exists(self._state_path):
                with open(self._state_path, 'r') as f:
                    state = json.load(f)
                self._generation_count = state.get('generation_count', 0)
                self._feedback_count   = state.get('feedback_count', 0)
                if 'config' in state:
                    self.config.from_dict(state['config'])
                logger.info(
                    f"[{ENGINE_NAME}] Estado cargado: "
                    f"{self._generation_count} generaciones, "
                    f"{self._feedback_count} feedbacks"
                )
        except Exception as e:
            logger.warning(f"[{ENGINE_NAME}] No se pudo cargar estado: {e}")


# ── Instancia global ──────────────────────────────────────────────────────
_engine_instance = None

def get_engine() -> CicDreamEngine:
    """Retorna instancia singleton del motor."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = CicDreamEngine()
    return _engine_instance
