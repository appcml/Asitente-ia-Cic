"""
modules/image_generator/main.py — Motor de imágenes PROPIO de Cic_IA
======================================================================
Sin DALL-E. Sin APIs de pago. 100% local con Pillow + NumPy.
Fallback opcional: Pollinations.ai (gratis, sin key).

Motores disponibles:
  1. SVG     — escenas vectoriales (paisajes, ciudades, cosmos, abstracto)
  2. PIL     — imágenes en píxeles reales con ruido, texturas, capas
  3. FRACTAL — arte matemático (Mandelbrot, Julia sets)
  auto       — elige el más adecuado según el estilo

Autor: Cic_IA Dev
"""

import os, io, math, hashlib, base64, logging
from datetime import datetime
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

logger = logging.getLogger('cic_image')

# ── CicDream — Motor propio con aprendizaje ───────────────────────────────
try:
    from .cicdream import cicdream_generate, cicdream_status, is_ready as cicdream_ready
    _CICDREAM_OK = True
    logger.info('[main] CicDream motor propio cargado')
except Exception as _cd_err:
    _CICDREAM_OK = False
    def cicdream_generate(**kw): return {'success': False, 'images': [], 'error': 'CicDream no disponible'}
    def cicdream_status(**kw):   return {'ready': False}
    def cicdream_ready():        return False
    logger.warning(f'[main] CicDream no disponible: {_cd_err}')

# ─── Verificar dependencias críticas ───────────────────────────────────────
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("[CicImage] NumPy no instalado. Algunos motores no funcionarán.")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("[CicImage] Requests no instalado. Fallback Pollinations desactivado.")


# ─── Paletas por temática ──────────────────────────────────────────────────

PALETTES = {
    'naturaleza': [(45,106,79),(82,183,136),(149,213,178),(184,228,199),(216,243,220)],
    'ciudad':     [(26,26,46),(22,33,62),(15,52,96),(83,52,131),(233,69,96)],
    'oceano':     [(3,4,94),(0,119,182),(0,180,216),(144,224,239),(202,240,248)],
    'atardecer':  [(255,107,53),(247,147,30),(255,215,0),(255,69,0),(139,26,26)],
    'espacio':    [(13,13,13),(26,26,46),(22,33,62),(123,45,139),(224,64,251)],
    'cyberpunk':  [(10,10,30),(0,255,200),(255,0,120),(180,0,255),(255,230,0)],
    'fantasy':    [(30,10,60),(100,20,140),(200,50,255),(255,180,50),(255,240,200)],
    'anime':      [(255,200,220),(255,150,180),(200,100,255),(100,150,255),(255,255,200)],
    'default':    [(108,99,255),(72,219,251),(29,209,161),(255,217,61),(255,107,107)],
}

STYLE_TO_ENGINE = {
    'realistic':  'pil',
    'artistic':   'pil',
    'anime':      'pil',
    'sketch':     'pil',
    '3d':         'pil',
    'minimalist': 'svg',
    'fantasy':    'svg',
    'cyberpunk':  'svg',
    'abstract':   'svg',
    'fractal':    'fractal',
    'mandelbrot': 'fractal',
    'cartoon':    'svg',
    'landscape':  'svg',
    'space':      'pil',
}

# Palabras clave del prompt → forzar motor SVG (tienen generadores específicos)
SVG_KEYWORDS = [
    'cyberpunk','cyber','neon','ciudad','city','urbano','urban',
    'bosque','forest','árbol','tree','paisaje','landscape',
    'fantasía','fantasy','dragón','dragon','castillo','castle',
    'espacio','galaxy','cosmos','nebulosa','espacio','stars',
    'cartoon','anime','dibujo','ilustración',
    'abstracto','abstract','geométrico',
    'minimalista','minimalist',
]

def _prompt_prefers_svg(prompt: str) -> bool:
    p = prompt.lower()
    return any(k in p for k in SVG_KEYWORDS)

THEME_KEYWORDS = {
    'naturaleza': ['bosque','árbol','verde','naturaleza','forest','tree','grass','flower','flor'],
    'ciudad':     ['ciudad','urbano','building','city','urban','calle','street'],
    'oceano':     ['mar','océano','agua','sea','ocean','playa','beach','wave','ola'],
    'atardecer':  ['atardecer','amanecer','sunset','sunrise','sol','sun','naranja','cielo rojo'],
    'espacio':    ['espacio','galaxia','space','galaxy','stars','estrellas','cosmos','nebula','luna'],
    'cyberpunk':  ['cyberpunk','neon','futuro','cyber','robot','tech','hack'],
    'fantasy':    ['fantasía','dragón','dragon','magic','wizard','mago','castillo','castle'],
    'anime':      ['anime','manga','kawaii','chibi'],
}

SIZES = {
    'square':    (768, 768),
    'landscape': (1024, 576),
    'portrait':  (576, 1024),
    '512':       (512, 512),
}


# ═══════════════════════════════════════════════════════════════════════════
# ENTRADA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

