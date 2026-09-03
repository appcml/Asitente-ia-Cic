"""
modules/audio_studio/main.py
==============================
Audio Studio — Motor principal.

Funciones:
  • TTS  (texto → audio)  : gTTS (gratis) + ElevenLabs (premium) + Edge-TTS (gratis, HD)
  • STT  (audio → texto)  : OpenAI Whisper API
  • Podcast: combina segmentos TTS para generar un episodio completo
  • Efectos: silencio entre bloques, intro/outro

Variables de entorno opcionales:
  ELEVENLABS_API_KEY   → activa voces ElevenLabs
  OPENAI_API_KEY       → activa Whisper STT
"""

import os
import io
import base64
import logging
import time
import json
import re
import tempfile
from typing import Optional

import requests

logger = logging.getLogger("cic_ia.audio_studio")

# ──────────────────────────────────────────────────────────────────
# CONSTANTES
# ──────────────────────────────────────────────────────────────────

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY", "")

# Voces ElevenLabs más populares (id → nombre amigable)
ELEVENLABS_VOICES = {
    "21m00Tcm4TlvDq8ikWAM": "Rachel (EN, femenina)",
    "AZnzlk1XvdvUeBnXmlld": "Domi (EN, femenina)",
    "EXAVITQu4vr4xnSDxMaL": "Bella (EN, femenina)",
    "ErXwobaYiN019PkySvjV": "Antoni (EN, masculina)",
    "MF3mGyEYCl7XYWbV9V6O": "Elli (EN, femenina)",
    "TxGEqnHWrfWFTfGW9XjX": "Josh (EN, masculina)",
    "VR6AewLTigWG4xSOukaG": "Arnold (EN, masculina)",
    "pNInz6obpgDQGcFmaJgB": "Adam (EN, masculina)",
    "yoZ06aMxZJJ28mfd3POQ": "Sam (EN, masculina)",
}

# Idiomas soportados por gTTS
GTTS_LANGS = {
    "es": "Español",
    "en": "Inglés",
    "pt": "Portugués",
    "fr": "Francés",
    "de": "Alemán",
    "it": "Italiano",
    "ja": "Japonés",
    "zh": "Chino",
}

# Voces Edge-TTS (gratuitas, HD, sin API key)
EDGE_VOICES = {
    "es-CL-CatalinaNeural":   "Catalina (ES-CL, femenina) — Español Chile",
    "es-CL-LorenzoNeural":    "Lorenzo (ES-CL, masculino) — Español Chile",
    "es-ES-ElviraNeural":     "Elvira (ES-ES, femenina)",
    "es-ES-AlvaroNeural":     "Álvaro (ES-ES, masculino)",
    "es-MX-DaliaNeural":      "Dalia (ES-MX, femenina)",
    "es-MX-JorgeNeural":      "Jorge (ES-MX, masculino)",
    "en-US-JennyNeural":      "Jenny (EN-US, femenina)",
    "en-US-GuyNeural":        "Guy (EN-US, masculino)",
    "en-GB-SoniaNeural":      "Sonia (EN-GB, femenina)",
    "pt-BR-FranciscaNeural":  "Francisca (PT-BR, femenina)",
}


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

def _available_engines() -> list:
    engines = ["gtts"]  # siempre disponible
    if ELEVENLABS_API_KEY:
        engines.append("elevenlabs")
    engines.append("edge_tts")  # no requiere key pero sí asyncio
    return engines


# ──────────────────────────────────────────────────────────────────
# TTS
# ──────────────────────────────────────────────────────────────────

def tts_gtts(text: str, lang: str = "es", slow: bool = False) -> bytes:
    """Genera audio MP3 con gTTS (Google TTS, gratis)."""
    try:
        from gtts import gTTS
    except ImportError:
        raise RuntimeError("gTTS no instalado. Agrega 'gtts' a requirements.txt")

    buf = io.BytesIO()
    tts = gTTS(text=text, lang=lang, slow=slow)
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


def tts_edge(text: str, voice: str = "es-CL-CatalinaNeural", rate: str = "+0%", volume: str = "+0%") -> bytes:
    """
    Genera audio MP3 con edge-tts (Microsoft, gratis, HD).
    Requiere: pip install edge-tts
    """
    try:
        import asyncio
        import edge_tts
    except ImportError:
        raise RuntimeError("edge-tts no instalado. Agrega 'edge-tts' a requirements.txt")

    async def _gen():
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        return buf.read()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(_gen())
    except RuntimeError:
        # En Flask con hilos, crear loop nuevo
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_gen())


