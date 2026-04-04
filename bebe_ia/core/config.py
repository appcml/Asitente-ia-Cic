"""
Configuración central del sistema
"""
import torch
import os

class Config:
    # Modelo
    VOCAB_SIZE = 5000
    EMBED_DIM = 256
    NUM_HEADS = 8
    NUM_LAYERS = 6
    HIDDEN_DIM = 512
    MAX_SEQ_LEN = 512
    DROPOUT = 0.1
    
    # Entrenamiento
    LEARNING_RATE = 1e-4
    BATCH_SIZE = 4
    GRADIENT_ACCUMULATION_STEPS = 4
    
    # Memoria
    MEMORY_CAPACITY = 10000
    SIMILARITY_THRESHOLD = 0.85
    
    # Rutas (relativas al proyecto)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")
    MEMORY_DIR = os.path.join(BASE_DIR, "memory")
    LOGS_DIR = os.path.join(BASE_DIR, "training_logs")
    
    MODEL_PATH = os.path.join(CHECKPOINT_DIR, "model.pt")
    MEMORY_PATH = os.path.join(MEMORY_DIR, "vector_store.db")
    TOKENIZER_PATH = os.path.join(CHECKPOINT_DIR, "tokenizer.json")
    
    # Crear directorios si no existen
    @classmethod
    def ensure_dirs(cls):
        for d in [cls.CHECKPOINT_DIR, cls.MEMORY_DIR, cls.LOGS_DIR]:
            os.makedirs(d, exist_ok=True)
    
    # Dispositivo
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
