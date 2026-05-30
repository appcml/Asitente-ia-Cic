"""
modules/image_generator/cicdream/embeddings.py
================================================
CicDream v1.0 — Sistema de Embeddings
Convierte texto (prompt) en vectores numéricos.

Sin modelos externos. Implementación propia basada en:
- Vocabulario semántico por categorías
- TF-IDF simplificado
- Vectores de concepto con pesos aprendibles
- Retroalimentación ajusta los pesos internamente
"""

import numpy as np
import hashlib
import re
import json
import os
import logging

logger = logging.getLogger('cicdream.embeddings')

# ═══════════════════════════════════════════════════════════════════════════
# VOCABULARIO SEMÁNTICO
# Cada concepto tiene un vector de características en 64 dimensiones
# Dimensiones representan: [color, forma, textura, luz, emoción, ...]
# ═══════════════════════════════════════════════════════════════════════════

# Dimensiones del espacio de embedding
EMBED_DIM = 64

# Categorías semánticas y sus conceptos
# Formato: concepto → [peso_color, peso_forma, peso_textura, peso_luz,
#                       peso_emocion, peso_detalle, peso_escala, peso_tiempo]
SEMANTIC_VOCAB = {

    # ── NATURALEZA ───────────────────────────────────────────────────────
    'árbol':      [0.4, 0.7, 0.6, 0.5, 0.3, 0.7, 0.6, 0.4],
    'arbol':      [0.4, 0.7, 0.6, 0.5, 0.3, 0.7, 0.6, 0.4],
    'tree':       [0.4, 0.7, 0.6, 0.5, 0.3, 0.7, 0.6, 0.4],
    'bosque':     [0.5, 0.6, 0.8, 0.4, 0.2, 0.8, 0.9, 0.5],
    'forest':     [0.5, 0.6, 0.8, 0.4, 0.2, 0.8, 0.9, 0.5],
    'montaña':    [0.3, 0.9, 0.5, 0.6, 0.1, 0.6, 1.0, 0.3],
    'mountain':   [0.3, 0.9, 0.5, 0.6, 0.1, 0.6, 1.0, 0.3],
    'río':        [0.2, 0.3, 0.7, 0.7, 0.4, 0.5, 0.7, 0.6],
    'mar':        [0.1, 0.2, 0.9, 0.8, 0.5, 0.4, 0.9, 0.7],
    'ocean':      [0.1, 0.2, 0.9, 0.8, 0.5, 0.4, 0.9, 0.7],
    'flor':       [0.9, 0.8, 0.5, 0.7, 0.8, 0.9, 0.2, 0.6],
    'flower':     [0.9, 0.8, 0.5, 0.7, 0.8, 0.9, 0.2, 0.6],
    'desierto':   [0.8, 0.4, 0.3, 0.9, 0.2, 0.3, 0.8, 0.3],
    'desert':     [0.8, 0.4, 0.3, 0.9, 0.2, 0.3, 0.8, 0.3],
    'nieve':      [0.05, 0.3, 0.7, 0.9, 0.1, 0.5, 0.6, 0.2],
    'snow':       [0.05, 0.3, 0.7, 0.9, 0.1, 0.5, 0.6, 0.2],

    # ── CIELO Y ESPACIO ──────────────────────────────────────────────────
    'cielo':      [0.2, 0.1, 0.3, 0.9, 0.4, 0.2, 0.9, 0.7],
    'sky':        [0.2, 0.1, 0.3, 0.9, 0.4, 0.2, 0.9, 0.7],
    'noche':      [0.05, 0.1, 0.2, 0.1, 0.6, 0.3, 0.9, 0.1],
    'night':      [0.05, 0.1, 0.2, 0.1, 0.6, 0.3, 0.9, 0.1],
    'atardecer':  [0.9, 0.2, 0.3, 0.8, 0.7, 0.4, 0.8, 0.8],
    'sunset':     [0.9, 0.2, 0.3, 0.8, 0.7, 0.4, 0.8, 0.8],
    'amanecer':   [0.8, 0.2, 0.3, 0.9, 0.8, 0.4, 0.8, 0.9],
    'sunrise':    [0.8, 0.2, 0.3, 0.9, 0.8, 0.4, 0.8, 0.9],
    'espacio':    [0.05, 0.1, 0.1, 0.05, 0.9, 0.5, 1.0, 0.5],
    'space':      [0.05, 0.1, 0.1, 0.05, 0.9, 0.5, 1.0, 0.5],
    'galaxia':    [0.3, 0.5, 0.2, 0.3, 0.9, 0.7, 1.0, 0.5],
    'galaxy':     [0.3, 0.5, 0.2, 0.3, 0.9, 0.7, 1.0, 0.5],
    'nebulosa':   [0.6, 0.3, 0.4, 0.4, 0.8, 0.6, 0.9, 0.5],
    'estrellas':  [0.9, 0.1, 0.1, 0.3, 0.7, 0.4, 1.0, 0.5],
    'stars':      [0.9, 0.1, 0.1, 0.3, 0.7, 0.4, 1.0, 0.5],
    'luna':       [0.9, 0.9, 0.2, 0.5, 0.6, 0.5, 0.8, 0.3],
    'moon':       [0.9, 0.9, 0.2, 0.5, 0.6, 0.5, 0.8, 0.3],

    # ── CIUDAD Y ARQUITECTURA ────────────────────────────────────────────
    'ciudad':     [0.5, 0.9, 0.6, 0.6, 0.5, 0.9, 0.9, 0.5],
    'city':       [0.5, 0.9, 0.6, 0.6, 0.5, 0.9, 0.9, 0.5],
    'edificio':   [0.4, 0.9, 0.7, 0.5, 0.2, 0.8, 0.8, 0.4],
    'building':   [0.4, 0.9, 0.7, 0.5, 0.2, 0.8, 0.8, 0.4],
    'castillo':   [0.5, 1.0, 0.8, 0.6, 0.7, 0.9, 0.9, 0.2],
    'castle':     [0.5, 1.0, 0.8, 0.6, 0.7, 0.9, 0.9, 0.2],
    'calle':      [0.4, 0.5, 0.7, 0.5, 0.4, 0.7, 0.5, 0.5],
    'street':     [0.4, 0.5, 0.7, 0.5, 0.4, 0.7, 0.5, 0.5],
    'puente':     [0.3, 0.8, 0.6, 0.6, 0.4, 0.7, 0.6, 0.4],

    # ── ESTILOS Y ESTÉTICA ───────────────────────────────────────────────
    'cyberpunk':  [0.7, 0.8, 0.7, 0.3, 0.8, 0.9, 0.8, 0.2],
    'fantasy':    [0.7, 0.7, 0.6, 0.6, 0.9, 0.8, 0.7, 0.5],
    'realista':   [0.5, 0.7, 0.8, 0.7, 0.3, 0.9, 0.6, 0.5],
    'realistic':  [0.5, 0.7, 0.8, 0.7, 0.3, 0.9, 0.6, 0.5],
    'anime':      [0.8, 0.7, 0.4, 0.7, 0.8, 0.8, 0.5, 0.5],
    'abstracto':  [0.7, 0.4, 0.5, 0.5, 0.7, 0.5, 0.5, 0.5],
    'abstract':   [0.7, 0.4, 0.5, 0.5, 0.7, 0.5, 0.5, 0.5],
    'minimalista':[0.3, 0.6, 0.2, 0.8, 0.4, 0.3, 0.4, 0.5],
    'minimalist': [0.3, 0.6, 0.2, 0.8, 0.4, 0.3, 0.4, 0.5],

    # ── MODIFICADORES DE LUZ ─────────────────────────────────────────────
    'oscuro':     [0.1, 0.5, 0.5, 0.1, 0.6, 0.5, 0.5, 0.4],
    'dark':       [0.1, 0.5, 0.5, 0.1, 0.6, 0.5, 0.5, 0.4],
    'brillante':  [0.9, 0.5, 0.5, 0.9, 0.7, 0.6, 0.5, 0.6],
    'bright':     [0.9, 0.5, 0.5, 0.9, 0.7, 0.6, 0.5, 0.6],
    'neon':       [1.0, 0.6, 0.4, 0.8, 0.8, 0.7, 0.4, 0.3],
    'niebla':     [0.3, 0.2, 0.8, 0.3, 0.5, 0.3, 0.7, 0.5],
    'fog':        [0.3, 0.2, 0.8, 0.3, 0.5, 0.3, 0.7, 0.5],
    'lluvia':     [0.2, 0.3, 0.8, 0.4, 0.5, 0.5, 0.6, 0.4],
    'rain':       [0.2, 0.3, 0.8, 0.4, 0.5, 0.5, 0.6, 0.4],

    # ── PERSONAJES ───────────────────────────────────────────────────────
    'persona':    [0.5, 0.8, 0.5, 0.6, 0.7, 0.9, 0.4, 0.5],
    'person':     [0.5, 0.8, 0.5, 0.6, 0.7, 0.9, 0.4, 0.5],
    'robot':      [0.4, 0.9, 0.8, 0.5, 0.5, 0.9, 0.5, 0.3],
    'dragón':     [0.7, 0.9, 0.7, 0.6, 0.9, 0.9, 0.8, 0.4],
    'dragon':     [0.7, 0.9, 0.7, 0.6, 0.9, 0.9, 0.8, 0.4],

    # ── EMOCIONES Y AMBIENTE ─────────────────────────────────────────────
    'épico':      [0.7, 0.9, 0.7, 0.8, 1.0, 0.9, 0.9, 0.5],
    'epic':       [0.7, 0.9, 0.7, 0.8, 1.0, 0.9, 0.9, 0.5],
    'tranquilo':  [0.4, 0.3, 0.4, 0.6, 0.2, 0.4, 0.5, 0.6],
    'peaceful':   [0.4, 0.3, 0.4, 0.6, 0.2, 0.4, 0.5, 0.6],
    'misterioso': [0.2, 0.5, 0.5, 0.2, 0.8, 0.6, 0.6, 0.4],
    'mysterious': [0.2, 0.5, 0.5, 0.2, 0.8, 0.6, 0.6, 0.4],
    'hermoso':    [0.8, 0.7, 0.6, 0.8, 0.9, 0.8, 0.6, 0.6],
    'beautiful':  [0.8, 0.7, 0.6, 0.8, 0.9, 0.8, 0.6, 0.6],
}

