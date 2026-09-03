"""
modules/audio_studio/music_mixer.py
=====================================
Mezcla audio TTS con música de fondo usando pydub + ffmpeg.

Categorías disponibles (música generada proceduralmente con tono):
  epic, sad, happy, relaxing, dramatic, romantic, mystery, energetic, ambient, neutral

Si pydub no está disponible, retorna solo el audio TTS sin mezcla.
"""

import io
import os
import math
import struct
import logging
import base64
from typing import Optional

logger = logging.getLogger("cic_ia.audio_studio.mixer")

# Volúmenes por defecto (la voz siempre al 100%, música reducida)
DEFAULT_MUSIC_VOLUME = -14  # dB  (la voz queda por encima)
FADE_IN_MS  = 2000
FADE_OUT_MS = 3000

# ──────────────────────────────────────────────────────────────────
# GENERADOR DE MÚSICA PROCEDURAL (sin dependencias externas)
# Genera WAV puro con ondas sinusoidales para cada categoría
# ──────────────────────────────────────────────────────────────────

MUSIC_PROFILES = {
    "epic": {
        "desc": "Épica / Aventura",
        "emoji": "⚔️",
        "notes": [130.81, 164.81, 196.00, 261.63, 329.63],  # C3 E3 G3 C4 E4
        "tempo": 0.5, "amplitude": 0.35, "wave": "square",
    },
    "sad": {
        "desc": "Triste / Melancólica",
        "emoji": "😢",
        "notes": [146.83, 174.61, 220.00, 261.63],  # D3 F3 A3 C4 (menor)
        "tempo": 1.2, "amplitude": 0.20, "wave": "sine",
    },
    "happy": {
        "desc": "Alegre / Positiva",
        "emoji": "😊",
        "notes": [261.63, 329.63, 392.00, 523.25],  # C4 E4 G4 C5 (mayor)
        "tempo": 0.4, "amplitude": 0.28, "wave": "triangle",
    },
    "relaxing": {
        "desc": "Relajante / Meditación",
        "emoji": "🧘",
        "notes": [174.61, 220.00, 261.63, 293.66],  # F3 A3 C4 D4
        "tempo": 2.0, "amplitude": 0.15, "wave": "sine",
    },
    "dramatic": {
        "desc": "Dramática / Intensa",
        "emoji": "🎭",
        "notes": [110.00, 138.59, 164.81, 220.00],  # A2 C#3 E3 A3
        "tempo": 0.3, "amplitude": 0.40, "wave": "sawtooth",
    },
    "romantic": {
        "desc": "Romántica",
        "emoji": "❤️",
        "notes": [261.63, 311.13, 392.00, 440.00],  # C4 Eb4 G4 A4
        "tempo": 1.0, "amplitude": 0.18, "wave": "sine",
    },
    "mystery": {
        "desc": "Misterio / Suspenso",
        "emoji": "🔮",
        "notes": [138.59, 155.56, 185.00, 207.65],  # C#3 Eb3 F#3 Ab3
        "tempo": 0.8, "amplitude": 0.22, "wave": "triangle",
    },
    "energetic": {
        "desc": "Energética / Motivacional",
        "emoji": "⚡",
        "notes": [196.00, 261.63, 329.63, 440.00],  # G3 C4 E4 A4
        "tempo": 0.25, "amplitude": 0.32, "wave": "square",
    },
    "ambient": {
        "desc": "Ambiente / Naturaleza",
        "emoji": "🌿",
        "notes": [220.00, 246.94, 293.66, 329.63],  # A3 B3 D4 E4
        "tempo": 3.0, "amplitude": 0.12, "wave": "sine",
    },
    "neutral": {
        "desc": "Neutral / Sin música",
        "emoji": "🔇",
        "notes": [],
        "tempo": 1.0, "amplitude": 0.0, "wave": "sine",
    },
}


def _wave_sample(wave_type: str, t: float, freq: float, amp: float) -> float:
    """Genera una muestra de onda para el tipo dado."""
    phase = 2 * math.pi * freq * t
    if wave_type == "sine":
        return amp * math.sin(phase)
    elif wave_type == "square":
        return amp * (1.0 if math.sin(phase) >= 0 else -1.0)
    elif wave_type == "triangle":
        return amp * (2 / math.pi) * math.asin(math.sin(phase))
    elif wave_type == "sawtooth":
        return amp * (2 * (freq * t - math.floor(freq * t + 0.5)))
    return 0.0


def generate_music_wav(category: str, duration_sec: float, sample_rate: int = 22050) -> bytes:
    """
    Genera música procedural como bytes WAV para la categoría dada.
    duration_sec: duración total en segundos (se agrega fade)
    """
    profile = MUSIC_PROFILES.get(category, MUSIC_PROFILES["neutral"])

    if not profile["notes"] or profile["amplitude"] == 0:
        # Silencio: WAV vacío de la duración correcta
        return _build_wav_silence(duration_sec, sample_rate)

    notes  = profile["notes"]
    tempo  = profile["tempo"]
    amp    = profile["amplitude"]
    wave   = profile["wave"]
    total_samples = int(duration_sec * sample_rate)
    samples = []

    for i in range(total_samples):
        t = i / sample_rate
        # Ciclo entre notas según tempo
        note_idx = int(t / tempo) % len(notes)
        freq     = notes[note_idx]
        # Fade in / out
        fade = 1.0
        fi_samples = int(FADE_IN_MS / 1000 * sample_rate)
        fo_samples = int(FADE_OUT_MS / 1000 * sample_rate)
        if i < fi_samples:
            fade = i / fi_samples
        elif i > total_samples - fo_samples:
            fade = (total_samples - i) / fo_samples
        # Suavizar transición entre notas (10ms de crossfade)
        note_phase = (t % tempo) / tempo
        if note_phase < 0.05:
            fade *= note_phase / 0.05
        s = _wave_sample(wave, t, freq, amp * fade)
        # Clamp
        samples.append(max(-1.0, min(1.0, s)))

    return _samples_to_wav(samples, sample_rate)


