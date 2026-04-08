"""
Motor de Red Neuronal Mejorado para Cic_IA v7.0
"""

import os
import pickle
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger('cic_neural')

class CicNeuralEngine:
    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
        
        self.intent_classifier = None
        self.relevance_model = None
        self.vectorizer = None
        self.label_encoder = None
        self.is_trained = False
        self.training_history = []
        self.version = 0
        
        self.config = {
            'intent_layers': [128, 64, 32],
            'relevance_layers': [64, 32],
            'max_features': 5000,
            'validation_split': 0.15
        }
        
        self._load_or_create()
    
    def _load_or_create(self):
        model_path = os.path.join(self.model_dir, 'cic_neural_v2.pkl')
        
        if os.path.exists(model_path):
            try:
                with open(model_path, 'rb') as f:
                    data = pickle.load(f)
                
                self.intent_classifier = data.get('intent_classifier')
                self.relevance_model = data.get('relevance_model')
                self.vectorizer = data.get('vectorizer')
                self.label_encoder = data.get('label_encoder')
                self.is_trained = data.get('is_trained', False)
                self.training_history = data.get('history', [])
                self.version = data.get('version', 0)
                
                logger.info(f"🧠 Modelos cargados (v{self.version})")
                return
            except Exception as e:
                logger.error(f"Error cargando: {e}")
        
        self._create_new_models()
    
    def _create_new_models(self):
        try:
            from sklearn.neural_network import MLPClassifier
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.preprocessing import LabelEncoder
            
            self.intent_classifier = MLPClassifier(
                hidden_layer_sizes=tuple(self.config['intent_layers']),
                activation='relu',
                solver='adam',
                alpha=0.001,
                max_iter=1000,
                random_state=42,
                early_stopping=True,
                validation_fraction=self.config['validation_split'],
                n_iter_no_change=10
            )
            
            self.relevance_model = MLPClassifier(
                hidden_layer_sizes=tuple(self.config['relevance_layers']),
                activation='tanh',
                solver='adam',
                max_iter=500,
                random_state=42
            )
            
            self.vectorizer = TfidfVectorizer(
                max_features=self.config['max_features'],
                ngram_range=(1, 2),
                stop_words='english',
                min_df=2
            )
            
            self.label_encoder = LabelEncoder()
            logger.info("🧠 Nuevos modelos creados")
            
        except ImportError:
            logger.warning("scikit-learn no disponible")
            self.intent_classifier = None
    
    def train(self, texts: List[str], labels: List[str]) -> Dict:
        if self.intent_classifier is None:
            return {'success': False, 'error': 'Modelos no disponibles'}
        
        if len(texts) < 5 or len(set(labels)) < 2:
            return {'success': False, 'error': 'Mínimo 5 ejemplos y 2 clases'}
        
        try:
            X = self.vectorizer.fit_transform(texts)
            y = self.label_encoder.fit_transform(labels)
            
            self.intent_classifier.fit(X, y)
            
            train_score = self.intent_classifier.score(X, y)
            
            metrics = {
                'train_accuracy': float(train_score),
                'iterations': int(self.intent_classifier.n_iter_),
                'loss': float(self.intent_classifier.loss_),
                'classes': list(self.label_encoder.classes_),
                'samples': len(texts)
            }
            
            self.is_trained = True
            self.version += 1
            
            self.training_history.append({
                'timestamp': datetime.utcnow().isoformat(),
                'version': self.version,
                'metrics': metrics
            })
            
            self._save_models()
            
            return {'success': True, 'metrics': metrics, 'version': self.version}
            
        except Exception as e:
            logger.error(f"Error entrenando: {e}")
            return {'success': False, 'error': str(e)}
    
    def retrain_with_feedback(self, feedback_data: List[Dict]) -> Dict:
        if not feedback_data:
            return {'success': False, 'error': 'No hay datos'}
        
        texts = []
        labels = []
        
        for item in feedback_data:
            texts.append(item['user_message'])
            correct = item.get('correct_intent') or item.get('intent')
            if correct:
                labels.append(correct)
        
        return self.train(texts, labels)
    
    def predict_intent(self, text: str) -> Dict:
        if not self.is_trained or self.intent_classifier is None:
            return {'intent': 'unknown', 'confidence': 0.0, 'all_probabilities': {}}
        
        try:
            X = self.vectorizer.transform([text])
            prediction = self.intent_classifier.predict(X)[0]
            probabilities = self.intent_classifier.predict_proba(X)[0]
            
            intent = self.label_encoder.inverse_transform([prediction])[0]
            confidence = float(np.max(probabilities))
            
            all_probs = {
                self.label_encoder.inverse_transform([i])[0]: float(p)
                for i, p in enumerate(probabilities)
            }
            
            return {
                'intent': intent,
                'confidence': confidence,
                'all_probabilities': all_probs,
                'is_uncertain': confidence < 0.6
            }
            
        except Exception as e:
            logger.error(f"Error predicción: {e}")
            return {'intent': 'unknown', 'confidence': 0.0, 'error': str(e)}
    
    def predict_relevance(self, query: str, document: str) -> float:
        if not self.is_trained:
            return self._fallback_relevance(query, document)
        
        try:
            combined = f"{query} [SEP] {document}"
            X = self.vectorizer.transform([combined])
            relevance = self.relevance_model.predict_proba(X)[0][1]
            return float(relevance)
        except:
            return self._fallback_relevance(query, document)
    
    def _fallback_relevance(self, query: str, document: str) -> float:
        q_words = set(query.lower().split())
        d_words = set(document.lower().split())
        if not q_words:
            return 0.0
        return len(q_words & d_words) / len(q_words)
    
    def _save_models(self):
        try:
            model_path = os.path.join(self.model_dir, 'cic_neural_v2.pkl')
            with open(model_path, 'wb') as f:
                pickle.dump({
                    'intent_classifier': self.intent_classifier,
                    'relevance_model': self.relevance_model,
                    'vectorizer': self.vectorizer,
                    'label_encoder': self.label_encoder,
                    'is_trained': self.is_trained,
                    'history': self.training_history,
                    'version': self.version,
                    'config': self.config
                }, f)
        except Exception as e:
            logger.error(f"Error guardando: {e}")
    
    def get_stats(self) -> Dict:
        return {
            'is_trained': self.is_trained,
            'version': self.version,
            'training_samples': sum(h['samples'] for h in self.training_history),
            'training_sessions': len(self.training_history),
            'classes': list(self.label_encoder.classes_) if self.label_encoder else []
        }