def tts_elevenlabs(text: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM",
                   model: str = "eleven_multilingual_v2",
                   stability: float = 0.5, similarity: float = 0.75) -> bytes:
    """Genera audio MP3 con ElevenLabs (premium)."""
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY no configurada")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs error {resp.status_code}: {resp.text[:200]}")
    return resp.content


def generate_tts(text: str, engine: str = "gtts", **kwargs) -> dict:
    """
    Punto de entrada unificado para TTS.
    Retorna dict con audio_b64, formato, engine, duración estimada.
    """
    t0 = time.time()
    text = text.strip()
    if not text:
        return {"success": False, "error": "El texto no puede estar vacío"}

    if len(text) > 5000:
        return {"success": False, "error": "Texto demasiado largo (máx 5000 chars). Usa el modo podcast para textos largos."}

    try:
        if engine == "elevenlabs":
            audio = tts_elevenlabs(text, **kwargs)
            fmt = "mp3"
        elif engine == "edge_tts":
            voice = kwargs.get("voice", "es-CL-CatalinaNeural")
            rate  = kwargs.get("rate", "+0%")
            vol   = kwargs.get("volume", "+0%")
            audio = tts_edge(text, voice=voice, rate=rate, volume=vol)
            fmt = "mp3"
        else:  # gtts (default)
            lang = kwargs.get("lang", "es")
            slow = kwargs.get("slow", False)
            audio = tts_gtts(text, lang=lang, slow=slow)
            fmt = "mp3"

        elapsed = round(time.time() - t0, 2)
        words   = len(text.split())
        est_dur = round(words / 2.5, 1)  # ~2.5 palabras/seg

        return {
            "success":     True,
            "audio_b64":   _b64(audio),
            "format":      fmt,
            "engine":      engine,
            "chars":       len(text),
            "words":       words,
            "est_duration": est_dur,
            "gen_time":    elapsed,
        }
    except Exception as e:
        logger.error(f"TTS error ({engine}): {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ──────────────────────────────────────────────────────────────────
# STT (Speech-to-Text)
# ──────────────────────────────────────────────────────────────────

def transcribe_whisper(audio_bytes: bytes, filename: str = "audio.mp3",
                       language: Optional[str] = None) -> dict:
    """
    Transcribe audio usando OpenAI Whisper API.
    Soporta: mp3, mp4, mpeg, mpga, m4a, wav, webm (máx 25MB).
    """
    if not OPENAI_API_KEY:
        return {"success": False, "error": "OPENAI_API_KEY no configurada para STT/Whisper"}

    if len(audio_bytes) > 25 * 1024 * 1024:
        return {"success": False, "error": "Audio demasiado grande (máx 25MB para Whisper)"}

    t0 = time.time()
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    files = {"file": (filename, audio_bytes, "audio/mpeg")}
    data  = {"model": "whisper-1", "response_format": "verbose_json"}
    if language:
        data["language"] = language

    try:
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)
        if resp.status_code != 200:
            return {"success": False, "error": f"Whisper error {resp.status_code}: {resp.text[:300]}"}

        result  = resp.json()
        elapsed = round(time.time() - t0, 2)

        return {
            "success":   True,
            "text":      result.get("text", ""),
            "language":  result.get("language", ""),
            "duration":  result.get("duration", 0),
            "segments":  result.get("segments", []),
            "gen_time":  elapsed,
        }
    except Exception as e:
        logger.error(f"STT Whisper error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ──────────────────────────────────────────────────────────────────
# PODCAST GENERATOR
# ──────────────────────────────────────────────────────────────────

def split_into_segments(text: str, max_chars: int = 800) -> list[str]:
    """
    Divide texto largo en segmentos naturales (por párrafos/oraciones)
    para generar audio por bloques y luego concatenar.
    """
    # Intentar dividir por párrafos primero
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    segments = []
    current  = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                segments.append(current)
            # Si el párrafo es muy largo, dividir por oraciones
            if len(para) > max_chars:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                sent_buf  = ""
                for s in sentences:
                    if len(sent_buf) + len(s) + 1 <= max_chars:
                        sent_buf = (sent_buf + " " + s).strip()
                    else:
                        if sent_buf:
                            segments.append(sent_buf)
                        sent_buf = s
                if sent_buf:
                    segments.append(sent_buf)
                current = ""
            else:
                current = para

    if current:
        segments.append(current)

    return segments


def _silence_mp3(ms: int = 500) -> bytes:
    """Genera silencio como bytes MP3 vacío (frame nulo)."""
    # MP3 frame de silencio: 128kbps, 44100Hz
    # Usamos gTTS con espacio para obtener silencio real
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        gTTS(text=" ", lang="es").write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return b""


def generate_podcast(script: str, engine: str = "gtts", host_voice: dict = None,
                     guest_voice: dict = None, format_type: str = "monologue",
                     title: str = "Podcast", **kwargs) -> dict:
    """
    Genera un episodio de podcast completo.

    Formatos:
      - monologue: un solo narrador
      - dialogue: dos voces alternadas (separadas por líneas con "HOST:" / "GUEST:")

    Parámetros de voz: igual que generate_tts().
    """
    t0 = time.time()

    if not script.strip():
        return {"success": False, "error": "El guión no puede estar vacío"}

    if len(script) > 50000:
        return {"success": False, "error": "Guión demasiado largo (máx 50.000 chars)"}

    host_voice  = host_voice  or {}
    guest_voice = guest_voice or {}

    audio_parts = []
    segments    = []
    errors      = []

    try:
        if format_type == "dialogue":
            # Parsear líneas HOST: ... / GUEST: ...
            lines = script.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.upper().startswith("HOST:"):
                    text_part = line[5:].strip()
                    speaker   = "host"
                elif line.upper().startswith("GUEST:"):
                    text_part = line[6:].strip()
                    speaker   = "guest"
                else:
                    text_part = line
                    speaker   = "host"

                if text_part:
                    segments.append({"speaker": speaker, "text": text_part})
        else:
            # Monólogo: dividir por segmentos
            for seg in split_into_segments(script):
                segments.append({"speaker": "host", "text": seg})

        # Generar audio para cada segmento
        total = len(segments)
        for i, seg in enumerate(segments):
            voice_kwargs = host_voice if seg["speaker"] == "host" else guest_voice

            # En diálogo con edge_tts se pueden asignar voces distintas
            if engine == "edge_tts" and format_type == "dialogue":
                if seg["speaker"] == "guest" and "voice" not in voice_kwargs:
                    voice_kwargs = {**voice_kwargs, "voice": "es-CL-LorenzoNeural"}

            result = generate_tts(seg["text"], engine=engine, **{**kwargs, **voice_kwargs})

            if result["success"]:
                audio_parts.append(result["audio_b64"])
            else:
                errors.append(f"Segmento {i+1}: {result['error']}")
                logger.warning(f"Podcast seg {i+1}/{total} falló: {result['error']}")

        if not audio_parts:
            return {"success": False, "error": "No se pudo generar ningún segmento de audio", "details": errors}

        elapsed     = round(time.time() - t0, 2)
        total_words = sum(len(s["text"].split()) for s in segments)
        est_dur     = round(total_words / 2.5, 1)

        return {
            "success":      True,
            "audio_parts":  audio_parts,        # lista de base64, uno por segmento
            "segments":     segments,            # [{speaker, text}, ...]
            "total_parts":  len(audio_parts),
            "failed_parts": len(errors),
            "errors":       errors,
            "engine":       engine,
            "format":       "mp3",
            "format_type":  format_type,
            "title":        title,
            "words":        total_words,
            "est_duration": est_dur,
            "gen_time":     elapsed,
        }

    except Exception as e:
        logger.error(f"Podcast error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ──────────────────────────────────────────────────────────────────
# INFO del módulo
# ──────────────────────────────────────────────────────────────────

def module_info() -> dict:
    engines = _available_engines()
    return {
        "module":  "audio_studio",
        "version": "1.0.0",
        "name":    "🎙️ Audio Studio",
        "description": "TTS (texto→voz), STT (voz→texto) y generador de podcast",
        "features": {
            "tts": {
                "available": True,
                "engines":   engines,
                "gtts_langs":       GTTS_LANGS,
                "edge_voices":      EDGE_VOICES,
                "elevenlabs_voices": ELEVENLABS_VOICES if ELEVENLABS_API_KEY else {},
                "elevenlabs_active": bool(ELEVENLABS_API_KEY),
            },
            "stt": {
                "available": bool(OPENAI_API_KEY),
                "engine":    "openai_whisper",
                "formats":   ["mp3", "mp4", "wav", "webm", "m4a", "ogg"],
                "max_size_mb": 25,
                "languages": "auto-detect o especificar código ISO 639-1",
            },
            "podcast": {
                "available":  True,
                "formats":    ["monologue", "dialogue"],
                "max_chars":  50000,
                "engines":    engines,
            },
        },
        "env_keys": {
            "ELEVENLABS_API_KEY": "Activa voces ElevenLabs (opcional)",
            "OPENAI_API_KEY":     "Activa transcripción Whisper STT (opcional)",
        },
    }
