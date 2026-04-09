"""
Módulo de Asistencia de Programación
Genera código en múltiples lenguajes, explica, depura
"""

import re
import logging

logger = logging.getLogger('cic_ia.code_assistant')

class CodeAssistantModule:
    def __init__(self):
        self.languages = {
            'python': {
                'name': 'Python',
                'extensions': ['.py'],
                'comment': '#',
                'description': 'Lenguaje versátil para IA, datos y web'
            },
            'javascript': {
                'name': 'JavaScript',
                'extensions': ['.js'],
                'comment': '//',
                'description': 'Lenguaje web frontend y backend (Node.js)'
            },
            'html': {
                'name': 'HTML',
                'extensions': ['.html', '.htm'],
                'comment': '<!-- -->',
                'description': 'Estructura de páginas web'
            },
            'css': {
                'name': 'CSS',
                'extensions': ['.css'],
                'comment': '/* */',
                'description': 'Estilos y diseño web'
            },
            'sql': {
                'name': 'SQL',
                'extensions': ['.sql'],
                'comment': '--',
                'description': 'Lenguaje de bases de datos'
            },
            'java': {
                'name': 'Java',
                'extensions': ['.java'],
                'comment': '//',
                'description': 'Lenguaje orientado a objetos, enterprise'
            },
            'cpp': {
                'name': 'C++',
                'extensions': ['.cpp', '.cc'],
                'comment': '//',
                'description': 'Sistemas, juegos, alto rendimiento'
            },
            'csharp': {
                'name': 'C#',
                'extensions': ['.cs'],
                'comment': '//',
                'description': 'Aplicaciones Windows, Unity, .NET'
            },
            'php': {
                'name': 'PHP',
                'extensions': ['.php'],
                'comment': '//',
                'description': 'Desarrollo web backend'
            },
            'ruby': {
                'name': 'Ruby',
                'extensions': ['.rb'],
                'comment': '#',
                'description': 'Desarrollo web rápido (Rails)'
            },
            'go': {
                'name': 'Go',
                'extensions': ['.go'],
                'comment': '//',
                'description': 'Sistemas distribuidos, microservicios'
            },
            'rust': {
                'name': 'Rust',
                'extensions': ['.rs'],
                'comment': '//',
                'description': 'Sistemas seguros y de alto rendimiento'
            },
            'swift': {
                'name': 'Swift',
                'extensions': ['.swift'],
                'comment': '//',
                'description': 'Desarrollo iOS y macOS'
            },
            'kotlin': {
                'name': 'Kotlin',
                'extensions': ['.kt'],
                'comment': '//',
                'description': 'Android, backend, multiplataforma'
            },
            'typescript': {
                'name': 'TypeScript',
                'extensions': ['.ts'],
                'comment': '//',
                'description': 'JavaScript con tipos estáticos'
            },
            'bash': {
                'name': 'Bash/Shell',
                'extensions': ['.sh'],
                'comment': '#',
                'description': 'Automatización de sistemas Linux/Mac'
            },
            'powershell': {
                'name': 'PowerShell',
                'extensions': ['.ps1'],
                'comment': '#',
                'description': 'Automatización Windows'
            },
            'r': {
                'name': 'R',
                'extensions': ['.r'],
                'comment': '#',
                'description': 'Estadística y análisis de datos'
            },
            'matlab': {
                'name': 'MATLAB',
                'extensions': ['.m'],
                'comment': '%',
                'description': 'Cálculo numérico, ingeniería'
            }
        }
        
        self.templates = self._load_templates()
    
    def _load_templates(self):
        """Plantillas de código comunes"""
        return {
            'python_web_scraper': '''
import requests
from bs4 import BeautifulSoup

def scrape_url(url):
    """Extrae información de una página web"""
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extraer título
        title = soup.find('title').get_text() if soup.find('title') else 'Sin título'
        
        # Extraer todos los párrafos
        paragraphs = [p.get_text() for p in soup.find_all('p')]
        
        return {
            'title': title,
            'paragraphs': paragraphs[:5],  # Primeros 5 párrafos
            'status': response.status_code
        }
    except Exception as e:
        return {'error': str(e)}

# Uso
if __name__ == '__main__':
    result = scrape_url('https://ejemplo.com')
    print(result)
''',
            'python_flask_app': '''
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/data', methods=['POST'])
def get_data():
    data = request.get_json()
    # Procesar datos
    return jsonify({'success': True, 'data': data})

if __name__ == '__main__':
    app.run(debug=True)
''',
            'html_basic_template': '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mi Aplicación</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .container {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Bienvenido</h1>
        <p>Contenido de la página</p>
    </div>
    <script>
        // JavaScript aquí
        console.log('Página cargada');
    </script>
</body>
</html>
''',
            'sql_basic_queries': '''
-- Crear tabla
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insertar datos
INSERT INTO usuarios (nombre, email) 
VALUES ('Juan Pérez', 'juan@email.com');

-- Consultar datos
SELECT * FROM usuarios WHERE fecha_registro > DATE('now', '-7 days');

-- Actualizar
UPDATE usuarios SET nombre = 'Juan Pérez G.' WHERE id = 1;

-- Eliminar
DELETE FROM usuarios WHERE id = 1;
'''
        }
    
    def detect_language(self, query):
        """Detecta el lenguaje de programación solicitado"""
        query_lower = query.lower()
        
        for lang_id, lang_info in self.languages.items():
            # Verificar nombre completo
            if lang_info['name'].lower() in query_lower:
                return lang_id
            
            # Verificar extensiones
            for ext in lang_info['extensions']:
                if ext.replace('.', '') in query_lower:
                    return lang_id
        
        # Palabras clave específicas
        keywords = {
            'python': ['python', 'django', 'flask', 'pandas', 'numpy'],
            'javascript': ['javascript', 'js', 'node', 'react', 'vue', 'angular'],
            'html': ['html', 'html5', 'etiquetas', 'tags'],
            'css': ['css', 'css3', 'estilos', 'flexbox', 'grid'],
            'sql': ['sql', 'mysql', 'postgresql', 'sqlite', 'query', 'consulta'],
            'java': ['java', 'spring', 'android java'],
            'cpp': ['c++', 'cpp', 'cplusplus'],
            'csharp': ['c#', 'csharp', '.net', 'dotnet'],
            'php': ['php', 'laravel', 'symfony'],
            'typescript': ['typescript', 'ts', 'angular', 'nestjs']
        }
        
        for lang, words in keywords.items():
            if any(w in query_lower for w in words):
                return lang
        
        return 'python'  # Default
    
    def generate_code(self, query, language=None):
        """
        Genera código basado en la descripción
        
        Args:
            query: Descripción de lo que se necesita
            language: Lenguaje específico (auto-detecta si es None)
        """
        if language is None:
            language = self.detect_language(query)
        
        lang_info = self.languages.get(language, self.languages['python'])
        
        # Detectar tipo de tarea
        task_type = self._detect_task_type(query)
        
        # Generar código según tarea
        if task_type == 'web_scraper':
            code = self.templates.get('python_web_scraper', '# Template no disponible')
        elif task_type == 'flask_app':
            code = self.templates.get('python_flask_app', '# Template no disponible')
        elif task_type == 'html_template':
            code = self.templates.get('html_basic_template', '<!-- Template no disponible -->')
        elif task_type == 'sql_queries':
            code = self.templates.get('sql_basic_queries', '-- Template no disponible')
        else:
            # Generación genérica basada en descripción
            code = self._generate_generic_code(query, language, lang_info)
        
        return {
            'success': True,
            'language': language,
            'language_name': lang_info['name'],
            'code': code.strip(),
            'task_type': task_type,
            'explanation': self._generate_explanation(code, language, task_type),
            'suggestions': self._get_suggestions(language, task_type)
        }
    
    def _detect_task_type(self, query):
        """Detecta el tipo de tarea solicitada"""
        query_lower = query.lower()
        
        patterns = {
            'web_scraper': ['scraper', 'scraping', 'extraer datos', 'web scraping', 'crawler', 'raspador'],
            'flask_app': ['flask', 'api rest', 'backend python', 'servidor web python'],
            'html_template': ['html template', 'plantilla html', 'página web básica', 'estructura html'],
            'sql_queries': ['sql', 'consulta sql', 'query', 'base de datos sql'],
            'data_analysis': ['análisis datos', 'pandas', 'csv', 'excel python'],
            'automation': ['automatizar', 'script', 'automation', 'bot'],
            'machine_learning': ['machine learning', 'ml', 'scikit', 'tensorflow', 'pytorch']
        }
        
        for task, keywords in patterns.items():
            if any(kw in query_lower for kw in keywords):
                return task
        
        return 'generic'
    
    def _generate_generic_code(self, query, language, lang_info):
        """Genera código genérico con comentarios explicativos"""
        comment = lang_info['comment']
        
        templates = {
            'python': f'''
{comment} {query}
{comment} Generado por Cic_IA Code Assistant

def main():
    """
    Función principal
    Implementa: {query[:50]}...
    """
    # TODO: Implementar lógica aquí
    print("Hola desde Python!")
    
    # Ejemplo de estructura
    data = []
    for i in range(10):
        data.append(i * 2)
    
    return data

if __name__ == '__main__':
    result = main()
    print(f"Resultado: {{result}}")
''',
            'javascript': f'''
{comment} {query}
{comment} Generado por Cic_IA Code Assistant

function main() {{
    // Función principal
    console.log("Hola desde JavaScript!");
    
    // TODO: Implementar lógica aquí
    const data = [];
    for (let i = 0; i < 10; i++) {{
        data.push(i * 2);
    }}
    
    return data;
}}

// Ejecutar
const result = main();
console.log("Resultado:", result);
''',
            'html': f'''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>{query[:30]}</title>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{query[:50]}</h1>
        <p>Implementación de: {query}</p>
        <!-- TODO: Agregar contenido -->
    </div>
</body>
</html>
''',
            'sql': f'''
-- {query}
-- Generado por Cic_IA Code Assistant

-- TODO: Adaptar nombres de tablas y columnas según tu esquema

-- Ejemplo de consulta
SELECT 
    columna1,
    columna2,
    COUNT(*) as total
FROM tabla_ejemplo
WHERE condicion = 'valor'
GROUP BY columna1
ORDER BY total DESC;

-- Ejemplo de inserción
INSERT INTO tabla_ejemplo (columna1, columna2)
VALUES ('valor1', 'valor2');
'''
        }
        
        return templates.get(language, templates['python'])
    
    def _generate_explanation(self, code, language, task_type):
        """Genera explicación del código"""
        explanations = {
            'web_scraper': 'Este scraper usa requests para obtener páginas web y BeautifulSoup para extraer información específica como títulos y párrafos.',
            'flask_app': 'Esta aplicación Flask crea un servidor web con rutas para mostrar páginas HTML y procesar datos vía API REST.',
            'html_template': 'Plantilla HTML5 básica con estructura semántica, metadatos responsive y espacio para CSS y JavaScript.',
            'sql_queries': 'Consultas SQL fundamentales: crear tablas, insertar, consultar, actualizar y eliminar datos.',
            'generic': 'Código estructurado con función principal, comentarios explicativos y manejo básico de datos.'
        }
        
        return explanations.get(task_type, explanations['generic'])
    
    def _get_suggestions(self, language, task_type):
        """Sugerencias de mejora o próximos pasos"""
        return [
            f'Agregar manejo de errores (try/except en {language})',
            'Incluir validación de entrada de datos',
            'Agregar tests unitarios',
            'Documentar funciones con docstrings',
            'Considerar patrones de diseño (MVC, Singleton, etc.)'
        ]
    
    def explain_code(self, code_snippet, language=None):
        """Explica código existente línea por línea"""
        if language is None:
            language = self.detect_language(code_snippet)
        
        lines = code_snippet.strip().split('\n')
        explanation = []
        
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Detectar tipo de línea
            if line_stripped.startswith('#') or line_stripped.startswith('//'):
                explanation.append(f"Línea {i}: **Comentario** - {line_stripped[1:].strip()}")
            elif 'def ' in line or 'function ' in line:
                explanation.append(f"Línea {i}: **Definición de función** - {line_stripped}")
            elif 'import ' in line or 'from ' in line:
                explanation.append(f"Línea {i}: **Importación de librerías** - {line_stripped}")
            elif '=' in line and '==' not in line:
                explanation.append(f"Línea {i}: **Asignación de variable** - {line_stripped}")
            elif 'if ' in line or 'for ' in line or 'while ' in line:
                explanation.append(f"Línea {i}: **Estructura de control** - {line_stripped}")
            else:
                explanation.append(f"Línea {i}: **Código ejecutable** - {line_stripped[:50]}...")
        
        return {
            'language': language,
            'total_lines': len(lines),
            'explanation': explanation,
            'summary': f'El código tiene aproximadamente {len([l for l in lines if l.strip()])} líneas ejecutables en {self.languages.get(language, {}).get("name", language)}.'
        }
    
    def debug_code(self, code_snippet, error_message=None):
        """Ayuda a depurar código con errores"""
        common_errors = {
            'SyntaxError': 'Error de sintaxis - revisa puntos, comas, paréntesis y sangría',
            'IndentationError': 'Error de sangría - Python requiere sangría consistente',
            'NameError': 'Variable no definida - revisa nombres de variables',
            'TypeError': 'Error de tipo - verifica que los tipos de datos sean compatibles',
            'IndexError': 'Índice fuera de rango - revisa los límites de listas/arrays',
            'KeyError': 'Clave no encontrada en diccionario',
            'AttributeError': 'Atributo no existe - revisa nombres de métodos/atributos',
            'ModuleNotFoundError': 'Módulo no instalado - ejecuta: pip install nombre_modulo'
        }
        
        suggestions = []
        
        if error_message:
            for error_type, description in common_errors.items():
                if error_type in error_message:
                    suggestions.append(f"**{error_type}**: {description}")
        
        # Análisis estático básico
        if 'print(' not in code_snippet and language == 'python':
            suggestions.append("💡 Agrega `print()` para debuguear valores intermedios")
        
        if 'try:' not in code_snippet and 'except' not in code_snippet:
            suggestions.append("💡 Considera usar try/except para manejo de errores")
        
        return {
            'error_analysis': suggestions,
            'general_tips': [
                'Revisa la sintaxis con un linter (pylint, eslint)',
                'Prueba el código en partes pequeñas',
                'Verifica que todas las dependencias estén instaladas',
                'Consulta la documentación oficial del lenguaje'
            ]
        }
    
    def convert_code(self, code_snippet, from_lang, to_lang):
        """Convierte código entre lenguajes (conversión conceptual)"""
        conversions = {
            ('python', 'javascript'): self._python_to_js,
            ('javascript', 'python'): self._js_to_python,
        }
        
        converter = conversions.get((from_lang, to_lang))
        if converter:
            return {
                'success': True,
                'original_language': from_lang,
                'target_language': to_lang,
                'converted_code': converter(code_snippet),
                'note': 'Conversión automática - revisar y ajustar manualmente'
            }
        
        return {
            'success': False,
            'error': f'Conversión de {from_lang} a {to_lang} no implementada aún',
            'supported': list(conversions.keys())
        }
    
    def _python_to_js(self, python_code):
        """Conversión básica Python a JavaScript"""
        # Reemplazos simples
        js_code = python_code.replace('def ', 'function ')
        js_code = js_code.replace('print(', 'console.log(')
        js_code = js_code.replace('# ', '// ')
        js_code = js_code.replace('None', 'null')
        js_code = js_code.replace('True', 'true')
        js_code = js_code.replace('False', 'false')
        
        return f"// Convertido desde Python\n// Revisar manualmente\n\n{js_code}"
    
    def _js_to_python(self, js_code):
        """Conversión básica JavaScript a Python"""
        py_code = js_code.replace('function ', 'def ')
        py_code = py_code.replace('console.log(', 'print(')
        py_code = py_code.replace('// ', '# ')
        py_code = py_code.replace('null', 'None')
        py_code = py_code.replace('true', 'True')
        py_code = py_code.replace('false', 'False')
        
        return f"# Convertido desde JavaScript\n# Revisar manualmente\n\n{py_code}"
