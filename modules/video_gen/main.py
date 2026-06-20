"""
CicVideo — Motor Propio de Generación de Video
Cic_IA · Módulo video_gen · v1.0.0

Arquitectura de motores (cascada AUTO):
  1. hf_zeroscope      → HuggingFace ZeroScope v2 (gratuito con token)
  2. replicate_zero    → Replicate ZeroScope (gratuito con cuenta)
  3. pollinations_img  → Pollinations: secuencia de imágenes → GIF
  4. cicvideo_math     → Motor propio: matemáticas + PIL (siempre disponible)

Características:
  - Texto → Video
  - Imagen de referencia → Video animado
  - Resoluciones: 480p / 720p / 1080p
  - Duraciones: 3s / 5s / 8s / 15s
  - Efectos: wave / particles / zoom / flow / gradient / auto
  - Salida: GIF animado o WebP animado (sin dependencias de ffmpeg)
  - Sistema de feedback y aprendizaje integrado
"""

import os
import io
import math
import time
import base64
import logging
import requests
import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger("cic_ia.video_gen")

# ─── Configuración de resoluciones y duraciones ──────────────────────────────

RESOLUTIONS = {
    "480p":  (854,  480),
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
}

# (segundos, fps) → n_frames = seg * fps
# FPS bajos para archivos más pequeños y generación más rápida
DURATIONS = {
    "3s":  (3,  8),    # 24  frames — rápido
    "5s":  (5,  8),    # 40  frames — estándar
    "8s":  (8,  10),   # 80  frames — largo
    "15s": (15, 8),    # 120 frames — máximo
}

CASCADE_AUTO = ["hf_zeroscope", "replicate_zero", "pollinations_img", "cicvideo_math"]

# ─── Paleta semántica para motor propio ──────────────────────────────────────

_PALETTES = {
    "ocean":   [(0,105,148),(70,130,180),(95,158,160),(0,191,255),(25,25,112)],
    "sunset":  [(255,69,0),(255,140,0),(255,215,0),(255,99,71),(220,20,60)],
    "night":   [(10,10,40),(25,25,112),(72,61,139),(123,104,238),(20,20,60)],
    "fire":    [(200,20,0),(255,69,0),(255,140,0),(255,215,0),(150,10,0)],
    "space":   [(0,0,0),(20,20,80),(72,61,139),(138,43,226),(75,0,130)],
    "forest":  [(20,60,20),(34,85,34),(85,107,47),(107,142,35),(46,139,87)],
    "snow":    [(220,240,255),(240,248,255),(176,196,222),(200,220,240),(135,206,250)],
    "urban":   [(50,50,60),(90,90,100),(130,130,140),(180,180,190),(60,60,70)],
    "nature":  [(34,120,34),(80,140,60),(100,160,80),(140,180,100),(60,100,40)],
    "default": [(40,80,160),(80,120,200),(120,160,220),(60,100,180),(20,60,140)],
}

_KEYWORD_MAP = {
    "ocean": ["mar","ocean","agua","playa","río","lago","piscina","wave","lluvia"],
    "sunset": ["sol","atardecer","amanecer","sunset","naranja","dorado","tarde"],
    "night": ["noche","night","oscuro","luna","estrellas","dark","medianoche"],
    "fire": ["fuego","fire","llama","calor","lava","explosión","incendio"],
    "space": ["espacio","galaxia","cosmos","universo","space","planet","nasa","nebula"],
    "forest": ["bosque","forest","árbol","selva","naturaleza","verde","jungle"],
    "snow": ["nieve","snow","frío","hielo","invierno","blanco","glaciar"],
    "urban": ["ciudad","urban","calle","edificio","metro","gris","concreto"],
    "nature": ["campo","flores","prado","jardín","nature","montaña","primavera"],
}

def _detect_palette(prompt: str) -> list:
    p = prompt.lower()
    for key, words in _KEYWORD_MAP.items():
        if any(w in p for w in words):
            return _PALETTES[key]
    return _PALETTES["default"]

