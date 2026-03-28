"""
🍼 Bebé IA - Un asistente que crece desde cero
"""
__version__ = "0.1.0"
__author__ = "Tu Nombre"

from .core.config import Config
from .core.tokenizer import SimpleTokenizer
from .core.model import BebeTransformer
from .core.memory import MemorySystem
from .core.learner import ContinualLearner
from .core.personality import BebePersonality

__all__ = [
    'Config',
    'SimpleTokenizer', 
    'BebeTransformer',
    'MemorySystem',
    'ContinualLearner',
    'BebePersonality'
]
