"""
Modelos de base de datos - Centralizado
Todos los modelos SQLAlchemy en un solo archivo
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class Memory(db.Model):
    """Memorias de la IA"""
    __tablename__ = 'memories'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(50), default='local')
    topic = db.Column(db.String(200))
    file_path = db.Column(db.String(500))
    file_type = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    access_count = db.Column(db.Integer, default=0)
    relevance_score = db.Column(db.Float, default=0.5)

    def __repr__(self):
        return f'<Memory {self.id}: {self.topic}>'


class Conversation(db.Model):
    """Historial de conversaciones"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    has_attachment = db.Column(db.Boolean, default=False)
    attachment_path = db.Column(db.String(500))
    sources_used = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Conversation {self.id}>'


class LearningLog(db.Model):
    """Registro diario de aprendizaje"""
    __tablename__ = 'learning_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=date.today, unique=True)
    count = db.Column(db.Integer, default=0)
    web_searches = db.Column(db.Integer, default=0)
    auto_learned = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<LearningLog {self.date}: {self.count}>'


class DeveloperSession(db.Model):
    """Sesiones de desarrollador activas"""
    __tablename__ = 'developer_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True)
    username = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_access = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DevSession {self.username}>'


class WebSearchCache(db.Model):
    """Caché de búsquedas web"""
    __tablename__ = 'web_search_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(500), unique=True)
    results = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<WebCache {self.query[:30]}...>'


class KnowledgeEvolution(db.Model):
    """Evolución del conocimiento (auditoría)"""
    __tablename__ = 'knowledge_evolution'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    topic = db.Column(db.String(200))
    action = db.Column(db.String(50))  # learned, updated, deleted
    old_content = db.Column(db.Text)
    new_content = db.Column(db.Text)
    source = db.Column(db.String(50))

    def __repr__(self):
        return f'<Evolution {self.action}: {self.topic}>'