def generar(prompt: str, style: str = 'realistic', size: str = 'square',
            quality: str = 'standard', count: int = 1, model: str = 'auto',
            user_id: int = None) -> dict:
    """
    Genera imágenes con el motor propio de Cic_IA.
    No requiere ninguna API de pago.
    """
    count = max(1, min(4, int(count)))
    W, H  = SIZES.get(size, (1024, 1024))

    # Semilla determinística basada en prompt
    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)

    # Prompt enriquecido con estilo para mejores resultados externos
    _style_hints = {
        'realistic':  'photorealistic, 8K, sharp focus, cinematic lighting, DSLR',
        'artistic':   'digital painting, concept art, masterpiece, ArtStation trending',
        'anime':      'anime art style, cel-shaded, vibrant colors, Studio Ghibli',
        'cyberpunk':  'cyberpunk aesthetic, neon lights, rain-soaked streets, holographic',
        'fantasy':    'epic fantasy art, magical lighting, Tolkien-inspired, detailed',
        'space':      'space nebula, stars, galaxy, cosmic, photorealistic astronomy',
        'sketch':     'pencil sketch, detailed linework, charcoal texture, hand-drawn',
        '3d':         '3D render, Unreal Engine 5, PBR materials, volumetric lighting',
        'abstract':   'abstract art, vivid colors, geometric shapes, expressionist',
        'minimalist': 'minimalist design, clean composition, flat colors, modern',
        'cartoon':    'cartoon style, vibrant colors, clean lines, Pixar inspired',
    }
    suffix  = _style_hints.get(style, '')
    enhanced = f"{prompt}, {suffix}" if suffix else prompt

    # Determinar si el usuario pidió motor propio explícitamente
    own_motors    = ('svg', 'pil', 'fractal')
    use_own       = model in own_motors
    engine        = model if use_own else 'external'  # siempre definida
    # Motores externos = todo lo demás (auto, pollinations_*, hf_*, fal_*, etc.)
    force_external = None if model in ('auto',) + own_motors else model

    logger.info(f"[CicImage] model={model} style={style} size={W}x{H} count={count} use_own={use_own}")

    images = []

    # ── CASO 1: Motor propio solicitado explícitamente ───────────────────
    if use_own:
        engine = model  # svg | pil | fractal
        for i in range(count):
            img_seed = seed + i * 1337
            try:
                if engine == 'svg':
                    result = _engine_svg(prompt, style, W, H, img_seed)
                elif engine == 'fractal':
                    result = _engine_fractal(prompt, W, H, img_seed)
                else:
                    result = _engine_pil(prompt, style, W, H, img_seed, quality)
                if result:
                    images.append(result)
            except Exception as e:
                logger.error(f"[CicImage] Motor propio {engine} falló: {e}")
                try:
                    images.append(_engine_svg(prompt, style, W, H, img_seed))
                except Exception:
                    pass

    # ── CASO 2: Motor externo (auto o específico) — PRIORIDAD PRINCIPAL ──
    else:
        images = _run_external_cascade(enhanced, W, H, seed, count,
                                        force_motor=force_external,
                                        style=style, quality=quality,
                                        user_id=user_id)

    # ── CASO 3: Si externos fallaron → usar motor SVG propio como fallback ──
    if not images:
        logger.warning("[CicImage] Externos fallaron — usando SVG como fallback")
        try:
            for i in range(count):
                img_seed = seed + i * 1337
                result = _engine_svg(prompt, style, W, H, img_seed)
                if result:
                    result['provider'] = 'CicDream Arte (modo offline)'
                    images.append(result)
        except Exception as e:
            logger.error(f"[CicImage] SVG fallback también falló: {e}")

    if not images:
        return {
            'success': False,
            'error': 'No se pudo conectar con ningún motor de imágenes. Intenta de nuevo en unos segundos.',
            'images': []
        }

    return {
        'success':      True,
        'images':       images,
        'count':        len(images),
        'provider':     images[0].get('provider', 'Cic_IA Engine'),
        'engine':       images[0].get('engine', engine),
        'prompt_usado': prompt,
        'original':     prompt,
        'generado_en':  datetime.utcnow().isoformat(),
    }


# ─── Selector de motor ────────────────────────────────────────────────────

def _select_engine(style: str, prompt: str = '') -> str:
    """Selecciona el motor óptimo según estilo y palabras clave del prompt."""
    # Si el estilo tiene motor específico, respetarlo
    engine = STYLE_TO_ENGINE.get(style, 'pil')
    # Si el prompt tiene keywords de SVG y el motor es PIL, preferir SVG
    if engine == 'pil' and _prompt_prefers_svg(prompt):
        return 'svg'
    return engine

def _detect_palette(prompt: str) -> list:
    p = prompt.lower()
    for theme, words in THEME_KEYWORDS.items():
        if any(w in p for w in words):
            return PALETTES[theme]
    return PALETTES['default']

def _rng_factory(seed: int):
    """Generador LCG determinístico para resultados reproducibles."""
    state = [seed & 0x7fffffff]
    def rng(lo=0.0, hi=1.0):
        state[0] = (state[0] * 1664525 + 1013904223) & 0x7fffffff
        return lo + (state[0] / 0x7fffffff) * (hi - lo)
    return rng

def _pil_to_b64(img: Image.Image, quality_hint: str = 'standard') -> str:
    """Convierte PIL Image a base64 PNG."""
    # Redimensionar si es muy grande para ahorrar ancho de banda
    max_side = 1024 if quality_hint == 'standard' else 1280
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


# ═══════════════════════════════════════════════════════════════════════════
# MOTOR 1 — SVG (vectorial, siempre disponible, sin dependencias extra)
# ═══════════════════════════════════════════════════════════════════════════

def _engine_svg(prompt: str, style: str, W: int, H: int, seed: int) -> dict:
    """Genera arte vectorial SVG puro según el estilo."""
    rng      = _rng_factory(seed)
    palette  = _detect_palette(prompt)

    generators = {
        'landscape': _svg_landscape,
        'fantasy':   _svg_landscape,
        'cyberpunk': _svg_cyberpunk,
        'abstract':  _svg_abstract,
        'minimalist':_svg_minimalist,
        'cartoon':   _svg_cartoon,
        'space':     _svg_space,
    }

    # Mapeo de estilos a generadores
    style_map = {
        'cyberpunk': 'cyberpunk', 'abstract': 'abstract',
        'minimalist': 'minimalist', 'cartoon': 'cartoon',
        'fantasy': 'fantasy', 'landscape': 'landscape',
    }
    gen_key = style_map.get(style, 'landscape')
    fn = generators.get(gen_key, _svg_landscape)

    svg_str = fn(W, H, palette, rng)
    b64     = base64.b64encode(svg_str.encode()).decode()

    return {
        'url':      f"data:image/svg+xml;base64,{b64}",
        'type':     'svg',
        'provider': 'Cic_IA — Motor SVG',
        'engine':   'svg',
        'size':     f"{W}x{H}",
    }


def _rgb(c): return f"rgb({c[0]},{c[1]},{c[2]})"
def _hex(c): return '#{:02x}{:02x}{:02x}'.format(c[0],c[1],c[2])

def _svg_landscape(W, H, palette, rng):
    c1,c2,c3,c4,c5 = [_hex(c) for c in palette[:5]]
    # Cielo con degradado simulado via rectángulos
    sky_layers = ''
    sky_steps = 8
    for i in range(sky_steps):
        y  = H * i / sky_steps
        h  = H / sky_steps + 1
        a  = 0.15 + (1 - i/sky_steps) * 0.85
        sky_layers += f'<rect x="0" y="{y:.1f}" width="{W}" height="{h:.1f}" fill="{c1}" opacity="{a:.2f}"/>'

    # Nubes
    clouds = ''
    for _ in range(int(rng(3,7))):
        cx, cy = W*rng(0.1,0.9), H*rng(0.05,0.35)
        for j in range(int(rng(3,6))):
            rx = W*rng(0.04,0.10)
            ry = rx*rng(0.45,0.7)
            ox = rx*rng(-1.2,1.2)
            oy = ry*rng(-0.5,0.5)
            clouds += f'<ellipse cx="{cx+ox:.1f}" cy="{cy+oy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="white" opacity="{rng(0.4,0.85):.2f}"/>'

    # Capas de terreno
    layers = ''
    for li in range(5):
        base_y = H * (0.38 + li * 0.13)
        pts = []
        for j in range(20):
            x = W * j / 19
            y = base_y + (rng(-0.5,0.5)) * H * 0.12
            pts.append(f"{x:.1f},{y:.1f}")
        pts += [f"{W},{H}", f"0,{H}"]
        col = _hex(palette[li % 5])
        op  = 0.55 + li * 0.09
        layers += f'<polygon points="{" ".join(pts)}" fill="{col}" opacity="{op:.2f}"/>'

    # Sol / luna
    sx, sy = W*rng(0.15,0.85), H*rng(0.06,0.22)
    sr = W * rng(0.04, 0.09)
    glow = f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{sr*1.8:.1f}" fill="{c5}" opacity="0.2"/>'
    sun  = f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{sr:.1f}" fill="{c5}" opacity="0.95"/>'

    # Partículas (estrellas o polvo)
    pts_svg = ''
    for _ in range(40):
        px,py = W*rng(),H*rng(0,0.45)
        pr = rng(0.8,2.5)
        pts_svg += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{pr:.1f}" fill="white" opacity="{rng(0.1,0.6):.2f}"/>'

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{sky_layers}{pts_svg}{clouds}{glow}{sun}{layers}</svg>'


