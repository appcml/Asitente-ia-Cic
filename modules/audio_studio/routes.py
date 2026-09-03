"""
modules/audio_studio/routes.py  v2
=====================================
Endpoints Flask del Audio Studio.

Rutas:
  GET  /api/audio/info
  GET  /api/audio/voices
  POST /api/audio/tts
  POST /api/audio/stt
  POST /api/audio/podcast
  GET  /api/audio/music/categories
  POST /api/audio/mix
  GET  /api/audio/projects
  POST /api/audio/projects
  GET  /api/audio/projects/<id>
  PUT  /api/audio/projects/<id>
  DELETE /api/audio/projects/<id>
"""

import base64
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

logger = logging.getLogger("cic_ia.audio_studio.routes")

bp = Blueprint("audio_studio", __name__, url_prefix="/api/audio")


# ──────────────────────────────────────────────────────────────────
# Helper: obtener usuario desde token
# ──────────────────────────────────────────────────────────────────
def _get_user_from_token(token: str):
    if not token:
        return None
    try:
        from cic_ia_mejorado import UserSession, User
        sess = UserSession.query.filter_by(token=token).first()
        if not sess:
            return None
        return User.query.get(sess.user_id)
    except Exception as e:
        logger.warning(f"_get_user_from_token error: {e}")
        return None


