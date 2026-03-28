# Datos Personales

**⚠️ ESTA CARPETA ESTÁ EN .gitignore Y NO SE SUBE A GITHUB**

Aquí guarda:
- Tus conversaciones privadas con el bebé
- Datos sensibles de entrenamiento
- Checkpoints personales

## Ejemplo de uso
```python
# Cargar tus datos privados
from bebe_ia.data.dataset import load_conversations_from_json

mis_datos = load_conversations_from_json("data_personal/mis_conversaciones.json")
bebe.learner.conversations.extend(mis_datos)
