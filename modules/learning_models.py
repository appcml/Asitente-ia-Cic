"""
Tablas del colegio interno de CicBrain.
Copiar este archivo a modules/learning_models.py

No reemplaza los modelos de cic_ia_mejorado.py.
Se registran sobre el mismo `db`.
"""

from datetime import datetime


def register_learning_models(db):
    """Devuelve las clases ligadas a la instancia SQLAlchemy existente."""

    class ExamQuestion(db.Model):
        __tablename__ = 'exam_question'
        id = db.Column(db.Integer, primary_key=True)
        question = db.Column(db.Text, nullable=False)
        expected = db.Column(db.Text)                 # respuesta de referencia, si existe
        source_url = db.Column(db.String(500))
        source_title = db.Column(db.String(300))
        kind = db.Column(db.String(30), default='generated')  # fixed | generated
        active = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class ExamRun(db.Model):
        __tablename__ = 'exam_run'
        id = db.Column(db.Integer, primary_key=True)
        cycle_id = db.Column(db.String(40), index=True)
        question_id = db.Column(db.Integer, db.ForeignKey('exam_question.id'))
        question = db.Column(db.Text, nullable=False)
        student_answer = db.Column(db.Text)
        student_confidence = db.Column(db.Float, default=0.0)
        student_answered = db.Column(db.Boolean, default=False)
        teacher_answer = db.Column(db.Text)
        teacher_provider = db.Column(db.String(40))
        grade = db.Column(db.Integer)                 # 0, 1, 2
        grade_reason = db.Column(db.Text)
        status = db.Column(db.String(20), default='cuarentena', index=True)
        # cuarentena | promovido | rechazado
        source_url = db.Column(db.String(500))
        created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    class LearningCycle(db.Model):
        __tablename__ = 'learning_cycle'
        id = db.Column(db.Integer, primary_key=True)
        cycle_id = db.Column(db.String(40), unique=True, index=True)
        started_at = db.Column(db.DateTime, default=datetime.utcnow)
        finished_at = db.Column(db.DateTime)
        asked = db.Column(db.Integer, default=0)
        student_only = db.Column(db.Integer, default=0)
        promoted = db.Column(db.Integer, default=0)
        rejected = db.Column(db.Integer, default=0)
        fixed_score = db.Column(db.Float)             # 0-1 sobre el examen fijo
        frozen = db.Column(db.Boolean, default=False) # True si el examen fijo bajó
        note = db.Column(db.Text)

    return ExamQuestion, ExamRun, LearningCycle
