"""
modules/audio_studio/__init__.py
=================================
Audio Studio — TTS, STT y herramientas de podcast para Cic_IA.

Exporta register(app) como punto de contacto con cic_ia_mejorado.py.
"""
from .routes import register

__all__ = ['register']
