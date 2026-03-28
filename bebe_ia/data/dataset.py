"""
Utilidades para cargar y procesar datos de entrenamiento
"""
import json
import os

def load_conversations_from_json(path):
    """Cargar conversaciones desde archivo JSON"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_conversations(conversations, path):
    """Guardar conversaciones a JSON"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(conversations, f, ensure_ascii=False, indent=2)

def load_text_file(path):
    """Cargar texto plano"""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()