def _svg_cyberpunk(W, H, palette, rng):
    bg = _hex(palette[0])
    lines_svg = ''
    # Líneas de horizonte
    for i in range(int(rng(20,35))):
        y  = H * rng(0.3, 0.9)
        x1 = W * rng(0,0.4)
        x2 = W * rng(0.6,1.0)
        col = _hex(palette[int(rng(1,5))])
        sw  = rng(0.5, 2.5)
        lines_svg += f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{col}" stroke-width="{sw:.1f}" opacity="{rng(0.3,0.9):.2f}"/>'

    # Edificios
    buildings = ''
    num_b = int(rng(8,15))
    for i in range(num_b):
        bw = W * rng(0.04, 0.10)
        bh = H * rng(0.15, 0.55)
        bx = W * i / num_b + rng(-0.01,0.01)*W
        by = H - bh
        col = _hex(palette[int(rng(0,3))])
        buildings += f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{col}" opacity="0.85"/>'
        # Ventanas
        for wi in range(int(bh/20)):
            for wj in range(int(bw/12)):
                if rng() > 0.45:
                    wx = bx + wj*11 + 3
                    wy = by + wi*18 + 5
                    wc = _hex(palette[int(rng(1,5))])
                    buildings += f'<rect x="{wx:.1f}" y="{wy:.1f}" width="7" height="10" fill="{wc}" opacity="{rng(0.5,1.0):.2f}"/>'

    # Reflejo en suelo
    floor_y = H * 0.8
    floor_h = H * 0.2
    reflect = f'<rect x="0" y="{floor_y:.1f}" width="{W}" height="{floor_h:.1f}" fill="{_hex(palette[1])}" opacity="0.35"/>'

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="{bg}"/>{lines_svg}{buildings}{reflect}</svg>'


def _svg_abstract(W, H, palette, rng):
    c1,c2 = _hex(palette[0]), _hex(palette[1])
    shapes = ''
    # Círculos grandes
    for _ in range(8):
        cx,cy = W*rng(),H*rng()
        r     = W*rng(0.05,0.3)
        col   = _hex(palette[int(rng(0,5))])
        shapes += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}" opacity="{rng(0.08,0.35):.2f}"/>'
    # Líneas
    for _ in range(20):
        x1,y1,x2,y2 = W*rng(),H*rng(),W*rng(),H*rng()
        col = _hex(palette[int(rng(0,5))])
        sw  = rng(0.5,5)
        shapes += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="{sw:.1f}" opacity="{rng(0.2,0.7):.2f}"/>'
    # Polígonos
    for _ in range(12):
        cx,cy = W*rng(),H*rng()
        s     = W*rng(0.03,0.12)
        n     = int(rng(3,8))
        pts   = ' '.join(f"{cx+s*math.cos(2*math.pi*k/n):.1f},{cy+s*math.sin(2*math.pi*k/n):.1f}" for k in range(n))
        col   = _hex(palette[int(rng(0,5))])
        shapes += f'<polygon points="{pts}" fill="{col}" opacity="{rng(0.3,0.75):.2f}"/>'
    # Círculos pequeños
    for _ in range(30):
        cx,cy = W*rng(),H*rng()
        r     = rng(2,10)
        col   = _hex(palette[int(rng(0,5))])
        shapes += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}" opacity="0.8"/>'

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="{c1}"/><rect width="{W}" height="{H}" fill="{c2}" opacity="0.4"/>{shapes}</svg>'


def _svg_minimalist(W, H, palette, rng):
    c1,c2 = _hex(palette[0]), _hex(palette[2] if len(palette)>2 else palette[0])
    shapes = ''
    for i in range(int(rng(2,5))):
        x,y = W*rng(0.05,0.45), H*rng(0.05,0.7)
        w,h = W*rng(0.08,0.22), H*rng(0.04,0.28)
        col = _hex(palette[i % len(palette)])
        shapes += f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{col}" rx="6" opacity="0.9"/>'
    cx,cy,cr = W*rng(0.25,0.75), H*rng(0.2,0.7), W*rng(0.07,0.14)
    shapes += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{cr:.1f}" fill="{c2}" opacity="0.8"/>'
    yl = H*rng(0.4,0.75)
    shapes += f'<line x1="{W*0.08:.1f}" y1="{yl:.1f}" x2="{W*0.92:.1f}" y2="{yl:.1f}" stroke="{c1}" stroke-width="1.5" opacity="0.4"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="#f7f8fc"/>{shapes}</svg>'


