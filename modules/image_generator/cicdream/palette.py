"""
modules/image_generator/cicdream/palette.py
============================================
CicDream v1.0 — Sistema de Paletas Semánticas

Convierte un vector de embedding en una paleta de colores real.
Las paletas se ajustan con feedback del usuario en tiempo real.

Sin librerías externas — solo NumPy y matemáticas de color.
"""

import numpy as np
import json
import os
import logging
from typing import Tuple

logger = logging.getLogger('cicdream.palette')

# ═══════════════════════════════════════════════════════════════════════════
# PALETAS BASE POR CONCEPTO
# Cada paleta = lista de colores RGB normalizados [0.0 - 1.0]
# Estructura: (r, g, b, weight)  ← weight = importancia del color
# ═══════════════════════════════════════════════════════════════════════════

BASE_PALETTES = {

    # ── NATURALEZA ───────────────────────────────────────────────────────
    'bosque': [
        (0.10, 0.35, 0.10, 1.0),   # verde oscuro
        (0.20, 0.55, 0.15, 0.9),   # verde medio
        (0.35, 0.65, 0.20, 0.7),   # verde claro
        (0.45, 0.30, 0.10, 0.6),   # marrón tierra
        (0.15, 0.25, 0.08, 0.8),   # verde muy oscuro
        (0.60, 0.75, 0.35, 0.4),   # amarillo verdoso
    ],
    'desierto': [
        (0.85, 0.70, 0.40, 1.0),   # arena
        (0.75, 0.55, 0.25, 0.9),   # arena oscura
        (0.95, 0.80, 0.50, 0.7),   # arena clara
        (0.60, 0.40, 0.20, 0.6),   # tierra rojiza
        (0.90, 0.85, 0.65, 0.5),   # arena brillante
        (0.40, 0.25, 0.10, 0.4),   # sombra profunda
    ],
    'oceano': [
        (0.02, 0.20, 0.60, 1.0),   # azul profundo
        (0.05, 0.40, 0.80, 0.9),   # azul medio
        (0.10, 0.60, 0.90, 0.7),   # azul claro
        (0.70, 0.90, 0.95, 0.5),   # espuma blanca
        (0.00, 0.15, 0.45, 0.8),   # abismo
        (0.15, 0.75, 0.85, 0.4),   # turquesa
    ],
    'nieve': [
        (0.92, 0.95, 1.00, 1.0),   # blanco nieve
        (0.75, 0.85, 0.95, 0.9),   # azul hielo
        (0.60, 0.75, 0.90, 0.7),   # azul frío
        (0.95, 0.97, 1.00, 0.8),   # blanco puro
        (0.40, 0.55, 0.75, 0.5),   # sombra azulada
        (0.80, 0.88, 0.95, 0.6),   # reflejo
    ],

    # ── CIELO Y TIEMPO ───────────────────────────────────────────────────
    'atardecer': [
        (1.00, 0.40, 0.05, 1.0),   # naranja intenso
        (1.00, 0.65, 0.10, 0.9),   # amarillo naranja
        (0.90, 0.20, 0.10, 0.8),   # rojo fuego
        (0.50, 0.10, 0.30, 0.7),   # púrpura oscuro
        (1.00, 0.80, 0.30, 0.6),   # dorado
        (0.20, 0.05, 0.20, 0.5),   # cielo nocturno
    ],
    'amanecer': [
        (1.00, 0.75, 0.40, 1.0),   # dorado suave
        (1.00, 0.55, 0.30, 0.9),   # naranja pastel
        (0.80, 0.60, 0.80, 0.7),   # lila
        (0.40, 0.60, 0.90, 0.8),   # azul cielo
        (1.00, 0.90, 0.60, 0.6),   # amarillo pálido
        (0.95, 0.40, 0.20, 0.5),   # rojo suave
    ],
    'noche': [
        (0.02, 0.02, 0.10, 1.0),   # negro azulado
        (0.05, 0.05, 0.20, 0.9),   # azul muy oscuro
        (0.10, 0.10, 0.35, 0.7),   # azul noche
        (0.90, 0.90, 0.80, 0.6),   # blanco estrella
        (0.20, 0.15, 0.40, 0.5),   # púrpura oscuro
        (0.50, 0.50, 0.70, 0.4),   # gris azulado
    ],
    'lluvia': [
        (0.30, 0.35, 0.45, 1.0),   # gris azulado
        (0.20, 0.25, 0.35, 0.9),   # gris oscuro
        (0.50, 0.55, 0.65, 0.7),   # gris medio
        (0.10, 0.15, 0.25, 0.8),   # casi negro
        (0.70, 0.75, 0.85, 0.5),   # gris claro
        (0.40, 0.70, 0.90, 0.4),   # azul lluvia
    ],

    # ── ESPACIO ──────────────────────────────────────────────────────────
    'espacio': [
        (0.02, 0.02, 0.08, 1.0),   # negro espacial
        (0.05, 0.00, 0.15, 0.9),   # negro púrpura
        (0.90, 0.90, 0.95, 0.7),   # blanco estrella
        (0.40, 0.10, 0.70, 0.6),   # púrpura nebulosa
        (0.10, 0.30, 0.80, 0.5),   # azul profundo
        (0.80, 0.30, 0.80, 0.4),   # magenta nebulosa
    ],
    'nebulosa': [
        (0.60, 0.10, 0.80, 1.0),   # púrpura
        (0.20, 0.50, 0.90, 0.9),   # azul eléctrico
        (0.90, 0.20, 0.50, 0.7),   # rosa cósmico
        (0.10, 0.80, 0.80, 0.6),   # cyan brillante
        (0.02, 0.02, 0.08, 0.8),   # negro base
        (1.00, 0.90, 0.60, 0.5),   # amarillo estrella
    ],

    # ── CIUDAD ───────────────────────────────────────────────────────────
    'ciudad': [
        (0.20, 0.20, 0.25, 1.0),   # gris urbano
        (0.35, 0.35, 0.40, 0.9),   # gris medio
        (0.50, 0.50, 0.55, 0.7),   # gris claro
        (0.90, 0.80, 0.50, 0.6),   # luz amarilla
        (0.10, 0.10, 0.15, 0.8),   # sombra profunda
        (0.70, 0.70, 0.75, 0.4),   # concreto claro
    ],
    'cyberpunk': [
        (0.00, 0.90, 0.80, 1.0),   # cyan neón
        (0.90, 0.00, 0.50, 0.9),   # magenta neón
        (0.05, 0.05, 0.10, 0.8),   # negro profundo
        (0.80, 0.00, 0.90, 0.7),   # púrpura eléctrico
        (1.00, 0.80, 0.00, 0.6),   # amarillo neón
        (0.00, 0.50, 0.90, 0.5),   # azul eléctrico
    ],

    # ── FANTASÍA Y MAGIA ─────────────────────────────────────────────────
    'fantasy': [
        (0.50, 0.10, 0.70, 1.0),   # púrpura mágico
        (0.90, 0.70, 0.20, 0.9),   # dorado épico
        (0.10, 0.40, 0.70, 0.7),   # azul místico
        (0.20, 0.60, 0.30, 0.6),   # verde esmeralda
        (0.80, 0.20, 0.20, 0.5),   # rojo dragón
        (0.95, 0.95, 0.90, 0.4),   # luz mágica
    ],

    # ── ANIME ────────────────────────────────────────────────────────────
    'anime': [
        (1.00, 0.75, 0.80, 1.0),   # rosa sakura
        (0.40, 0.60, 0.95, 0.9),   # azul cielo anime
        (1.00, 0.90, 0.40, 0.7),   # amarillo brillante
        (0.20, 0.80, 0.60, 0.6),   # verde vibrante
        (0.90, 0.30, 0.50, 0.5),   # rojo vibrante
        (0.95, 0.95, 1.00, 0.4),   # blanco luminoso
    ],

    # ── ABSTRACTO Y MINIMALISTA ──────────────────────────────────────────
    'abstracto': [
        (0.90, 0.20, 0.20, 1.0),   # rojo primario
        (0.20, 0.40, 0.90, 0.9),   # azul primario
        (1.00, 0.85, 0.10, 0.8),   # amarillo primario
        (0.05, 0.05, 0.05, 0.7),   # negro
        (0.95, 0.95, 0.95, 0.6),   # blanco
        (0.50, 0.50, 0.50, 0.4),   # gris
    ],
    'minimalista': [
        (0.95, 0.95, 0.95, 1.0),   # blanco predominante
        (0.10, 0.10, 0.10, 0.8),   # negro acento
        (0.40, 0.60, 0.90, 0.5),   # azul acento suave
        (0.90, 0.90, 0.90, 0.7),   # gris muy claro
        (0.20, 0.20, 0.20, 0.4),   # gris oscuro
        (0.70, 0.80, 0.95, 0.3),   # azul muy suave
    ],

    # ── PALETA NEUTRAL (fallback) ─────────────────────────────────────────
    'neutral': [
        (0.50, 0.50, 0.60, 1.0),
        (0.30, 0.40, 0.60, 0.8),
        (0.70, 0.65, 0.50, 0.7),
        (0.20, 0.25, 0.35, 0.6),
        (0.80, 0.75, 0.65, 0.5),
        (0.10, 0.15, 0.20, 0.4),
    ],
}

