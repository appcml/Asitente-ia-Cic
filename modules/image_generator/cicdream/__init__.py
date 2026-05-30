"""
modules/image_generator/cicdream/__init__.py
============================================
CicDream v1.0 — Motor propio de generación de imágenes

Exporta la interfaz pública del motor.
El exterior solo necesita importar desde aquí.

Uso desde main.py:
    from .cicdream import CicDream, cicdream_generate, cicdream_feedback

Uso desde routes.py:
    from .cicdream import cicdream_status
"""

import logging
import numpy as np

logger = logging.getLogger('cicdream')

# ── Importar componentes ──────────────────────────────────────────────────
try:
    from .engine   import CicDreamEngine,   get_engine,   ENGINE_NAME, ENGINE_VERSION
    from .feedback import CicDreamFeedback, get_feedback
    from .trainer  import CicDreamTrainer,  get_trainer
    from .embeddings import CicDreamEmbeddings
    from .palette    import CicDreamPalette
    from .diffusion  import CicDiffusion, DiffusionConfig
    _READY = True
except ImportError as e:
    _READY = False
    logger.error(f"[CicDream] Error al cargar componentes: {e}")
    ENGINE_NAME    = "CicDream"
    ENGINE_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════════════
# INTERFAZ PÚBLICA SIMPLIFICADA
# Todo el sistema se usa a través de estas funciones
# ═══════════════════════════════════════════════════════════════════════════

