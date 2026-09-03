"""
modules/audio_studio/music_mixer.py  v2
=========================================
Mezcla audio TTS con música de fondo procedural.

NO requiere ffmpeg. Opera directamente con bytes WAV/PCM.
Genera música sintetizada con ondas matemáticas puras.
Exporta el resultado como WAV (reproducible en todos los navegadores).

Categorías:
  epic, sad, happy, relaxing, dramatic, romantic, mystery, energetic, ambient, neutral
"""

import io
import math
import struct
import logging
import base64

logger = logging.getLogger("cic_ia.audio_studio.mixer")

DEFAULT_MUSIC_VOLUME = -14   # dB
FADE_IN_MS           = 1500
FADE_OUT_MS          = 2000
SAMPLE_RATE          = 11025  # Hz — bajo consumo de RAM, calidad aceptable
MAX_DURATION_SEC     = 90.0   # límite para evitar OOM en Render plan gratuito

# ──────────────────────────────────────────────────────────────────
# PERFILES MUSICALES
# ──────────────────────────────────────────────────────────────────
MUSIC_PROFILES = {
    "epic": {
        "desc": "Épica / Aventura", "emoji": "⚔️",
        "notes": [130.81, 164.81, 196.00, 261.63, 329.63],
        "tempo": 0.5, "amplitude": 0.30, "wave": "square",
    },
    "sad": {
        "desc": "Triste / Melancólica", "emoji": "😢",
        "notes": [146.83, 174.61, 220.00, 261.63],
        "tempo": 1.4, "amplitude": 0.18, "wave": "sine",
    },
    "happy": {
        "desc": "Alegre / Positiva", "emoji": "😊",
        "notes": [261.63, 329.63, 392.00, 523.25],
        "tempo": 0.4, "amplitude": 0.25, "wave": "triangle",
    },
    "relaxing": {
        "desc": "Relajante / Meditación", "emoji": "🧘",
        "notes": [174.61, 220.00, 261.63, 293.66],
        "tempo": 2.0, "amplitude": 0.13, "wave": "sine",
    },
    "dramatic": {
        "desc": "Dramática / Intensa", "emoji": "🎭",
        "notes": [110.00, 138.59, 164.81, 220.00],
        "tempo": 0.3, "amplitude": 0.35, "wave": "sawtooth",
    },
    "romantic": {
        "desc": "Romántica", "emoji": "❤️",
        "notes": [261.63, 311.13, 392.00, 440.00],
        "tempo": 1.0, "amplitude": 0.16, "wave": "sine",
    },
    "mystery": {
        "desc": "Misterio / Suspenso", "emoji": "🔮",
        "notes": [138.59, 155.56, 185.00, 207.65],
        "tempo": 0.9, "amplitude": 0.20, "wave": "triangle",
    },
    "energetic": {
        "desc": "Energética / Motivacional", "emoji": "⚡",
        "notes": [196.00, 261.63, 329.63, 440.00],
        "tempo": 0.25, "amplitude": 0.28, "wave": "square",
    },
    "ambient": {
        "desc": "Ambiente / Naturaleza", "emoji": "🌿",
        "notes": [220.00, 246.94, 293.66, 329.63],
        "tempo": 3.0, "amplitude": 0.11, "wave": "sine",
    },
    "neutral": {
        "desc": "Neutral / Sin música", "emoji": "🔇",
        "notes": [], "tempo": 1.0, "amplitude": 0.0, "wave": "sine",
    },
}


# ──────────────────────────────────────────────────────────────────
# GENERADOR DE ONDAS
# ──────────────────────────────────────────────────────────────────
def _wave(wave_type: str, t: float, freq: float, amp: float) -> float:
    phase = 2 * math.pi * freq * t
    if wave_type == "sine":
        return amp * math.sin(phase)
    elif wave_type == "square":
        return amp * (1.0 if math.sin(phase) >= 0 else -1.0)
    elif wave_type == "triangle":
        return amp * (2 / math.pi) * math.asin(max(-1.0, min(1.0, math.sin(phase))))
    elif wave_type == "sawtooth":
        return amp * (2 * (freq * t - math.floor(freq * t + 0.5)))
    return 0.0