# Mapeo de keywords → paleta
KEYWORD_TO_PALETTE = {
    # Naturaleza
    'árbol': 'bosque', 'arbol': 'bosque', 'tree': 'bosque',
    'bosque': 'bosque', 'forest': 'bosque',
    'desierto': 'desierto', 'desert': 'desierto',
    'mar': 'oceano', 'ocean': 'oceano', 'sea': 'oceano', 'agua': 'oceano',
    'nieve': 'nieve', 'snow': 'nieve', 'hielo': 'nieve', 'ice': 'nieve',
    # Cielo
    'atardecer': 'atardecer', 'sunset': 'atardecer',
    'amanecer': 'amanecer', 'sunrise': 'amanecer',
    'noche': 'noche', 'night': 'noche',
    'lluvia': 'lluvia', 'rain': 'lluvia', 'tormenta': 'lluvia',
    # Espacio
    'espacio': 'espacio', 'space': 'espacio', 'cosmos': 'espacio',
    'galaxia': 'nebulosa', 'galaxy': 'nebulosa',
    'nebulosa': 'nebulosa',
    'estrellas': 'espacio', 'stars': 'espacio',
    # Ciudad
    'ciudad': 'ciudad', 'city': 'ciudad', 'urbano': 'ciudad', 'urban': 'ciudad',
    'cyberpunk': 'cyberpunk', 'neon': 'cyberpunk',
    # Estilos
    'fantasy': 'fantasy', 'fantasía': 'fantasy', 'mágico': 'fantasy', 'magic': 'fantasy',
    'anime': 'anime', 'manga': 'anime',
    'abstracto': 'abstracto', 'abstract': 'abstracto',
    'minimalista': 'minimalista', 'minimalist': 'minimalista',
}


