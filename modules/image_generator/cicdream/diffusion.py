"""
modules/image_generator/cicdream/diffusion.py
==============================================
CicDream v1.0 — Motor de Difusión Matemática

Implementación propia de difusión estocástica desde cero.
Sin modelos preentrenados. Solo NumPy y matemáticas puras.

Basado en:
- DDPM (Denoising Diffusion Probabilistic Models)
- Ecuaciones Diferenciales Estocásticas (SDE)
- Classifier-Free Guidance adaptado a paletas semánticas

Proceso:
  x_T (ruido puro)
     → T pasos de denoising guiado por embedding
     → x_0 (imagen coherente)

Fórmulas implementadas:
  Forward:  q(x_t|x_0) = N(x_t; √ᾱ_t·x_0, (1-ᾱ_t)·I)
  Reverse:  p(x_{t-1}|x_t) = N(x_{t-1}; μ_θ(x_t,t), σ_t²·I)
  Guidance: ε_guided = ε_null + w·(ε_text - ε_null)
"""

import numpy as np
import logging
import math

logger = logging.getLogger('cicdream.diffusion')

# ═══════════════════════════════════════════════════════════════════════════
# HIPERPARÁMETROS DEL PROCESO DE DIFUSIÓN
# Estos valores se ajustan con feedback del trainer
# ═══════════════════════════════════════════════════════════════════════════

class DiffusionConfig:
    """
    Configuración del proceso de difusión.
    Todos los parámetros son ajustables por el trainer con feedback.
    """
    def __init__(self):
        # Pasos de difusión
        # Más pasos = mejor calidad, más lento
        # v1: 20 pasos (rápido), v2: 50, v3: 100
        self.T = 20

        # Schedule de ruido — controla cuánto ruido en cada paso
        # 'linear': uniforme, 'cosine': mejor calidad (DDPM mejorado)
        self.schedule = 'cosine'

        # Rango del schedule lineal
        self.beta_start = 0.0001
        self.beta_end   = 0.02

        # Guidance scale — cuánto influye el texto en la imagen
        # 1.0 = sin guía, 7.5 = balanceado, 15.0 = muy guiado
        self.guidance_scale = 7.5

        # Resolución interna del espacio latente
        # La imagen final se upscale desde esto
        self.latent_size = 64   # 64x64 latente → upscale a resolución final

        # Semilla base (se suma al seed del usuario)
        self.base_seed = 42

        # Fuerza de las frecuencias de detalle
        self.detail_strength = 0.6

        # Temperatura del ruido inicial
        self.noise_temperature = 1.0

    def to_dict(self) -> dict:
        return {
            'T':                  self.T,
            'schedule':           self.schedule,
            'beta_start':         self.beta_start,
            'beta_end':           self.beta_end,
            'guidance_scale':     self.guidance_scale,
            'latent_size':        self.latent_size,
            'detail_strength':    self.detail_strength,
            'noise_temperature':  self.noise_temperature,
        }

    def from_dict(self, d: dict):
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, v)
        return self


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULE DE RUIDO
# Define cuánto ruido agregar/quitar en cada paso t
# ═══════════════════════════════════════════════════════════════════════════

