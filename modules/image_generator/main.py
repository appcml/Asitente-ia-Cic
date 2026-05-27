"""
modules/image_generator/main.py
================================
Módulo independiente de generación de imágenes para Cic_IA.
Se actualiza solo, sin tocar el bot principal.

Estrategia de generación (en orden de prioridad):
  1. Pollinations.ai  — API gratuita, sin key, funciona ya
  2. Picsum / SVG     — fallback visual si Pollinations falla
  3. Arte generativo  — fallback puro Python/SVG, siempre funciona

Autor: Cic_IA Dev
"""

import os
import io
import math
import hashlib
import requests
import base64
import urllib.parse
import logging
from datetime import datetime

logger = logging.getLogger('cic_image')

# ─── Directorio de salida (relativo al proyecto) ───────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'generated')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Config por estilo ──────────────────────────────────────────────────────
STYLE_PROMPTS = {
    'realistic':  'photorealistic, high detail, 8k, professional photography',
    'artistic':   'oil painting, fine art, colorful, brushstrokes visible',
    'cartoon':    'cartoon style, vibrant colors, clean lines, illustration',
    'abstract':   'abstract art, geometric shapes, modern art, vivid colors',
    'minimalist': 'minimalist, clean, simple, white background, elegant',
}

# ─── Colores por temática (para arte generativo) ────────────────────────────
THEME_PALETTES = {
    'naturaleza':  ['#2d6a4f', '#52b788', '#95d5b2', '#b7e4c7', '#d8f3dc'],
    'ciudad':      ['#1a1a2e', '#16213e', '#0f3460', '#533483', '#e94560'],
    'oceano':      ['#03045e', '#0077b6', '#00b4d8', '#90e0ef', '#caf0f8'],
    'atardecer':   ['#ff6b35', '#f7931e', '#ffd700', '#ff4500', '#8b1a1a'],
    'espacio':     ['#0d0d0d', '#1a1a2e', '#16213e', '#7b2d8b', '#e040fb'],
    'default':     ['#6c63ff', '#48dbfb', '#1dd1a1', '#ffd93d', '#ff6b6b'],
}


# ═══════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — esta es la que llama el bot
# ═══════════════════════════════════════════════════════════════════════════

def generar(prompt: str, style: str = 'realistic', size: str = '512x512', count: int = 1) -> dict:
    """
    Genera imágenes a partir de un prompt de texto.

    Parámetros:
        prompt  : descripción de la imagen
        style   : realistic | artistic | cartoon | abstract | minimalist
        size    : 512x512 | 768x768 | 1024x1024 | 1024x576
        count   : cantidad de imágenes (1-4)

    Retorna:
        {
          "success": True,
          "images": [{"url": "...", "type": "url|base64|svg"}],
          "provider": "pollinations|generativo",
          "prompt_usado": "..."
        }
    """
    count = max(1, min(count, 4))

    # Construir prompt enriquecido con el estilo
    style_suffix = STYLE_PROMPTS.get(style, '')
    prompt_completo = f"{prompt}, {style_suffix}" if style_suffix else prompt

    logger.info(f"[ImageGen] prompt='{prompt[:60]}' style={style} size={size} count={count}")

    images = []

    for i in range(count):
        # Intentar Pollinations.ai (gratis, no requiere API key)
        result = _generar_pollinations(prompt_completo, size, seed=i * 42)

        # Si falla, usar arte generativo SVG
        if not result:
            result = _generar_svg_artistico(prompt, style, size, seed=i)

        if result:
            images.append(result)

    if not images:
        return {
            'success': False,
            'error':   'No se pudo generar ninguna imagen',
            'images':  []
        }

    return {
        'success':      True,
        'images':       images,
        'provider':     images[0].get('provider', 'desconocido'),
        'prompt_usado': prompt_completo,
        'generado_en':  datetime.utcnow().isoformat()
    }


# ═══════════════════════════════════════════════════════════════════════════
# PROVEEDOR 1 — Pollinations.ai (gratuito, sin API key)
# ═══════════════════════════════════════════════════════════════════════════