def _samples_to_wav(samples: list, sr: int) -> bytes:
    """Convierte lista de floats [-1,1] a bytes WAV 16-bit mono."""
    n = len(samples)
    data_size = n * 2
    buf = io.BytesIO()
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVE')
    buf.write(b'fmt ')
    buf.write(struct.pack('<I', 16))
    buf.write(struct.pack('<H', 1))       # PCM
    buf.write(struct.pack('<H', 1))       # mono
    buf.write(struct.pack('<I', sr))
    buf.write(struct.pack('<I', sr * 2))  # byte rate
    buf.write(struct.pack('<H', 2))       # block align
    buf.write(struct.pack('<H', 16))      # bits per sample
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))
    for s in samples:
        val = max(-32768, min(32767, int(s * 32767)))
        buf.write(struct.pack('<h', val))
    buf.seek(0)
    return buf.read()


def generate_music_wav(category: str, duration_sec: float, sr: int = SAMPLE_RATE) -> bytes:
    """Genera música procedural como WAV."""
    duration_sec = min(duration_sec, MAX_DURATION_SEC)
    profile = MUSIC_PROFILES.get(category, MUSIC_PROFILES["neutral"])

    if not profile["notes"] or profile["amplitude"] == 0:
        n = int(duration_sec * sr)
        return _samples_to_wav([0.0] * n, sr)

    notes  = profile["notes"]
    tempo  = profile["tempo"]
    amp    = profile["amplitude"]
    wave   = profile["wave"]
    total  = int(duration_sec * sr)
    fi     = int(FADE_IN_MS / 1000 * sr)
    fo     = int(FADE_OUT_MS / 1000 * sr)
    samples = []

    for i in range(total):
        t        = i / sr
        note_idx = int(t / tempo) % len(notes)
        freq     = notes[note_idx]
        fade     = 1.0
        if i < fi:
            fade = i / fi
        elif i > total - fo:
            fade = (total - i) / fo
        note_phase = (t % tempo) / tempo
        if note_phase < 0.05:
            fade *= note_phase / 0.05
        s = _wave(wave, t, freq, amp * fade)
        samples.append(max(-1.0, min(1.0, s)))

    return _samples_to_wav(samples, sr)


