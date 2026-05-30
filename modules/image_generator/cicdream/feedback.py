"""
modules/image_generator/cicdream/feedback.py
=============================================
CicDream v1.0 — Sistema de Feedback y Aprendizaje

Responsabilidades:
1. Guardar cada generación en PostgreSQL
2. Recibir feedback del usuario (rating + detalles)
3. Aplicar ajustes al motor en tiempo real
4. Construir memoria de qué funciona para cada concepto

Tablas que crea automáticamente:
  cicdream_generation  ← cada imagen generada
  cicdream_feedback    ← rating + detalles del usuario
  cicdream_learned     ← parámetros aprendidos por concepto
"""

import json
import logging
import hashlib
from datetime import datetime

logger = logging.getLogger('cicdream.feedback')


# ═══════════════════════════════════════════════════════════════════════════
# SQL — Definición de tablas
# ═══════════════════════════════════════════════════════════════════════════

SQL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS cicdream_generation (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER,
    prompt          TEXT NOT NULL,
    prompt_hash     VARCHAR(32),
    style           VARCHAR(50),
    size            VARCHAR(20),
    quality         VARCHAR(20),
    engine_version  VARCHAR(20),
    seed            BIGINT,
    steps           INTEGER,
    guidance_scale  FLOAT,
    time_ms         INTEGER,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cicdream_feedback (
    id              SERIAL PRIMARY KEY,
    generation_id   INTEGER REFERENCES cicdream_generation(id),
    user_id         INTEGER,
    rating          FLOAT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    details         TEXT,
    tags            TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cicdream_learned (
    id                  SERIAL PRIMARY KEY,
    concept             VARCHAR(100) UNIQUE NOT NULL,
    guidance_scale      FLOAT DEFAULT 7.5,
    detail_strength     FLOAT DEFAULT 0.6,
    noise_temp          FLOAT DEFAULT 1.0,
    diffusion_steps     INTEGER DEFAULT 20,
    palette_adjustments TEXT DEFAULT '{}',
    vocab_adjustments   TEXT DEFAULT '{}',
    avg_rating          FLOAT DEFAULT 0.0,
    total_feedbacks     INTEGER DEFAULT 0,
    total_generations   INTEGER DEFAULT 0,
    last_updated        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gen_prompt_hash
    ON cicdream_generation(prompt_hash);
CREATE INDEX IF NOT EXISTS idx_gen_user
    ON cicdream_generation(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_gen
    ON cicdream_feedback(generation_id);
CREATE INDEX IF NOT EXISTS idx_learned_concept
    ON cicdream_learned(concept);
"""


# ═══════════════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class CicDreamFeedback:
    """
    Sistema de feedback y aprendizaje de CicDream.

    Flujo completo:
    1. generate()  → guardar generación → retornar generation_id
    2. Usuario ve imagen
    3. submit()    → guardar feedback → ajustar motor en tiempo real
    4. get_params() → leer parámetros aprendidos para próxima generación
    """

    def __init__(self, db_engine=None):
        """
        Args:
            db_engine: SQLAlchemy engine (de cic_ia_mejorado.py)
                       Si es None, usa modo memoria (sin BD)
        """
        self.db      = db_engine
        self._memory = {}   # fallback sin BD
        self._ensure_tables()

    # ── Configuración de tablas ───────────────────────────────────────────

    def _ensure_tables(self):
        """Crea las tablas si no existen."""
        if self.db is None:
            logger.info("[Feedback] Modo memoria (sin BD)")
            return
        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                # Ejecutar cada CREATE TABLE por separado
                for stmt in SQL_CREATE_TABLES.strip().split(';'):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(text(stmt))
                conn.commit()
            logger.info("[Feedback] Tablas cicdream_* verificadas/creadas")
        except Exception as e:
            logger.error(f"[Feedback] Error creando tablas: {e}")

    # ── Registro de generación ────────────────────────────────────────────

    def save_generation(self, user_id: int, prompt: str,
                         style: str, size: str, quality: str,
                         generation_result: dict) -> int:
        """
        Guarda una generación en la BD.

        Returns:
            generation_id (int) — para vincularlo con el feedback después
        """
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:32]

        record = {
            'user_id':        user_id,
            'prompt':         prompt[:1000],
            'prompt_hash':    prompt_hash,
            'style':          style,
            'size':           size,
            'quality':        quality,
            'engine_version': generation_result.get('provider', 'CicDream v1.0'),
            'seed':           generation_result.get('seed', 0),
            'steps':          generation_result.get('steps', 20),
            'guidance_scale': generation_result.get('guidance', 7.5),
            'time_ms':        generation_result.get('time_ms', 0),
        }

        if self.db is None:
            # Modo memoria
            gen_id = len(self._memory) + 1
            self._memory[gen_id] = {'generation': record, 'feedback': None}
            return gen_id

        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                result = conn.execute(
                    text("""
                        INSERT INTO cicdream_generation
                            (user_id, prompt, prompt_hash, style, size, quality,
                             engine_version, seed, steps, guidance_scale, time_ms)
                        VALUES
                            (:user_id, :prompt, :prompt_hash, :style, :size, :quality,
                             :engine_version, :seed, :steps, :guidance_scale, :time_ms)
                        RETURNING id
                    """),
                    record
                )
                gen_id = result.fetchone()[0]
                conn.commit()

            # Actualizar contador en cicdream_learned
            self._increment_generation_count(prompt)
            return gen_id

        except Exception as e:
            logger.error(f"[Feedback] Error guardando generación: {e}")
            return 0

    # ── Recibir feedback ──────────────────────────────────────────────────

    def submit(self, generation_id: int,
                user_id: int,
                rating: float,
                details: str = '',
                tags: list = None,
                engine=None) -> dict:
        """
        Recibe y procesa feedback del usuario.

        Args:
            generation_id: ID de la generación (de save_generation)
            user_id:       ID del usuario
            rating:        1.0 a 5.0
            details:       Texto libre ("más oscuro", "más detalle")
            tags:          Lista de tags seleccionados
            engine:        Instancia de CicDreamEngine (para ajuste en tiempo real)

        Returns:
            dict con resultado del ajuste
        """
        import numpy as np
        rating = float(np.clip(rating, 1.0, 5.0))
        tags   = tags or []
        tags_str = json.dumps(tags)

        # Guardar en BD
        fb_id = self._save_feedback_db(
            generation_id, user_id, rating, details, tags_str
        )

        # Obtener el prompt de la generación
        prompt = self._get_prompt(generation_id)
        style  = self._get_style(generation_id)

        # Ajustar motor en tiempo real
        adjustments = {}
        if engine is not None and prompt:
            try:
                adjustments = engine.apply_feedback(
                    prompt   = prompt,
                    rating   = rating,
                    details  = details,
                    tags     = tags,
                    style    = style or 'realistic',
                )
            except Exception as e:
                logger.error(f"[Feedback] Error ajustando motor: {e}")

        # Actualizar parámetros aprendidos por concepto
        self._update_learned(prompt, rating, adjustments)

        logger.info(
            f"[Feedback] id={fb_id} gen={generation_id} "
            f"rating={rating:.1f} user={user_id}"
        )

        return {
            'success':      True,
            'feedback_id':  fb_id,
            'rating':       rating,
            'adjustments':  adjustments,
            'message':      self._feedback_message(rating),
        }

    # ── Recuperar parámetros aprendidos ───────────────────────────────────

    def get_learned_params(self, prompt: str) -> dict:
        """
        Recupera parámetros aprendidos para un concepto.
        Usado por el engine antes de generar para partir de
        la mejor configuración conocida.
        """
        concept = self._extract_concept(prompt)

        if self.db is None:
            return {}

        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT guidance_scale, detail_strength, noise_temp,
                               diffusion_steps, avg_rating, total_feedbacks
                        FROM cicdream_learned
                        WHERE concept = :concept
                    """),
                    {'concept': concept}
                ).fetchone()

            if row:
                return {
                    'concept':         concept,
                    'guidance_scale':  row[0],
                    'detail_strength': row[1],
                    'noise_temp':      row[2],
                    'diffusion_steps': row[3],
                    'avg_rating':      row[4],
                    'total_feedbacks': row[5],
                }
        except Exception as e:
            logger.warning(f"[Feedback] Error leyendo params: {e}")

        return {}

    # ── Estadísticas ──────────────────────────────────────────────────────

    def get_stats(self, user_id: int = None) -> dict:
        """Estadísticas del sistema de feedback."""
        if self.db is None:
            return {
                'total_generations': len(self._memory),
                'total_feedbacks':   sum(
                    1 for v in self._memory.values() if v['feedback']
                ),
                'mode': 'memory',
            }

        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                # Total generaciones
                total_gen = conn.execute(
                    text("SELECT COUNT(*) FROM cicdream_generation"
                         + (f" WHERE user_id={user_id}" if user_id else ""))
                ).scalar()

                # Total feedbacks
                total_fb = conn.execute(
                    text("SELECT COUNT(*) FROM cicdream_feedback"
                         + (f" WHERE user_id={user_id}" if user_id else ""))
                ).scalar()

                # Rating promedio
                avg_rating = conn.execute(
                    text("SELECT AVG(rating) FROM cicdream_feedback"
                         + (f" WHERE user_id={user_id}" if user_id else ""))
                ).scalar()

                # Conceptos aprendidos
                total_learned = conn.execute(
                    text("SELECT COUNT(*) FROM cicdream_learned")
                ).scalar()

                # Top conceptos
                top = conn.execute(
                    text("""
                        SELECT concept, avg_rating, total_feedbacks
                        FROM cicdream_learned
                        WHERE total_feedbacks > 0
                        ORDER BY avg_rating DESC
                        LIMIT 5
                    """)
                ).fetchall()

            return {
                'total_generations': total_gen or 0,
                'total_feedbacks':   total_fb   or 0,
                'avg_rating':        round(float(avg_rating or 0), 2),
                'concepts_learned':  total_learned or 0,
                'top_concepts': [
                    {'concept': r[0], 'avg_rating': round(r[1], 2),
                     'feedbacks': r[2]}
                    for r in (top or [])
                ],
            }
        except Exception as e:
            logger.error(f"[Feedback] Error obteniendo stats: {e}")
            return {}

    def get_history(self, user_id: int, limit: int = 20) -> list:
        """Historial de generaciones de un usuario."""
        if self.db is None:
            return list(self._memory.values())[:limit]

        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT g.id, g.prompt, g.style, g.created_at,
                               f.rating, f.details
                        FROM cicdream_generation g
                        LEFT JOIN cicdream_feedback f ON f.generation_id = g.id
                        WHERE g.user_id = :uid
                        ORDER BY g.created_at DESC
                        LIMIT :lim
                    """),
                    {'uid': user_id, 'lim': limit}
                ).fetchall()

            return [
                {
                    'id':        r[0],
                    'prompt':    r[1],
                    'style':     r[2],
                    'created':   r[3].isoformat() if r[3] else None,
                    'rating':    r[4],
                    'details':   r[5],
                }
                for r in (rows or [])
            ]
        except Exception as e:
            logger.error(f"[Feedback] Error obteniendo historial: {e}")
            return []

    # ── Helpers privados ──────────────────────────────────────────────────

    def _save_feedback_db(self, generation_id: int, user_id: int,
                           rating: float, details: str,
                           tags_str: str) -> int:
        if self.db is None:
            if generation_id in self._memory:
                self._memory[generation_id]['feedback'] = {
                    'rating': rating, 'details': details
                }
            return generation_id

        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                result = conn.execute(
                    text("""
                        INSERT INTO cicdream_feedback
                            (generation_id, user_id, rating, details, tags)
                        VALUES (:gen_id, :uid, :rating, :details, :tags)
                        RETURNING id
                    """),
                    {
                        'gen_id':  generation_id,
                        'uid':     user_id,
                        'rating':  rating,
                        'details': details[:500] if details else '',
                        'tags':    tags_str,
                    }
                )
                fb_id = result.fetchone()[0]
                conn.commit()
            return fb_id
        except Exception as e:
            logger.error(f"[Feedback] Error guardando feedback: {e}")
            return 0

    def _get_prompt(self, generation_id: int) -> str:
        if self.db is None:
            return self._memory.get(generation_id, {}).get(
                'generation', {}
            ).get('prompt', '')

        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                row = conn.execute(
                    text("SELECT prompt FROM cicdream_generation WHERE id=:id"),
                    {'id': generation_id}
                ).fetchone()
            return row[0] if row else ''
        except Exception:
            return ''

    def _get_style(self, generation_id: int) -> str:
        if self.db is None:
            return 'realistic'
        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                row = conn.execute(
                    text("SELECT style FROM cicdream_generation WHERE id=:id"),
                    {'id': generation_id}
                ).fetchone()
            return row[0] if row else 'realistic'
        except Exception:
            return 'realistic'

    def _extract_concept(self, prompt: str) -> str:
        """Extrae el concepto principal del prompt."""
        if not prompt:
            return 'general'
        tokens = prompt.lower().split()
        # El concepto = primera palabra sustantiva (>3 chars)
        for t in tokens:
            if len(t) > 3 and t not in {'para', 'con', 'bajo', 'sobre',
                                          'entre', 'desde', 'hasta', 'the',
                                          'and', 'with', 'under', 'over'}:
                return t[:50]
        return tokens[0][:50] if tokens else 'general'

    def _update_learned(self, prompt: str, rating: float,
                         adjustments: dict):
        """Actualiza la tabla de parámetros aprendidos."""
        if not prompt or self.db is None:
            return

        concept = self._extract_concept(prompt)

        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                # Upsert — insertar o actualizar
                conn.execute(
                    text("""
                        INSERT INTO cicdream_learned
                            (concept, guidance_scale, detail_strength,
                             diffusion_steps, avg_rating, total_feedbacks,
                             last_updated)
                        VALUES
                            (:concept, :guidance, :detail, :steps,
                             :rating, 1, NOW())
                        ON CONFLICT (concept) DO UPDATE SET
                            guidance_scale  = (cicdream_learned.guidance_scale
                                               * cicdream_learned.total_feedbacks
                                               + EXCLUDED.guidance_scale)
                                              / (cicdream_learned.total_feedbacks + 1),
                            detail_strength = (cicdream_learned.detail_strength
                                               * cicdream_learned.total_feedbacks
                                               + EXCLUDED.detail_strength)
                                              / (cicdream_learned.total_feedbacks + 1),
                            diffusion_steps = EXCLUDED.diffusion_steps,
                            avg_rating      = (cicdream_learned.avg_rating
                                               * cicdream_learned.total_feedbacks
                                               + EXCLUDED.avg_rating)
                                              / (cicdream_learned.total_feedbacks + 1),
                            total_feedbacks = cicdream_learned.total_feedbacks + 1,
                            last_updated    = NOW()
                    """),
                    {
                        'concept': concept,
                        'guidance': adjustments.get('guidance_scale', 7.5),
                        'detail':   adjustments.get('detail_strength', 0.6),
                        'steps':    adjustments.get('diffusion_steps', 20),
                        'rating':   rating,
                    }
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"[Feedback] Error actualizando learned: {e}")

    def _increment_generation_count(self, prompt: str):
        """Incrementa el contador de generaciones para un concepto."""
        if not prompt or self.db is None:
            return
        concept = self._extract_concept(prompt)
        try:
            from sqlalchemy import text
            with self.db.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO cicdream_learned (concept, total_generations)
                        VALUES (:c, 1)
                        ON CONFLICT (concept) DO UPDATE SET
                            total_generations = cicdream_learned.total_generations + 1
                    """),
                    {'c': concept}
                )
                conn.commit()
        except Exception:
            pass

    def _feedback_message(self, rating: float) -> str:
        """Mensaje de respuesta según el rating."""
        if rating >= 4.5:
            return "¡Excelente! CicDream aprendió que esta configuración funciona muy bien."
        elif rating >= 3.5:
            return "Buena imagen. CicDream reforzó los parámetros actuales."
        elif rating >= 2.5:
            return "CicDream tomó nota. Los ajustes mejorarán el próximo resultado."
        else:
            return "CicDream ajustó sus parámetros. La próxima imagen será diferente."


# ── Instancia global ──────────────────────────────────────────────────────
_feedback_instance = None

def get_feedback(db_engine=None) -> CicDreamFeedback:
    """Retorna instancia singleton del sistema de feedback."""
    global _feedback_instance
    if _feedback_instance is None:
        _feedback_instance = CicDreamFeedback(db_engine)
    return _feedback_instance