def _detect_effect(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ["agua","ola","wave","río","lluvia","mar","flujo"]):
        return "wave"
    if any(w in p for w in ["espacio","galaxia","partícula","estrella","cosmos","universe"]):
        return "particles"
    if any(w in p for w in ["zoom","acercar","pulso","corazón","latido","pulse"]):
        return "zoom"
    if any(w in p for w in ["flujo","lava","neblina","niebla","flow","humo"]):
        return "flow"
    return "gradient"


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR PROPIO — CicVideoMath
# ─────────────────────────────────────────────────────────────────────────────

class CicVideoMath:
    """
    Motor matemático propio de CicVideo.

    Genera animaciones frame-a-frame usando:
      · Ondas sinusoidales (wave)
      · Campo de partículas pseudoaleatorio (particles)
      · Pulso/zoom radial (zoom)
      · Flujo tipo Perlin simplificado (flow)
      · Gradiente rotacional (gradient)

    Sin dependencias externas — siempre disponible en cualquier hosting.
    Aprende de la paleta semántica del prompt para colorear el video.
    """

    version = "1.0.0"

    # ── Generadores de frame ──────────────────────────────────────────────

    def _frame_wave(self, W, H, t, c1, c2):
        xs = np.linspace(0, 2 * np.pi, W, dtype=np.float32)
        ys = np.linspace(0, 2 * np.pi, H, dtype=np.float32)
        X, Y = np.meshgrid(xs, ys)
        wave = (np.sin(X + t * 3.0) +
                np.cos(Y * 0.7 + t * 2.0) +
                np.sin((X + Y) * 0.5 + t * 1.5)) / 3.0
        mask = ((wave + 1.0) / 2.0)[:, :, np.newaxis]
        arr = (c1 * (1 - mask) + c2 * mask).astype(np.uint8)
        return arr

    def _frame_particles(self, W, H, t, palette):
        arr = np.zeros((H, W, 3), dtype=np.uint8)
        arr[:] = palette[0]
        rng = np.random.default_rng(int(t * 1000) % 65536)
        n = 80
        px = (rng.random(n) * W).astype(int)
        py = (rng.random(n) * H).astype(int)
        radii = rng.integers(3, 18, n)
        for i in range(n):
            col = np.array(palette[i % len(palette)], dtype=np.float32)
            r = int(radii[i])
            x0, y0 = int(px[i]), int(py[i])
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    dist2 = dx * dx + dy * dy
                    if dist2 <= r * r:
                        nx, ny = x0 + dx, y0 + dy
                        if 0 <= nx < W and 0 <= ny < H:
                            alpha = 1.0 - math.sqrt(dist2) / (r + 1)
                            arr[ny, nx] = np.clip(
                                arr[ny, nx] * (1 - alpha) + col * alpha, 0, 255
                            ).astype(np.uint8)
        return arr

    def _frame_zoom(self, W, H, t, c1, c2):
        pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi)
        xs = np.linspace(-1, 1, W, dtype=np.float32) * (1 + pulse * 0.4)
        ys = np.linspace(-1, 1, H, dtype=np.float32) * (1 + pulse * 0.4)
        X, Y = np.meshgrid(xs, ys)
        dist = np.sqrt(X ** 2 + Y ** 2)
        mask = np.clip(dist, 0, 1)[:, :, np.newaxis]
        return (c1 * (1 - mask) + c2 * mask).astype(np.uint8)

    def _frame_flow(self, W, H, t, c1, c2):
        xs = np.linspace(0, 4, W, dtype=np.float32)
        ys = np.linspace(0, 4, H, dtype=np.float32)
        X, Y = np.meshgrid(xs, ys)
        flow = (np.sin(X * 1.5 + t * 2) *
                np.cos(Y + t * 1.3) *
                np.sin(X * 0.8 - Y * 0.6 + t * 2.5))
        mask = ((flow + 1.0) / 2.0)[:, :, np.newaxis]
        return (c1 * (1 - mask) + c2 * mask).astype(np.uint8)

    def _frame_gradient(self, W, H, t, c1, c2):
        angle = t * 2 * math.pi
        ca, sa = math.cos(angle), math.sin(angle)
        xs = np.linspace(-1, 1, W, dtype=np.float32)
        ys = np.linspace(-1, 1, H, dtype=np.float32)
        X, Y = np.meshgrid(xs, ys)
        rot = X * ca - Y * sa
        mask = ((rot + 1.0) / 2.0)[:, :, np.newaxis]
        return (c1 * (1 - mask) + c2 * mask).astype(np.uint8)

    # ── Animación sobre imagen de referencia ─────────────────────────────

    def _animate_ref(self, ref: Image.Image, W, H, t, effect):
        img = ref.resize((W, H), Image.LANCZOS).convert("RGB")
        arr = np.array(img, dtype=np.float32)

        if effect == "wave":
            new = np.zeros_like(arr)
            for y in range(H):
                off = int(20 * math.sin(2 * math.pi * (y / H + t)))
                for x in range(W):
                    new[y, x] = arr[y, (x + off) % W]
            arr = new

        elif effect == "zoom":
            pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi)
            scale = 1.0 + pulse * 0.10
            nw, nh = int(W * scale), int(H * scale)
            big = Image.fromarray(arr.astype(np.uint8)).resize((nw, nh), Image.LANCZOS)
            l, tp = (nw - W) // 2, (nh - H) // 2
            arr = np.array(big.crop((l, tp, l + W, tp + H)), dtype=np.float32)

        elif effect == "flow":
            sx, sy = int(t * 40 % W), int(t * 15 % H)
            arr = np.roll(np.roll(arr, sx, axis=1), sy, axis=0)

        elif effect == "particles":
            rng = np.random.default_rng(42)
            noise = rng.random((H, W, 3)).astype(np.float32) * 30
            p = 0.5 + 0.5 * math.sin(t * 4 * math.pi)
            arr = arr + noise * p

        else:  # gradient / default — Ken Burns lento
            sx = int(t * 25 % W)
            arr = np.roll(arr, sx, axis=1)

        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

    # ── Overlay de texto ─────────────────────────────────────────────────

    def _add_text(self, img: Image.Image, text: str, t: float) -> Image.Image:
        if not text:
            return img
        draw = ImageDraw.Draw(img)
        w, h = img.size
        label = text[:72] + ("…" if len(text) > 72 else "")
        fade = min(1.0, t * 4)
        alpha = int(fade * 220)
        # sombra
        draw.text((w // 2 + 1, h - 44 + 1), label, fill=(0, 0, 0), anchor="mm")
        draw.text((w // 2,     h - 44),     label, fill=(255, 255, 255), anchor="mm")
        return img

    # ── Generador principal de frames ─────────────────────────────────────

    def generate_frames(self, prompt: str, W: int, H: int,
                        n_frames: int, fps: int,
                        effect: str = "auto",
                        ref: Image.Image = None) -> list:
        palette = _detect_palette(prompt)
        if effect == "auto":
            effect = _detect_effect(prompt)

        c1 = np.array(palette[0], dtype=np.float32)
        c2 = np.array(palette[min(2, len(palette) - 1)], dtype=np.float32)

        frames = []
        for i in range(n_frames):
            t = i / max(n_frames - 1, 1)

            if ref is not None:
                frame_arr = None
                pil_frame = self._animate_ref(ref, W, H, t, effect)
            else:
                if effect == "wave":
                    frame_arr = self._frame_wave(W, H, t, c1, c2)
                elif effect == "particles":
                    frame_arr = self._frame_particles(W, H, t, palette)
                elif effect == "zoom":
                    frame_arr = self._frame_zoom(W, H, t, c1, c2)
                elif effect == "flow":
                    frame_arr = self._frame_flow(W, H, t, c1, c2)
                else:
                    frame_arr = self._frame_gradient(W, H, t, c1, c2)
                pil_frame = Image.fromarray(frame_arr, "RGB")

            pil_frame = self._add_text(pil_frame, prompt, t)
            frames.append(pil_frame)

        return frames

    # ── Exportadores ─────────────────────────────────────────────────────

    def to_gif(self, frames: list, fps: int) -> bytes:
        buf = io.BytesIO()
        dur = int(1000 / fps)
        frames[0].save(
            buf, format="GIF", save_all=True,
            append_images=frames[1:], duration=dur, loop=0, optimize=True
        )
        return buf.getvalue()

    def to_webp(self, frames: list, fps: int) -> bytes:
        # Reducir tamaño para WebP animado
        resized = [f.resize(
            (min(f.width, 854), min(f.height, 480)), Image.LANCZOS
        ) if f.width > 854 else f for f in frames]
        buf = io.BytesIO()
        dur = int(1000 / fps)
        resized[0].save(
            buf, format="WEBP", save_all=True,
            append_images=resized[1:], duration=dur, loop=0, quality=75
        )
        return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# MOTORES EXTERNOS GRATUITOS
# ─────────────────────────────────────────────────────────────────────────────

class HFZeroscope:
    """
    Motor: HuggingFace ZeroScope v2 (576w)
    Modelo: cerspense/zeroscope_v2_576w
    Coste: gratuito con HUGGINGFACE_TOKEN
    Límite: 24 frames, 576x320
    Aprende de: técnica open-source de video difusión latente
    """
    URL = "https://api-inference.huggingface.co/models/cerspense/zeroscope_v2_576w"

    def __init__(self):
        self.token = os.environ.get("HUGGINGFACE_TOKEN", "")

    def available(self) -> bool:
        return bool(self.token)

    def generate(self, prompt: str, n_frames: int) -> dict:
        if not self.available():
            return {"success": False, "error": "HUGGINGFACE_TOKEN no configurado"}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": prompt,
            "parameters": {
                "num_frames": min(n_frames, 24),
                "num_inference_steps": 20,
                "guidance_scale": 7.5,
                "width": 576,
                "height": 320,
            }
        }
        try:
            r = requests.post(self.URL, headers=headers, json=payload, timeout=90)
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and ("video" in ct or "octet" in ct):
                return {
                    "success": True, "motor": "hf_zeroscope",
                    "data": base64.b64encode(r.content).decode(), "format": "mp4"
                }
            if r.status_code == 503:
                return {"success": False, "error": "Modelo HF cargando (503), reintenta en ~30s"}
            return {"success": False, "error": f"HF HTTP {r.status_code}: {r.text[:150]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ReplicateZero:
    """
    Motor: Replicate — ZeroScope v2
    Modelo: anotherjesse/zeroscope-v2-xl (o cerspense/zeroscope-v2-576w)
    Coste: gratuito con cuenta Replicate (cuota limitada mensual)
    Aprende de: API de predicciones asíncronas de Replicate
    """
    def __init__(self):
        self.token = os.environ.get("REPLICATE_API_TOKEN", "")

    def available(self) -> bool:
        return bool(self.token)

    def generate(self, prompt: str, W: int, H: int, n_frames: int) -> dict:
        if not self.available():
            return {"success": False, "error": "REPLICATE_API_TOKEN no configurado"}
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json"
        }
        # ZeroScope 576w — resolución máxima segura en free tier
        payload = {
            "version": "9f747673945c62801b13b84701c783929c0ee784e4748ec062204894dda1a351",
            "input": {
                "prompt": prompt,
                "num_frames": min(n_frames, 24),
                "width": min(W, 576),
                "height": min(H, 320),
                "num_inference_steps": 20,
                "guidance_scale": 7.5,
                "fps": 8,
            }
        }
        try:
            r = requests.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers, json=payload, timeout=30
            )
            if r.status_code != 201:
                return {"success": False, "error": f"Replicate {r.status_code}: {r.text[:150]}"}
            pred_id = r.json().get("id")
            poll = f"https://api.replicate.com/v1/predictions/{pred_id}"
            # Polling máx 90s
            for _ in range(18):
                time.sleep(5)
                pr = requests.get(poll, headers=headers, timeout=15)
                pd = pr.json()
                if pd.get("status") == "succeeded":
                    out = pd.get("output")
                    url = out if isinstance(out, str) else (out[0] if out else None)
                    if url:
                        vr = requests.get(url, timeout=30)
                        return {
                            "success": True, "motor": "replicate_zero",
                            "data": base64.b64encode(vr.content).decode(), "format": "mp4"
                        }
                elif pd.get("status") in ("failed", "canceled"):
                    return {"success": False, "error": f"Replicate falló: {pd.get('error')}"}
            return {"success": False, "error": "Timeout Replicate (>90s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class PollinationsImg:
    """
    Motor: Pollinations.ai — secuencia de imágenes → GIF
    API: https://image.pollinations.ai/prompt/{text}
    Coste: completamente gratuito, sin autenticación
    Estrategia: genera N imágenes con variación de seed y las convierte a GIF
    Aprende de: técnica de animación por interpolación de frames
    """
    BASE = "https://image.pollinations.ai/prompt"

    def available(self) -> bool:
        return True  # sin autenticación requerida

    def generate(self, prompt: str, n_frames: int = 8, W: int = 512, H: int = 288) -> dict:
        try:
            import urllib.parse
            frames = []
            # Limitar en Pollinations para velocidad
            target = min(n_frames, 10)
            for i in range(target):
                safe = urllib.parse.quote(f"{prompt}, frame {i+1} of {target}", safe="")
                url = f"{self.BASE}/{safe}?width={min(W,512)}&height={min(H,288)}&seed={i*13+7}&nologo=true"
                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200:
                        img = Image.open(io.BytesIO(r.content)).convert("RGB")
                        frames.append(img)
                except Exception:
                    continue

            if len(frames) < 3:
                return {"success": False, "error": f"Solo {len(frames)} frames de Pollinations"}

            # Duplicar frames para suavizar movimiento
            smooth = []
            for j in range(len(frames) - 1):
                smooth.append(frames[j])
                # frame intermedio interpolado
                a = np.array(frames[j], dtype=np.float32)
                b = np.array(frames[j + 1], dtype=np.float32)
                mid = Image.fromarray(((a + b) / 2).astype(np.uint8), "RGB")
                smooth.append(mid)
            smooth.append(frames[-1])

            buf = io.BytesIO()
            smooth[0].save(
                buf, format="GIF", save_all=True,
                append_images=smooth[1:], duration=150, loop=0, optimize=True
            )
            return {
                "success": True, "motor": "pollinations_img",
                "data": base64.b64encode(buf.getvalue()).decode(), "format": "gif"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class VideoGeneratorModule:
    """
    Orquestador principal de CicVideo.
    Gestiona cascada, parámetros, validación y respuesta unificada.
    """

    def __init__(self):
        self.math       = CicVideoMath()
        self.hf         = HFZeroscope()
        self.replicate  = ReplicateZero()
        self.pollinations = PollinationsImg()

    # ── API pública ───────────────────────────────────────────────────────

    def generate(
        self,
        prompt:     str,
        resolution: str = "480p",
        duration:   str = "5s",
        motor:      str = "auto",
        effect:     str = "auto",
        ref_b64:    str = None,
    ) -> dict:
        """
        Genera un video.

        Returns:
            {
                success: bool,
                data: str (base64),
                format: 'gif'|'webp'|'mp4',
                motor: str,
                resolution: str,
                duration: str,
                frames: int,
                fps: int,
                effect_used: str,
                generation_time: float,
                prompt_enhanced: str,
            }
        """
        t0 = time.time()

        # Validar
        if resolution not in RESOLUTIONS:
            resolution = "480p"
        if duration not in DURATIONS:
            duration = "5s"
        if not prompt or not prompt.strip():
            return {"success": False, "error": "El prompt no puede estar vacío"}

        W, H = RESOLUTIONS[resolution]
        secs, fps = DURATIONS[duration]
        n_frames = secs * fps

        # Imagen de referencia
        ref_img = None
        if ref_b64:
            try:
                raw = base64.b64decode(ref_b64)
                ref_img = Image.open(io.BytesIO(raw)).convert("RGB")
            except Exception as e:
                logger.warning(f"CicVideo: no se pudo decodificar ref_image: {e}")

        # Mejorar prompt
        enhanced = self._enhance_prompt(prompt)

        # Resolver efecto
        eff = effect if effect != "auto" else _detect_effect(prompt)

        # Ejecutar cascada
        result = self._cascade(motor, enhanced, W, H, n_frames, fps, eff, ref_img)

        # Metadata
        result["resolution"]       = resolution
        result["duration"]         = duration
        result["frames"]           = n_frames
        result["fps"]              = fps
        result["effect_used"]      = eff
        result["generation_time"]  = round(time.time() - t0, 2)
        result["prompt_enhanced"]  = enhanced
        result["prompt_original"]  = prompt

        return result

    def info(self) -> dict:
        return {
            "module":   "CicVideo",
            "version":  "1.0.0",
            "motors": {
                "cicvideo_math":  {"available": True, "type": "propio",  "cost": "gratuito"},
                "hf_zeroscope":   {"available": self.hf.available(),         "type": "externo", "cost": "gratuito (HF token)"},
                "replicate_zero": {"available": self.replicate.available(),   "type": "externo", "cost": "gratuito (cuota)"},
                "pollinations":   {"available": True, "type": "externo",  "cost": "gratuito (sin key)"},
            },
            "resolutions":  list(RESOLUTIONS.keys()),
            "durations":    list(DURATIONS.keys()),
            "effects":      ["auto", "wave", "particles", "zoom", "flow", "gradient"],
            "cascade_auto": CASCADE_AUTO,
            "supports_ref_image": True,
            "output_formats": ["gif", "webp", "mp4"],
        }

    # ── Cascada interna ───────────────────────────────────────────────────

    def _cascade(self, motor, prompt, W, H, n_frames, fps, effect, ref_img) -> dict:
        if motor == "auto":
            order = CASCADE_AUTO
        elif motor == "cicvideo_math":
            order = ["cicvideo_math"]
        elif motor == "hf_zeroscope":
            order = ["hf_zeroscope", "cicvideo_math"]
        elif motor == "replicate":
            order = ["replicate_zero", "cicvideo_math"]
        elif motor == "pollinations":
            order = ["pollinations_img", "cicvideo_math"]
        else:
            order = CASCADE_AUTO

        for name in order:
            logger.info(f"CicVideo: probando motor '{name}'")
            res = self._try(name, prompt, W, H, n_frames, fps, effect, ref_img)
            if res.get("success"):
                res["motor"] = name
                return res
            logger.warning(f"CicVideo: '{name}' falló → {res.get('error','?')}")

        return {"success": False, "error": "Todos los motores fallaron"}

    def _try(self, name, prompt, W, H, n_frames, fps, effect, ref_img) -> dict:
        if name == "hf_zeroscope":
            return self.hf.generate(prompt, n_frames)

        elif name == "replicate_zero":
            return self.replicate.generate(prompt, W, H, n_frames)

        elif name == "pollinations_img":
            # Pollinations solo en resoluciones ≤ 480p para velocidad
            if W > 854:
                return {"success": False, "error": "Pollinations limitado a 480p"}
            return self.pollinations.generate(prompt, n_frames, W, H)

        elif name == "cicvideo_math":
            return self._math_generate(prompt, W, H, n_frames, fps, effect, ref_img)

        return {"success": False, "error": f"Motor desconocido: {name}"}

    def _math_generate(self, prompt, W, H, n_frames, fps, effect, ref_img) -> dict:
        try:
            # Limitar frames en resoluciones altas para evitar OOM en Render free
            if W >= 1920 and n_frames > 32:
                n_frames = 32
            elif W >= 1280 and n_frames > 60:
                n_frames = 60

            frames = self.math.generate_frames(
                prompt=prompt, W=W, H=H,
                n_frames=n_frames, fps=fps,
                effect=effect, ref=ref_img
            )

            # Intentar WebP primero (mejor calidad), fallback a GIF
            try:
                data = self.math.to_webp(frames, fps)
                fmt = "webp"
            except Exception:
                data = self.math.to_gif(frames, fps)
                fmt = "gif"

            return {
                "success": True,
                "data":    base64.b64encode(data).decode(),
                "format":  fmt,
                "frames_actual": len(frames),
            }
        except Exception as e:
            logger.error(f"CicVideoMath error: {e}")
            return {"success": False, "error": str(e)}

    def _enhance_prompt(self, prompt: str) -> str:
        extras = "cinematic, smooth motion, high quality, professional"
        if "cinematic" not in prompt.lower():
            return f"{prompt.strip()}, {extras}"
        return prompt.strip()