def _svg_cartoon(W, H, palette, rng):
    c1,c2 = _hex(palette[0]), _hex(palette[2] if len(palette)>2 else palette[1])
    sky_h  = H * 0.72
    nubes  = ''
    for i in range(int(rng(2,5))):
        nx,ny = W*rng(0.05,0.9), H*rng(0.05,0.25)
        nr    = W*rng(0.04,0.08)
        for j in range(int(rng(3,5))):
            ox,oy = nr*rng(-1.4,1.4), nr*rng(-0.4,0.4)
            rx2   = nr*rng(0.6,1.1)
            nubes += f'<ellipse cx="{nx+ox:.1f}" cy="{ny+oy:.1f}" rx="{rx2:.1f}" ry="{rx2*0.65:.1f}" fill="white" opacity="0.95"/>'
    arboles = ''
    for i in range(int(rng(3,6))):
        ax  = W*(0.08 + i*0.18 + rng(-0.02,0.02))
        ay  = sky_h
        esc = rng(0.6,1.2)
        ht  = H*0.13*esc; wt = W*0.025*esc; rc = W*0.07*esc
        arboles += (f'<rect x="{ax-wt/2:.1f}" y="{ay-ht:.1f}" width="{wt:.1f}" height="{ht:.1f}" fill="#8B4513"/>'
                   +f'<circle cx="{ax:.1f}" cy="{ay-ht:.1f}" r="{rc:.1f}" fill="{c1}"/>'
                   +f'<circle cx="{ax-rc*0.5:.1f}" cy="{ay-ht*0.65:.1f}" r="{rc*0.78:.1f}" fill="{c2}" opacity="0.8"/>')
    sx,sy,sr = W*0.82, H*0.13, W*0.07
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<rect width="{W}" height="{sky_h:.1f}" fill="#87CEEB"/>
<rect y="{sky_h:.1f}" width="{W}" height="{H-sky_h:.1f}" fill="#90EE90"/>
<circle cx="{sx}" cy="{sy}" r="{sr*1.4:.1f}" fill="#FFD700" opacity="0.3"/>
<circle cx="{sx}" cy="{sy}" r="{sr:.1f}" fill="#FFD700"/>
{nubes}{arboles}</svg>'''


def _svg_space(W, H, palette, rng):
    stars = ''
    for _ in range(200):
        sx,sy = W*rng(),H*rng()
        sr    = rng(0.5,2.5)
        sa    = rng(0.3,1.0)
        stars += f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{sr:.1f}" fill="white" opacity="{sa:.2f}"/>'
    # Nebulosas
    nebulas = ''
    for i in range(int(rng(3,6))):
        nx,ny = W*rng(0.1,0.9), H*rng(0.1,0.9)
        nr    = W*rng(0.06,0.2)
        col   = _hex(palette[int(rng(1,5))])
        nebulas += f'<ellipse cx="{nx:.1f}" cy="{ny:.1f}" rx="{nr:.1f}" ry="{nr*rng(0.4,0.9):.1f}" fill="{col}" opacity="{rng(0.06,0.18):.2f}"/>'
    # Planeta
    px,py = W*rng(0.2,0.8), H*rng(0.15,0.75)
    pr    = W*rng(0.05,0.12)
    pc    = _hex(palette[int(rng(1,5))])
    ring_w = pr*rng(1.6,2.2)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<rect width="{W}" height="{H}" fill="#050816"/>
{stars}{nebulas}
<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{ring_w:.1f}" ry="{pr*0.25:.1f}" fill="none" stroke="{pc}" stroke-width="{pr*0.12:.1f}" opacity="0.6"/>
<circle cx="{px:.1f}" cy="{py:.1f}" r="{pr:.1f}" fill="{pc}" opacity="0.92"/>
<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{ring_w:.1f}" ry="{pr*0.25:.1f}" fill="none" stroke="{pc}" stroke-width="{pr*0.06:.1f}" opacity="0.3"/>
</svg>'''


# ═══════════════════════════════════════════════════════════════════════════
# MOTOR 2 — PIL / NumPy (píxeles reales, texturas, efectos)
# ═══════════════════════════════════════════════════════════════════════════

def _engine_pil(prompt: str, style: str, W: int, H: int, seed: int, quality: str) -> dict:
    """Genera imágenes en píxeles usando PIL y NumPy."""
    palette = _detect_palette(prompt)
    rng     = _rng_factory(seed)
    np.random.seed(seed % (2**31))

    generators = {
        'realistic': _pil_realistic,
        'artistic':  _pil_artistic,
        'anime':     _pil_anime,
        'sketch':    _pil_sketch,
        '3d':        _pil_3d,
        'space':     _pil_space,
    }
    fn  = generators.get(style, _pil_artistic)
    img = fn(W, H, palette, rng)

    # Post-proceso
    img = _postprocess(img, quality)

    return {
        'url':      f"data:image/png;base64,{_pil_to_b64(img, quality)}",
        'type':     'base64',
        'provider': 'Cic_IA — Motor PIL',
        'engine':   'pil',
        'size':     f"{W}x{H}",
    }


def _pil_realistic(W, H, palette, rng) -> Image.Image:
    """Paisaje fotorrealista con ruido y capas de gradiente."""
    img  = Image.new('RGB', (W, H))
    pix  = img.load()
    c1, c2, c3, c4, c5 = palette[:5]

    # Cielo: gradiente vertical con ruido Perlin-like
    noise = np.random.normal(0, 4, (H, W, 3)).astype(np.float32)

    for y in range(H):
        t = y / H
        # Interpolación cielo→horizonte
        if t < 0.5:
            r = int(c1[0]*(1-t*2) + c2[0]*t*2 + noise[y,:,0].mean())
            g = int(c1[1]*(1-t*2) + c2[1]*t*2 + noise[y,:,1].mean())
            b = int(c1[2]*(1-t*2) + c2[2]*t*2 + noise[y,:,2].mean())
        else:
            t2 = (t-0.5)*2
            r  = int(c3[0]*(1-t2) + c4[0]*t2)
            g  = int(c3[1]*(1-t2) + c4[1]*t2)
            b_ = int(c3[2]*(1-t2) + c4[2]*t2)
            r,g,b = r,g,b_
        for x in range(W):
            nr = int(noise[y,x,0]*0.5)
            ng = int(noise[y,x,1]*0.5)
            nb = int(noise[y,x,2]*0.5)
            pix[x,y] = (
                max(0,min(255,r+nr)),
                max(0,min(255,g+ng)),
                max(0,min(255,b+nb)),
            )

    # Terreno con ruido
    terrain_arr = np.array(img, dtype=np.float32)
    horizon = int(H * 0.55)
    ground_noise = np.random.normal(0, 12, (H-horizon, W, 3))
    terrain_arr[horizon:] = np.clip(
        terrain_arr[horizon:] * 0.6 + [[c4]] * (H-horizon) + ground_noise * 0.4, 0, 255
    )
    img = Image.fromarray(terrain_arr.astype(np.uint8))

    # Aplicar blur suave para cohesión
    img = img.filter(ImageFilter.GaussianBlur(radius=1.2))

    # Sol/luna difuso
    draw = ImageDraw.Draw(img)
    sx, sy = int(W * rng(0.15,0.85)), int(H * rng(0.06,0.22))
    sr = int(W * rng(0.04, 0.09))
    for r_offset in range(sr*3, 0, -3):
        alpha_f = (1 - r_offset/(sr*3)) * 0.25
        col     = tuple(int(c * alpha_f + 255*(1-alpha_f)) for c in c5)
        draw.ellipse([sx-r_offset, sy-r_offset, sx+r_offset, sy+r_offset], fill=col)
    draw.ellipse([sx-sr, sy-sr, sx+sr, sy+sr], fill=c5)

    return img


def _pil_artistic(W, H, palette, rng) -> Image.Image:
    """Arte pictórico con pinceladas simuladas."""
    # Base con ruido de color
    arr  = np.zeros((H, W, 3), dtype=np.float32)
    c1, c2, c3, c4, c5 = palette[:5]

    # Capa base: gradiente diagonal
    for y in range(H):
        for x_chunk in range(0, W, 32):
            t  = (y/H + x_chunk/W) / 2
            c  = [int(c1[i]*(1-t) + c2[i]*t) for i in range(3)]
            arr[y, x_chunk:x_chunk+32] = c

    # Pinceladas: elipses de colores de la paleta
    img  = Image.fromarray(arr.astype(np.uint8))
    draw = ImageDraw.Draw(img, 'RGBA')
    num_strokes = int(rng(80, 180))
    for _ in range(num_strokes):
        bx   = int(W * rng())
        by   = int(H * rng())
        bw   = int(W * rng(0.02, 0.14))
        bh   = int(bw * rng(0.2, 0.5))
        col  = palette[int(rng(0, len(palette)-0.01))]
        alpha= int(rng(80, 200))
        angle= rng(0, 360)
        # Simular ángulo con transformación manual
        draw.ellipse([bx-bw, by-bh, bx+bw, by+bh], fill=(*col, alpha))

    img = img.convert('RGB')
    img = img.filter(ImageFilter.SMOOTH)
    return img


