"""
CicVideo — Rutas Flask
Registra los endpoints del módulo de video en la app principal.

Uso en cic_ia_mejorado.py:
    from modules.video_gen.routes import register_video_routes
    register_video_routes(app, db, token_required, dev_required)
"""

import json
import logging
from flask import request, jsonify

logger = logging.getLogger("cic_ia.video_gen.routes")


def register_video_routes(app, db, token_required, dev_required):
    """Registra todas las rutas de CicVideo en la app Flask."""

    from modules.video_gen.main import VideoGeneratorModule
    _vm = VideoGeneratorModule()

    # ─────────────────────────────────────────────────────────────────────
    # GET /api/video/info  — info pública del módulo (sin auth)
    # ─────────────────────────────────────────────────────────────────────
    @app.route("/api/video/info", methods=["GET"])
    def video_info():
        """
        Retorna motores disponibles, resoluciones, efectos y capacidades.
        Público — sin login requerido.
        """
        return jsonify(_vm.info())

    # ─────────────────────────────────────────────────────────────────────
    # POST /api/video/generate  — generación de video (requiere login)
    # ─────────────────────────────────────────────────────────────────────
    @app.route("/api/video/generate", methods=["POST"])
    @token_required
    def video_generate(current_user):
        """
        Genera un video desde texto o imagen de referencia.

        Body JSON:
        {
            "prompt":     "Un atardecer sobre el mar con olas",
            "resolution": "480p",        // 480p | 720p | 1080p
            "duration":   "5s",          // 3s | 5s | 8s | 15s
            "motor":      "auto",        // auto | cicvideo_math | hf_zeroscope | replicate | pollinations
            "effect":     "auto",        // auto | wave | particles | zoom | flow | gradient
            "ref_image":  "<base64>"     // opcional — imagen de referencia
        }

        Response:
        {
            "success": true,
            "data":    "<base64 del GIF/WebP/MP4>",
            "format":  "gif",
            "motor":   "cicvideo_math",
            "resolution": "480p",
            "duration":   "5s",
            "frames":     40,
            "fps":        8,
            "effect_used": "wave",
            "generation_time": 3.2,
            "prompt_enhanced": "..."
        }
        """
        try:
            data = request.json or {}

            prompt     = data.get("prompt", "").strip()
            resolution = data.get("resolution", "480p")
            duration   = data.get("duration", "5s")
            motor      = data.get("motor", "auto")
            effect     = data.get("effect", "auto")
            ref_image  = data.get("ref_image")  # base64 o None

            if not prompt:
                return jsonify({"success": False, "error": "El prompt no puede estar vacío"}), 400

            if len(prompt) > 500:
                prompt = prompt[:500]

            logger.info(
                f"CicVideo generate: user={current_user.username} "
                f"res={resolution} dur={duration} motor={motor} effect={effect}"
            )

            result = _vm.generate(
                prompt=prompt,
                resolution=resolution,
                duration=duration,
                motor=motor,
                effect=effect,
                ref_b64=ref_image,
            )

            # Guardar estadística (no crítico — no bloquea respuesta)
            try:
                from modules.video_gen.main import VideoGeneratorModule  # noqa
                # Intentar guardar en SystemConfig como log liviano
                pass
            except Exception:
                pass

            return jsonify(result)

        except Exception as e:
            logger.error(f"video_generate error: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    # ─────────────────────────────────────────────────────────────────────
    # POST /api/video/feedback  — feedback del usuario
    # ─────────────────────────────────────────────────────────────────────
    @app.route("/api/video/feedback", methods=["POST"])
    @token_required
    def video_feedback(current_user):
        """
        Registra feedback del usuario sobre un video generado.

        Body: { "rating": 1-5, "motor": "cicvideo_math", "comment": "..." }
        """
        try:
            data    = request.json or {}
            rating  = int(data.get("rating", 3))
            motor   = data.get("motor", "unknown")
            comment = data.get("comment", "")[:300]

            if not 1 <= rating <= 5:
                return jsonify({"error": "rating debe ser 1–5"}), 400

            logger.info(
                f"CicVideo feedback: user={current_user.username} "
                f"rating={rating}/5 motor={motor}"
            )

            return jsonify({
                "success": True,
                "message": f"Feedback {rating}/5 registrado. ¡Gracias, ayuda a mejorar CicVideo!",
                "motor": motor,
                "rating": rating,
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ─────────────────────────────────────────────────────────────────────
    # POST /api/video/train  — entrenamiento del motor propio (solo dev)
    # ─────────────────────────────────────────────────────────────────────
    @app.route("/api/video/train", methods=["POST"])
    @dev_required
    def video_train():
        """
        Genera un video de entrenamiento con el motor matemático.
        Permite probar efectos, resoluciones y verificar el motor propio.

        Body: {
            "prompt": "...",
            "effect": "wave",
            "resolution": "480p",
            "duration": "3s"
        }
        """
        try:
            data       = request.json or {}
            prompt     = data.get("prompt", "video de entrenamiento CicVideo algoritmo matemático")
            effect     = data.get("effect", "gradient")
            resolution = data.get("resolution", "480p")
            duration   = data.get("duration", "3s")

            result = _vm.generate(
                prompt=prompt,
                resolution=resolution,
                duration=duration,
                motor="cicvideo_math",
                effect=effect,
            )

            # No retornar data (base64) en respuesta de train para no saturar logs
            return jsonify({
                "success":         result.get("success"),
                "motor":           result.get("motor"),
                "effect_used":     result.get("effect_used"),
                "frames":          result.get("frames"),
                "fps":             result.get("fps"),
                "resolution":      result.get("resolution"),
                "generation_time": result.get("generation_time"),
                "format":          result.get("format"),
                "has_data":        bool(result.get("data")),
                "error":           result.get("error"),
            })

        except Exception as e:
            logger.error(f"video_train error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # ─────────────────────────────────────────────────────────────────────
    # GET /api/video/motors  — estado de motores (solo dev)
    # ─────────────────────────────────────────────────────────────────────
    @app.route("/api/video/motors", methods=["GET"])
    @dev_required
    def video_motors():
        """Retorna estado detallado de cada motor (disponibilidad, tokens, etc.)"""
        info = _vm.info()
        return jsonify(info)

    logger.info("✅ CicVideo: rutas registradas (/api/video/*)")
