"""
modules/image_generator/cicdream/trainer.py
============================================
CicDream v1.0 — Trainer / Optimizador

Responsabilidades:
1. Analizar el historial de feedback acumulado
2. Optimizar los parámetros matemáticos del motor
3. Detectar patrones de qué funciona para qué concepto
4. Ajustar ecuaciones de difusión con gradiente descendente simple
5. Programar mejoras automáticas en background

Algoritmo de optimización propio:
  - Gradient Descent simplificado sobre el espacio de hiperparámetros
  - Loss function: 1 - (avg_rating / 5.0)
  - Learning rate adaptativo según cantidad de feedbacks
"""

import numpy as np
import json
import os
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger('cicdream.trainer')


# ═══════════════════════════════════════════════════════════════════════════
# ESPACIO DE HIPERPARÁMETROS
# Define los rangos válidos para cada parámetro optimizable
# ═══════════════════════════════════════════════════════════════════════════

PARAM_SPACE = {
    # nombre          min    max    step   descripción
    'guidance_scale': (1.0,  15.0,  0.1,  'Fuerza de guía del texto'),
    'detail_strength':(0.1,   1.0,  0.05, 'Nivel de detalle fino'),
    'noise_temp':     (0.5,   2.0,  0.05, 'Temperatura del ruido inicial'),
    'diffusion_steps':(5,     60,   5,    'Pasos de denoising'),
    'blend_factor':   (0.1,   0.6,  0.05, 'Mezcla difusión/paleta'),
}

# Learning rates iniciales por parámetro
LEARNING_RATES = {
    'guidance_scale':  0.3,
    'detail_strength': 0.05,
    'noise_temp':      0.05,
    'diffusion_steps': 2.0,
    'blend_factor':    0.03,
}


