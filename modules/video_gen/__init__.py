# modules/video_gen/__init__.py
from modules.video_gen.main import VideoGeneratorModule
from modules.video_gen.routes import register_video_routes

__all__ = ["VideoGeneratorModule", "register_video_routes"]