# ═══════════════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class CicDreamPalette:
    """
    Genera paletas de colores desde embeddings o prompts.
    Aprende de feedback ajustando colores gradualmente.
    """

    def __init__(self, weights_path: str = None):
        # Copia local de paletas — se ajusta con feedback
        self.palettes = {k: list(v) for k, v in BASE_PALETTES.items()}
        self.weights_path = weights_path or '/tmp/cicdream_palette_weights.json'
        self._load_learned_palettes()

    # ── Selección de paleta ───────────────────────────────────────────────

    def select_palette_name(self, prompt: str) -> str:
        """Selecciona el nombre de paleta más adecuado para el prompt."""
        tokens  = prompt.lower().split()
        scores  = {}

        for token in tokens:
            if token in KEYWORD_TO_PALETTE:
                palette_name = KEYWORD_TO_PALETTE[token]
                scores[palette_name] = scores.get(palette_name, 0) + 1

        if scores:
            # La paleta con más coincidencias gana
            return max(scores, key=scores.get)
        return 'neutral'

    def get_palette(self, prompt: str,
                    embedding: np.ndarray = None) -> list:
        """
        Retorna paleta de colores como lista de (R, G, B) en [0-255].
        
        Args:
            prompt:    Texto del usuario
            embedding: Vector de embedding (opcional, mejora la selección)
        
        Returns:
            Lista de (R, G, B) — 6 colores principales
        """
        palette_name = self.select_palette_name(prompt)

        # Si hay embedding, refinar la selección
        if embedding is not None:
            palette_name = self._refine_with_embedding(palette_name, embedding)

        raw = self.palettes.get(palette_name, self.palettes['neutral'])

        # Convertir a RGB 0-255 ordenado por peso
        sorted_colors = sorted(raw, key=lambda x: x[3], reverse=True)
        rgb_palette   = [(
            int(np.clip(r * 255, 0, 255)),
            int(np.clip(g * 255, 0, 255)),
            int(np.clip(b * 255, 0, 255)),
        ) for r, g, b, w in sorted_colors]

        return rgb_palette

    def get_palette_array(self, prompt: str,
                           embedding: np.ndarray = None,
                           width: int = 512,
                           height: int = 512) -> np.ndarray:
        """
        Genera un array NumPy con gradiente de la paleta.
        Listo para usar en el motor de difusión.
        """
        colors = self.get_palette(prompt, embedding)
        return self._build_gradient(colors, width, height)

    # ── Construcción de gradientes ────────────────────────────────────────

    def _build_gradient(self, colors: list,
                         width: int, height: int) -> np.ndarray:
        """
        Construye un gradiente suave entre los colores de la paleta.
        Retorna array (H, W, 3) float32 en [0, 1].
        """
        arr = np.zeros((height, width, 3), dtype=np.float32)
        n   = len(colors)
        if n == 0:
            return arr

        # Gradiente radial con múltiples colores
        cy, cx = height / 2, width / 2
        max_dist = np.sqrt(cx**2 + cy**2)

        Y, X = np.mgrid[0:height, 0:width]
        dist = np.sqrt((X - cx)**2 + (Y - cy)**2) / max_dist  # 0-1

        # Asignar color según distancia al centro
        for y in range(height):
            for x in range(width):
                # No usar loops — vectorizar
                pass

        # Versión vectorizada
        dist_flat = dist.flatten()
        for c in range(3):
            channel = np.zeros(height * width, dtype=np.float32)
            for i, (color_idx_float) in enumerate(
                    np.linspace(0, n - 1, height * width)):
                lo  = int(color_idx_float)
                hi  = min(lo + 1, n - 1)
                t   = color_idx_float - lo
                lo_val = colors[lo][c] / 255.0
                hi_val = colors[hi][c] / 255.0
                channel[i] = lo_val * (1 - t) + hi_val * t

            # Remapear según distancia al centro
            arr[:, :, c] = channel.reshape(height, width)

        return arr

    def build_gradient_fast(self, colors: list,
                             width: int, height: int) -> np.ndarray:
        """
        Gradiente rápido vectorizado con NumPy puro.
        Mezcla radial + lineal de la paleta.
        """
        n   = max(len(colors), 1)
        arr = np.zeros((height, width, 3), dtype=np.float32)

        # Gradiente lineal horizontal (paleta de izquierda a derecha)
        x_pos = np.linspace(0, n - 1, width)
        for xi in range(width):
            lo  = int(x_pos[xi])
            hi  = min(lo + 1, n - 1)
            t   = x_pos[xi] - lo
            for c in range(3):
                lo_v = colors[lo][c] / 255.0
                hi_v = colors[hi][c] / 255.0
                arr[:, xi, c] = lo_v * (1 - t) + hi_v * t

        # Gradiente vertical (oscurecer arriba, aclarar abajo según paleta)
        y_factor = np.linspace(0.7, 1.0, height).reshape(-1, 1, 1)
        arr = arr * y_factor

        # Gradiente radial suave encima
        cy, cx = height / 2.0, width / 2.0
        Y, X   = np.mgrid[0:height, 0:width]
        radial = 1.0 - np.sqrt(((X - cx) / (width / 2))**2 +
                                ((Y - cy) / (height / 2))**2) * 0.3
        radial = np.clip(radial, 0.5, 1.0)
        arr   *= radial[:, :, np.newaxis]

        return np.clip(arr, 0.0, 1.0)

    # ── Refinamiento con embedding ────────────────────────────────────────

    def _refine_with_embedding(self, palette_name: str,
                                embedding: np.ndarray) -> str:
        """
        Refina la selección de paleta usando el embedding.
        Usa las dimensiones de luz [3] y emoción [4].
        """
        # dim 3 = luz (alta → paleta más brillante)
        # dim 4 = emoción (alta → paleta más intensa)
        luz     = float(embedding[3]) if len(embedding) > 3 else 0.5
        emocion = float(embedding[4]) if len(embedding) > 4 else 0.5

        # Noche muy oscura si luz < 0.2
        if palette_name == 'neutral' and luz < 0.2:
            return 'noche'
        # Atardecer si luz alta y emoción media-alta
        if palette_name == 'neutral' and luz > 0.7 and emocion > 0.5:
            return 'atardecer'
        return palette_name

    # ── Mezcla de paletas ─────────────────────────────────────────────────

    def blend_palettes(self, name_a: str, name_b: str,
                        factor: float = 0.5) -> list:
        """
        Mezcla dos paletas. factor=0.0 → paleta A, factor=1.0 → paleta B.
        Útil cuando el prompt combina dos conceptos.
        """
        pa = self.palettes.get(name_a, self.palettes['neutral'])
        pb = self.palettes.get(name_b, self.palettes['neutral'])
        n  = min(len(pa), len(pb))
        blended = []
        for i in range(n):
            r = pa[i][0] * (1 - factor) + pb[i][0] * factor
            g = pa[i][1] * (1 - factor) + pb[i][1] * factor
            b = pa[i][2] * (1 - factor) + pb[i][2] * factor
            w = pa[i][3] * (1 - factor) + pb[i][3] * factor
            blended.append((r, g, b, w))
        return blended

    # ── Aprendizaje por feedback ──────────────────────────────────────────

    def adjust_from_feedback(self, prompt: str, rating: float,
                              details: str = ''):
        """
        Ajusta los colores de la paleta según feedback.
        
        Si rating > 3: refuerza los colores actuales
        Si rating < 3: suaviza los colores (los acerca a neutral)
        
        Si details menciona colores específicos → los incorpora
        """
        palette_name = self.select_palette_name(prompt)
        palette      = self.palettes.get(palette_name, self.palettes['neutral'])

        factor = (rating - 3.0) / 20.0  # [-0.10, +0.10]

        # Ajustar saturación de la paleta
        adjusted = []
        for r, g, b, w in palette:
            # Acercar/alejar del gris neutro (0.5, 0.5, 0.5)
            nr = r + (r - 0.5) * factor
            ng = g + (g - 0.5) * factor
            nb = b + (b - 0.5) * factor
            adjusted.append((
                float(np.clip(nr, 0.0, 1.0)),
                float(np.clip(ng, 0.0, 1.0)),
                float(np.clip(nb, 0.0, 1.0)),
                float(np.clip(w + factor * 0.1, 0.1, 1.0)),
            ))

        # Incorporar colores del feedback textual
        if details:
            adjusted = self._inject_feedback_colors(adjusted, details, rating)

        self.palettes[palette_name] = adjusted
        self._save_learned_palettes()

        logger.info(f"[Palette] Ajuste feedback: paleta={palette_name} "
                    f"rating={rating:.1f} factor={factor:.3f}")

    def _inject_feedback_colors(self, palette: list,
                                  details: str, rating: float) -> list:
        """
        Si el usuario menciona colores en el feedback, los inyecta.
        Ejemplo: 'más oscuro' → oscurece la paleta
        """
        details_lower = details.lower()
        modified = list(palette)

        # Modificadores de brillo
        if any(w in details_lower for w in ['oscuro', 'dark', 'más oscuro', 'darker']):
            modified = [(r * 0.7, g * 0.7, b * 0.7, w)
                        for r, g, b, w in modified]
        elif any(w in details_lower for w in ['claro', 'bright', 'más claro', 'brighter']):
            modified = [(min(r * 1.3, 1.0), min(g * 1.3, 1.0), min(b * 1.3, 1.0), w)
                        for r, g, b, w in modified]

        # Modificadores de saturación
        if any(w in details_lower for w in ['más colorido', 'vibrante', 'saturado', 'vivid']):
            modified = [(
                float(np.clip(r + (r - 0.5) * 0.3, 0, 1)),
                float(np.clip(g + (g - 0.5) * 0.3, 0, 1)),
                float(np.clip(b + (b - 0.5) * 0.3, 0, 1)),
                w
            ) for r, g, b, w in modified]

        # Colores directos mencionados
        from embeddings import COLOR_VOCAB
        for color_word, rgb in COLOR_VOCAB.items():
            if color_word in details_lower:
                # Agregar el color mencionado a la paleta con peso medio
                modified.append((rgb[0], rgb[1], rgb[2], 0.6))
                break  # un color extra por feedback

        return modified

    # ── Persistencia ──────────────────────────────────────────────────────

    def _save_learned_palettes(self):
        try:
            data = {k: v for k, v in self.palettes.items()}
            with open(self.weights_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"[Palette] No se pudieron guardar paletas: {e}")

    def _load_learned_palettes(self):
        try:
            if os.path.exists(self.weights_path):
                with open(self.weights_path, 'r') as f:
                    data = json.load(f)
                for k, v in data.items():
                    self.palettes[k] = [tuple(c) for c in v]
                logger.info(f"[Palette] Paletas aprendidas cargadas: {len(data)}")
        except Exception as e:
            logger.warning(f"[Palette] No se pudieron cargar paletas: {e}")

    # ── Info de paleta ─────────────────────────────────────────────────────

    def describe(self, prompt: str) -> dict:
        """Describe la paleta seleccionada para un prompt."""
        name   = self.select_palette_name(prompt)
        colors = self.get_palette(prompt)
        return {
            'palette_name':   name,
            'colors_rgb':     colors,
            'colors_hex':     ['#{:02x}{:02x}{:02x}'.format(*c) for c in colors],
            'total_palettes': len(self.palettes),
        }


# ── Instancia global ──────────────────────────────────────────────────────
_palette_instance = None

def get_palette() -> CicDreamPalette:
    global _palette_instance
    if _palette_instance is None:
        _palette_instance = CicDreamPalette()
    return _palette_instance
