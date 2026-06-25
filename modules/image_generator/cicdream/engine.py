"""
modules/image_generator/cicdream/engine.py
==========================================
CicDream v1.0 — Motor Principal con aprendizaje desde dataset
"""

import numpy as np
import io
import base64
import logging
import time
import json
import os
import re
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger('cicdream.engine')

try:
    from peft import PeftModel
except ImportError:
    logger.warning("Peft no instalado. Instalalo con: pip install peft")

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

ENGINE_NAME    = "CicDream"
ENGINE_VERSION = "1.0.0"
ENGINE_AUTHOR  = "Cic_IA Dev"

OUTPUT_SIZES = {
    'square':    (512, 512),
    'landscape': (512, 288),
    'portrait':  (288, 512),
    '512':       (512, 512),
    'small':     (256, 256),
}

QUALITY_STEPS = {
    'standard': 20,
    'hd':       40,
}

# ── Colores CSS conocidos → RGB ───────────────────────────────────────────
_CSS_COLORS = {
    'rojo': (220,50,50), 'red': (220,50,50), 'azul': (50,100,220),
    'blue': (50,100,220), 'verde': (50,180,80), 'green': (50,180,80),
    'amarillo': (240,220,50), 'yellow': (240,220,50), 'naranja': (240,140,50),
    'orange': (240,140,50), 'morado': (140,50,200), 'purple': (140,50,200),
    'violeta': (140,50,200), 'rosa': (240,100,160), 'pink': (240,100,160),
    'blanco': (245,245,245), 'white': (245,245,245), 'negro': (20,20,20),
    'black': (20,20,20), 'gris': (150,150,150), 'gray': (150,150,150),
    'grey': (150,150,150), 'celeste': (100,200,240), 'cyan': (50,220,220),
    'turquesa': (50,200,180), 'turquoise': (50,200,180), 'dorado': (220,180,50),
    'gold': (220,180,50), 'plateado': (180,180,200), 'silver': (180,180,200),
    'marron': (140,80,40), 'brown': (140,80,40), 'beige': (220,200,170),
    'oscuro': (40,40,60), 'dark': (40,40,60), 'claro': (220,220,240),
    'light': (220,220,240), 'neon': (0,255,150), 'magenta': (220,50,220),
}


def _extract_colors_from_text(text: str) -> list:
    """Extrae colores de un texto de notas técnicas."""
    if not text:
        return []
    colors = []
    text_lower = text.lower()
    for color_name, rgb in _CSS_COLORS.items():
        if color_name in text_lower:
            colors.append(rgb)
    # Buscar hex colors #RRGGBB
    hex_matches = re.findall(r'#([0-9a-fA-F]{6})', text)
    for hx in hex_matches[:3]:
        r = int(hx[0:2], 16); g = int(hx[2:4], 16); b = int(hx[4:6], 16)
        colors.append((r, g, b))
    return colors[:6]  # máximo 6 colores


def _prompt_similarity(p1: str, p2: str) -> float:
    """Similitud simple entre dos prompts basada en palabras compartidas."""
    w1 = set(p1.lower().split())
    w2 = set(p2.lower().split())
    if not w1 or not w2:
        return 0.0
    intersection = w1 & w2
    union = w1 | w2
    return len(intersection) / len(union)


def _get_learned_palette(prompt: str, style: str) -> list:
    """
    Busca en la BD imágenes de entrenamiento similares al prompt
    y extrae su paleta de colores aprendida.
    Retorna lista de tuplas RGB o [] si no hay datos.
    """
    try:
        from flask import current_app
        from sqlalchemy import text
        db = current_app.extensions['sqlalchemy'].engine

        with db.connect() as conn:
            rows = conn.execute(text("""
                SELECT g.prompt, g.style, f.details, f.rating
                FROM cicdream_generation g
                LEFT JOIN cicdream_feedback f ON f.generation_id = g.id
                WHERE f.rating >= 3.5
                ORDER BY f.rating DESC, g.created_at DESC
                LIMIT 100
            """)).fetchall()

        if not rows:
            return []

        best_colors = []
        best_score  = 0.0

        for row in rows:
            db_prompt  = row[0] or ''
            db_style   = row[1] or ''
            db_details = row[2] or ''
            db_rating  = float(row[3] or 0)

            sim = _prompt_similarity(prompt, db_prompt)
            if db_style == style:
                sim += 0.15
            sim *= (db_rating / 5.0)

            if sim > best_score:
                colors = _extract_colors_from_text(db_details)
                if colors:
                    best_score  = sim
                    best_colors = colors

        if best_score > 0.1 and best_colors:
            logger.info(f"[CicDream] Paleta aprendida (score={best_score:.2f}): {len(best_colors)} colores")
            return best_colors

    except Exception as e:
        logger.debug(f"[CicDream] No se pudo obtener paleta aprendida: {e}")

    return []


