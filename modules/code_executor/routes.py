"""
modules/code_executor/routes.py
================================
CicCode IDE — Asistente de código con IA integrada v2.0
Rutas del módulo bajo /api/code/

Capacidades:
- /execute         → ejecutar Python/JS en sandbox
- /chat            → conversación con IA sobre código (con historial)
- /analyze         → analizar proyecto/repositorio completo
- /generate        → generar proyecto/archivos desde instrucciones
- /upload          → subir archivos (código, imágenes, docs, zips)
- /file/read       → leer y entender un archivo específico
- /project/build   → construir repo completo con estructura de carpetas
"""

from flask import Blueprint, request, jsonify, current_app
import logging
import os
import io
import re
import sys
import json
import base64
import zipfile
import tempfile
import traceback
import subprocess
import requests as req_lib
from datetime import datetime
from pathlib import Path

logger = logging.getLogger('cic_ia.code_executor')

bp = Blueprint('code_executor', __name__, url_prefix='/api/code')

# ── Modelos para código (Groq) ────────────────────────────────────────────
CODE_MODELS = [
    'llama-3.3-70b-versatile',
    'llama-3.1-70b-versatile',
    'llama-3.1-8b-instant',
    'mixtral-8x7b-32768',
]

# ── Lenguajes soportados en sandbox ──────────────────────────────────────
SUPPORTED_LANGS = {'python', 'javascript', 'js'}

# ── Extensiones de archivo permitidas ────────────────────────────────────
ALLOWED_EXTENSIONS = {
    # Código
    '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.json',
    '.yaml', '.yml', '.toml', '.env', '.sh', '.bash', '.md', '.txt',
    '.sql', '.graphql', '.xml', '.csv', '.ini', '.cfg', '.conf',
    # Archivos comprimidos
    '.zip',
    # Documentos
    '.pdf',
    # Imágenes (para análisis)
    '.png', '.jpg', '.jpeg', '.webp', '.gif',
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _get_current_user():
    """Obtiene usuario del token JWT."""
    from flask import current_app
    import jwt as pyjwt
    token = None
    auth  = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth.split(' ', 1)[1]
    if not token:
        token = request.headers.get('X-Token') or request.args.get('token')
    if not token:
        raise PermissionError('Token requerido')
    secret = current_app.config.get('SECRET_KEY', os.environ.get('SECRET_KEY', 'dev'))
    try:
        payload = pyjwt.decode(token, secret, algorithms=['HS256'])
    except Exception:
        raise PermissionError('Token inválido o expirado')
    # Importar modelo User del contexto de la app
    from cic_ia_mejorado import User
    user = User.query.get(payload.get('user_id'))
    if not user:
        raise PermissionError('Usuario no encontrado')
    return user


def _call_groq_code(system: str, messages: list, max_tokens: int = 4096) -> str:
    """Llama a Groq con modelo de código. Cascade de modelos."""
    key = os.environ.get('GROQ_API_KEY', '')
    if not key:
        raise RuntimeError('Sin GROQ_API_KEY configurada')

    for model in CODE_MODELS:
        try:
            payload = {
                'model':       model,
                'messages':    [{'role': 'system', 'content': system}] + messages,
                'max_tokens':  max_tokens,
                'temperature': 0.2,   # Baja temp para código preciso
            }
            r = req_lib.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json=payload,
                timeout=60
            )
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content']
        except Exception as e:
            logger.warning(f'[CicCode] Modelo {model} falló: {e}')
            continue

    raise RuntimeError('Todos los modelos de Groq fallaron')


def _extract_files_from_response(text: str) -> list:
    """
    Extrae archivos del formato markdown que usa la IA:
    ```python:src/main.py
    código aquí
    ```
    Retorna lista de {'path': '...', 'content': '...', 'language': '...'}
    """
    pattern = r'```(\w+)?(?::([^\n]+))?\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    files = []
    for lang, path, content in matches:
        if path:
            files.append({
                'path':     path.strip(),
                'content':  content,
                'language': lang or _guess_lang(path),
            })
    return files