def _build_wav_silence(duration_sec: float, sample_rate: int) -> bytes:
    n = int(duration_sec * sample_rate)
    return _samples_to_wav([0.0] * n, sample_rate)


def _samples_to_wav(samples: list, sample_rate: int) -> bytes:
    """Convierte lista de float [-1, 1] a bytes WAV 16-bit mono."""
    buf = io.BytesIO()
    n_samples  = len(samples)
    data_bytes = n_samples * 2  # 16-bit = 2 bytes por muestra
    # WAV header
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_bytes))
    buf.write(b'WAVE')
    buf.write(b'fmt ')
    buf.write(struct.pack('<I', 16))           # chunk size
    buf.write(struct.pack('<H', 1))            # PCM
    buf.write(struct.pack('<H', 1))            # mono
    buf.write(struct.pack('<I', sample_rate))  # sample rate
    buf.write(struct.pack('<I', sample_rate * 2))  # byte rate
    buf.write(struct.pack('<H', 2))            # block align
    buf.write(struct.pack('<H', 16))           # bits per sample
    buf.write(b'data')
    buf.write(struct.pack('<I', data_bytes))
    for s in samples:
        val = int(s * 32767)
        val = max(-32768, min(32767, val))
        buf.write(struct.pack('<h', val))
    buf.seek(0)
    return buf.read()


# ──────────────────────────────────────────────────────────────────
# MEZCLADOR PRINCIPAL
# ──────────────────────────────────────────────────────────────────

def mix_audio_with_music(
    voice_mp3: bytes,
    category: str = "epic",
    music_volume_db: float = DEFAULT_MUSIC_VOLUME,
) -> dict:
    """
    Mezcla audio de voz (MP3) con música de fondo procedural.

    Retorna dict con:
      success: bool
      audio_b64: str  (MP3 base64)
      format: 'mp3'
      category: str
      error: str (si falla)
    """
    if category == "neutral":
        return {
            "success": True,
            "audio_b64": base64.b64encode(voice_mp3).decode(),
            "format":    "mp3",
            "category":  "neutral",
            "mixed":     False,
        }

    try:
        from pydub import AudioSegment
        from pydub.effects import normalize
    except ImportError:
        logger.warning("pydub no instalado — retornando solo voz")
        return {
            "success":   True,
            "audio_b64": base64.b64encode(voice_mp3).decode(),
            "format":    "mp3",
            "category":  category,
            "mixed":     False,
            "warning":   "pydub no disponible, sin mezcla",
        }

    try:
        # 1. Cargar voz
        voice_seg = AudioSegment.from_mp3(io.BytesIO(voice_mp3))
        duration_ms = len(voice_seg)
        duration_sec = duration_ms / 1000.0

        # 2. Generar música de la misma duración + 2s de cola
        music_wav = generate_music_wav(category, duration_sec + 2.0)
        music_seg = AudioSegment.from_wav(io.BytesIO(music_wav))

        # 3. Ajustar duración música = duración voz exacta
        if len(music_seg) > duration_ms:
            music_seg = music_seg[:duration_ms]
        else:
            music_seg = music_seg + AudioSegment.silent(duration=duration_ms - len(music_seg))

        # 4. Bajar volumen de la música
        music_seg = music_seg + music_volume_db  # dB adjustment

        # 5. Mezclar overlay (voz encima de música)
        mixed = music_seg.overlay(voice_seg)

        # 6. Normalizar y exportar a MP3
        mixed = normalize(mixed)
        out_buf = io.BytesIO()
        mixed.export(out_buf, format="mp3", bitrate="128k")
        out_buf.seek(0)
        result_bytes = out_buf.read()

        return {
            "success":   True,
            "audio_b64": base64.b64encode(result_bytes).decode(),
            "format":    "mp3",
            "category":  category,
            "mixed":     True,
            "duration_sec": round(duration_sec, 1),
        }

    except Exception as e:
        logger.error(f"Error mezclando audio: {e}", exc_info=True)
        # Fallback: retornar solo la voz
        return {
            "success":   True,
            "audio_b64": base64.b64encode(voice_mp3).decode(),
            "format":    "mp3",
            "category":  category,
            "mixed":     False,
            "warning":   f"Mezcla falló ({e}), retornando solo voz",
        }


def get_categories() -> list:
    """Retorna lista de categorías disponibles para el frontend."""
    return [
        {"id": k, "desc": v["desc"], "emoji": v["emoji"]}
        for k, v in MUSIC_PROFILES.items()
    ]