# Colores directos → vector de color dominante (R,G,B normalizado)
COLOR_VOCAB = {
    'rojo':    [1.0, 0.0, 0.0],  'red':    [1.0, 0.0, 0.0],
    'verde':   [0.0, 0.8, 0.0],  'green':  [0.0, 0.8, 0.0],
    'azul':    [0.0, 0.0, 1.0],  'blue':   [0.0, 0.0, 1.0],
    'amarillo':[1.0, 1.0, 0.0],  'yellow': [1.0, 1.0, 0.0],
    'naranja': [1.0, 0.5, 0.0],  'orange': [1.0, 0.5, 0.0],
    'morado':  [0.5, 0.0, 0.8],  'purple': [0.5, 0.0, 0.8],
    'rosa':    [1.0, 0.4, 0.7],  'pink':   [1.0, 0.4, 0.7],
    'blanco':  [1.0, 1.0, 1.0],  'white':  [1.0, 1.0, 1.0],
    'negro':   [0.0, 0.0, 0.0],  'black':  [0.0, 0.0, 0.0],
    'dorado':  [1.0, 0.8, 0.0],  'golden': [1.0, 0.8, 0.0],
    'plateado':[0.7, 0.7, 0.8],  'silver': [0.7, 0.7, 0.8],
    'cyan':    [0.0, 1.0, 1.0],  'celeste':[0.4, 0.8, 1.0],
    'magenta': [1.0, 0.0, 1.0],
}