def _generar_pollinations(prompt: str, size: str, seed: int = 0) -> dict | None:
    """
    Usa Pollinations.ai — API pública gratuita de generación de imágenes.
    Documentación: https://pollinations.ai/
    """
    try:
        # Parsear tamaño
        partes = size.split('x')
        ancho  = int(partes[0]) if len(partes) == 2 else 512
        alto   = int(partes[1]) if len(partes) == 2 else 512

        # Codificar prompt para URL
        prompt_encoded = urllib.parse.quote(prompt)

        # URL de Pollinations — genera imagen directo
        url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width={ancho}&height={alto}&seed={seed}&nologo=true"

        # Verificar que la URL responde
        response = requests.get(url, timeout=30, stream=True)

        if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
            # Convertir a base64 para retornar embebido
            img_data = response.content
            b64 = base64.b64encode(img_data).decode('utf-8')

            # Detectar formato
            content_type = response.headers.get('Content-Type', 'image/jpeg')

            logger.info(f"[ImageGen] Pollinations OK — {len(img_data)} bytes")
            return {
                'url':      f"data:{content_type};base64,{b64}",
                'type':     'base64',
                'provider': 'pollinations',
                'size':     f"{ancho}x{alto}",
                'bytes':    len(img_data)
            }

    except requests.Timeout:
        logger.warning("[ImageGen] Pollinations timeout — usando fallback")
    except Exception as e:
        logger.warning(f"[ImageGen] Pollinations error: {e}")

    return None


# ═══════════════════════════════════════════════════════════════════════════
# PROVEEDOR 2 — Arte generativo SVG (siempre funciona, 0 dependencias)
# ═══════════════════════════════════════════════════════════════════════════

def _generar_svg_artistico(prompt: str, style: str, size: str, seed: int = 0) -> dict:
    """
    Genera arte visual único basado en el prompt usando SVG puro.
    No requiere ninguna dependencia externa.
    El resultado es determinístico: mismo prompt = misma imagen.
    """
    # Seed determinístico basado en el prompt
    hash_val  = int(hashlib.md5((prompt + str(seed)).encode()).hexdigest(), 16)
    rng_state = hash_val

    def rng():
        nonlocal rng_state
        rng_state = (rng_state * 1103515245 + 12345) & 0x7fffffff
        return rng_state / 0x7fffffff

    # Parsear tamaño
    partes = size.split('x')
    W = int(partes[0]) if len(partes) == 2 else 512
    H = int(partes[1]) if len(partes) == 2 else 512

    # Paleta de colores según temática del prompt
    palette = _detectar_paleta(prompt)

    # Generar SVG según estilo
    if style == 'abstract':
        svg_content = _svg_abstracto(W, H, palette, rng)
    elif style == 'minimalist':
        svg_content = _svg_minimalista(W, H, palette, rng)
    elif style == 'cartoon':
        svg_content = _svg_cartoon(W, H, palette, rng, prompt)
    else:
        # Por defecto: paisaje generativo
        svg_content = _svg_paisaje(W, H, palette, rng)

    # Convertir SVG a data URL
    svg_b64 = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')

    return {
        'url':      f"data:image/svg+xml;base64,{svg_b64}",
        'type':     'svg',
        'provider': 'generativo',
        'size':     f"{W}x{H}",
        'bytes':    len(svg_content)
    }