class CicDream:
    """
    Clase fachada de CicDream.
    Punto único de entrada para todo el motor.

    Ejemplo:
        cd = CicDream()
        results = cd.generate("un árbol en el bosque")
        cd.feedback(gen_id=1, rating=5.0, details="perfecto")
    """

    _instance = None

    def __new__(cls, db_engine=None):
        """Singleton — una sola instancia por proceso."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_engine=None):
        if self._initialized:
            return

        if not _READY:
            raise ImportError("CicDream no pudo cargar sus componentes")

        self.engine   = get_engine()
        self.feedback = get_feedback(db_engine)
        self.trainer  = get_trainer()

        # Vincular trainer con engine
        # Al iniciar aplica los mejores parámetros históricos
        self.trainer.apply_best_to_config(self.engine.config)

        # Iniciar background training
        self.trainer.start_background_training(
            config   = self.engine.config,
            interval = 120  # optimizar cada 2 minutos
        )

        self._initialized = True
        logger.info(
            f"[CicDream] Sistema inicializado — "
            f"{ENGINE_NAME} v{ENGINE_VERSION} listo"
        )

    # ── Generación ────────────────────────────────────────────────────────

    def generate(self, prompt: str,
                  style:   str = 'realistic',
                  size:    str = 'square',
                  quality: str = 'standard',
                  seed:    int = None,
                  count:   int = 1,
                  user_id: int = None) -> dict:
        """
        Genera imágenes y guarda la generación en BD.

        Returns:
            {
              'success':       True,
              'images':        [...],   # lista de imágenes
              'generation_id': int,     # para vincular con feedback
              'provider':      str,
              'engine':        'cicdream',
            }
        """
        # Consultar parámetros aprendidos para este concepto
        concept = self._extract_concept(prompt)
        learned = self.feedback.get_learned_params(prompt)
        if learned and learned.get('total_feedbacks', 0) >= 3:
            # Aplicar parámetros aprendidos si hay suficiente historial
            if 'guidance_scale' in learned:
                self.engine.config.guidance_scale = learned['guidance_scale']
            if 'diffusion_steps' in learned:
                self.engine.config.T = int(learned['diffusion_steps'])
            if 'detail_strength' in learned:
                self.engine.config.detail_strength = learned['detail_strength']
            logger.info(
                f"[CicDream] Usando params aprendidos para '{concept}': "
                f"guidance={learned['guidance_scale']:.2f}"
            )

        # También consultar parámetros del trainer por concepto
        concept_params = self.trainer.get_concept_params(concept)
        if concept_params:
            self.trainer._apply_to_config(self.engine.config)

        # Generar
        results = self.engine.generate(
            prompt  = prompt,
            style   = style,
            size    = size,
            quality = quality,
            seed    = seed,
            count   = count,
        )

        if not results:
            return {
                'success': False,
                'error':   'Motor CicDream no pudo generar imagen',
                'images':  [],
            }

        # Guardar generación en BD
        gen_id = 0
        if user_id is not None:
            gen_id = self.feedback.save_generation(
                user_id          = user_id,
                prompt           = prompt,
                style            = style,
                size             = size,
                quality          = quality,
                generation_result = results[0],
            )

        return {
            'success':       True,
            'images':        results,
            'count':         len(results),
            'generation_id': gen_id,
            'provider':      f"{ENGINE_NAME} v{ENGINE_VERSION}",
            'engine':        'cicdream',
            'concept':       concept,
        }

    # ── Feedback ──────────────────────────────────────────────────────────

    def submit_feedback(self, generation_id: int,
                         rating: float,
                         details: str = '',
                         tags: list = None,
                         user_id: int = None) -> dict:
        """
        Recibe feedback y ajusta el motor en tiempo real.

        Args:
            generation_id: ID retornado por generate()
            rating:        1.0 (malo) a 5.0 (excelente)
            details:       "más oscuro", "más detalle", etc.
            tags:          ["buena composición", "colores incorrectos", ...]
            user_id:       ID del usuario

        Returns:
            {'success': True, 'message': str, 'adjustments': dict}
        """
        # 1. Guardar en BD + ajustar engine
        result = self.feedback.submit(
            generation_id = generation_id,
            user_id       = user_id or 0,
            rating        = rating,
            details       = details,
            tags          = tags,
            engine        = self.engine,
        )

        # 2. Encolar en trainer para optimización matemática
        prompt = self.feedback._get_prompt(generation_id)
        self.trainer.queue_feedback(rating, prompt, details)

        # 3. Si hay muchos feedbacks acumulados → procesar inmediatamente
        with self.trainer._queue_lock:
            queue_size = len(self.trainer._feedback_queue)
        if queue_size >= 5:
            self.trainer._process_queue(self.engine.config)

        return result

    # ── Estado y estadísticas ─────────────────────────────────────────────

    def status(self) -> dict:
        """Estado completo del sistema CicDream."""
        engine_status  = self.engine.status()
        trainer_report = self.trainer.get_convergence_report()
        fb_stats       = self.feedback.get_stats()

        return {
            'name':        ENGINE_NAME,
            'version':     ENGINE_VERSION,
            'ready':       _READY,
            'engine':      engine_status,
            'trainer': {
                'updates':     trainer_report.get('updates', 0),
                'trend':       trainer_report.get('status', 'unknown'),
                'improvement': trainer_report.get('improvement_pct', 0),
                'best_loss':   trainer_report.get('best_loss', 1.0),
            },
            'feedback': {
                'total_generations': fb_stats.get('total_generations', 0),
                'total_feedbacks':   fb_stats.get('total_feedbacks', 0),
                'avg_rating':        fb_stats.get('avg_rating', 0),
                'concepts_learned':  fb_stats.get('concepts_learned', 0),
            },
        }

    def describe(self, prompt: str) -> dict:
        """Cómo CicDream interpreta un prompt."""
        return self.engine.describe_prompt(prompt)

    def history(self, user_id: int, limit: int = 20) -> list:
        """Historial de generaciones de un usuario."""
        return self.feedback.get_history(user_id, limit)

    def _extract_concept(self, prompt: str) -> str:
        tokens = prompt.lower().split()
        for t in tokens:
            if len(t) > 3 and t not in {
                'para','con','bajo','sobre','entre',
                'desde','hasta','the','and','with'
            }:
                return t[:30]
        return tokens[0][:30] if tokens else 'general'


# ═══════════════════════════════════════════════════════════════════════════
# FUNCIONES DE CONVENIENCIA
# Para usar sin instanciar la clase
# ═══════════════════════════════════════════════════════════════════════════

def cicdream_generate(prompt: str, style: str = 'realistic',
                       size: str = 'square', quality: str = 'standard',
                       seed: int = None, count: int = 1,
                       user_id: int = None, db_engine=None) -> dict:
    """Genera imágenes con CicDream. Función de conveniencia."""
    try:
        cd = CicDream(db_engine)
        return cd.generate(prompt, style, size, quality, seed, count, user_id)
    except Exception as e:
        logger.error(f"[CicDream] cicdream_generate error: {e}", exc_info=True)
        return {
            'success': False,
            'error':   str(e),
            'images':  [],
            'engine':  'cicdream',
        }


def cicdream_feedback(generation_id: int, rating: float,
                       details: str = '', tags: list = None,
                       user_id: int = None, db_engine=None) -> dict:
    """Envía feedback a CicDream. Función de conveniencia."""
    try:
        cd = CicDream(db_engine)
        return cd.submit_feedback(generation_id, rating, details, tags, user_id)
    except Exception as e:
        logger.error(f"[CicDream] cicdream_feedback error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


def cicdream_status(db_engine=None) -> dict:
    """Estado de CicDream. Función de conveniencia."""
    try:
        cd = CicDream(db_engine)
        return cd.status()
    except Exception as e:
        return {
            'name':    ENGINE_NAME,
            'version': ENGINE_VERSION,
            'ready':   False,
            'error':   str(e),
        }


def is_ready() -> bool:
    """Retorna True si CicDream está disponible."""
    return _READY


# ── Exportaciones públicas ────────────────────────────────────────────────
__all__ = [
    'CicDream',
    'cicdream_generate',
    'cicdream_feedback',
    'cicdream_status',
    'is_ready',
    'ENGINE_NAME',
    'ENGINE_VERSION',
    # Componentes individuales (para uso avanzado)
    'CicDreamEngine',
    'CicDreamFeedback',
    'CicDreamTrainer',
    'CicDreamEmbeddings',
    'CicDreamPalette',
    'CicDiffusion',
    'DiffusionConfig',
]
