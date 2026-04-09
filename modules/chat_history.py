"""
Módulo de Historial de Conversaciones
Gestiona el historial completo de chats por usuario
"""

from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger('cic_ia.chat_history')

class ChatHistoryModule:
    def __init__(self, db_session, ConversationModel, UserModel):
        self.db = db_session
        self.Conversation = ConversationModel
        self.User = UserModel
    
    def get_user_history(self, user_id, limit=50, offset=0, date_from=None, date_to=None):
        """
        Obtiene historial de conversaciones de un usuario
        
        Args:
            user_id: ID del usuario
            limit: Cantidad de mensajes a retornar
            offset: Para paginación
            date_from: Fecha inicio (datetime)
            date_to: Fecha fin (datetime)
        """
        query = self.Conversation.query.filter_by(user_id=user_id)
        
        if date_from:
            query = query.filter(self.Conversation.timestamp >= date_from)
        if date_to:
            query = query.filter(self.Conversation.timestamp <= date_to)
        
        total = query.count()
        
        conversations = query.order_by(
            self.Conversation.timestamp.desc()
        ).offset(offset).limit(limit).all()
        
        return {
            'total': total,
            'offset': offset,
            'limit': limit,
            'conversations': [{
                'id': c.id,
                'user_message': c.user_message,
                'bot_response': c.bot_response,
                'intent': c.intent_detected,
                'mode': getattr(c, 'mode_used', 'unknown'),
                'timestamp': c.timestamp.isoformat() if c.timestamp else None,
                'date_formatted': c.timestamp.strftime('%d/%m/%Y %H:%M') if c.timestamp else None
            } for c in conversations]
        }
    
    def get_conversation_stats(self, user_id):
        """Estadísticas de conversación del usuario"""
        total = self.Conversation.query.filter_by(user_id=user_id).count()
        
        # Por intento
        intents = self.db.query(
            self.Conversation.intent_detected,
            self.db.func.count(self.Conversation.id)
        ).filter_by(user_id=user_id).group_by(
            self.Conversation.intent_detected
        ).all()
        
        # Por modo
        modes = self.db.query(
            getattr(self.Conversation, 'mode_used', 'unknown'),
            self.db.func.count(self.Conversation.id)
        ).filter_by(user_id=user_id).group_by(
            getattr(self.Conversation, 'mode_used', 'unknown')
        ).all()
        
        # Últimos 7 días
        week_ago = datetime.utcnow() - timedelta(days=7)
        last_week = self.Conversation.query.filter(
            self.Conversation.user_id == user_id,
            self.Conversation.timestamp >= week_ago
        ).count()
        
        # Primera y última conversación
        first = self.Conversation.query.filter_by(user_id=user_id).order_by(
            self.Conversation.timestamp.asc()
        ).first()
        last = self.Conversation.query.filter_by(user_id=user_id).order_by(
            self.Conversation.timestamp.desc()
        ).first()
        
        return {
            'total_conversations': total,
            'last_7_days': last_week,
            'by_intent': {intent: count for intent, count in intents if intent},
            'by_mode': {mode: count for mode, count in modes if mode},
            'first_conversation': first.timestamp.isoformat() if first else None,
            'last_conversation': last.timestamp.isoformat() if last else None,
            'average_per_day': round(total / 30, 2) if total > 0 else 0  # Últimos 30 días asumidos
        }
    
    def search_conversations(self, user_id, keyword, limit=20):
        """Busca en el historial por palabra clave"""
        search_pattern = f"%{keyword}%"
        
        results = self.Conversation.query.filter(
            self.Conversation.user_id == user_id,
            self.db.or_(
                self.Conversation.user_message.ilike(search_pattern),
                self.Conversation.bot_response.ilike(search_pattern)
            )
        ).order_by(self.Conversation.timestamp.desc()).limit(limit).all()
        
        return {
            'keyword': keyword,
            'matches': len(results),
            'conversations': [{
                'id': c.id,
                'user_message': c.user_message,
                'bot_response': c.bot_response[:200] + '...' if len(c.bot_response) > 200 else c.bot_response,
                'timestamp': c.timestamp.isoformat() if c.timestamp else None
            } for c in results]
        }
    
    def export_history(self, user_id, format='json'):
        """Exporta historial en formato JSON o CSV"""
        history = self.get_user_history(user_id, limit=10000)
        
        if format == 'json':
            return {
                'format': 'json',
                'data': history['conversations'],
                'exported_at': datetime.utcnow().isoformat()
            }
        
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Fecha', 'Usuario', 'Cic_IA', 'Intención', 'Modo'])
            
            for conv in history['conversations']:
                writer.writerow([
                    conv['date_formatted'],
                    conv['user_message'].replace('\n', ' '),
                    conv['bot_response'].replace('\n', ' ')[:500],
                    conv['intent'],
                    conv['mode']
                ])
            
            return {
                'format': 'csv',
                'data': output.getvalue(),
                'filename': f'historial_cic_ia_{user_id}_{datetime.now().strftime("%Y%m%d")}.csv'
            }
        
        return {'error': 'Formato no soportado'}
    
    def delete_conversation(self, user_id, conversation_id):
        """Elimina una conversación específica"""
        conv = self.Conversation.query.filter_by(
            id=conversation_id, 
            user_id=user_id
        ).first()
        
        if not conv:
            return {'success': False, 'error': 'Conversación no encontrada'}
        
        self.db.delete(conv)
        self.db.commit()
        
        return {'success': True, 'message': f'Conversación {conversation_id} eliminada'}
    
    def get_conversation_thread(self, conversation_id):
        """Obtiene una conversación específica con contexto"""
        conv = self.Conversation.query.get(conversation_id)
        
        if not conv:
            return {'error': 'Conversación no encontrada'}
        
        # Obtener conversaciones cercanas (contexto)
        nearby = self.Conversation.query.filter(
            self.Conversation.user_id == conv.user_id,
            self.Conversation.timestamp.between(
                conv.timestamp - timedelta(minutes=30),
                conv.timestamp + timedelta(minutes=30)
            )
        ).order_by(self.Conversation.timestamp).all()
        
        return {
            'conversation': {
                'id': conv.id,
                'user_message': conv.user_message,
                'bot_response': conv.bot_response,
                'intent': conv.intent_detected,
                'mode': getattr(conv, 'mode_used', 'unknown'),
                'timestamp': conv.timestamp.isoformat()
            },
            'context': [{
                'id': c.id,
                'user_message': c.user_message[:100],
                'timestamp': c.timestamp.isoformat()
            } for c in nearby if c.id != conv.id]
        }
