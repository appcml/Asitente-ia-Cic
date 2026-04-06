"""
Servicio de autenticación para modo desarrollador
Totalmente independiente y reutilizable
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app


class DevAuthService:
    """
    Servicio de autenticación para desarrolladores
    Gestiona login, tokens y sesiones
    """
    
    def __init__(self):
        self.active_sessions = {}  # En producción: usar Redis o base de datos
    
    def init_app(self, app):
        """Inicializar con la aplicación Flask"""
        self.app = app
    
    def verify_credentials(self, username, password):
        """
        Verificar credenciales contra configuración
        Returns: bool
        """
        config = current_app.config
        
        expected_user = config.get('DEV_USERNAME')
        expected_pass = config.get('DEV_PASSWORD')
        
        return username == expected_user and password == expected_pass
    
    def generate_token(self, username):
        """
        Generar token seguro de sesión
        Returns: str (token)
        """
        token = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + current_app.config.get(
            'TOKEN_EXPIRY', 
            timedelta(hours=24)
        )
        
        self.active_sessions[token] = {
            'username': username,
            'created_at': datetime.utcnow(),
            'expires_at': expiry,
            'last_used': datetime.utcnow()
        }
        
        return token
    
    def verify_token(self, token):
        """
        Verificar si token es válido y no expiró
        Returns: bool
        """
        if not token or token not in self.active_sessions:
            return False
        
        session = self.active_sessions[token]
        
        # Verificar expiración
        if datetime.utcnow() > session['expires_at']:
            del self.active_sessions[token]
            return False
        
        # Actualizar último uso
        session['last_used'] = datetime.utcnow()
        return True
    
    def revoke_token(self, token):
        """
        Revocar token (logout)
        Returns: bool
        """
        if token in self.active_sessions:
            del self.active_sessions[token]
            return True
        return False
    
    def get_session_info(self, token):
        """
        Obtener info de sesión si es válida
        Returns: dict o None
        """
        if self.verify_token(token):
            return self.active_sessions.get(token)
        return None
    
    def cleanup_expired(self):
        """
        Limpiar sesiones expiradas
        Returns: int (cantidad eliminada)
        """
        now = datetime.utcnow()
        expired = [
            token for token, session in self.active_sessions.items()
            if now > session['expires_at']
        ]
        for token in expired:
            del self.active_sessions[token]
        return len(expired)


# Instancia global del servicio
dev_auth = DevAuthService()


# ========== DECORADORES ==========

def dev_required(f):
    """
    Decorador para proteger rutas de desarrollador
    Uso: @dev_required antes de la función de la ruta
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Dev-Token')
        
        if not token:
            return jsonify({
                'error': 'Token requerido',
                'code': 'NO_TOKEN'
            }), 401
        
        if not dev_auth.verify_token(token):
            return jsonify({
                'error': 'Token inválido o expirado',
                'code': 'INVALID_TOKEN'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


# ========== RUTAS AUXILIARES (opcional, para importar) ==========

def dev_login_route():
    """Endpoint de login para desarrollador - puede importarse en routes"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({
            'success': False,
            'error': 'Usuario y contraseña requeridos'
        }), 400
    
    if dev_auth.verify_credentials(username, password):
        token = dev_auth.generate_token(username)
        return jsonify({
            'success': True,
            'token': token,
            'username': username,
            'expires_in': '24h'
        })
    else:
        # Respuesta genérica para no revelar qué falló
        return jsonify({
            'success': False,
            'error': 'Credenciales inválidas'
        }), 401


def dev_logout_route():
    """