class NoiseSchedule:
    """
    Calcula los coeficientes α, β, σ para cada paso t.
    
    β_t  = cuánto ruido se agrega en el paso t
    α_t  = cuánto de la señal original queda en el paso t  
    ᾱ_t  = producto acumulado de todos los α hasta t
    σ_t  = desviación estándar del ruido en el paso t
    """

    def __init__(self, config: DiffusionConfig):
        self.T      = config.T
        self.betas  = self._compute_betas(config)
        self.alphas = 1.0 - self.betas
        self.alphas_cumprod = np.cumprod(self.alphas)  # ᾱ_t

        # Coeficientes precomputados para eficiencia
        self.sqrt_alphas_cumprod         = np.sqrt(self.alphas_cumprod)
        self.sqrt_one_minus_alphas_cumprod = np.sqrt(1.0 - self.alphas_cumprod)

        # Coeficientes para el paso reverso
        self.alphas_cumprod_prev = np.concatenate([[1.0], self.alphas_cumprod[:-1]])
        self.posterior_variance  = (
            self.betas * (1.0 - self.alphas_cumprod_prev)
            / (1.0 - self.alphas_cumprod)
        )

    def _compute_betas(self, config: DiffusionConfig) -> np.ndarray:
        """Calcula el schedule de ruido."""
        if config.schedule == 'linear':
            return np.linspace(config.beta_start, config.beta_end, config.T)

        elif config.schedule == 'cosine':
            # Schedule coseno — más suave, mejor calidad
            # Fórmula: ᾱ_t = cos²(π/2 · (t/T + s)/(1 + s))
            s = 0.008
            steps = config.T + 1
            x = np.linspace(0, config.T, steps)
            alphas_cumprod = np.cos(
                ((x / config.T) + s) / (1 + s) * math.pi * 0.5
            ) ** 2
            alphas_cumprod = alphas_cumprod / alphas_cumprod[0]
            betas = 1 - (alphas_cumprod[1:] / alphas_cumprod[:-1])
            return np.clip(betas, 0.0001, 0.9999)

        else:
            return np.linspace(config.beta_start, config.beta_end, config.T)

    def q_sample(self, x0: np.ndarray, t: int,
                  noise: np.ndarray = None) -> np.ndarray:
        """
        Proceso FORWARD: agrega ruido gaussiano a x0 en el paso t.
        
        q(x_t | x_0) = √ᾱ_t · x_0 + √(1-ᾱ_t) · ε
        """
        if noise is None:
            noise = np.random.randn(*x0.shape).astype(np.float32)

        sqrt_alpha  = self.sqrt_alphas_cumprod[t]
        sqrt_1m_alpha = self.sqrt_one_minus_alphas_cumprod[t]

        return sqrt_alpha * x0 + sqrt_1m_alpha * noise

    def predict_x0_from_noise(self, xt: np.ndarray,
                               t: int, noise_pred: np.ndarray) -> np.ndarray:
        """
        Predice x_0 desde x_t y la predicción de ruido.
        
        x̂_0 = (x_t - √(1-ᾱ_t) · ε_θ) / √ᾱ_t
        """
        sqrt_alpha    = self.sqrt_alphas_cumprod[t]
        sqrt_1m_alpha = self.sqrt_one_minus_alphas_cumprod[t]
        return (xt - sqrt_1m_alpha * noise_pred) / (sqrt_alpha + 1e-8)

    def p_sample(self, xt: np.ndarray, t: int,
                  noise_pred: np.ndarray) -> np.ndarray:
        """
        Proceso REVERSE: un paso de denoising.
        
        p(x_{t-1} | x_t) = N(x_{t-1}; μ_θ(x_t, t), σ_t² · I)
        
        μ_θ = (1/√α_t) · (x_t - β_t/√(1-ᾱ_t) · ε_θ)
        """
        alpha_t       = self.alphas[t]
        alpha_bar_t   = self.alphas_cumprod[t]
        beta_t        = self.betas[t]
        sqrt_1m_alpha = self.sqrt_one_minus_alphas_cumprod[t]

        # Media del paso reverso
        mu = (1.0 / math.sqrt(alpha_t + 1e-8)) * (
            xt - (beta_t / (sqrt_1m_alpha + 1e-8)) * noise_pred
        )

        # Varianza del paso reverso
        if t > 0:
            variance = self.posterior_variance[t]
            sigma    = math.sqrt(variance + 1e-8)
            noise    = np.random.randn(*xt.shape).astype(np.float32)
            return mu + sigma * noise
        else:
            # Último paso: sin ruido
            return mu