# ──────────────────────────────────────────────────────────────────
# PARSEAR WAV PARA OBTENER SAMPLES PCM
# ──────────────────────────────────────────────────────────────────
def _wav_to_samples(wav_bytes: bytes) -> tuple:
    """
    Parsea un WAV y retorna (samples_float, sample_rate, duration_ms).
    Soporta WAV 16-bit mono o stereo.
    """
    buf = io.BytesIO(wav_bytes)
    buf.read(4)   # RIFF
    buf.read(4)   # chunk size
    buf.read(4)   # WAVE
    buf.read(4)   # fmt
    fmt_size = struct.unpack('<I', buf.read(4))[0]
    audio_fmt = struct.unpack('<H', buf.read(2))[0]
    channels  = struct.unpack('<H', buf.read(2))[0]
    sr        = struct.unpack('<I', buf.read(4))[0]
    buf.read(4)   # byte rate
    buf.read(2)   # block align
    bits      = struct.unpack('<H', buf.read(2))[0]
    if fmt_size > 16:
        buf.read(fmt_size - 16)
    # Buscar chunk data
    while True:
        chunk_id   = buf.read(4)
        chunk_size = struct.unpack('<I', buf.read(4))[0]
        if chunk_id == b'data':
            raw = buf.read(chunk_size)
            break
        buf.read(chunk_size)
    # Convertir a floats
    if bits == 16:
        n = len(raw) // 2
        if channels == 2:
            # Stereo → mono (promediar)
            samples = [(struct.unpack('<h', raw[i*4:i*4+2])[0] +
                        struct.unpack('<h', raw[i*4+2:i*4+4])[0]) / 2 / 32768.0
                       for i in range(n // 2)]
        else:
            samples = [struct.unpack('<h', raw[i*2:i*2+2])[0] / 32768.0
                       for i in range(n)]
    else:
        samples = [0.0]
    duration_ms = int(len(samples) / sr * 1000)
    return samples, sr, duration_ms


# ──────────────────────────────────────────────────────────────────
# ESTIMAR DURACIÓN DE MP3 SIN DECODIFICAR
# ──────────────────────────────────────────────────────────────────
def _estimate_mp3_duration_sec(mp3_bytes: bytes, default_kbps: int = 128) -> float:
    """
    Estima la duración de un MP3 por su tamaño (sin decodificar).
    128kbps → 16000 bytes/segundo.
    """
    bytes_per_sec = default_kbps * 1000 // 8
    return max(1.0, len(mp3_bytes) / bytes_per_sec)


# ──────────────────────────────────────────────────────────────────
# MEZCLADOR PRINCIPAL — SIN FFMPEG
# ──────────────────────────────────────────────────────────────────
def mix_audio_with_music(
    voice_mp3: bytes,
    category: str = "epic",
    music_volume_db: float = DEFAULT_MUSIC_VOLUME,
) -> dict:
    """
    Mezcla audio de voz (MP3) con música procedural.
    
    Estrategia sin ffmpeg:
    1. Estima la duración del MP3 de voz por tamaño
    2. Genera música WAV de esa duración
    3. Mezcla la música WAV con samples del MP3 via pydub (si disponible)
       o devuelve la mezcla en formato WAV puro (sin voz, solo música) 
       superpuesta sobre el MP3 original en el cliente.
    
    Si pydub está disponible (con soporte mp3): mezcla real, retorna WAV.
    Si no: genera solo la música WAV y la retorna junto al MP3 original
           para que el frontend los mezcle vía Web Audio API.
    """
    if category == "neutral":
        return {
            "success":   True,
            "audio_b64": base64.b64encode(voice_mp3).decode(),
            "format":    "mp3",
            "category":  "neutral",
            "mixed":     False,
        }

    sr = SAMPLE_RATE
    music_vol = 10 ** (music_volume_db / 20.0)   # dB → lineal

    # Estimar duración de la voz
    duration_sec = _estimate_mp3_duration_sec(voice_mp3)
    duration_sec = min(duration_sec, MAX_DURATION_SEC)

    # Intentar mezcla real con pydub (si tiene soporte MP3 sin ffmpeg)
    try:
        from pydub import AudioSegment

        # gTTS genera MP3 que pydub puede leer con minimp3 (sin ffmpeg)
        voice_seg = AudioSegment.from_mp3(io.BytesIO(voice_mp3))
        voice_seg = voice_seg.set_frame_rate(sr).set_channels(1).set_sample_width(2)
        duration_ms  = len(voice_seg)
        duration_sec = duration_ms / 1000.0

        # Generar música
        music_wav = generate_music_wav(category, duration_sec + 1.0, sr)
        music_seg = AudioSegment.from_wav(io.BytesIO(music_wav))

        # Ajustar duración
        if len(music_seg) > duration_ms:
            music_seg = music_seg[:duration_ms]
        elif len(music_seg) < duration_ms:
            music_seg = music_seg + AudioSegment.silent(duration=duration_ms - len(music_seg))

        # Bajar volumen música
        music_seg = music_seg + music_volume_db

        # Mezclar: voz sobre música
        mixed = music_seg.overlay(voice_seg)

        # Exportar como WAV (sin ffmpeg)
        out = io.BytesIO()
        mixed.export(out, format="wav")
        out.seek(0)
        result = out.read()

        return {
            "success":      True,
            "audio_b64":    base64.b64encode(result).decode(),
            "format":       "wav",
            "category":     category,
            "mixed":        True,
            "duration_sec": round(duration_sec, 1),
        }

    except Exception as e:
        logger.warning(f"pydub mezcla falló ({e}) — usando mezcla WAV pura")

    # ── Fallback: mezcla WAV pura ─────────────────────────────────
    # Genera música WAV y la mezcla matemáticamente
    # La voz se convierte a silencio (no tenemos decodificador MP3 puro),
    # pero la música sí se genera y se superpone.
    # El frontend puede reproducir ambos tracks juntos vía Web Audio API.
    try:
        music_wav = generate_music_wav(category, duration_sec, sr)
        music_samples, _, _ = _wav_to_samples(music_wav)
        # Escalar música
        scaled = [s * music_vol for s in music_samples]
        result_wav = _samples_to_wav(scaled, sr)

        return {
            "success":       True,
            "audio_b64":     base64.b64encode(voice_mp3).decode(),  # voz original
            "music_b64":     base64.b64encode(result_wav).decode(), # música separada
            "format":        "mp3",
            "music_format":  "wav",
            "category":      category,
            "mixed":         False,
            "separate_tracks": True,  # el frontend los mezcla
            "duration_sec":  round(duration_sec, 1),
        }
    except Exception as e2:
        logger.error(f"Fallback mezcla WAV falló: {e2}")
        return {
            "success":   True,
            "audio_b64": base64.b64encode(voice_mp3).decode(),
            "format":    "mp3",
            "category":  category,
            "mixed":     False,
            "warning":   str(e2),
        }


def get_categories() -> list:
    return [
        {"id": k, "desc": v["desc"], "emoji": v["emoji"]}
        for k, v in MUSIC_PROFILES.items()
    ]
