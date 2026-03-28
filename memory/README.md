# Memoria del Bebé IA

Base de datos SQLite con los recuerdos del bebé.

## Archivos
- `vector_store.db` - Base de datos principal (Git LFS)

## Estructura
Tabla `memories`:
- content: texto del recuerdo
- embedding: vector de similitud
- context: categoría (conversación, aprendizaje, etc.)
- importance: 0-1, qué tan importante es recordar
- timestamp: cuándo ocurrió