class CicDreamEngine:

    def __init__(self):
        if not _imports_ok:
            raise ImportError("Componentes de CicDream no disponibles")

        # === Intentar cargar modelo CicDream v1 con LoRA desde HuggingFace ===
        self._has_custom_model = False
        self._custom_pipe = None

        try:
            from diffusers import StableDiffusionPipeline
            from peft import PeftModel
            import torch

            logger.info("[CicDream] Cargando modelo base + LoRA entrenado...")

            self._custom_pipe = StableDiffusionPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                torch_dtype=torch.float16,
                safety_checker=None,
                use_auth_token=os.environ.get('HUGGINGFACE_TOKEN', '')
            )
            self._custom_pipe = self._custom_pipe.to(
                "cuda" if torch.cuda.is_available() else "cpu"
            )

            # Cargar LoRA entrenado
            self._custom_pipe.unet = PeftModel.from_pretrained(
                self._custom_pipe.unet,
                "cmarinanlincopan/cicdream-v1"
            )

            self._has_custom_model = True
            logger.info("[CicDream] ✅ CicDream v1 (LoRA) cargado correctamente desde HuggingFace")

        except Exception as e:
            self._has_custom_model = False
            self._custom_pipe = None
            logger.warning(f"[CicDream] No se pudo cargar modelo LoRA (se usará motor local): {e}")

        # === Inicializar componentes locales siempre ===
        self.embeddings = CicDreamEmbeddings()
        self.palette    = CicDreamPalette()
        self.config     = DiffusionConfig()
        self.diffusion  = CicDiffusion(self.config)

        self._generation_count = 0
        self._feedback_count   = 0
        self._state_path = '/tmp/cicdream_engine_state.json'
        self._load_state()

        logger.info(f"[{ENGINE_NAME}] v{ENGINE_VERSION} iniciado — LoRA activo: {self._has_custom_model}")

    def generate(self, prompt: str,
                  style:   str = 'realistic',
                  size:    str = 'square',
                  quality: str = 'standard',
                  seed:    int = None,
                  count:   int = 1) -> list:

        if not prompt or not prompt.strip():
            raise ValueError("El prompt no puede estar vacío")

        count = max(1, min(4, count))
        W, H  = OUTPUT_SIZES.get(size, (512, 512))

        # ── Motor Pollinations (principal en producción) ──────────────────
        try:
            import requests as _req, base64 as _b64, urllib.parse as _up
            _enhanced = self._enhance_prompt(prompt, style)
            _model_map = {
                'realistic': 'flux', 'artistic': 'flux', 'anime': 'flux',
                'cyberpunk': 'flux', 'fantasy': 'flux', 'space': 'flux',
                'sketch': 'turbo', '3d': 'flux', 'abstract': 'turbo',
                'minimalist': 'turbo', 'cartoon': 'flux',
            }
            _model  = _model_map.get(style, 'flux')
            _seed_v = seed if seed is not None else int(time.time() * 1000) % (2**31)
            _results = []

            for _i in range(count):
                _s   = _seed_v + _i * 1337
                _enc = _up.quote(_enhanced)
                _url = f'https://image.pollinations.ai/prompt/{_enc}?model={_model}&width={W}&height={H}&seed={_s}&nologo=true&enhance=false'
                _r   = _req.get(_url, timeout=60)
                if _r.status_code == 200 and 'image' in _r.headers.get('Content-Type', ''):
                    _b = _b64.b64encode(_r.content).decode()
                    _results.append({
                        'url': f"data:image/png;base64,{_b}", 'type': 'base64',
                        'provider': f"CicDream v1.0", 'engine': 'cicdream',
                        'seed': _s, 'time_ms': 0, 'size': f"{W}x{H}",
                    })
                    logger.info(f"[CicDream] Imagen {_i+1}/{count} via Pollinations ({_model})")
                else:
                    logger.warning(f"[CicDream] Pollinations falló ({_r.status_code})")

            if _results:
                return _results
            logger.warning("[CicDream] Pollinations no retornó imágenes — usando motor local")

        except Exception as _e:
            logger.warning(f"[CicDream] Pollinations error: {_e} — usando motor local")

        # ── Motor local con paleta aprendida ─────────────────────────────
        self.config.T = QUALITY_STEPS.get(quality, 20)
        enhanced  = self._enhance_prompt(prompt, style)
        t0        = time.time()
        embedding = self.embeddings.encode(enhanced)

        # Intentar usar paleta aprendida del dataset
        learned_colors = _get_learned_palette(prompt, style)
        if learned_colors:
            palette_arr = self.palette.build_from_colors(learned_colors, W, H)
            logger.info(f"[CicDream] Usando paleta aprendida de {len(learned_colors)} colores")
        else:
            palette_arr = self.palette.build_gradient_fast(
                self.palette.get_palette(enhanced, embedding), W, H
            )

        results = []
        for i in range(count):
            img_seed = (seed + i * 1337) if seed is not None else (
                int(time.time() * 1000) % (2**31) + i * 1337
            )
            try:
                img_array = self.diffusion.generate(
                    embedding=embedding, palette_arr=palette_arr,
                    width=W, height=H, seed=img_seed,
                )
                img_pil = self._postprocess_pil(img_array, style, quality)
                b64 = self._to_base64(img_pil)
                t1  = time.time()
                results.append({
                    'url':      f"data:image/png;base64,{b64}",
                    'type':     'base64',
                    'provider': f"{ENGINE_NAME} v{ENGINE_VERSION}{'+ Dataset' if learned_colors else ''}",
                    'engine':   'cicdream',
                    'seed':     img_seed,
                    'time_ms':  int((t1 - t0) * 1000),
                    'size':     f"{W}x{H}",
                    'steps':    self.config.T,
                    'guidance': self.config.guidance_scale,
                })
            except Exception as e:
                logger.error(f"[{ENGINE_NAME}] Error generando imagen {i+1}: {e}", exc_info=True)

        self._generation_count += len(results)
        self._save_state()
        return results

    def _enhance_prompt(self, prompt: str, style: str) -> str:
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

    def _postprocess_pil(self, img_array: np.ndarray, style: str, quality: str) -> Image.Image:
        img = Image.fromarray(img_array.astype(np.uint8), 'RGB')
        if quality == 'hd':
            img = img.filter(ImageFilter.SHARPEN)
            img = ImageEnhance.Sharpness(img).enhance(1.4)
        contrast_map = {'cyberpunk':1.3,'fantasy':1.2,'realistic':1.1,'anime':1.2,'space':1.3,'sketch':0.9}
        img = ImageEnhance.Contrast(img).enhance(contrast_map.get(style, 1.1))
        saturation_map = {'cyberpunk':1.5,'anime':1.4,'fantasy':1.3,'realistic':1.0,'minimalist':0.7,'sketch':0.3}
        img = ImageEnhance.Color(img).enhance(saturation_map.get(style, 1.1))
        img = img.filter(ImageFilter.SMOOTH_MORE)
        return img

    def _to_base64(self, img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    def apply_feedback(self, prompt: str, rating: float,
                        details: str = '', tags: list = None,
                        style: str = 'realistic') -> dict:
        rating = float(np.clip(rating, 1.0, 5.0))
        tags   = tags or []
        full_details = details + (' ' + ' '.join(tags) if tags else '')
        embedding = self.embeddings.encode(prompt)
        self.embeddings.adjust_from_feedback(prompt, rating, details, tags)
        self.palette.adjust_from_feedback(prompt, rating, full_details)
        self.diffusion.adjust_from_feedback(rating, full_details, embedding)
        self._feedback_count += 1
        self._save_state()
        return {
            'rating':          rating,
            'guidance_scale':  round(self.config.guidance_scale, 2),
            'diffusion_steps': self.config.T,
            'detail_strength': round(self.config.detail_strength, 2),
            'feedback_count':  self._feedback_count,
            'palette_name':    self.palette.select_palette_name(prompt),
        }

    def status(self) -> dict:
        return {
            'name':        ENGINE_NAME,
            'version':     ENGINE_VERSION,
            'ready':       _imports_ok,
            'generations': self._generation_count,
            'feedbacks':   self._feedback_count,
            'config': {
                'T':           self.config.T,
                'guidance':    self.config.guidance_scale,
                'detail':      self.config.detail_strength,
                'schedule':    self.config.schedule,
                'latent_size': self.config.latent_size,
            },
            'capabilities': {
                'sizes':         list(OUTPUT_SIZES.keys()),
                'quality':       list(QUALITY_STEPS.keys()),
                'feedback':      True,
                'learning':      True,
                'dataset_learn': True,
            }
        }

    def describe_prompt(self, prompt: str) -> dict:
        emb = self.embeddings.encode(prompt)
        pal = self.palette.describe(prompt)
        return {'prompt': prompt, 'embedding': self.embeddings.describe(prompt),
                'palette': pal, 'engine': ENGINE_NAME}

    def _save_state(self):
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
        try:
            if os.path.exists(self._state_path):
                with open(self._state_path, 'r') as f:
                    state = json.load(f)
                self._generation_count = state.get('generation_count', 0)
                self._feedback_count   = state.get('feedback_count', 0)
                if 'config' in state:
                    self.config.from_dict(state['config'])
        except Exception as e:
            logger.warning(f"[{ENGINE_NAME}] No se pudo cargar estado: {e}")


_engine_instance = None

def get_engine() -> CicDreamEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = CicDreamEngine()
    return _engine_instance
