"""
modules/audio_studio/routes.py
================================
Endpoints Flask del Audio Studio.

Rutas registradas:
  GET  /api/audio/info              → info del módulo (público)
  POST /api/audio/tts               → texto → audio (requiere login)
  POST /api/audio/stt               → audio → texto (requiere login)
  POST /api/audio/podcast           → guión → podcast (requiere login)
  GET  /api/audio/voices            → lista de voces disponibles (público)

Uso en cic_ia_mejorado.py (agregar al bloque de registros):
  try:
      from modules.audio_studio.routes import register
      register(app)
      logger.info('✅ Audio Studio registrado')
  except Exception as _ae:
      logger.warning(f'Audio Studio no cargado: {_ae}')
"""

import base64
import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger("cic_ia.audio_studio.routes")

bp = Blueprint("audio_studio", __name__, url_prefix="/api/audio")


def register(app):
    """Registra el Blueprint de Audio Studio en la app Flask."""
    # Importamos main aquí para evitar imports circulares en arranque
    from modules.audio_studio import main as audio_main

    # ─────────────────────────────────────────────────────────────
    # GET /api/audio/info  — pública, sin auth
    # ─────────────────────────────────────────────────────────────
    @bp.route("/info", methods=["GET"])
    def audio_info():
        """
        Retorna capacidades del módulo: engines disponibles, voces,
        idiomas, límites, etc.
        """
        return jsonify(audio_main.module_info())

    # ─────────────────────────────────────────────────────────────
    # GET /api/audio/voices  — pública, sin auth
    # ─────────────────────────────────────────────────────────────
    @bp.route("/voices", methods=["GET"])
    def audio_voices():
        """Lista todas las voces disponibles por motor."""
        info = audio_main.module_info()
        return jsonify({
            "success": True,
            "gtts_langs":        info["features"]["tts"]["gtts_langs"],
            "edge_voices":       info["features"]["tts"]["edge_voices"],
            "elevenlabs_voices": info["features"]["tts"]["elevenlabs_voices"],
            "elevenlabs_active": info["features"]["tts"]["elevenlabs_active"],
        })

    # ─────────────────────────────────────────────────────────────
    # POST /api/audio/tts  — requiere login
    # ─────────────────────────────────────────────────────────────
    @bp.route("/tts", methods=["POST"])
    def audio_tts():
        """
        Convierte texto a audio.

        Body JSON:
        {
            "text":    "Hola mundo, esto es una prueba",   // requerido
            "engine":  "gtts" | "edge_tts" | "elevenlabs", // default: "gtts"

            // Para gTTS:
            "lang":    "es",          // código ISO 639-1
            "slow":    false,

            // Para edge_tts:
            "voice":   "es-CL-CatalinaNeural",
            "rate":    "+0%",         // velocidad: "-20%" más lento, "+20%" más rápido
            "volume":  "+0%",

            // Para ElevenLabs:
            "voice_id":    "21m00Tcm4TlvDq8ikWAM",
            "model":       "eleven_multilingual_v2",
            "stability":   0.5,
            "similarity":  0.75
        }

        Response:
        {
            "success":       true,
            "audio_b64":     "<base64 MP3>",
            "format":        "mp3",
            "engine":        "gtts",
            "chars":         28,
            "words":         5,
            "est_duration":  2.0,
            "gen_time":      1.3
        }
        """
        data   = request.json or {}
        text   = data.get("text", "").strip()
        engine = data.get("engine", "gtts")

        if not text:
            return jsonify({"success": False, "error": "El campo 'text' es requerido"}), 400

        # Parámetros específicos por motor
        kwargs = {}
        if engine == "gtts":
            kwargs["lang"] = data.get("lang", "es")
            kwargs["slow"] = bool(data.get("slow", False))
        elif engine == "edge_tts":
            kwargs["voice"]  = data.get("voice", "es-CL-CatalinaNeural")
            kwargs["rate"]   = data.get("rate", "+0%")
            kwargs["volume"] = data.get("volume", "+0%")
        elif engine == "elevenlabs":
            kwargs["voice_id"]   = data.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
            kwargs["model"]      = data.get("model", "eleven_multilingual_v2")
            kwargs["stability"]  = float(data.get("stability", 0.5))
            kwargs["similarity"] = float(data.get("similarity", 0.75))
        else:
            return jsonify({"success": False, "error": f"Motor '{engine}' no reconocido. Usa: gtts, edge_tts, elevenlabs"}), 400

        result = audio_main.generate_tts(text, engine=engine, **kwargs)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 500

    # ─────────────────────────────────────────────────────────────
    # POST /api/audio/stt  — requiere login
    # ─────────────────────────────────────────────────────────────
    @bp.route("/stt", methods=["POST"])
    def audio_stt():
        """
        Transcribe audio a texto usando OpenAI Whisper.

        Acepta dos formatos:
          1. multipart/form-data con campo 'audio' (archivo)
          2. JSON con campo 'audio_b64' (base64) y 'filename'

        Body JSON (opción 2):
        {
            "audio_b64":  "<base64>",
            "filename":   "grabacion.mp3",    // para inferir MIME type
            "language":   "es"                // opcional, auto-detect si se omite
        }

        Response:
        {
            "success":  true,
            "text":     "Transcripción del audio aquí",
            "language": "es",
            "duration": 12.4,
            "segments": [...],
            "gen_time": 3.1
        }
        """
        # Opción 1: archivo multipart
        if "audio" in request.files:
            f        = request.files["audio"]
            filename = f.filename or "audio.mp3"
            audio_bytes = f.read()
            language    = request.form.get("language")
        else:
            # Opción 2: JSON base64
            data = request.json or {}
            b64  = data.get("audio_b64", "")
            if not b64:
                return jsonify({"success": False, "error": "Se requiere 'audio' (multipart) o 'audio_b64' (JSON)"}), 400
            try:
                audio_bytes = base64.b64decode(b64)
            except Exception:
                return jsonify({"success": False, "error": "audio_b64 no es base64 válido"}), 400
            filename = data.get("filename", "audio.mp3")
            language = data.get("language")

        result = audio_main.transcribe_whisper(audio_bytes, filename=filename, language=language)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 500

    # ─────────────────────────────────────────────────────────────
    # POST /api/audio/podcast  — requiere login
    # ─────────────────────────────────────────────────────────────
    @bp.route("/podcast", methods=["POST"])
    def audio_podcast():
        """
        Genera un episodio de podcast completo desde un guión.

        Body JSON:
        {
            "script":       "Texto completo del episodio...",   // requerido
            "title":        "Mi primer podcast",
            "engine":       "gtts" | "edge_tts" | "elevenlabs",
            "format_type":  "monologue" | "dialogue",

            // Si format_type == "dialogue", el script debe tener líneas:
            // HOST: Bienvenidos al programa...
            // GUEST: Gracias por invitarme...

            // Voces por rol (opcional, parámetros del motor elegido):
            "host_voice":  {"lang": "es"},                       // para gTTS
            "guest_voice": {"lang": "es"},

            // Para edge_tts con diálogo:
            "host_voice":  {"voice": "es-CL-CatalinaNeural"},
            "guest_voice": {"voice": "es-CL-LorenzoNeural"},

            // Parámetros globales del motor (si no están en host/guest_voice):
            "lang":   "es",
            "voice":  "es-CL-CatalinaNeural"
        }

        Response:
        {
            "success":      true,
            "title":        "Mi primer podcast",
            "audio_parts":  ["<base64>", "<base64>", ...],  // un MP3 por segmento
            "segments":     [{"speaker": "host", "text": "..."}, ...],
            "total_parts":  4,
            "failed_parts": 0,
            "engine":       "gtts",
            "format_type":  "monologue",
            "words":        320,
            "est_duration": 128.0,
            "gen_time":     5.2
        }
        """
        data        = request.json or {}
        script      = data.get("script", "").strip()
        title       = data.get("title", "Podcast")
        engine      = data.get("engine", "gtts")
        format_type = data.get("format_type", "monologue")
        host_voice  = data.get("host_voice", {})
        guest_voice = data.get("guest_voice", {})

        if not script:
            return jsonify({"success": False, "error": "El campo 'script' es requerido"}), 400

        # Parámetros globales del motor
        kwargs = {}
        if engine == "gtts":
            kwargs["lang"] = data.get("lang", "es")
            kwargs["slow"] = bool(data.get("slow", False))
        elif engine == "edge_tts":
            kwargs["voice"]  = data.get("voice", "es-CL-CatalinaNeural")
            kwargs["rate"]   = data.get("rate", "+0%")
            kwargs["volume"] = data.get("volume", "+0%")
        elif engine == "elevenlabs":
            kwargs["voice_id"]   = data.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
            kwargs["stability"]  = float(data.get("stability", 0.5))
            kwargs["similarity"] = float(data.get("similarity", 0.75))

        result = audio_main.generate_podcast(
            script=script,
            engine=engine,
            host_voice=host_voice,
            guest_voice=guest_voice,
            format_type=format_type,
            title=title,
            **kwargs,
        )

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 500

    # Registrar el blueprint
    app.register_blueprint(bp)
    logger.info("✅ Audio Studio rutas registradas en /api/audio/*")
