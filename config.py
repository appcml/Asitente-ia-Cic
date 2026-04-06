"""
Configuración centralizada de Cic_IA
Todas las variables sensibles deben ir en variables de entorno
"""

import os
from datetime import timedelta


class Config:
    """Configuración base"""
    
    # Seguridad
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cic-ia-secret-2024')
    
    # Base de datos
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///cic_ia.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Archivos
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Auto-aprendizaje
    LEARNING_INTERVAL = 10800  # 3 horas
    FIRST_LEARNING_DELAY = 180  # 3 minutos
    
    # Credenciales DESARROLLADOR - SOLO PARA TI
    # En producción, configurar en variables de entorno de Render:
    # DEV_USERNAME = tu_usuario_secreto
    # DEV_PASSWORD = tu_clave_super_segura
    
    DEV_USERNAME = os.environ.get('DEV_USERNAME', 'admin')
    DEV_PASSWORD = os.environ.get('DEV_PASSWORD', 'CicDev2024!')
    
    # Tokens expiran en 24 horas
    TOKEN_EXPIRY = timedelta(hours=24)


class DevelopmentConfig(Config):
    """Configuración desarrollo local"""
    DEBUG = True


class ProductionConfig(Config):
    """Configuración producción (Render)"""
    DEBUG = False


# Diccionario de configuraciones
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': ProductionConfig
}