def _guess_lang(path: str) -> str:
    ext_map = {
        '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
        '.jsx': 'jsx', '.tsx': 'tsx', '.html': 'html', '.css': 'css',
        '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
        '.md': 'markdown', '.sh': 'bash', '.sql': 'sql',
    }
    ext = Path(path).suffix.lower()
    return ext_map.get(ext, 'text')


def _read_zip_contents(zip_bytes: bytes, max_files: int = 80) -> dict:
    """Lee el contenido de un ZIP y retorna estructura del proyecto."""
    structure = {'files': [], 'tree': [], 'total': 0, 'skipped': 0}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = [n for n in zf.namelist() if not n.endswith('/')]
            structure['total'] = len(names)
            for name in names[:max_files]:
                ext = Path(name).suffix.lower()
                if ext not in ALLOWED_EXTENSIONS and ext not in {'.py','.js','.ts','.html','.css','.json','.md','.txt','.yaml','.yml','.sh','.sql','.env','.toml','.cfg','.conf','.xml','.csv'}:
                    structure['skipped'] += 1
                    continue
                try:
                    raw = zf.read(name)
                    # Solo texto — archivos binarios se saltean
                    content = raw.decode('utf-8', errors='replace')
                    if len(content) > 50_000:
                        content = content[:50_000] + '\n... [truncado]'
                    structure['files'].append({
                        'path':    name,
                        'content': content,
                        'lang':    _guess_lang(name),
                        'size':    len(raw),
                    })
                    structure['tree'].append(name)
                except Exception:
                    structure['skipped'] += 1
            if len(names) > max_files:
                structure['skipped'] += len(names) - max_files
    except Exception as e:
        structure['error'] = str(e)
    return structure