# ═══════════════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class CicDreamTrainer:
    """
    Optimizador continuo de CicDream.

    Usa gradient descent simplificado sobre el espacio
    de hiperparámetros, guiado por el feedback de usuarios.

    El gradiente se aproxima así:
      ∂L/∂θ ≈ (L(θ+δ) - L(θ-δ)) / (2δ)
    donde L = 1 - avg_rating/5  (loss a minimizar)

    Con cada feedback:
      θ ← θ - lr · ∂L/∂θ
    """

    def __init__(self, state_path: str = None):
        self.state_path = state_path or '/tmp/cicdream_trainer_state.json'

        # Parámetros actuales del optimizador
        self.params = {
            'guidance_scale':  7.5,
            'detail_strength': 0.6,
            'noise_temp':      1.0,
            'diffusion_steps': 20,
            'blend_factor':    0.35,
        }

        # Gradientes acumulados (momentum)
        self.gradients = {k: 0.0 for k in self.params}

        # Learning rates adaptativos (Adam-like)
        self.lr        = dict(LEARNING_RATES)
        self.lr_decay  = 0.995   # decay por cada actualización
        self.momentum  = 0.9     # factor de momentum

        # Historial de pérdida para detectar convergencia
        self.loss_history  = []
        self.param_history = []

        # Contadores
        self.update_count   = 0
        self.total_feedbacks= 0

        # Mejores parámetros encontrados
        self.best_params = dict(self.params)
        self.best_loss   = 1.0

        # Por concepto
        self.concept_params = {}

        # Background training thread
        self._train_thread  = None
        self._stop_flag     = threading.Event()
        self._feedback_queue= []
        self._queue_lock    = threading.Lock()

        self._load_state()

    # ── Paso de optimización ──────────────────────────────────────────────

    def step(self, rating: float, prompt: str = '',
              details: str = '', config=None) -> dict:
        """
        Ejecuta un paso de optimización con el feedback recibido.

        Args:
            rating:  1.0 - 5.0
            prompt:  Prompt que generó la imagen
            details: Detalles del usuario
            config:  Instancia de DiffusionConfig a actualizar

        Returns:
            dict con los nuevos parámetros y la pérdida
        """
        # Loss actual: cuanto más bajo mejor
        # rating=5 → loss=0.0, rating=1 → loss=0.8
        loss = 1.0 - (rating / 5.0) * 0.8

        self.loss_history.append(loss)
        self.total_feedbacks += 1

        # ── Calcular gradientes ────────────────────────────────────────
        # El gradiente aproxima en qué dirección ajustar cada parámetro
        grads = self._compute_gradients(rating, details, prompt)

        # ── Actualizar con momentum ────────────────────────────────────
        new_params = {}
        for name, grad in grads.items():
            # Momentum: suaviza la dirección del gradiente
            self.gradients[name] = (
                self.momentum * self.gradients[name] +
                (1 - self.momentum) * grad
            )

            # Gradient descent step
            lr = self.lr[name] * (self.lr_decay ** self.update_count)
            delta = lr * self.gradients[name]

            # Aplicar con clipping para estabilidad
            p_min, p_max, p_step, _ = PARAM_SPACE[name]
            new_val = float(np.clip(
                self.params[name] - delta,
                p_min, p_max
            ))
            # Redondear al step más cercano
            new_val = round(new_val / p_step) * p_step
            new_params[name] = new_val

        self.params.update(new_params)
        self.update_count += 1

        # ── Guardar mejores parámetros ─────────────────────────────────
        if loss < self.best_loss:
            self.best_loss   = loss
            self.best_params = dict(self.params)
            logger.info(
                f"[Trainer] Nuevos mejores parámetros: loss={loss:.3f} "
                f"guidance={self.params['guidance_scale']:.2f}"
            )

        # ── Actualizar parámetros por concepto ─────────────────────────
        if prompt:
            concept = self._extract_concept(prompt)
            self._update_concept_params(concept, new_params, rating)

        # ── Registrar historial ────────────────────────────────────────
        self.param_history.append({
            'step':   self.update_count,
            'loss':   round(loss, 4),
            'params': dict(self.params),
        })
        # Mantener historial acotado
        if len(self.param_history) > 100:
            self.param_history = self.param_history[-50:]
        if len(self.loss_history) > 200:
            self.loss_history = self.loss_history[-100:]

        # ── Aplicar al config de difusión ──────────────────────────────
        if config is not None:
            self._apply_to_config(config)

        self._save_state()

        logger.info(
            f"[Trainer] step={self.update_count} loss={loss:.3f} "
            f"guidance={self.params['guidance_scale']:.2f} "
            f"T={self.params['diffusion_steps']:.0f} "
            f"detail={self.params['detail_strength']:.2f}"
        )

        return {
            'step':   self.update_count,
            'loss':   round(loss, 4),
            'params': dict(self.params),
            'best':   dict(self.best_params),
            'trend':  self._get_trend(),
        }

    # ── Cálculo de gradientes ─────────────────────────────────────────────

    def _compute_gradients(self, rating: float,
                            details: str, prompt: str) -> dict:
        """
        Calcula gradientes aproximados para cada parámetro.

        Estrategia:
        - Rating alto (≥4) → reforzar dirección actual (grad negativo)
        - Rating bajo (≤2) → revertir dirección (grad positivo)
        - Detalles textuales → gradientes específicos por parámetro
        """
        grads = {}
        details_lower = (details or '').lower()
        factor = (3.0 - rating) / 5.0  # positivo si malo, negativo si bueno

        # ── guidance_scale ────────────────────────────────────────────
        # Más colorido/vibrante → aumentar guidance
        # Sin relación con prompt → puede ser guidance muy alto o bajo
        if any(w in details_lower for w in ['vibrante', 'colorido', 'saturado']):
            grads['guidance_scale'] = -0.5  # aumentar
        elif any(w in details_lower for w in ['sin relación', 'no corresponde', 'diferente']):
            # Probar reducir guidance (puede estar sobreguiando)
            grads['guidance_scale'] = 0.3
        else:
            grads['guidance_scale'] = factor * 0.4

        # ── detail_strength ───────────────────────────────────────────
        # Más detalle pedido → aumentar
        # Demasiado ruido/borroso → reducir
        if any(w in details_lower for w in ['más detalle', 'nítido', 'sharp', 'detail']):
            grads['detail_strength'] = -0.08  # aumentar
        elif any(w in details_lower for w in ['borroso', 'ruido', 'blur', 'noise']):
            grads['detail_strength'] = 0.08   # reducir
        else:
            grads['detail_strength'] = factor * 0.03

        # ── noise_temp ────────────────────────────────────────────────
        # Más variedad/creativo → aumentar temperatura
        # Más predecible/consistente → reducir
        if any(w in details_lower for w in ['creativo', 'diferente', 'variado', 'unique']):
            grads['noise_temp'] = -0.05   # aumentar creatividad
        elif any(w in details_lower for w in ['consistente', 'similar', 'igual']):
            grads['noise_temp'] = 0.05    # reducir aleatoriedad
        else:
            grads['noise_temp'] = factor * 0.02

        # ── diffusion_steps ───────────────────────────────────────────
        # Mejor calidad pedida → más pasos
        # Muy lento → reducir pasos
        if any(w in details_lower for w in ['calidad', 'mejor', 'quality', 'hd']):
            grads['diffusion_steps'] = -3.0  # aumentar pasos
        elif any(w in details_lower for w in ['rápido', 'fast', 'quick']):
            grads['diffusion_steps'] = 3.0   # reducir pasos
        else:
            grads['diffusion_steps'] = factor * 2.0

        # ── blend_factor ──────────────────────────────────────────────
        # Colores incorrectos → ajustar mezcla con paleta
        if any(w in details_lower for w in ['color', 'tono', 'paleta', 'hue']):
            grads['blend_factor'] = -factor * 0.04
        else:
            grads['blend_factor'] = factor * 0.02

        return grads

    # ── Análisis de tendencia ─────────────────────────────────────────────

    def _get_trend(self) -> str:
        """Detecta si el motor está mejorando, empeorando o estable."""
        if len(self.loss_history) < 5:
            return 'insufficient_data'

        recent = self.loss_history[-5:]
        slope  = np.polyfit(range(len(recent)), recent, 1)[0]

        if slope < -0.02:
            return 'improving'    # loss bajando → mejorando
        elif slope > 0.02:
            return 'degrading'    # loss subiendo → empeorando
        else:
            return 'stable'

    def get_convergence_report(self) -> dict:
        """Reporte completo del estado de convergencia."""
        if len(self.loss_history) < 3:
            return {'status': 'insufficient_data', 'feedbacks': self.total_feedbacks}

        recent_loss = np.mean(self.loss_history[-10:]) if len(self.loss_history) >= 10 \
                      else np.mean(self.loss_history)
        initial_loss = np.mean(self.loss_history[:5]) if len(self.loss_history) >= 5 \
                       else self.loss_history[0]

        improvement = (initial_loss - recent_loss) / (initial_loss + 1e-8)

        return {
            'status':          self._get_trend(),
            'feedbacks':       self.total_feedbacks,
            'updates':         self.update_count,
            'initial_loss':    round(float(initial_loss), 4),
            'current_loss':    round(float(recent_loss), 4),
            'improvement_pct': round(float(improvement * 100), 1),
            'best_loss':       round(self.best_loss, 4),
            'best_params':     self.best_params,
            'current_params':  dict(self.params),
        }

    # ── Parámetros por concepto ───────────────────────────────────────────

    def _update_concept_params(self, concept: str,
                                params: dict, rating: float):
        """Mantiene parámetros óptimos por concepto."""
        if concept not in self.concept_params:
            self.concept_params[concept] = {
                'params':    dict(params),
                'avg_rating': rating,
                'count':      1,
            }
        else:
            cp = self.concept_params[concept]
            n  = cp['count']
            # Promedio ponderado exponencial
            alpha = 0.3  # peso del nuevo dato
            for k in params:
                if k in cp['params']:
                    cp['params'][k] = (
                        (1 - alpha) * cp['params'][k] +
                        alpha * params[k]
                    )
            cp['avg_rating'] = (cp['avg_rating'] * n + rating) / (n + 1)
            cp['count'] = n + 1

    def get_concept_params(self, concept: str) -> dict:
        """Retorna los mejores parámetros aprendidos para un concepto."""
        if concept in self.concept_params:
            cp = self.concept_params[concept]
            if cp['count'] >= 3:  # mínimo 3 feedbacks para confiar
                return cp['params']
        return {}

    def _extract_concept(self, prompt: str) -> str:
        """Extrae concepto principal del prompt."""
        tokens = prompt.lower().split()
        for t in tokens:
            if len(t) > 3 and t not in {
                'para', 'con', 'bajo', 'sobre', 'entre',
                'desde', 'hasta', 'the', 'and', 'with', 'under'
            }:
                return t[:30]
        return tokens[0][:30] if tokens else 'general'

    # ── Aplicar al config ─────────────────────────────────────────────────

    def _apply_to_config(self, config):
        """Aplica los parámetros optimizados al DiffusionConfig."""
        config.guidance_scale  = self.params['guidance_scale']
        config.detail_strength = self.params['detail_strength']
        config.noise_temperature = self.params['noise_temp']
        config.T               = int(self.params['diffusion_steps'])

    def apply_best_to_config(self, config):
        """Aplica los MEJORES parámetros históricos al config."""
        config.guidance_scale  = self.best_params.get('guidance_scale', 7.5)
        config.detail_strength = self.best_params.get('detail_strength', 0.6)
        config.noise_temperature = self.best_params.get('noise_temp', 1.0)
        config.T               = int(self.best_params.get('diffusion_steps', 20))

    # ── Training en background ────────────────────────────────────────────

    def queue_feedback(self, rating: float, prompt: str = '',
                        details: str = ''):
        """Encola feedback para procesamiento asíncrono."""
        with self._queue_lock:
            self._feedback_queue.append({
                'rating':  rating,
                'prompt':  prompt,
                'details': details,
                'ts':      time.time(),
            })

    def start_background_training(self, config=None, interval: int = 60):
        """
        Inicia el entrenamiento en background.
        Procesa la cola de feedback cada `interval` segundos.
        """
        if self._train_thread and self._train_thread.is_alive():
            return

        self._stop_flag.clear()

        def _train_loop():
            logger.info(f"[Trainer] Background training iniciado (cada {interval}s)")
            while not self._stop_flag.is_set():
                time.sleep(interval)
                self._process_queue(config)

        self._train_thread = threading.Thread(
            target=_train_loop, daemon=True, name='CicDreamTrainer'
        )
        self._train_thread.start()

    def stop_background_training(self):
        """Detiene el entrenamiento en background."""
        self._stop_flag.set()
        if self._train_thread:
            self._train_thread.join(timeout=5)
        logger.info("[Trainer] Background training detenido")

    def _process_queue(self, config=None):
        """Procesa todos los feedbacks en la cola."""
        with self._queue_lock:
            queue = list(self._feedback_queue)
            self._feedback_queue.clear()

        if not queue:
            return

        logger.info(f"[Trainer] Procesando {len(queue)} feedbacks en cola")
        for item in queue:
            self.step(
                rating  = item['rating'],
                prompt  = item['prompt'],
                details = item['details'],
                config  = config,
            )

    # ── Persistencia ──────────────────────────────────────────────────────

    def _save_state(self):
        """Guarda el estado del trainer."""
        try:
            state = {
                'params':          self.params,
                'gradients':       self.gradients,
                'lr':              self.lr,
                'loss_history':    self.loss_history[-50:],
                'update_count':    self.update_count,
                'total_feedbacks': self.total_feedbacks,
                'best_params':     self.best_params,
                'best_loss':       self.best_loss,
                'concept_params':  self.concept_params,
                'last_updated':    datetime.utcnow().isoformat(),
            }
            with open(self.state_path, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"[Trainer] No se pudo guardar estado: {e}")

    def _load_state(self):
        """Carga el estado previo del trainer."""
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, 'r') as f:
                    state = json.load(f)
                self.params          = state.get('params',          self.params)
                self.gradients       = state.get('gradients',       self.gradients)
                self.lr              = state.get('lr',              self.lr)
                self.loss_history    = state.get('loss_history',    [])
                self.update_count    = state.get('update_count',    0)
                self.total_feedbacks = state.get('total_feedbacks', 0)
                self.best_params     = state.get('best_params',     dict(self.params))
                self.best_loss       = state.get('best_loss',       1.0)
                self.concept_params  = state.get('concept_params',  {})
                logger.info(
                    f"[Trainer] Estado cargado: "
                    f"{self.update_count} updates, "
                    f"loss={self.best_loss:.3f}"
                )
        except Exception as e:
            logger.warning(f"[Trainer] No se pudo cargar estado: {e}")

    # ── Reset ──────────────────────────────────────────────────────────────

    def reset(self, keep_best: bool = True):
        """Reinicia el trainer, opcionalmente conservando mejores params."""
        if keep_best and self.best_params:
            self.params = dict(self.best_params)
        self.gradients       = {k: 0.0 for k in self.params}
        self.lr              = dict(LEARNING_RATES)
        self.loss_history    = []
        self.param_history   = []
        self.update_count    = 0
        self._save_state()
        logger.info("[Trainer] Reset completado")


# ── Instancia global ──────────────────────────────────────────────────────
_trainer_instance = None

def get_trainer() -> CicDreamTrainer:
    """Retorna instancia singleton del trainer."""
    global _trainer_instance
    if _trainer_instance is None:
        _trainer_instance = CicDreamTrainer()
    return _trainer_instance