def _detectar_paleta(prompt: str) -> list:
    """Detecta la paleta apropiada según palabras clave del prompt."""
    prompt_lower = prompt.lower()
    keywords = {
        'naturaleza': ['bosque', 'árbol', 'verde', 'naturaleza', 'forest', 'tree', 'nature', 'grass'],
        'ciudad':     ['ciudad', 'urbano', 'building', 'city', 'urban', 'noche', 'night'],
        'oceano':     ['mar', 'océano', 'agua', 'sea', 'ocean', 'water', 'playa', 'beach'],
        'atardecer':  ['atardecer', 'amanecer', 'sunset', 'sunrise', 'sol', 'sun', 'naranja'],
        'espacio':    ['espacio', 'galaxia', 'space', 'galaxy', 'stars', 'estrellas', 'cosmos'],
    }
    for theme, words in keywords.items():
        if any(w in prompt_lower for w in words):
            return THEME_PALETTES[theme]
    return THEME_PALETTES['default']


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _svg_paisaje(W: int, H: int, palette: list, rng) -> str:
    """Genera un paisaje abstracto con capas de ondas."""
    c1, c2, c3, c4, c5 = palette[:5]

    # Generar puntos para polígonos de paisaje
    layers = []
    for layer_idx in range(4):
        base_y = H * (0.4 + layer_idx * 0.15)
        points = []
        num_points = 12
        for j in range(num_points + 2):
            x = W * j / (num_points + 1)
            y = base_y + (rng() - 0.5) * H * 0.25
            points.append(f"{x:.1f},{y:.1f}")
        points.append(f"{W},{H}")
        points.append(f"0,{H}")
        pts_str = ' '.join(points)
        color = palette[layer_idx % len(palette)]
        opacity = 0.7 + layer_idx * 0.08
        layers.append(f'<polygon points="{pts_str}" fill="{color}" opacity="{opacity:.2f}"/>')

    # Círculo (sol/luna)
    cx = W * (0.2 + rng() * 0.6)
    cy = H * (0.1 + rng() * 0.25)
    cr = W * (0.06 + rng() * 0.08)
    sun_color = palette[-1]

    # Estrellas/partículas
    particles = []
    for _ in range(30):
        px = rng() * W
        py = rng() * H * 0.5
        pr = 1 + rng() * 2.5
        particles.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{pr:.1f}" fill="white" opacity="{0.3+rng()*0.5:.2f}"/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="2"/></filter>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#sky)"/>
  {''.join(particles)}
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{cr*1.4:.1f}" fill="{sun_color}" opacity="0.3" filter="url(#blur)"/>
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{cr:.1f}" fill="{sun_color}" opacity="0.9"/>
  {''.join(layers)}
</svg>'''
    return svg


def _svg_abstracto(W: int, H: int, palette: list, rng) -> str:
    """Genera arte abstracto con formas geométricas."""
    shapes = []

    # Fondo con gradiente
    c1, c2 = palette[0], palette[1]

    # Círculos grandes de fondo
    for _ in range(6):
        cx   = rng() * W
        cy   = rng() * H
        r    = W * (0.1 + rng() * 0.35)
        col  = palette[int(rng() * len(palette))]
        op   = 0.15 + rng() * 0.4
        shapes.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}" opacity="{op:.2f}"/>')

    # Líneas diagonales
    for _ in range(15):
        x1   = rng() * W
        y1   = rng() * H
        x2   = rng() * W
        y2   = rng() * H
        col  = palette[int(rng() * len(palette))]
        sw   = 1 + rng() * 4
        op   = 0.3 + rng() * 0.5
        shapes.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="{sw:.1f}" opacity="{op:.2f}"/>')

    # Triángulos
    for _ in range(8):
        cx   = rng() * W
        cy   = rng() * H
        s    = W * (0.05 + rng() * 0.12)
        col  = palette[int(rng() * len(palette))]
        op   = 0.4 + rng() * 0.4
        pts  = f"{cx:.1f},{cy-s:.1f} {cx-s:.1f},{cy+s:.1f} {cx+s:.1f},{cy+s:.1f}"
        shapes.append(f'<polygon points="{pts}" fill="{col}" opacity="{op:.2f}"/>')

    # Círculos pequeños de detalle
    for _ in range(20):
        cx   = rng() * W
        cy   = rng() * H
        r    = 3 + rng() * 12
        col  = palette[int(rng() * len(palette))]
        shapes.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}" opacity="0.7"/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  {''.join(shapes)}
</svg>'''
    return svg


def _svg_minimalista(W: int, H: int, palette: list, rng) -> str:
    """Genera composición minimalista."""
    bg    = '#f8f9fa'
    c1    = palette[0]
    c2    = palette[2] if len(palette) > 2 else palette[0]

    shapes = []
    # Rectángulos de bloque color
    for i in range(3):
        x    = W * (0.1 + rng() * 0.3)
        y    = H * (0.1 + rng() * 0.6)
        w    = W * (0.1 + rng() * 0.25)
        h    = H * (0.05 + rng() * 0.3)
        col  = palette[i % len(palette)]
        shapes.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{col}" rx="4"/>')

    # Círculo central
    cx = W * (0.3 + rng() * 0.4)
    cy = H * (0.3 + rng() * 0.4)
    cr = W * (0.08 + rng() * 0.1)
    shapes.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{cr:.1f}" fill="{c2}" opacity="0.8"/>')

    # Línea horizontal
    y_line = H * (0.5 + rng() * 0.3)
    shapes.append(f'<line x1="{W*0.1:.1f}" y1="{y_line:.1f}" x2="{W*0.9:.1f}" y2="{y_line:.1f}" stroke="{c1}" stroke-width="1.5" opacity="0.4"/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <rect width="{W}" height="{H}" fill="{bg}"/>
  {''.join(shapes)}
</svg>'''
    return svg


def _svg_cartoon(W: int, H: int, palette: list, rng, prompt: str) -> str:
    """Genera una escena cartoon simple."""
    cielo  = '#87CEEB'
    tierra = '#90EE90'
    c1     = palette[0]
    c2     = palette[2] if len(palette) > 2 else palette[1]

    # Sol
    sx = W * 0.8
    sy = H * 0.15
    sr = W * 0.08

    # Nubes
    nubes = []
    for i in range(3):
        nx = W * (0.1 + i * 0.3 + rng() * 0.1)
        ny = H * (0.1 + rng() * 0.2)
        nr = W * (0.05 + rng() * 0.06)
        nubes.append(f'<ellipse cx="{nx:.1f}" cy="{ny:.1f}" rx="{nr*1.8:.1f}" ry="{nr:.1f}" fill="white" opacity="0.9"/>')
        nubes.append(f'<ellipse cx="{nx+nr*0.8:.1f}" cy="{ny-nr*0.3:.1f}" rx="{nr:.1f}" ry="{nr*0.8:.1f}" fill="white" opacity="0.9"/>')

    # Árbol simple
    def arbol(ax, ay, escala):
        h_tronco = H * 0.12 * escala
        w_tronco = W * 0.025 * escala
        r_copa   = W * 0.07 * escala
        return [
            f'<rect x="{ax-w_tronco/2:.1f}" y="{ay-h_tronco:.1f}" width="{w_tronco:.1f}" height="{h_tronco:.1f}" fill="#8B4513"/>',
            f'<circle cx="{ax:.1f}" cy="{ay-h_tronco:.1f}" r="{r_copa:.1f}" fill="{c1}"/>',
            f'<circle cx="{ax-r_copa*0.5:.1f}" cy="{ay-h_tronco*0.7:.1f}" r="{r_copa*0.8:.1f}" fill="{c2}" opacity="0.7"/>',
        ]

    arboles = []
    for i in range(4):
        ax = W * (0.1 + i * 0.25 + rng() * 0.05)
        ay = H * 0.75
        escala = 0.7 + rng() * 0.6
        arboles.extend(arbol(ax, ay, escala))

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <!-- Cielo -->
  <rect width="{W}" height="{H*0.75:.1f}" fill="{cielo}"/>
  <!-- Tierra -->
  <rect y="{H*0.75:.1f}" width="{W}" height="{H*0.25:.1f}" fill="{tierra}"/>
  <!-- Sol -->
  <circle cx="{sx:.1f}" cy="{sy:.1f}" r="{sr*1.3:.1f}" fill="#FFD700" opacity="0.3"/>
  <circle cx="{sx:.1f}" cy="{sy:.1f}" r="{sr:.1f}" fill="#FFD700"/>
  <!-- Nubes -->
  {''.join(nubes)}
  <!-- Árboles -->
  {''.join(arboles)}
</svg>'''
    return svg
