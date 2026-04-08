"""
Modelos de Base de Datos para Cic_IA v7.0
Auto-Aprendizaje con Feedback y Evolución
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import json

db = SQLAlchemy()

# ========== MODELOS PRINCIPALES ==========

class Memory(db.Model):
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
    confidence_score = db.Column(db.Float, default=0.5)
    verification_status = db.Column(db.String(20), default='unverified')
    usage_context = db.Column(db.JSON, default=list)

class Conversation(db.Model):
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    has_attachment = db.Column(db.Boolean, default=False)
    attachment_path = db.Column(db.String(500))
    sources_used = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    intent_detected = db.Column(db.String(50))
    confidence = db.Column(db.Float)
    context_snapshot = db.Column(db.JSON)
    
    feedback = db.relationship('FeedbackLog', backref='conversation', lazy=True, uselist=False)

class LearningLog(db.Model):
    __tablename__ = 'learning_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=date.today, unique=True)
    count = db.Column(db.Integer, default=0)
    web_searches = db.Column(db.Integer, default=0)
    auto_learned = db.Column(db.Integer, default=0)
    successful_interactions = db.Column(db.Integer, default=0)
    failed_interactions = db.Column(db.Integer, default=0)
    avg_satisfaction = db.Column(db.Float, default=0.0)

class DeveloperSession(db.Model):
    __tablename__ = 'developer_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True)
    username = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_access = db.Column(db.DateTime, default=datetime.utcnow)

class WebSearchCache(db.Model):
    __tablename__ = 'web_search_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(500), unique=True)
    results = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    usage_count = db.Column(db.Integer, default=0)

class KnowledgeEvolution(db.Model):
    __tablename__ = 'knowledge_evolution'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    topic = db.Column(db.String(200))
    action = db.Column(db.String(50))
    old_content = db.Column(db.Text)
    new_content = db.Column(db.Text)
    source = db.Column(db.String(50))
    triggered_by = db.Column(db.String(50))

class ManualLearningQueue(db.Model):
    __tablename__ = 'manual_learning_queue'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(200))
    source_url = db.Column(db.String(500))
    priority = db.Column(db.Integer, default=1)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)

# ========== NUEVOS MODELOS PARA AUTO-APRENDIZAJE ==========

class FeedbackLog(db.Model):
    __tablename__ = 'feedback_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), unique=True)
    feedback_type = db.Column(db.String(20), nullable=False)
    score = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50))
    reason = db.Column(db.Text)
    user_correction = db.Column(db.Text)
    used_for_training = db.Column(db.Boolean, default=False)
    training_batch_id = db.Column(db.Integer, db.ForeignKey('training_batches.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class CuriosityGap(db.Model):
    __tablename__ = 'curiosity_gaps'
    
    id = db.Column(db.Integer, primary_key=True)
    concept = db.Column(db.String(200), nullable=False, unique=True)
    mention_count = db.Column(db.Integer, default=1)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_mentioned = db.Column(db.DateTime, default=datetime.utcnow)
    context_examples = db.Column(db.JSON, default=list)
    priority = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    learned_memory_id = db.Column(db.Integer, db.ForeignKey('memories.id'))
    
    def calculate_priority(self):
        import math
        days_since_first = (datetime.utcnow() - self.first_seen).days
        recency_boost = 1.0 / (1 + days_since_first)
        self.priority = self.mention_count * recency_boost * 10
        return self.priority

class TrainingBatch(db.Model):
    __tablename__ = 'training_batches'
    
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    samples_used = db.Column(db.Integer)
    accuracy_before = db.Column(db.Float)
    accuracy_after = db.Column(db.Float)
    loss = db.Column(db.Float)
    status = db.Column(db.String(20), default='running')
    feedbacks = db.relationship('FeedbackLog', backref='batch', lazy=True)

class WorkingMemorySnapshot(db.Model):
    __tablename__ = 'working_memory_snapshots'
    
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'))
    turns_json = db.Column(db.JSON)
    current_topic = db.Column(db.String(200))
    topic_shift_detected = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ========== FUNCIÓN DE INICIALIZACIÓN ==========

def init_database(app):
    """Inicializa la base de datos con todas las tablas"""
    with app.app_context():
        db.init_app(app)
        db.create_all()
        print("✅ Base de datos inicializada con modelos de auto-aprendizaje")
