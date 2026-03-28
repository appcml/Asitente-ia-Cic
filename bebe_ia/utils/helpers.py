"""
Funciones auxiliares
"""
import torch
import random
import numpy as np

def set_seed(seed=42):
    """Fijar semillas para reproducibilidad"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def count_parameters(model):
    """Contar parámetros entrenables"""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

def format_time(seconds):
    """Formatear segundos a legible"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"
