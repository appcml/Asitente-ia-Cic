"""
Módulo de Gestión de Archivos
Maneja subida, almacenamiento y procesamiento de archivos
"""

import os
import hashlib
import mimetypes
from datetime import datetime
import logging

logger = logging.getLogger('cic_ia.file_manager')

class FileManagerModule:
    def __init__(self, upload_folder='uploads', max_size=16*1024*1024):
        self.upload_folder = upload_folder
        self.max_size = max_size  # 16MB default
        self.allowed_extensions = {
            'document': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.md'],
            'data': ['.csv', '.xlsx', '.xls', '.json', '.xml', '.db', '.sqlite'],
            'image': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'],
            'code': ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.h', 
                    '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.ts', '.sql'],
            'archive': ['.zip', '.tar', '.gz', '.rar', '.7z']
        }
        
        # Flatten para verificación rápida
        self.all_extensions = []
        for cat, exts in self.allowed_extensions.items():
            self.all_extensions.extend(exts)
        
        os.makedirs(upload_folder, exist_ok=True)
    
    def validate_file(self, file_obj):
        """Valida archivo antes de subir"""
        # Verificar nombre
        if not file_obj or not file_obj.filename:
            return {'valid': False, 'error': 'No se proporcionó archivo'}
        
        # Verificar extensión
        ext = os.path.splitext(file_obj.filename)[1].lower()
        if ext not in self.all_extensions:
            return {
                'valid': False, 
                'error': f'Extensión no permitida: {ext}',
                'allowed': self.all_extensions
            }
        
        # Verificar tamaño
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(0)
        
        if size > self.max_size:
            return {
                'valid': False,
                'error': f'Archivo muy grande: {size/1024/1024:.2f}MB (máx: {self.max_size/1024/1024}MB)'
            }
        
        # Detectar categoría
        category = self._detect_category(ext)
        
        return {
            'valid': True,
            'filename': file_obj.filename,
            'extension': ext,
            'size': size,
            'size_formatted': self._format_size(size),
            'category': category,
            'mime_type': mimetypes.guess_type(file_obj.filename)[0] or 'unknown'
        }
    
    def save_file(self, file_obj, user_id=None, custom_name=None):
        """Guarda archivo en disco con metadatos"""
        validation = self.validate_file(file_obj)
        if not validation['valid']:
            return validation
        
        # Generar nombre único
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        original_name = custom_name or file_obj.filename
        safe_name = self._safe_filename(original_name)
        
        if user_id:
            user_folder = os.path.join(self.upload_folder, f'user_{user_id}')
            os.makedirs(user_folder, exist_ok=True)
            base_path = user_folder
        else:
            base_path = self.upload_folder
        
        # Nombre final: timestamp_hash_nombre
        file_hash = hashlib.md5(f"{original_name}{timestamp}".encode()).hexdigest()[:8]
        final_name = f"{timestamp}_{file_hash}_{safe_name}"
        file_path = os.path.join(base_path, final_name)
        
        # Guardar
        file_obj.save(file_path)
        
        # Verificar integridad
        saved_hash = self._calculate_hash(file_path)
        
        return {
            'success': True,
            'original_name': original_name,
            'saved_name': final_name,
            'file_path': file_path,
            'relative_path': os.path.relpath(file_path, self.upload_folder),
            'size': validation['size'],
            'category': validation['category'],
            'hash': saved_hash,
            'uploaded_at': datetime.now().isoformat()
        }
    
    def get_file_info(self, file_path):
        """Obtiene información de archivo guardado"""
        if not os.path.exists(file_path):
            return {'error': 'Archivo no encontrado'}
        
        stat = os.stat(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        
        return {
            'exists': True,
            'path': file_path,
            'size': stat.st_size,
            'size_formatted': self._format_size(stat.st_size),
            'category': self._detect_category(ext),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'hash': self._calculate_hash(file_path)
        }
    
    def list_user_files(self, user_id, category=None):
        """Lista archivos de un usuario"""
        user_folder = os.path.join(self.upload_folder, f'user_{user_id}')
        
        if not os.path.exists(user_folder):
            return {'files': [], 'total': 0, 'total_size': 0}
        
        files = []
        total_size = 0
        
        for filename in os.listdir(user_folder):
            file_path = os.path.join(user_folder, filename)
            if os.path.isfile(file_path):
                info = self.get_file_info(file_path)
                if info.get('exists'):
                    # Filtrar por categoría si se especifica
                    if category and info.get('category') != category:
                        continue
                    
                    files.append({
                        'name': filename,
                        'original_name': self._extract_original_name(filename),
                        'size': info['size_formatted'],
                        'category': info['category'],
                        'modified': info['modified']
                    })
                    total_size += info['size']
        
        return {
            'files': sorted(files, key=lambda x: x['modified'], reverse=True),
            'total': len(files),
            'total_size': self._format_size(total_size)
        }
    
    def delete_file(self, file_path, user_id=None):
        """Elimina archivo"""
        # Verificar que pertenezca al usuario
        if user_id:
            expected_prefix = os.path.join(self.upload_folder, f'user_{user_id}')
            if not file_path.startswith(expected_prefix):
                return {'success': False, 'error': 'Acceso no autorizado'}
        
        if os.path.exists(file_path):
            os.remove(file_path)
            return {'success': True, 'message': 'Archivo eliminado'}
        
        return {'success': False, 'error': 'Archivo no encontrado'}
    
    def _detect_category(self, extension):
        """Detecta categoría por extensión"""
        for cat, exts in self.allowed_extensions.items():
            if extension in exts:
                return cat
        return 'unknown'
    
    def _safe_filename(self, filename):
        """Limpia nombre de archivo"""
        # Remover caracteres peligrosos
        safe = "".join(c for c in filename if c.isalnum() or c in '._- ')
        return safe.strip()
    
    def _extract_original_name(self, saved_name):
        """Extrae nombre original del nombre guardado"""
        # Formato: timestamp_hash_nombreoriginal
        parts = saved_name.split('_', 2)
        return parts[2] if len(parts) >= 3 else saved_name
    
    def _format_size(self, size_bytes):
        """Formatea tamaño en unidades legibles"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"
    
    def _calculate_hash(self, file_path, algorithm='md5'):
        """Calcula hash de archivo"""
        hash_obj = hashlib.md5() if algorithm == 'md5' else hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        
        return hash_obj.hexdigest()