def register(app):
    """Registra el Blueprint en la app Flask y crea tablas nuevas."""

    # Crear tabla podcast_project si no existe
    try:
        from modules.audio_studio.models import PodcastProject
        from cic_ia_mejorado import db
        with app.app_context():
            db.create_all()
        logger.info("✅ Tabla podcast_project verificada/creada")
    except Exception as e:
        logger.warning(f"No se pudo crear tabla podcast_project: {e}")

    from modules.audio_studio import main as audio_main

    # ─── GET /api/audio/info ──────────────────────────────────────
    @bp.route("/info", methods=["GET"])
    def audio_info():
        return jsonify(audio_main.module_info())

    # ─── GET /api/audio/voices ───────────────────────────────────
    @bp.route("/voices", methods=["GET"])
    def audio_voices():
        info = audio_main.module_info()
        return jsonify({
            "success": True,
            "gtts_langs":        info["features"]["tts"]["gtts_langs"],
            "edge_voices":       info["features"]["tts"]["edge_voices"],
            "elevenlabs_voices": info["features"]["tts"]["elevenlabs_voices"],
            "elevenlabs_active": info["features"]["tts"]["elevenlabs_active"],
        })

    # ─── POST /api/audio/tts ─────────────────────────────────────
    @bp.route("/tts", methods=["POST"])
    def audio_tts():
        data   = request.json or {}
        text   = data.get("text", "").strip()
        engine = data.get("engine", "gtts")
        if not text:
            return jsonify({"success": False, "error": "El campo 'text' es requerido"}), 400
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
            return jsonify({"success": False, "error": f"Motor '{engine}' no reconocido"}), 400
        result = audio_main.generate_tts(text, engine=engine, **kwargs)
        return jsonify(result), (200 if result["success"] else 500)

    # ─── POST /api/audio/stt ─────────────────────────────────────
    @bp.route("/stt", methods=["POST"])
    def audio_stt():
        if "audio" in request.files:
            f = request.files["audio"]
            filename    = f.filename or "audio.mp3"
            audio_bytes = f.read()
            language    = request.form.get("language")
        else:
            data = request.json or {}
            b64  = data.get("audio_b64", "")
            if not b64:
                return jsonify({"success": False, "error": "Se requiere 'audio' o 'audio_b64'"}), 400
            try:
                audio_bytes = base64.b64decode(b64)
            except Exception:
                return jsonify({"success": False, "error": "audio_b64 inválido"}), 400
            filename = data.get("filename", "audio.mp3")
            language = data.get("language")
        result = audio_main.transcribe_whisper(audio_bytes, filename=filename, language=language)
        return jsonify(result), (200 if result["success"] else 500)

    # ─── POST /api/audio/podcast ─────────────────────────────────
    @bp.route("/podcast", methods=["POST"])
    def audio_podcast():
        data        = request.json or {}
        script      = data.get("script", "").strip()
        title       = data.get("title", "Podcast")
        engine      = data.get("engine", "gtts")
        format_type = data.get("format_type", "monologue")
        host_voice  = data.get("host_voice", {})
        guest_voice = data.get("guest_voice", {})
        music_cat   = data.get("music_cat", "neutral")
        music_vol   = float(data.get("music_volume_db", -14))
        if not script:
            return jsonify({"success": False, "error": "'script' es requerido"}), 400
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
            script=script, engine=engine,
            host_voice=host_voice, guest_voice=guest_voice,
            format_type=format_type, title=title, **kwargs,
        )
        if not result["success"]:
            return jsonify(result), 500

        # ── Mezclar con música si se pidió ────────────────────────
        if music_cat and music_cat != "neutral":
            from modules.audio_studio.music_mixer import mix_audio_with_music
            mixed_parts = []
            for b64 in result.get("audio_parts", []):
                try:
                    voice_bytes = base64.b64decode(b64)
                    mix_result  = mix_audio_with_music(voice_bytes, category=music_cat, music_volume_db=music_vol)
                    mixed_parts.append(mix_result.get("audio_b64", b64))
                except Exception as mix_err:
                    logger.warning(f"Mezcla falló para segmento: {mix_err}")
                    mixed_parts.append(b64)
            result["audio_parts"]  = mixed_parts
            result["music_cat"]    = music_cat
            result["music_mixed"]  = True
        else:
            result["music_cat"]    = "neutral"
            result["music_mixed"]  = False

        return jsonify(result)

    # ─── GET /api/audio/music/categories ─────────────────────────
    @bp.route("/music/categories", methods=["GET"])
    def audio_music_categories():
        from modules.audio_studio.music_mixer import get_categories
        return jsonify({"success": True, "categories": get_categories()})

    # ─── POST /api/audio/mix ─────────────────────────────────────
    @bp.route("/mix", methods=["POST"])
    def audio_mix():
        from modules.audio_studio.music_mixer import mix_audio_with_music
        data     = request.json or {}
        b64      = data.get("audio_b64", "")
        category = data.get("category", "epic")
        vol_db   = float(data.get("music_volume_db", -14))
        if not b64:
            return jsonify({"success": False, "error": "audio_b64 requerido"}), 400
        try:
            voice_bytes = base64.b64decode(b64)
        except Exception:
            return jsonify({"success": False, "error": "audio_b64 inválido"}), 400
        result = mix_audio_with_music(voice_bytes, category=category, music_volume_db=vol_db)
        return jsonify(result)

    # ─── PROYECTOS ────────────────────────────────────────────────

    def _auth(req):
        token = req.headers.get("Authorization", "").replace("Bearer ", "")
        return _get_user_from_token(token)

    @bp.route("/projects", methods=["GET"])
    def audio_list_projects():
        user = _auth(request)
        if not user:
            return jsonify({"success": False, "error": "No autorizado"}), 401
        from modules.audio_studio.models import PodcastProject
        projects = PodcastProject.query\
            .filter_by(user_id=user.id, deleted=False)\
            .order_by(PodcastProject.updated_at.desc()).all()
        return jsonify({"success": True, "projects": [p.to_dict() for p in projects]})

    @bp.route("/projects", methods=["POST"])
    def audio_save_project():
        user = _auth(request)
        if not user:
            return jsonify({"success": False, "error": "No autorizado"}), 401
        from modules.audio_studio.models import PodcastProject
        from cic_ia_mejorado import db
        data = request.json or {}
        if not data.get("title"):
            return jsonify({"success": False, "error": "title requerido"}), 400
        p = PodcastProject(
            user_id      = user.id,
            title        = data.get("title", "Sin título"),
            script       = data.get("script", ""),
            engine       = data.get("engine", "gtts"),
            format_type  = data.get("format_type", "monologue"),
            voice_config = data.get("voice_config", {}),
            music_cat    = data.get("music_cat", "neutral"),
            segments     = data.get("segments", []),
            audio_parts  = data.get("audio_parts", []),
        )
        db.session.add(p)
        db.session.commit()
        return jsonify({"success": True, "id": p.id, "message": "Proyecto guardado"})

    @bp.route("/projects/<int:pid>", methods=["GET"])
    def audio_get_project(pid):
        user = _auth(request)
        if not user:
            return jsonify({"success": False, "error": "No autorizado"}), 401
        from modules.audio_studio.models import PodcastProject
        p = PodcastProject.query.filter_by(id=pid, user_id=user.id, deleted=False).first()
        if not p:
            return jsonify({"success": False, "error": "Proyecto no encontrado"}), 404
        return jsonify({"success": True, "project": p.to_dict(full=True)})

    @bp.route("/projects/<int:pid>", methods=["PUT"])
    def audio_update_project(pid):
        user = _auth(request)
        if not user:
            return jsonify({"success": False, "error": "No autorizado"}), 401
        from modules.audio_studio.models import PodcastProject
        from cic_ia_mejorado import db
        p = PodcastProject.query.filter_by(id=pid, user_id=user.id, deleted=False).first()
        if not p:
            return jsonify({"success": False, "error": "Proyecto no encontrado"}), 404
        data = request.json or {}
        for field in ["title","script","engine","format_type","voice_config","music_cat","segments","audio_parts"]:
            if field in data:
                setattr(p, field, data[field])
        p.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"success": True, "message": "Actualizado"})

    @bp.route("/projects/<int:pid>", methods=["DELETE"])
    def audio_delete_project(pid):
        user = _auth(request)
        if not user:
            return jsonify({"success": False, "error": "No autorizado"}), 401
        from modules.audio_studio.models import PodcastProject
        from cic_ia_mejorado import db
        p = PodcastProject.query.filter_by(id=pid, user_id=user.id, deleted=False).first()
        if not p:
            return jsonify({"success": False, "error": "Proyecto no encontrado"}), 404
        p.deleted = True
        p.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"success": True, "message": "Eliminado"})

    # Registrar blueprint
    app.register_blueprint(bp)
    logger.info("✅ Audio Studio v2 rutas registradas en /api/audio/*")