# ═══════════════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class CicDreamEmbeddings:
    """
    Convierte un prompt de texto en un vector numérico de EMBED_DIM dimensiones.
    El vector captura: semántica, colores, emoción, escala, luz, detalle.
    
    Aprendizaje: los pesos del vocabulario se ajustan con feedback del usuario.
    """

    def __init__(self, weights_path: str = None):
        # Pesos del vocabulario — ajustables con feedback
        self.vocab_weights = {k: np.array(v, dtype=np.float32)
                              for k, v in SEMANTIC_VOCAB.items()}
        self.color_weights  = {k: np.array(v, dtype=np.float32)
                               for k, v in COLOR_VOCAB.items()}

        # Historial de ajustes — para aprendizaje incremental
        self.adjustment_history = []

        # Cargar pesos aprendidos si existen
        self.weights_path = weights_path or '/tmp/cicdream_vocab_weights.json'
        self._load_learned_weights()

    # ── Tokenización ──────────────────────────────────────────────────────

    def tokenize(self, text: str) -> list:
        """Divide el texto en tokens limpios."""
        text = text.lower().strip()
        # Eliminar caracteres especiales, mantener letras, números, espacios
        text = re.sub(r'[^\w\sáéíóúüñ]', ' ', text)
        tokens = [t for t in text.split() if len(t) > 1]
        return tokens

    # ── Embedding principal ───────────────────────────────────────────────

    def encode(self, prompt: str) -> np.ndarray:
        """
        Convierte un prompt en vector de EMBED_DIM dimensiones.
        
        El vector tiene esta estructura:
        [0:8]   → características semánticas (color, forma, textura, luz, emoción, detalle, escala, tiempo)
        [8:11]  → color dominante (R, G, B)
        [11:16] → intensidad de conceptos clave (naturaleza, ciudad, espacio, personaje, abstracto)
        [16:32] → hash distribucional del texto (determinístico pero único por prompt)
        [32:48] → frecuencias de concepto (qué tan presente está cada categoría)
        [48:64] → reservado para ajustes de feedback
        """
        tokens = self.tokenize(prompt)
        vector = np.zeros(EMBED_DIM, dtype=np.float32)

        # ── Zona 1: características semánticas [0:8] ──────────────────
        semantic_sum  = np.zeros(8, dtype=np.float32)
        semantic_count = 0
        for token in tokens:
            if token in self.vocab_weights:
                semantic_sum  += self.vocab_weights[token]
                semantic_count += 1
        if semantic_count > 0:
            vector[0:8] = semantic_sum / semantic_count
        else:
            # Sin coincidencias → usar hash del prompt como base
            vector[0:8] = self._hash_to_features(prompt, 8)

        # ── Zona 2: color dominante [8:11] ────────────────────────────
        color_sum   = np.zeros(3, dtype=np.float32)
        color_count = 0
        for token in tokens:
            if token in self.color_weights:
                color_sum   += self.color_weights[token]
                color_count += 1
        if color_count > 0:
            vector[8:11] = color_sum / color_count
        else:
            vector[8:11] = self._infer_color_from_semantics(vector[0:8])

        # ── Zona 3: intensidad de categorías [11:16] ──────────────────
        categories = {
            'naturaleza': ['árbol','arbol','bosque','montaña','flor','río','mar','nieve','forest','mountain'],
            'ciudad':     ['ciudad','city','edificio','building','calle','street','puente'],
            'espacio':    ['espacio','space','galaxia','galaxy','nebulosa','estrellas','stars','luna'],
            'personaje':  ['persona','person','robot','dragón','dragon'],
            'abstracto':  ['abstracto','abstract','minimalista','minimalist'],
        }
        for idx, (cat, keywords) in enumerate(categories.items()):
            matches = sum(1 for t in tokens if t in keywords)
            vector[11 + idx] = min(1.0, matches / max(len(tokens), 1) * 5)

        # ── Zona 4: hash distribucional [16:32] ───────────────────────
        vector[16:32] = self._hash_to_features(prompt, 16)

        # ── Zona 5: frecuencias de concepto [32:48] ───────────────────
        vector[32:48] = self._concept_frequencies(tokens)

        # ── Zona 6: ajustes de feedback [48:64] ───────────────────────
        vector[48:64] = self._get_feedback_adjustments(prompt)

        # Normalizar todo el vector a [-1, 1]
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    # ── Helpers ───────────────────────────────────────────────────────────

    def _hash_to_features(self, text: str, n: int) -> np.ndarray:
        """Genera n features determinísticas desde el hash del texto."""
        h = hashlib.md5(text.encode()).hexdigest()
        features = np.array([int(h[i*2:(i*2)+2], 16) / 255.0
                              for i in range(min(n, 16))], dtype=np.float32)
        # Si n > 16, usar SHA256 para más bits
        if n > 16:
            h2    = hashlib.sha256(text.encode()).hexdigest()
            extra = np.array([int(h2[i*2:(i*2)+2], 16) / 255.0
                               for i in range(n - 16)], dtype=np.float32)
            features = np.concatenate([features, extra])
        return features[:n]

    def _infer_color_from_semantics(self, semantic_vec: np.ndarray) -> np.ndarray:
        """Infiere color dominante desde las características semánticas."""
        # peso_color (dim 0) alto → colores saturados
        # peso_luz (dim 3) alto  → colores claros
        sat   = semantic_vec[0]  # saturación
        light = semantic_vec[3]  # luminosidad
        # Color base neutro ajustado por saturación y luz
        r = 0.3 + sat * 0.5 + light * 0.2
        g = 0.3 + sat * 0.3 + light * 0.3
        b = 0.3 + sat * 0.2 + light * 0.4
        return np.clip(np.array([r, g, b], dtype=np.float32), 0, 1)

    def _concept_frequencies(self, tokens: list) -> np.ndarray:
        """Calcula frecuencia de cada concepto en el vocabulario."""
        freqs  = np.zeros(16, dtype=np.float32)
        total  = max(len(tokens), 1)
        known  = list(SEMANTIC_VOCAB.keys())[:16]
        for i, concept in enumerate(known):
            freqs[i] = tokens.count(concept) / total
        return freqs

    def _get_feedback_adjustments(self, prompt: str) -> np.ndarray:
        """
        Retorna ajustes aprendidos de feedback previo para prompts similares.
        Zona reservada [48:64] — se rellena con el trainer.
        """
        # Por ahora retorna ceros — el trainer los irá llenando
        return np.zeros(16, dtype=np.float32)

    # ── Similitud entre prompts ───────────────────────────────────────────

    def similarity(self, prompt_a: str, prompt_b: str) -> float:
        """
        Calcula similitud coseno entre dos prompts.
        Retorna valor entre 0 (diferente) y 1 (idéntico).
        """
        va = self.encode(prompt_a)
        vb = self.encode(prompt_b)
        dot     = np.dot(va, vb)
        norm_ab = np.linalg.norm(va) * np.linalg.norm(vb)
        if norm_ab == 0:
            return 0.0
        return float(np.clip(dot / norm_ab, 0.0, 1.0))

    # ── Aprendizaje por feedback ──────────────────────────────────────────

    def adjust_from_feedback(self, prompt: str, rating: float,
                              details: str = '', tags: list = None):
        """
        Ajusta los pesos del vocabulario según el feedback del usuario.
        
        Args:
            prompt:  El prompt que generó la imagen
            rating:  1.0 (malo) a 5.0 (excelente)
            details: Texto adicional del usuario ("más oscuro", "más detalle")
            tags:    Lista de tags seleccionados
        """
        tokens      = self.tokenize(prompt)
        detail_tokens = self.tokenize(details) if details else []
        all_tokens  = tokens + detail_tokens

        # Factor de ajuste: rating 5 → +0.05, rating 1 → -0.05
        adjustment = (rating - 3.0) / 40.0  # rango [-0.05, +0.05]

        adjusted_count = 0
        for token in all_tokens:
            if token in self.vocab_weights:
                # Ajuste suave — no cambia drásticamente un solo feedback
                self.vocab_weights[token] = np.clip(
                    self.vocab_weights[token] + adjustment,
                    0.0, 1.0
                )
                adjusted_count += 1

        # Registrar en historial
        self.adjustment_history.append({
            'prompt':     prompt,
            'rating':     rating,
            'details':    details,
            'adjusted':   adjusted_count,
        })

        # Guardar pesos aprendidos
        self._save_learned_weights()

        logger.info(f"[Embeddings] Feedback ajustó {adjusted_count} pesos "
                    f"(rating={rating:.1f}, factor={adjustment:.4f})")

    # ── Persistencia de pesos ─────────────────────────────────────────────

    def _save_learned_weights(self):
        """Guarda los pesos aprendidos en disco."""
        try:
            data = {k: v.tolist() for k, v in self.vocab_weights.items()}
            with open(self.weights_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"[Embeddings] No se pudieron guardar pesos: {e}")

    def _load_learned_weights(self):
        """Carga pesos aprendidos previamente."""
        try:
            if os.path.exists(self.weights_path):
                with open(self.weights_path, 'r') as f:
                    data = json.load(f)
                for k, v in data.items():
                    if k in self.vocab_weights:
                        self.vocab_weights[k] = np.array(v, dtype=np.float32)
                logger.info(f"[Embeddings] Pesos aprendidos cargados: {len(data)} términos")
        except Exception as e:
            logger.warning(f"[Embeddings] No se pudieron cargar pesos: {e}")

    # ── Info del embedding ────────────────────────────────────────────────

    def describe(self, prompt: str) -> dict:
        """
        Retorna descripción legible del embedding de un prompt.
        Útil para debug y para el panel de desarrollador.
        """
        vector  = self.encode(prompt)
        tokens  = self.tokenize(prompt)
        known   = [t for t in tokens if t in self.vocab_weights]
        colors  = [t for t in tokens if t in self.color_weights]

        return {
            'prompt':          prompt,
            'tokens':          tokens,
            'tokens_conocidos':known,
            'colores_detectados': colors,
            'dim_semantica':   float(np.mean(vector[0:8])),
            'color_dominante': [round(float(x), 3) for x in vector[8:11]],
            'categorias': {
                'naturaleza': float(vector[11]),
                'ciudad':     float(vector[12]),
                'espacio':    float(vector[13]),
                'personaje':  float(vector[14]),
                'abstracto':  float(vector[15]),
            },
            'norma_vector':    float(np.linalg.norm(vector)),
            'embed_dim':       EMBED_DIM,
        }


# ── Instancia global ──────────────────────────────────────────────────────
_embeddings_instance = None

def get_embeddings() -> CicDreamEmbeddings:
    """Retorna instancia singleton de CicDreamEmbeddings."""
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = CicDreamEmbeddings()
    return _embeddings_instance