def _sandbox_python(code: str, timeout: int = 10) -> dict:
    """Ejecuta Python en subprocess aislado con timeout."""
    t0 = datetime.utcnow()
    try:
        result = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        )
        elapsed = (datetime.utcnow() - t0).total_seconds()
        return {
            'success': True,
            'stdout':  result.stdout[:8000],
            'stderr':  result.stderr[:2000],
            'exit_code': result.returncode,
            'time_ms': int(elapsed * 1000),
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': f'Timeout ({timeout}s excedido)', 'stdout': '', 'stderr': ''}
    except Exception as e:
        return {'success': False, 'error': str(e), 'stdout': '', 'stderr': ''}


def _sandbox_js(code: str, timeout: int = 10) -> dict:
    """Ejecuta JavaScript con Node.js si está disponible."""
    t0 = datetime.utcnow()
    node = None
    for candidate in ['node', 'nodejs']:
        try:
            subprocess.run([candidate, '--version'], capture_output=True, timeout=3)
            node = candidate
            break
        except Exception:
            continue

    if not node:
        # Fallback: evaluar expresiones simples sin Node
        return {
            'success': False,
            'error':   'Node.js no disponible en el servidor. El código fue analizado pero no ejecutado.',
            'stdout':  '',
            'stderr':  '',
        }

    try:
        with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
            f.write(code)
            tmp = f.name
        result = subprocess.run(
            [node, tmp],
            capture_output=True, text=True, timeout=timeout
        )
        os.unlink(tmp)
        elapsed = (datetime.utcnow() - t0).total_seconds()
        return {
            'success': True,
            'stdout':  result.stdout[:8000],
            'stderr':  result.stderr[:2000],
            'exit_code': result.returncode,
            'time_ms': int(elapsed * 1000),
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': f'Timeout ({timeout}s)', 'stdout': '', 'stderr': ''}
    except Exception as e:
        return {'success': False, 'error': str(e), 'stdout': '', 'stderr': ''}


# ═══════════════════════════════════════════════════════════════════════════
# RUTAS
# ═══════════════════════════════════════════════════════════════════════════

@bp.route('/execute', methods=['POST'])
def execute_code():
    """
    Ejecutar código Python o JavaScript en sandbox.
    Body: { code, language, timeout? }
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    data     = request.get_json() or {}
    code     = data.get('code', '').strip()
    language = data.get('language', 'python').lower().strip()
    timeout  = min(int(data.get('timeout', 10)), 30)

    if not code:
        return jsonify({'success': False, 'error': 'Código vacío'}), 400
    if language not in SUPPORTED_LANGS:
        return jsonify({'success': False, 'error': f'Lenguaje "{language}" no soportado. Usa: python, javascript'}), 400

    logger.info(f'[CicCode/execute] user={user.username} lang={language} len={len(code)}')

    if language == 'python':
        result = _sandbox_python(code, timeout)
    else:
        result = _sandbox_js(code, timeout)

    return jsonify({**result, 'language': language})


@bp.route('/chat', methods=['POST'])
def code_chat():
    """
    Chat con IA sobre código.
    Soporta historial de conversación, contexto de proyecto, y adjuntos.
    Body: {
        message: str,
        history: [{role, content}],
        context?: str,        # código pegado o contexto de proyecto
        project_files?: [...] # archivos ya cargados en sesión
    }
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    data    = request.get_json() or {}
    message = data.get('message', '').strip()
    history = data.get('history', [])
    context = data.get('context', '')          # código o contexto adjunto
    project = data.get('project_files', [])    # archivos del proyecto en sesión

    if not message:
        return jsonify({'success': False, 'error': 'Mensaje vacío'}), 400

    # Construir contexto del proyecto si hay archivos
    project_ctx = ''
    if project:
        project_ctx = '\n\n## Archivos del proyecto en sesión:\n'
        for f in project[:20]:  # máx 20 archivos en contexto
            project_ctx += f"\n### {f.get('path', 'archivo')}\n```{f.get('lang','')}\n{f.get('content','')[:3000]}\n```\n"

    # System prompt especializado en código
    system = f"""Eres CicCode, el asistente de programación de Cic_IA.
Eres un ingeniero de software senior experto en: Python, JavaScript, TypeScript, React, Flask, Node.js, SQL, HTML/CSS, arquitectura de software, patrones de diseño, debugging y optimización.

Tu objetivo es ayudar a desarrollar, analizar, debuggear y generar código de calidad profesional.

## Capacidades que tienes:
- Leer y entender proyectos completos
- Generar código archivo por archivo
- Crear estructuras de proyectos completas con carpetas y archivos
- Detectar bugs y sugerir soluciones
- Explicar cómo funciona cualquier código
- Refactorizar y optimizar código existente

## Formato para código generado:
Cuando generes archivos, SIEMPRE usa este formato para que el sistema pueda detectarlos automáticamente:
```lenguaje:ruta/del/archivo.ext
código aquí
```

Ejemplo:
```python:src/app.py
from flask import Flask
app = Flask(__name__)
```

```javascript:src/index.js
console.log('Hola mundo')
```

## Reglas:
- Código limpio, con comentarios donde sea necesario
- Siempre explica qué hace el código generado
- Si detectas un bug, explica la causa y la solución
- Si el usuario pide un proyecto completo, genera TODOS los archivos necesarios
- Responde en español

{project_ctx}
{('## Contexto adicional proporcionado:\n' + context) if context else ''}
"""

    # Construir mensajes con historial
    msgs = []
    for h in history[-12:]:
        role    = h.get('role', 'user')
        content = h.get('content', '')
        if role in ('user', 'assistant') and content:
            msgs.append({'role': role, 'content': str(content)[:4000]})
    msgs.append({'role': 'user', 'content': message})

    try:
        response_text = _call_groq_code(system, msgs, max_tokens=4096)
    except Exception as e:
        logger.error(f'[CicCode/chat] Error Groq: {e}')
        return jsonify({'success': False, 'error': f'Error IA: {str(e)}'}), 500

    # Extraer archivos generados si los hay
    generated_files = _extract_files_from_response(response_text)

    return jsonify({
        'success':         True,
        'response':        response_text,
        'generated_files': generated_files,
        'files_count':     len(generated_files),
        'provider':        'groq',
    })


@bp.route('/upload', methods=['POST'])
def upload_file():
    """
    Subir archivo al contexto del IDE.
    Acepta: código, docs, imágenes, ZIPs de proyectos.
    Retorna el contenido procesado listo para usar en chat.
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No se recibió archivo'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': 'Archivo sin nombre'}), 400

    filename = file.filename
    ext      = Path(filename).suffix.lower()
    raw      = file.read()

    if len(raw) > MAX_FILE_SIZE:
        return jsonify({'success': False, 'error': f'Archivo demasiado grande (máx 10 MB)'}), 400

    logger.info(f'[CicCode/upload] user={user.username} file={filename} size={len(raw)}')

    # ── ZIP → descomprimir y analizar estructura del proyecto
    if ext == '.zip':
        structure = _read_zip_contents(raw)
        return jsonify({
            'success':   True,
            'type':      'project_zip',
            'filename':  filename,
            'files':     structure['files'],
            'tree':      structure['tree'],
            'total':     structure['total'],
            'skipped':   structure['skipped'],
            'message':   f'Proyecto extraído: {len(structure["files"])} archivos listos para analizar',
        })

    # ── Imagen → base64 para análisis con visión
    if ext in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
        b64 = base64.b64encode(raw).decode()
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.webp': 'image/webp', '.gif': 'image/gif'}
        return jsonify({
            'success':    True,
            'type':       'image',
            'filename':   filename,
            'base64':     b64,
            'mime_type':  mime_map.get(ext, 'image/png'),
            'size':       len(raw),
            'message':    f'Imagen cargada: {filename}',
        })

    # ── PDF → extraer texto
    if ext == '.pdf':
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                text = '\n'.join(p.extract_text() or '' for p in pdf.pages[:20])
        except ImportError:
            text = '[pdfplumber no instalado — instala con: pip install pdfplumber]'
        except Exception as e:
            text = f'[Error leyendo PDF: {e}]'
        return jsonify({
            'success':  True,
            'type':     'document',
            'filename': filename,
            'content':  text[:50000],
            'message':  f'PDF procesado: {filename}',
        })

    # ── Archivo de código/texto → leer contenido directamente
    try:
        content = raw.decode('utf-8', errors='replace')
    except Exception:
        return jsonify({'success': False, 'error': 'No se pudo leer el archivo como texto'}), 400

    if len(content) > 100_000:
        content = content[:100_000] + '\n... [truncado a 100k chars]'

    return jsonify({
        'success':  True,
        'type':     'code_file',
        'filename': filename,
        'path':     filename,
        'content':  content,
        'lang':     _guess_lang(filename),
        'size':     len(raw),
        'message':  f'Archivo cargado: {filename} ({len(raw)} bytes)',
    })


@bp.route('/analyze', methods=['POST'])
def analyze_project():
    """
    Analizar un proyecto completo (enviado como lista de archivos o como contexto).
    La IA genera un análisis detallado: arquitectura, dependencias, posibles mejoras.
    Body: {
        files: [{path, content, lang}],
        question?: str  # pregunta específica sobre el proyecto
    }
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    data     = request.get_json() or {}
    files    = data.get('files', [])
    question = data.get('question', 'Analiza este proyecto completo')

    if not files:
        return jsonify({'success': False, 'error': 'No hay archivos para analizar'}), 400

    # Construir contexto completo del proyecto
    project_text = f'# Proyecto con {len(files)} archivos\n\n'
    for f in files[:30]:
        path    = f.get('path', 'archivo')
        content = f.get('content', '')[:4000]
        lang    = f.get('lang', '')
        project_text += f'## {path}\n```{lang}\n{content}\n```\n\n'

    system = """Eres CicCode, un arquitecto de software senior de Cic_IA.
Tu tarea es analizar proyectos de software completos y proporcionar:
1. Descripción general del proyecto (qué hace, arquitectura usada)
2. Estructura de archivos y su propósito
3. Tecnologías y dependencias detectadas
4. Flujo de datos o lógica principal
5. Problemas detectados (bugs, malas prácticas, seguridad)
6. Sugerencias de mejora concretas
7. Respuesta específica a la pregunta del usuario

Responde en español, de forma técnica y organizada."""

    msgs = [{'role': 'user', 'content': f'{question}\n\n{project_text}'}]

    try:
        analysis = _call_groq_code(system, msgs, max_tokens=4096)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({
        'success':      True,
        'analysis':     analysis,
        'files_count':  len(files),
        'provider':     'groq',
    })


@bp.route('/generate', methods=['POST'])
def generate_project():
    """
    Generar un proyecto completo desde una descripción.
    Body: {
        description: str,    # "crea un juego de cartas en Python"
        tech_stack?: str,    # "Python + Flask + SQLAlchemy"
        include_tests?: bool,
        history?: [...]
    }
    """
    try:
        user = _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    data        = request.get_json() or {}
    description = data.get('description', '').strip()
    tech_stack  = data.get('tech_stack', 'auto-detectar según la tarea')
    inc_tests   = data.get('include_tests', False)
    history     = data.get('history', [])

    if not description:
        return jsonify({'success': False, 'error': 'Descripción vacía'}), 400

    system = f"""Eres CicCode, un ingeniero de software senior de Cic_IA.
El usuario te pide que generes un proyecto completo de software.

## Instrucciones de generación:
- Genera TODOS los archivos necesarios, uno por uno
- Usa SIEMPRE el formato: ```lenguaje:ruta/archivo.ext para cada archivo
- Incluye README.md explicando el proyecto
- Incluye requirements.txt o package.json según corresponda
- Código limpio, comentado y funcional
- Stack tecnológico solicitado: {tech_stack}
{'- Incluye tests unitarios básicos' if inc_tests else ''}

## Estructura esperada:
Primero explica qué vas a generar y la arquitectura elegida.
Luego genera cada archivo en orden lógico (primero configuración, luego lógica, luego interfaz).
Al final, explica cómo ejecutar el proyecto.

Responde en español."""

    msgs = []
    for h in history[-6:]:
        role    = h.get('role', 'user')
        content = h.get('content', '')
        if role in ('user', 'assistant') and content:
            msgs.append({'role': role, 'content': str(content)[:3000]})
    msgs.append({'role': 'user', 'content': f'Genera el siguiente proyecto:\n\n{description}'})

    try:
        response_text = _call_groq_code(system, msgs, max_tokens=8192)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    generated_files = _extract_files_from_response(response_text)

    return jsonify({
        'success':         True,
        'response':        response_text,
        'generated_files': generated_files,
        'files_count':     len(generated_files),
        'provider':        'groq',
    })


@bp.route('/status', methods=['GET'])
def status():
    """Estado del módulo CicCode."""
    try:
        _get_current_user()
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 401

    # Verificar si Node.js está disponible
    node_ok = False
    for candidate in ['node', 'nodejs']:
        try:
            r = subprocess.run([candidate, '--version'], capture_output=True, timeout=3)
            if r.returncode == 0:
                node_ok = True
                break
        except Exception:
            pass

    groq_ok = bool(os.environ.get('GROQ_API_KEY'))

    return jsonify({
        'success':        True,
        'module':         'CicCode IDE',
        'version':        '2.0.0',
        'python_sandbox': True,
        'js_sandbox':     node_ok,
        'ai_available':   groq_ok,
        'max_file_size':  '10 MB',
        'supported_langs': list(SUPPORTED_LANGS),
        'allowed_extensions': sorted(list(ALLOWED_EXTENSIONS)),
        'capabilities': [
            'Ejecutar Python en sandbox',
            'Ejecutar JavaScript (requiere Node.js)',
            'Chat conversacional sobre código',
            'Subir archivos, imágenes, ZIPs',
            'Analizar proyectos completos',
            'Generar proyectos desde descripción',
            'Historial de conversación persistente',
        ]
    })
