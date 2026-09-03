"""
modules/audio_studio/models.py
================================
Modelo PodcastProject para guardar proyectos de audio.
Se registra automáticamente en la BD al importar.
"""
from datetime import datetime
from cic_ia_mejorado import db


class PodcastProject(db.Model):
    __tablename__ = "podcast_project"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title        = db.Column(db.String(200), nullable=False)
    script       = db.Column(db.Text,   default="")
    engine       = db.Column(db.String(30),  default="gtts")
    format_type  = db.Column(db.String(20),  default="monologue")
    voice_config = db.Column(db.JSON,   default=dict)   # {host, guest, rate, lang}
    music_cat    = db.Column(db.String(30),  default="neutral")
    segments     = db.Column(db.JSON,   default=list)   # [{speaker, text}, ...]
    audio_parts  = db.Column(db.JSON,   default=list)   # [base64, ...] — solo si el usuario quiere guardarlos
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow)
    deleted      = db.Column(db.Boolean,  default=False)

    def to_dict(self, full=False):
        d = {
            "id":          self.id,
            "title":       self.title,
            "engine":      self.engine,
            "format_type": self.format_type,
            "music_cat":   self.music_cat,
            "voice_config": self.voice_config,
            "segments_count": len(self.segments or []),
            "has_audio":   bool(self.audio_parts),
            "created_at":  self.created_at.isoformat(),
            "updated_at":  self.updated_at.isoformat(),
        }
        if full:
            d["script"]      = self.script
            d["segments"]    = self.segments
            d["audio_parts"] = self.audio_parts  # puede ser grande
        return d