def _pil_anime(W, H, palette, rng) -> Image.Image:
    """Estilo anime: colores planos, cel-shading, contornos."""
    img  = Image.new('RGB', (W, H), color=palette[0])
    draw = ImageDraw.Draw(img)
    c1,c2,c3,c4,c5 = palette[:5]

    # Cielo plano
    sky_h = int(H * 0.6)
    draw.rectangle([0,0,W,sky_h], fill=c1)
    # Gradiente de cielo simplificado (bandas)
    for i in range(8):
        y_band = sky_h * i // 8
        h_band = sky_h // 8
        t      = i / 8
        col    = tuple(int(c1[j]*(1-t) + c2[j]*t) for j in range(3))
        draw.rectangle([0,y_band,W,y_band+h_band], fill=col)

    # Suelo/mar plano
    draw.rectangle([0,sky_h,W,H], fill=c3)

    # Figuras geométricas limpias (estilo anime: cel-shaded)
    # Montañas o edificios estilizados
    for i in range(int(rng(3,6))):
        mx = int(W * (0.1 + i*0.18 + rng(-0.05,0.05)))
        mh = int(H * rng(0.18, 0.42))
        mw = int(W * rng(0.10, 0.20))
        col = palette[i % len(palette)]
        shadow = tuple(max(0,c-40) for c in col)
        # Triángulo montaña
        pts = [(mx-mw, sky_h), (mx, sky_h-mh), (mx+mw, sky_h)]
        draw.polygon(pts, fill=col)
        # Sombra lateral
        shadow_pts = [(mx, sky_h-mh), (mx+mw, sky_h), (mx+mw//2, sky_h-mh//3)]
        draw.polygon(shadow_pts, fill=shadow)

    # Sol grande estilo anime
    sx,sy = int(W*rng(0.6,0.85)), int(H*rng(0.08,0.2))
    sr    = int(W*0.07)
    draw.ellipse([sx-sr,sy-sr,sx+sr,sy+sr], fill=c5)
    draw.ellipse([sx-sr+3,sy-sr+3,sx+sr-3,sy+sr-3], fill=tuple(min(255,c+40) for c in c5))

    # Contorno oscuro (cel-shading)
    img2 = img.filter(ImageFilter.FIND_EDGES)
    arr  = np.array(img)
    arr2 = np.array(img2)
    mask = arr2 > 20
    arr[mask] = [20,20,40]
    img = Image.fromarray(arr)

    return img


def _pil_sketch(W, H, palette, rng) -> Image.Image:
    """Boceto a lápiz: blanco y negro con texturas."""
    # Base blanca con textura de papel
    paper_noise = np.random.normal(245, 8, (H, W, 3)).clip(220, 255).astype(np.uint8)
    img  = Image.fromarray(paper_noise)
    draw = ImageDraw.Draw(img)

    # Líneas de boceto: rectángulos, elipses, líneas cruzadas
    for _ in range(int(rng(20,50))):
        x1,y1 = int(W*rng()), int(H*rng())
        x2,y2 = int(W*rng()), int(H*rng())
        shade = int(rng(10,90))
        draw.line([x1,y1,x2,y2], fill=(shade,shade,shade), width=int(rng(1,3)))

    for _ in range(int(rng(15,30))):
        cx,cy = int(W*rng()), int(H*rng())
        rx    = int(W*rng(0.02,0.15))
        ry    = int(rx*rng(0.3,1.2))
        shade = int(rng(20,120))
        draw.ellipse([cx-rx,cy-ry,cx+rx,cy+ry], outline=(shade,shade,shade), width=int(rng(1,3)))

    # Sombreado: líneas paralelas
    for _ in range(int(rng(8,20))):
        x0    = int(W*rng(0,0.8))
        y0    = int(H*rng())
        length= int(W*rng(0.05,0.3))
        shade = int(rng(60,160))
        for k in range(int(rng(5,15))):
            y_off = y0 + k*int(rng(3,8))
            if y_off < H:
                draw.line([x0, y_off, x0+length, y_off+int(rng(-4,4))], fill=(shade,shade,shade), width=1)

    img = img.filter(ImageFilter.SHARPEN)
    return img


def _pil_3d(W, H, palette, rng) -> Image.Image:
    """Render 3D simplificado: esferas y superficies con iluminación."""
    arr = np.zeros((H, W, 3), dtype=np.float32)
    c1  = np.array(palette[0], dtype=np.float32)
    c2  = np.array(palette[2], dtype=np.float32)

    # Fondo: gradiente oscuro
    for y in range(H):
        t = y / H
        arr[y] = c1 * (1-t) * 0.3 + c2 * t * 0.15

    # Superficie plana reflectante
    floor_y   = int(H * 0.65)
    floor_col = np.array(palette[1], dtype=np.float32) * 0.6
    arr[floor_y:] = floor_col

    img  = Image.fromarray(arr.astype(np.uint8))
    draw = ImageDraw.Draw(img)

    # Esferas con sombreado por raycast simplificado
    light = np.array([0.6, -0.8, 0.5])
    light = light / np.linalg.norm(light)

    spheres = []
    for _ in range(int(rng(2,5))):
        sx = int(W * rng(0.15, 0.85))
        sy = int(floor_y * rng(0.3, 0.85))
        sr = int(W * rng(0.04, 0.12))
        sc = palette[int(rng(0, len(palette)-0.01))]
        spheres.append((sx, sy, sr, sc))

    # Dibujar esferas con iluminación
    for (sx, sy, sr, sc) in spheres:
        for px in range(max(0,sx-sr), min(W,sx+sr)):
            for py in range(max(0,sy-sr), min(H,sy+sr)):
                dx = (px-sx)/sr; dy = (py-sy)/sr
                dist2 = dx*dx + dy*dy
                if dist2 <= 1.0:
                    dz  = math.sqrt(max(0, 1.0 - dist2))
                    n   = np.array([dx, dy, dz])
                    diff= max(0.0, float(np.dot(n, light)))
                    amb = 0.25
                    int_= min(1.0, amb + diff * 0.8 + diff**6 * 0.4)
                    col = tuple(int(min(255, sc[i]*int_)) for i in range(3))
                    img.putpixel((px, py), col)

    # Sombras suaves en el suelo
    for (sx, sy, sr, sc) in spheres:
        shadow_a = 0.35
        for px in range(max(0,sx-sr*2), min(W,sx+sr*2)):
            for py in range(max(0,floor_y), min(H,floor_y+sr)):
                dx  = (px-sx)/(sr*1.4); dy = (py-floor_y)/(sr*0.5)
                if dx*dx+dy*dy <= 1.0:
                    pix = img.getpixel((px,py))
                    img.putpixel((px,py), tuple(int(c*(1-shadow_a)) for c in pix))

    return img


def _pil_space(W, H, palette, rng) -> Image.Image:
    """Espacio: fondo oscuro, nebulosas difusas, estrellas."""
    arr = np.zeros((H, W, 3), dtype=np.float32)
    arr[:] = [5, 5, 15]  # fondo muy oscuro

    # Nebulosas con ruido gaussiano coloreado
    for _ in range(int(rng(3,7))):
        nx, ny = int(W*rng()), int(H*rng())
        nr     = int(W * rng(0.1, 0.35))
        col    = np.array(palette[int(rng(0, len(palette)-0.01))], dtype=np.float32)
        Y, X   = np.ogrid[:H, :W]
        dist   = np.sqrt((X-nx)**2 + (Y-ny)**2)
        mask   = np.exp(-dist**2 / (2*(nr*0.4)**2))
        for c in range(3):
            arr[:,:,c] += mask * col[c] * rng(0.06, 0.18)

    arr = np.clip(arr, 0, 255)
    img = Image.fromarray(arr.astype(np.uint8))

    # Estrellas como puntos blancos
    draw = ImageDraw.Draw(img)
    for _ in range(int(rng(200,400))):
        sx, sy = int(W*rng()), int(H*rng())
        br     = rng(0.3, 1.0)
        col    = tuple(int(br*255) for _ in range(3))
        sr     = rng(0, 1)
        if sr > 0.5:
            draw.ellipse([sx-1,sy-1,sx+1,sy+1], fill=col)
        else:
            img.putpixel((sx,sy), col)

    # Planeta grande
    px,py = int(W*rng(0.2,0.8)), int(H*rng(0.15,0.75))
    pr    = int(W*rng(0.06,0.14))
    pc    = palette[int(rng(0,len(palette)-0.01))]
    draw.ellipse([px-pr,py-pr,px+pr,py+pr], fill=pc)
    # Brillo especular
    draw.ellipse([px-pr//3,py-pr//2,px+pr//6,py-pr//6], fill=tuple(min(255,c+80) for c in pc))

    return img


def _postprocess(img: Image.Image, quality: str) -> Image.Image:
    """Mejoras básicas de post-proceso."""
    if quality == 'hd':
        img = ImageEnhance.Sharpness(img).enhance(1.4)
        img = ImageEnhance.Contrast(img).enhance(1.15)
        img = ImageEnhance.Color(img).enhance(1.1)
    else:
        img = ImageEnhance.Contrast(img).enhance(1.05)
        img = ImageEnhance.Color(img).enhance(1.05)
    return img


# ═══════════════════════════════════════════════════════════════════════════
# MOTOR 3 — FRACTAL (Mandelbrot, Julia sets)
# ═══════════════════════════════════════════════════════════════════════════

def _engine_fractal(prompt: str, W: int, H: int, seed: int) -> dict:
    """Genera arte fractal matemático."""
    palette = _detect_palette(prompt)
    rng     = _rng_factory(seed)
    np.random.seed(seed % (2**31))

    fractal_type = 'julia' if rng() > 0.4 else 'mandelbrot'
    if fractal_type == 'julia':
        img = _fractal_julia(W, H, palette, rng)
    else:
        img = _fractal_mandelbrot(W, H, palette)

    img = _postprocess(img, 'standard')

    return {
        'url':      f"data:image/png;base64,{_pil_to_b64(img)}",
        'type':     'base64',
        'provider': 'Cic_IA — Motor Fractal',
        'engine':   'fractal',
        'size':     f"{W}x{H}",
    }


def _fractal_mandelbrot(W: int, H: int, palette: list) -> Image.Image:
    """Conjunto de Mandelbrot en NumPy (vectorizado)."""
    MAX_ITER = 60
    zoom, cx, cy = 1.0, -0.5, 0.0

    x = np.linspace(-2.5/zoom + cx, 1.5/zoom + cx, W)
    y = np.linspace(-1.5/zoom + cy, 1.5/zoom + cy, H)
    C = x[np.newaxis,:] + 1j*y[:,np.newaxis]

    Z       = np.zeros_like(C)
    escaped = np.zeros(C.shape, dtype=np.float32)
    mask    = np.ones(C.shape, dtype=bool)

    for i in range(MAX_ITER):
        Z[mask]       = Z[mask]**2 + C[mask]
        newly_escaped = mask & (np.abs(Z) > 2)
        escaped[newly_escaped] = i + 1 - np.log2(np.log2(np.abs(Z[newly_escaped]) + 1e-10))
        mask[newly_escaped]    = False

    # Colorear con paleta
    norm  = escaped / MAX_ITER
    arr   = np.zeros((H, W, 3), dtype=np.uint8)
    n_col = len(palette)
    for i, col in enumerate(palette):
        lo = i / n_col; hi = (i+1) / n_col
        m  = (norm >= lo) & (norm < hi)
        t  = (norm[m] - lo) / (hi - lo + 1e-10)
        nc = palette[(i+1) % n_col]
        arr[m] = [
            int(col[0]*(1-t.mean()) + nc[0]*t.mean()),
            int(col[1]*(1-t.mean()) + nc[1]*t.mean()),
            int(col[2]*(1-t.mean()) + nc[2]*t.mean()),
        ]

    # Colorear pixel a pixel (más preciso)
    idx   = (norm * (n_col-1)).astype(int)
    idx   = np.clip(idx, 0, n_col-2)
    t_map = (norm * (n_col-1)) - idx
    for c in range(3):
        col_lo = np.array([palette[i][c] for i in range(n_col-1)])[idx]
        col_hi = np.array([palette[i][c] for i in range(1, n_col)])[idx]
        arr[:,:,c] = np.clip(col_lo*(1-t_map) + col_hi*t_map, 0, 255).astype(np.uint8)

    arr[escaped == 0] = [0,0,0]
    return Image.fromarray(arr)


def _fractal_julia(W: int, H: int, palette: list, rng) -> Image.Image:
    """Julia set con constante aleatoria pero bonita."""
    MAX_ITER = 60
    # Constantes clásicas interesantes + variación aleatoria
    c_options = [
        (-0.7269+0.1889j), (-0.8+0.156j), (0.285+0.01j),
        (-0.4+0.6j), (0.0+0.8j), (-0.7269+rng(-0.2,0.2)*1j),
    ]
    c   = c_options[int(rng(0, len(c_options)-0.01))]
    zoom= rng(0.9, 1.4)

    x   = np.linspace(-1.5/zoom, 1.5/zoom, W)
    y   = np.linspace(-1.5/zoom, 1.5/zoom, H)
    Z   = x[np.newaxis,:] + 1j*y[:,np.newaxis]

    escaped = np.zeros(Z.shape, dtype=np.float32)
    mask    = np.ones(Z.shape, dtype=bool)

    for i in range(MAX_ITER):
        Z[mask]       = Z[mask]**2 + c
        newly_escaped = mask & (np.abs(Z) > 2)
        escaped[newly_escaped] = i + 1
        mask[newly_escaped]    = False

    norm  = escaped / MAX_ITER
    n_col = len(palette)
    idx   = (norm * (n_col-1)).astype(int)
    idx   = np.clip(idx, 0, n_col-2)
    t_map = (norm * (n_col-1)) - idx

    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for c_ch in range(3):
        col_lo = np.array([palette[i][c_ch] for i in range(n_col-1)])[idx]
        col_hi = np.array([palette[i][c_ch] for i in range(1, n_col)])[idx]
        arr[:,:,c_ch] = np.clip(col_lo*(1-t_map)+col_hi*t_map, 0, 255).astype(np.uint8)

    arr[escaped == 0] = [5, 5, 15]
    return Image.fromarray(arr)



# ═══════════════════════════════════════════════════════════════════════════
# MOTORES EXTERNOS — todos gratuitos o con tier gratis
# Orden auto: Pollinations FLUX → Turbo → fal.ai → HF SDXL → HF FLUX →
#             Stability AI → Gemini → HF SD21 → Pollinations SD
# ═══════════════════════════════════════════════════════════════════════════

_HF_TOKEN         = os.environ.get('HUGGINGFACE_TOKEN', '')
_GEMINI_KEY       = os.environ.get('GEMINI_API_KEY', '')
_FAL_KEY          = os.environ.get('FAL_API_KEY', '')
_STABILITY_KEY    = os.environ.get('STABILITY_API_KEY', '')
_POLLINATIONS_KEY = os.environ.get('POLLINATIONS_API_KEY', '')

EXTERNAL_MOTORS = {
    'pollinations_flux':   ('Pollinations FLUX.1',          None,            '100% gratis, sin key, alta calidad'),
    'pollinations_turbo':  ('Pollinations Turbo SD',         None,            '100% gratis, rápido'),
    'pollinations_sd':     ('Pollinations Stable Diffusion', None,            '100% gratis, clásico'),
    'hf_flux':             ('HuggingFace FLUX.1-schnell',    'HF_TOKEN',      'Gratis sin key, mejor con token'),
    'hf_sdxl':             ('HuggingFace SDXL',              'HF_TOKEN',      'Alta resolución'),
    'hf_sd21':             ('HuggingFace SD 2.1',            'HF_TOKEN',      'Confiable'),
    'fal_flux_schnell':    ('fal.ai FLUX.1-schnell',         'FAL_KEY',       'Muy rápido ~1-3s'),
    'fal_flux_dev':        ('fal.ai FLUX.1-dev',             'FAL_KEY',       'Mayor calidad'),
    'stability_core':      ('Stability AI Core',             'STABILITY_KEY', 'Plan gratis disponible'),
    'stability_sd3':       ('Stability AI SD3',              'STABILITY_KEY', 'Stable Diffusion 3'),
    'gemini_flash':        ('Gemini 2.5 Flash Image',        'GEMINI_KEY',    '500 imgs/dia gratis'),
    'cicdream':            ('CicDream v1.0',                None,            'Motor propio con aprendizaje'),
    'cic_svg':             ('Cic_IA Motor SVG',              None,            'Arte vectorial propio'),
    'cic_pil':             ('Cic_IA Motor PIL',              None,            'Arte pixeles propio'),
    'cic_fractal':         ('Cic_IA Motor Fractal',          None,            'Arte matematico propio'),
}

_HF_MODELS = {
    'hf_flux':  'black-forest-labs/FLUX.1-schnell',
    'hf_sdxl':  'stabilityai/stable-diffusion-xl-base-1.0',
    'hf_sd21':  'stabilityai/stable-diffusion-2-1',
}

AUTO_CASCADE = [
    'gemini_flash',         # Google Gemini Flash — PRINCIPAL
    'pollinations_flux',    # Pollinations FLUX
    'pollinations_turbo',   # Pollinations Turbo
    'pollinations_sd',      # Pollinations SD
    'stability_core',       # Stability AI
    'fal_flux_schnell',     # fal.ai
    'fal_flux_dev',         # fal.ai dev
]


def _motor_name(key: str) -> str:
    info = EXTERNAL_MOTORS.get(key)
    return info[0] if info else key


def _pollinations_fallback(prompt: str, W: int, H: int, seed: int = 0) -> dict:
    return _ext_pollinations(prompt, W, H, seed, 'flux')


def _ext_pollinations(prompt: str, W: int, H: int, seed: int, model: str = 'flux') -> dict:
    """Pollinations.ai — nueva API gen.pollinations.ai con autenticación."""
    if not HAS_REQUESTS:
        return None
    try:
        import urllib.parse as _up
        enc = _up.quote(prompt[:800])

        # Limitar tamaño y aumentar timeout para Render free tier
        _W = min(W, 512)
        _H = min(H, 512)
        url = (f"https://image.pollinations.ai/prompt/{enc}"
               f"?width={_W}&height={_H}&seed={seed}"
               f"&model={model}&nologo=true&enhance=false")

        headers_poll = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        }

        # Agregar autenticación si hay API key configurada
        if _POLLINATIONS_KEY:
            headers_poll['Authorization'] = f'Bearer {_POLLINATIONS_KEY}'

        r = requests.get(url, timeout=120, stream=True, headers=headers_poll)
        if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''):
            ct  = r.headers.get('Content-Type', 'image/jpeg')
            b64 = base64.b64encode(r.content).decode()
            return {'url': f"data:{ct};base64,{b64}", 'type': 'base64',
                    'provider': _motor_name(f'pollinations_{model}'),
                    'engine': f'pollinations_{model}', 'size': f"{W}x{H}"}
        else:
            logger.warning(f"[Pollinations/{model}] HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        logger.warning(f"[Pollinations/{model}] {e}")
    return None


def _ext_huggingface(prompt: str, motor_key: str) -> dict:
    """HuggingFace Inference API — gratis, mas cuota con HUGGINGFACE_TOKEN."""
    if not HAS_REQUESTS:
        return None
    model_id = _HF_MODELS.get(motor_key)
    if not model_id:
        return None

    headers = {'Authorization': f'Bearer {_HF_TOKEN}'} if _HF_TOKEN else {}
    payload = {'inputs': prompt, 'parameters': {'guidance_scale': 7.0}}
    url = f'https://api-inference.huggingface.co/models/{model_id}'
    timeouts = (60, 90)

    for attempt, timeout in enumerate(timeouts, start=1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 503 and attempt < len(timeouts):
                import time
                wait_for = 6
                try:
                    body = r.json()
                    wait_for = max(wait_for, int(float(body.get('estimated_time', wait_for))))
                except Exception:
                    pass
                logger.warning(f"[HuggingFace/{motor_key}] 503, reintentando en {wait_for}s")
                time.sleep(wait_for)
                continue

            if r.status_code == 200:
                content_type = r.headers.get('Content-Type', '')
                if 'image' not in content_type.lower():
                    logger.warning(
                        f"[HuggingFace/{motor_key}] respuesta no es imagen: {content_type}"
                    )
                    return None
                mime = content_type.split(';', 1)[0] or 'image/png'
                b64 = base64.b64encode(r.content).decode()
                return {'url': f"data:{mime};base64,{b64}", 'type': 'base64',
                        'provider': _motor_name(motor_key), 'engine': motor_key}

            logger.warning(f"[HuggingFace/{motor_key}] status={r.status_code}")
            return None
        except Exception as e:
            logger.warning(f"[HuggingFace/{motor_key}] intento {attempt}: {e}")
    return None


def _ext_fal(prompt: str, W: int, H: int, motor_key: str) -> dict:
    """fal.ai — requiere FAL_API_KEY (~$0.003/imagen, muy rapido)."""
    if not HAS_REQUESTS or not _FAL_KEY:
        return None
    endpoints = {
        'fal_flux_schnell': 'https://fal.run/fal-ai/flux/schnell',
        'fal_flux_dev':     'https://fal.run/fal-ai/flux/dev',
    }
    url = endpoints.get(motor_key)
    if not url:
        return None
    try:
        r = requests.post(
            url,
            headers={'Authorization': f'Key {_FAL_KEY}', 'Content-Type': 'application/json'},
            json={'prompt': prompt,
                  'image_size': {'width': min(W, 1024), 'height': min(H, 1024)},
                  'num_images': 1, 'num_inference_steps': 4,
                  'enable_safety_checker': True},
            timeout=60,
        )
        body = r.json()
        if r.status_code == 200 and body.get('images'):
            img_url = body['images'][0]['url']
            img_r   = requests.get(img_url, timeout=30)
            b64     = base64.b64encode(img_r.content).decode()
            return {'url': f"data:image/png;base64,{b64}", 'type': 'base64',
                    'provider': _motor_name(motor_key), 'engine': motor_key}
    except Exception as e:
        logger.warning(f"[fal.ai/{motor_key}] {e}")
    return None


def _ext_stability(prompt: str, W: int, H: int, motor_key: str) -> dict:
    """Stability AI REST API — STABILITY_API_KEY (plan gratis disponible)."""
    if not HAS_REQUESTS or not _STABILITY_KEY:
        return None
    endpoints = {
        'stability_core': 'https://api.stability.ai/v2beta/stable-image/generate/core',
        'stability_sd3':  'https://api.stability.ai/v2beta/stable-image/generate/sd3',
    }
    url = endpoints.get(motor_key, endpoints['stability_core'])
    try:
        r = requests.post(
            url,
            headers={'Authorization': f'Bearer {_STABILITY_KEY}', 'Accept': 'image/*'},
            files={'none': ''},
            data={'prompt': prompt, 'output_format': 'png',
                  'width': min(W, 1024), 'height': min(H, 1024)},
            timeout=60,
        )
        if r.status_code == 200:
            b64 = base64.b64encode(r.content).decode()
            return {'url': f"data:image/png;base64,{b64}", 'type': 'base64',
                    'provider': _motor_name(motor_key), 'engine': motor_key}
        logger.warning(f"[Stability/{motor_key}] HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        logger.warning(f"[Stability/{motor_key}] {e}")
    return None


def _ext_gemini(prompt: str, W: int, H: int) -> dict:
    """Google Gemini imagen — gratis con GEMINI_API_KEY."""
    if not HAS_REQUESTS or not _GEMINI_KEY:
        return None

    # Modelos de imagen reales disponibles con esta API key
    gemini_models = [
        'gemini-3.1-flash-image',
        'gemini-2.5-flash-image',
        'gemini-3-pro-image',
        'gemini-3.1-flash-image-preview',
    ]

    for model_id in gemini_models:
        try:
            r = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/'
                f'{model_id}:generateContent?key={_GEMINI_KEY}',
                json={
                    'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {
                        'responseModalities': ['IMAGE', 'TEXT'],
                    }
                },
                timeout=60,
            )
            if r.status_code == 200:
                candidates = r.json().get('candidates', [])
                for candidate in candidates:
                    for part in candidate.get('content', {}).get('parts', []):
                        if 'inlineData' in part:
                            b64 = part['inlineData']['data']
                            mt  = part['inlineData'].get('mimeType', 'image/png')
                            logger.info(f"[Gemini] Imagen generada con {model_id}")
                            return {
                                'url': f"data:{mt};base64,{b64}",
                                'type': 'base64',
                                'provider': 'Gemini Image',
                                'engine': 'gemini_flash',
                                'size': f"{W}x{H}"
                            }
            else:
                logger.warning(f"[Gemini/{model_id}] HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.warning(f"[Gemini/{model_id}] {e}")
    return None


def _size_from_dims(W: int, H: int) -> str:
    if W == H: return '512' if W <= 512 else 'square'
    return 'landscape' if W > H else 'portrait'


def _ext_single(motor_key: str, prompt: str, W: int, H: int, seed: int,
                style: str = 'realistic', quality: str = 'standard',
                user_id: int = None) -> dict:
    """Dispatcher central — llama al motor correcto por ID."""
    if motor_key == 'cicdream':
        if not _CICDREAM_OK:
            return None
        r = cicdream_generate(
            prompt=prompt, style=style, size=_size_from_dims(W, H),
            quality=quality, seed=seed, count=1, user_id=user_id,
        )
        if r.get('success') and r.get('images'):
            img = r['images'][0]
            img['generation_id'] = r.get('generation_id', 0)
            return img
        return None
    elif motor_key.startswith('pollinations_'):
        return _ext_pollinations(prompt, W, H, seed, motor_key.replace('pollinations_', ''))
    elif motor_key.startswith('hf_'):
        return _ext_huggingface(prompt, motor_key)
    elif motor_key.startswith('fal_'):
        return _ext_fal(prompt, W, H, motor_key)
    elif motor_key.startswith('stability_'):
        return _ext_stability(prompt, W, H, motor_key)
    elif motor_key == 'gemini_flash':
        return _ext_gemini(prompt, W, H)
    return None


def _run_external_cascade(prompt: str, W: int, H: int,
                           seed: int, count: int,
                           force_motor: str = None,
                           style: str = 'realistic',
                           quality: str = 'standard',
                           user_id: int = None) -> list:
    """
    Cascada de motores externos en orden de prioridad AUTO_CASCADE.
    Si force_motor esta definido, usa solo ese motor.
    """
    motors_to_try = [force_motor] if force_motor else AUTO_CASCADE
    for motor_key in motors_to_try:
        try:
            first = _ext_single(motor_key, prompt, W, H, seed,
                                style=style, quality=quality, user_id=user_id)
            if first:
                results = [first]
                for i in range(1, count):
                    extra = _ext_single(motor_key, prompt, W, H, seed + i * 37,
                                        style=style, quality=quality, user_id=user_id)
                    results.append(extra if extra else first)
                logger.info(f"[Cascade] Motor usado: {motor_key} — {_motor_name(motor_key)}")
                return results
        except Exception as e:
            logger.warning(f"[Cascade] {motor_key} fallo: {e}")
            if force_motor:
                break
            continue
    return []