# ═══════════════════════════════════════════════════════════════════════════
# RED DE DENOISING (U-Net simplificada)
# Predice el ruido ε_θ(x_t, t, embedding)
# Sin redes neuronales reales — aproximación matemática propia
# ═══════════════════════════════════════════════════════════════════════════

class CicDenoisingNet:
    """
    Red de denoising simplificada.
    
    En lugar de una U-Net real (que requiere GPU y modelos entrenados),
    implementamos una aproximación matemática que:
    1. Usa el embedding para guiar la dirección del denoising
    2. Aplica filtros de frecuencia para estructurar la imagen
    3. Usa la paleta de colores para colorear semánticamente
    
    Esta es la v1 — irá mejorando con feedback y con el trainer.
    """

    def __init__(self, config: DiffusionConfig):
        self.config = config

        # Pesos de atención por dimensión del embedding
        # Ajustables con feedback
        self.attention_weights = np.ones(8, dtype=np.float32) / 8.0

        # Kernels de frecuencia para estructurar la imagen
        self.freq_kernels = self._init_freq_kernels()

    def _init_freq_kernels(self) -> list:
        """
        Inicializa kernels para detectar/generar frecuencias.
        Bajas frecuencias = estructura global (cielo, tierra)
        Altas frecuencias = detalles (texturas, bordes)
        """
        kernels = []

        # Kernel Gaussiano (frecuencias bajas — estructura)
        k = np.array([
            [1, 2, 1],
            [2, 4, 2],
            [1, 2, 1],
        ], dtype=np.float32) / 16.0
        kernels.append(('gaussian', k))

        # Kernel Laplaciano (frecuencias altas — bordes/detalles)
        k = np.array([
            [-1, -1, -1],
            [-1,  8, -1],
            [-1, -1, -1],
        ], dtype=np.float32)
        kernels.append(('laplacian', k))

        # Kernel Horizontal (estructura horizontal — horizonte, suelo)
        k = np.array([
            [-1, -1, -1],
            [ 2,  2,  2],
            [-1, -1, -1],
        ], dtype=np.float32) / 2.0
        kernels.append(('horizontal', k))

        # Kernel Vertical (estructura vertical — árboles, edificios)
        k = np.array([
            [-1,  2, -1],
            [-1,  2, -1],
            [-1,  2, -1],
        ], dtype=np.float32) / 2.0
        kernels.append(('vertical', k))

        return kernels

    def _convolve2d(self, image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
        """Convolución 2D manual sin scipy."""
        H, W    = image.shape
        kH, kW  = kernel.shape
        pH, pW  = kH // 2, kW // 2
        result  = np.zeros_like(image)

        # Padding
        padded = np.pad(image, ((pH, pH), (pW, pW)), mode='edge')

        for i in range(H):
            for j in range(W):
                region = padded[i:i+kH, j:j+kW]
                result[i, j] = np.sum(region * kernel)

        return result

    def _convolve2d_fast(self, image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
        """Convolución 2D vectorizada con stride tricks."""
        H, W   = image.shape
        kH, kW = kernel.shape
        pH, pW = kH // 2, kW // 2

        padded = np.pad(image, ((pH, pH), (pW, pW)), mode='edge')
        result = np.zeros((H, W), dtype=np.float32)

        for ki in range(kH):
            for kj in range(kW):
                result += kernel[ki, kj] * padded[ki:ki+H, kj:kj+W]

        return result

    def predict_noise(self, xt: np.ndarray, t: int,
                       embedding: np.ndarray,
                       palette_arr: np.ndarray) -> np.ndarray:
        """
        Predice el ruido ε_θ(x_t, t, c) donde c es el embedding.
        
        Estrategia:
        1. Extraer estructura de x_t con filtros de frecuencia
        2. Guiar con el embedding (semántica + paleta)
        3. Modular por el paso t (más detalle en pasos finales)
        
        Args:
            xt:          Estado actual (H, W, 3) float32
            t:           Paso actual (0 = imagen, T = ruido puro)
            embedding:   Vector de embedding (64,)
            palette_arr: Array de paleta (H, W, 3) float32
        
        Returns:
            noise_pred: Ruido predicho (H, W, 3) float32
        """
        H, W, C = xt.shape
        noise_pred = np.zeros_like(xt)

        # Progreso del proceso (1.0 = inicio, 0.0 = final)
        progress = t / max(self.config.T - 1, 1)

        # ── 1. Guía de paleta (estructura de color) ────────────────────
        # En pasos tempranos: guiar fuerte hacia paleta
        # En pasos tardíos: refinar detalles
        palette_guidance = (palette_arr - xt) * (0.3 + progress * 0.4)

        # ── 2. Guía de embedding (dirección semántica) ────────────────
        # Usar dimensiones del embedding para modular el denoising
        # dim [0:8] = características semánticas
        sem_features = embedding[0:8] if len(embedding) >= 8 else np.ones(8) * 0.5

        # Crear mapa de atención desde embedding
        # (qué partes de la imagen deben ser más intensas)
        attention_map = self._build_attention_map(sem_features, H, W)

        # ── 3. Análisis de frecuencias de x_t ─────────────────────────
        freq_guidance = np.zeros_like(xt)
        for c_idx in range(C):
            channel = xt[:, :, c_idx]

            # Estructura global (baja freq)
            low_freq = self._convolve2d_fast(
                channel, self.freq_kernels[0][1]  # gaussiano
            )
            # Detalles (alta freq) — solo en pasos finales
            if progress < 0.3:  # últimos 30% de pasos
                high_freq = self._convolve2d_fast(
                    channel, self.freq_kernels[1][1]  # laplaciano
                ) * self.config.detail_strength

                # Estructura vertical/horizontal según semantica
                if sem_features[1] > 0.6:  # forma vertical (árboles, edificios)
                    vert = self._convolve2d_fast(
                        channel, self.freq_kernels[3][1]
                    ) * 0.3
                    freq_guidance[:, :, c_idx] = (
                        low_freq * 0.5 + high_freq * 0.3 + vert * 0.2
                    )
                else:
                    freq_guidance[:, :, c_idx] = (
                        low_freq * 0.6 + high_freq * 0.4
                    )
            else:
                # Pasos iniciales: solo estructura global
                horiz = self._convolve2d_fast(
                    channel, self.freq_kernels[2][1]  # horizontal
                ) * 0.3
                freq_guidance[:, :, c_idx] = low_freq * 0.7 + horiz * 0.3

        # ── 4. Combinar todas las guías ────────────────────────────────
        # Pesos que cambian según el paso:
        # Inicio (t alto): más ruido gaussiano, menos estructura
        # Final (t bajo):  menos ruido, más detalle y color

        w_palette = 0.4 + (1.0 - progress) * 0.3   # 0.4 → 0.7
        w_freq    = 0.3 + (1.0 - progress) * 0.2   # 0.3 → 0.5
        w_attn    = 0.1 + (1.0 - progress) * 0.2   # 0.1 → 0.3
        w_random  = progress * 0.3                  # 0.3 → 0.0

        # Ruido base (se reduce con el progreso)
        base_noise = np.random.randn(H, W, C).astype(np.float32) * w_random

        noise_pred = (
            palette_guidance  * w_palette +
            freq_guidance     * w_freq    +
            attention_map[:, :, np.newaxis] * xt * w_attn +
            base_noise
        )

        return noise_pred.astype(np.float32)

    def _build_attention_map(self, sem_features: np.ndarray,
                              H: int, W: int) -> np.ndarray:
        """
        Construye un mapa de atención espacial desde el embedding.
        
        sem_features:
          [0] color,  [1] forma,  [2] textura, [3] luz
          [4] emoción,[5] detalle,[6] escala,  [7] tiempo
        
        El mapa guía qué zonas de la imagen deben ser más prominentes.
        """
        attn = np.ones((H, W), dtype=np.float32) * 0.5

        # Luz alta → zona superior más brillante (cielo)
        if sem_features[3] > 0.6:
            y_gradient = np.linspace(sem_features[3], 0.3, H)
            attn *= y_gradient[:, np.newaxis]

        # Escala alta → objetos grandes (llenar el frame)
        if sem_features[6] > 0.7:
            cy, cx = H / 2, W / 2
            Y, X   = np.mgrid[0:H, 0:W]
            dist   = 1.0 - np.sqrt(
                ((X - cx) / (W / 2))**2 + ((Y - cy) / (H / 2))**2
            ) * 0.4
            attn *= np.clip(dist, 0.3, 1.0)

        # Forma alta → bordes definidos
        if sem_features[1] > 0.7:
            # Aumentar atención en zonas con contraste
            attn = np.clip(attn * 1.2, 0.0, 1.0)

        return attn

    def adjust_attention(self, feedback_vector: np.ndarray):
        """
        Ajusta los pesos de atención con feedback.
        feedback_vector: vector 8D con dirección del ajuste
        """
        self.attention_weights = np.clip(
            self.attention_weights + feedback_vector * 0.05,
            0.01, 1.0
        )
        # Renormalizar
        total = self.attention_weights.sum()
        if total > 0:
            self.attention_weights /= total


# ═══════════════════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL DE DIFUSIÓN
# ═══════════════════════════════════════════════════════════════════════════

class CicDiffusion:
    """
    Motor de difusión completo de CicDream.
    
    Orquesta el proceso completo:
    1. Inicializar con ruido (x_T)
    2. T pasos de denoising guiado
    3. Aplicar guidance con el embedding
    4. Retornar imagen final x_0
    """

    def __init__(self, config: DiffusionConfig = None):
        self.config   = config or DiffusionConfig()
        self.schedule = NoiseSchedule(self.config)
        self.net      = CicDenoisingNet(self.config)

    def generate(self, embedding: np.ndarray,
                  palette_arr: np.ndarray,
                  width: int = 512, height: int = 512,
                  seed: int = 42) -> np.ndarray:
        """
        Genera una imagen desde un embedding y paleta.
        
        Args:
            embedding:   Vector de embedding (64,) del prompt
            palette_arr: Array de paleta (H, W, 3) guía de color
            width:       Ancho de la imagen final
            height:      Alto de la imagen final
            seed:        Semilla para reproducibilidad
        
        Returns:
            imagen: Array (H, W, 3) uint8 con la imagen generada
        """
        np.random.seed(seed % (2**31))

        L = self.config.latent_size  # tamaño del espacio latente

        # ── Paso 1: Escalar paleta al tamaño latente ───────────────────
        if palette_arr.shape[:2] != (L, L):
            palette_latent = self._resize_array(palette_arr, L, L)
        else:
            palette_latent = palette_arr.copy()

        # ── Paso 2: x_T — lienzo de ruido puro ────────────────────────
        # Este es el punto de partida: ruido gaussiano puro
        x_t = np.random.randn(L, L, 3).astype(np.float32)
        x_t *= self.config.noise_temperature

        logger.info(f"[Diffusion] Iniciando: {self.config.T} pasos, "
                    f"latente={L}x{L}, guidance={self.config.guidance_scale}")

        # ── Paso 3: Proceso reverso — T pasos de denoising ────────────
        for t in reversed(range(self.config.T)):

            # Predicción de ruido sin guía (null conditioning)
            null_embedding = np.zeros_like(embedding)
            noise_null     = self.net.predict_noise(
                x_t, t, null_embedding, palette_latent
            )

            # Predicción de ruido con guía (text conditioning)
            noise_text     = self.net.predict_noise(
                x_t, t, embedding, palette_latent
            )

            # Classifier-Free Guidance:
            # ε_guided = ε_null + w · (ε_text - ε_null)
            w = self.config.guidance_scale
            noise_guided = noise_null + w * (noise_text - noise_null)

            # Paso reverso: x_{t-1} desde x_t
            x_t = self.schedule.p_sample(x_t, t, noise_guided)

            # Log cada 5 pasos
            if t % 5 == 0:
                logger.debug(f"[Diffusion] t={t:3d} "
                             f"mean={x_t.mean():.3f} std={x_t.std():.3f}")

        # ── Paso 4: Post-proceso ────────────────────────────────────────
        x_0 = self._postprocess(x_t, palette_latent, embedding)

        # ── Paso 5: Upscale al tamaño final ────────────────────────────
        if (L, L) != (height, width):
            x_0 = self._resize_array(x_0, height, width)

        # ── Paso 6: Convertir a uint8 ─────────────────────────────────
        image = np.clip(x_0 * 255, 0, 255).astype(np.uint8)

        logger.info(f"[Diffusion] Imagen generada: {image.shape}")
        return image

    def _postprocess(self, x: np.ndarray,
                      palette: np.ndarray,
                      embedding: np.ndarray) -> np.ndarray:
        """
        Post-proceso final de la imagen latente.
        
        1. Normalizar al rango [0, 1]
        2. Mezclar suavemente con paleta (coherencia de color)
        3. Ajustar contraste y saturación
        4. Aplicar nitidez según detalle del embedding
        """
        # ── Normalización ─────────────────────────────────────────────
        x_min, x_max = x.min(), x.max()
        if x_max > x_min:
            x = (x - x_min) / (x_max - x_min)
        else:
            x = np.clip(x, 0, 1)

        # ── Mezcla final con paleta ────────────────────────────────────
        # Suave — preserva la variación del proceso difusivo
        blend_factor = 0.35
        x = x * (1 - blend_factor) + palette * blend_factor

        # ── Ajuste de contraste ────────────────────────────────────────
        # Usar dim de emoción del embedding para contraste
        emocion = float(embedding[4]) if len(embedding) > 4 else 0.5
        contrast = 0.8 + emocion * 0.4  # 0.8 a 1.2
        x = np.clip((x - 0.5) * contrast + 0.5, 0, 1)

        # ── Ajuste de saturación ───────────────────────────────────────
        # Saturar colores basado en dim de color del embedding
        color_intensity = float(embedding[0]) if len(embedding) > 0 else 0.5
        gray = x.mean(axis=2, keepdims=True)
        sat_factor = 0.5 + color_intensity * 1.0  # 0.5 a 1.5
        x = np.clip(gray + (x - gray) * sat_factor, 0, 1)

        # ── Nitidez ────────────────────────────────────────────────────
        # Detalle alto en embedding → más nitidez
        detail = float(embedding[5]) if len(embedding) > 5 else 0.5
        if detail > 0.6:
            # Unsharp mask simple
            kernel_blur = np.array([[1,2,1],[2,4,2],[1,2,1]],
                                    dtype=np.float32) / 16.0
            for c in range(3):
                blurred  = self._convolve_fast(x[:, :, c], kernel_blur)
                x[:, :, c] = np.clip(
                    x[:, :, c] + (x[:, :, c] - blurred) * detail * 0.5,
                    0, 1
                )

        return x.astype(np.float32)

    def _convolve_fast(self, img: np.ndarray,
                        kernel: np.ndarray) -> np.ndarray:
        """Convolución 2D rápida vectorizada."""
        H, W   = img.shape
        kH, kW = kernel.shape
        pH, pW = kH // 2, kW // 2
        padded = np.pad(img, ((pH, pH), (pW, pW)), mode='edge')
        result = np.zeros((H, W), dtype=np.float32)
        for ki in range(kH):
            for kj in range(kW):
                result += kernel[ki, kj] * padded[ki:ki+H, kj:kj+W]
        return result

    def _resize_array(self, arr: np.ndarray,
                       new_H: int, new_W: int) -> np.ndarray:
        """
        Redimensiona un array (H, W, C) al nuevo tamaño.
        Interpolación bilineal manual sin PIL/cv2.
        """
        H, W, C   = arr.shape
        y_indices = np.linspace(0, H - 1, new_H)
        x_indices = np.linspace(0, W - 1, new_W)

        result = np.zeros((new_H, new_W, C), dtype=np.float32)

        for c in range(C):
            for yi, y in enumerate(y_indices):
                y0, y1 = int(y), min(int(y) + 1, H - 1)
                fy     = y - y0
                for xi, x in enumerate(x_indices):
                    x0, x1 = int(x), min(int(x) + 1, W - 1)
                    fx     = x - x0
                    # Interpolación bilineal
                    val = (
                        arr[y0, x0, c] * (1 - fy) * (1 - fx) +
                        arr[y0, x1, c] * (1 - fy) * fx +
                        arr[y1, x0, c] * fy       * (1 - fx) +
                        arr[y1, x1, c] * fy       * fx
                    )
                    result[yi, xi, c] = val

        return result

    def _resize_fast(self, arr: np.ndarray,
                      new_H: int, new_W: int) -> np.ndarray:
        """Versión rápida del resize usando numpy repeat."""
        H, W, C = arr.shape
        # Resize con numpy (sin interpolación, pero rápido)
        y_idx = (np.linspace(0, H - 1, new_H)).astype(int)
        x_idx = (np.linspace(0, W - 1, new_W)).astype(int)
        return arr[y_idx][:, x_idx]

    # ── Ajuste por feedback ───────────────────────────────────────────────

    def adjust_from_feedback(self, rating: float,
                               details: str = '',
                               embedding: np.ndarray = None):
        """
        Ajusta los hiperparámetros del proceso de difusión con feedback.
        
        Rating 5 → reforzar configuración actual
        Rating 1 → explorar más (aumentar temperatura)
        Detalles → ajustar parámetros específicos
        """
        factor = (rating - 3.0) / 10.0  # [-0.2, +0.2]

        details_lower = (details or '').lower()

        # Más detalle pedido → aumentar pasos y detail_strength
        if any(w in details_lower for w in ['más detalle', 'más nítido', 'more detail', 'sharp']):
            self.config.detail_strength = min(1.0, self.config.detail_strength + 0.1)
            self.config.T = min(50, self.config.T + 5)

        # Más color / saturación
        if any(w in details_lower for w in ['más colorido', 'vibrante', 'saturado']):
            self.config.guidance_scale = min(15.0, self.config.guidance_scale + 0.5)

        # Más oscuro
        if any(w in details_lower for w in ['más oscuro', 'dark', 'oscuro']):
            self.config.noise_temperature = min(1.5, self.config.noise_temperature + 0.1)

        # Rating alto → reforzar guidance
        if rating >= 4.0:
            self.config.guidance_scale = min(12.0,
                self.config.guidance_scale + abs(factor))
        elif rating <= 2.0:
            # Rating bajo → explorar más
            self.config.noise_temperature = min(1.8,
                self.config.noise_temperature + 0.05)

        # Ajustar red de denoising
        if embedding is not None:
            feedback_vec = embedding[0:8] * factor
            self.net.adjust_attention(feedback_vec)

        logger.info(f"[Diffusion] Ajuste feedback: rating={rating:.1f} "
                    f"guidance={self.config.guidance_scale:.2f} "
                    f"T={self.config.T} "
                    f"detail={self.config.detail_strength:.2f}")


# ── Instancia global ──────────────────────────────────────────────────────
_diffusion_instance = None

def get_diffusion(config: DiffusionConfig = None) -> CicDiffusion:
    """Retorna instancia singleton de CicDiffusion."""
    global _diffusion_instance
    if _diffusion_instance is None:
        _diffusion_instance = CicDiffusion(config)
    return _diffusion_instance
