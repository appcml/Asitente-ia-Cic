"""
Sistema de memoria vectorial para el Bebé IA
"""
import torch
import torch.nn as nn
import numpy as np
from datetime import datetime
import json
import os

class MemorySystem:
    """
    Sistema de memoria semántica que almacena y recupera experiencias
    """
    def __init__(self, embed_dim, memory_path, device='cpu'):
        self.embed_dim = embed_dim
        self.memory_path = memory_path
        self.device = device
        
        # Embedding simple para convertir texto a vectores
        self.embedding = nn.Embedding(5000, embed_dim).to(device)
        
        # Almacenamiento de memorias
        self.memories = []
        self.vectors = []
        
        # Cargar memorias existentes
        self._load()
    
    def _text_to_vector(self, text):
        """Convertir texto a vector usando embeddings simples"""
        # Tokenización simple por palabras
        tokens = text.lower().split()
        # Convertir a índices (hash simple)
        indices = [hash(word) % 5000 for word in tokens[:50]]  # max 50 palabras
        if not indices:
            indices = [0]
        
        with torch.no_grad():
            embeddings = self.embedding(torch.tensor(indices).to(self.device))
            # Promedio de embeddings
            vector = embeddings.mean(dim=0).cpu().numpy()
        return vector
    
    def store(self, content, context="", importance=0.5):
        """Guardar una nueva memoria"""
        memory = {
            'content': content,
            'context': context,
            'importance': importance,
            'timestamp': datetime.now().isoformat(),
            'access_count': 0
        }
        
        vector = self._text_to_vector(content)
        
        self.memories.append(memory)
        self.vectors.append(vector)
        
        # Limitar capacidad
        if len(self.memories) > 10000:
            self._forget_old()
        
        self._save()
    
    def retrieve(self, query, k=3):
        """Recuperar las k memorias más relevantes"""
        if not self.memories:
            return []
        
        query_vector = self._text_to_vector(query)
        
        # Calcular similitud coseno
        similarities = []
        for i, vec in enumerate(self.vectors):
            sim = np.dot(query_vector, vec) / (np.linalg.norm(query_vector) * np.linalg.norm(vec) + 1e-8)
            # Ajustar por importancia y recencia
            time_bonus = 0.1 * (i / len(self.memories))  # Memorias recientes tienen bonus
            importance_bonus = self.memories[i]['importance'] * 0.2
            final_score = sim + time_bonus + importance_bonus
            similarities.append((final_score, i))
        
        # Ordenar y seleccionar top k
        similarities.sort(reverse=True)
        results = []
        for score, idx in similarities[:k]:
            memory = self.memories[idx].copy()
            memory['similarity'] = float(score)
            memory['access_count'] += 1
            results.append(memory)
        
        return results
    
    def _forget_old(self):
        """Olvidar memorias menos importantes"""
        # Calcular score de olvido
        scores = []
        for i, mem in enumerate(self.memories):
            age = len(self.memories) - i
            importance = mem['importance']
            access = mem['access_count']
            forget_score = age / (importance + 0.1) / (access + 1)
            scores.append((forget_score, i))
        
        # Eliminar las 1000 más olvidables
        scores.sort(reverse=True)
        to_remove = [idx for _, idx in scores[:1000]]
        
        self.memories = [m for i, m in enumerate(self.memories) if i not in to_remove]
        self.vectors = [v for i, v in enumerate(self.vectors) if i not in to_remove]
    
    def _save(self):
        """Guardar memorias a disco"""
        if self.memory_path:
            os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
            data = {
                'memories': self.memories,
                'vectors': [v.tolist() for v in self.vectors]
            }
            with open(self.memory_path, 'w') as f:
                json.dump(data, f)
    
    def _load(self):
        """Cargar memorias desde disco"""
        if self.memory_path and os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, 'r') as f:
                    data = json.load(f)
                self.memories = data.get('memories', [])
                self.vectors = [np.array(v) for v in data.get('vectors', [])]
                print(f"🧠 {len(self.memories)} memorias cargadas")
            except Exception as e:
                print(f"⚠️ Error cargando memorias: {e}")


"""
Sistema de aprendizaje continuo
"""
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

class ConversationDataset(Dataset):
    def __init__(self, conversations, tokenizer, max_len=512):
        self.data = []
        for conv in conversations:
            full_text = f"Usuario: {conv['input']}\nAsistente: {conv['output']}"
            tokens = tokenizer.encode(full_text)
            if len(tokens) <= max_len:
                self.data.append(tokens)
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        tokens = self.data[idx]
        return torch.tensor(tokens[:-1]), torch.tensor(tokens[1:])

class ContinualLearner:
    def __init__(self, model, tokenizer, device='cpu'):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.conversations = []
        self.optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
        self.ewc_lambda = 1000
        self.fisher_dict = {}
        self.optimal_params = {}
        
    def add_experience(self, user_input, model_output, feedback_score=1.0):
        """Añadir nueva experiencia"""
        from datetime import datetime
        self.conversations.append({
            'input': user_input,
            'output': model_output,
            'feedback': feedback_score,
            'timestamp': datetime.now().isoformat()
        })
        
        if abs(feedback_score - 0.5) > 0.3:
            self._quick_learn(user_input, model_output, feedback_score)
    
    def _quick_learn(self, input_text, target_text, weight):
        """Aprendizaje rápido"""
        self.model.train()
        full_text = f"Usuario: {input_text}\nAsistente: {target_text}"
        tokens = self.tokenizer.encode(full_text)
        
        if len(tokens) < 3:
            return
            
        x = torch.tensor([tokens[:-1]]).to(self.device)
        y = torch.tensor([tokens[1:]]).to(self.device)
        
        self.optimizer.zero_grad()
        output = self.model(x)
        loss = nn.CrossEntropyLoss()(output.view(-1, output.size(-1)), y.view(-1))
        
        weighted_loss = loss * (1 + abs(weight - 0.5))
        weighted_loss.backward()
        
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()
    
    def sleep_and_learn(self, epochs=1):
        """Aprendizaje profundo"""
        if len(self.conversations) < 10:
            return
        
        print("😴 El bebé está durmiendo y aprendiendo...")
        
        self._compute_fisher()
        self.optimal_params = {n: p.clone().detach() 
                              for n, p in self.model.named_parameters()}
        
        dataset = ConversationDataset(self.conversations, self.tokenizer)
        loader = DataLoader(dataset, batch_size=4, shuffle=True)
        
        self.model.train()
        for epoch in range(epochs):
            total_loss = 0
            for x, y in loader:
                x, y = x.to(self.device), y.to(self.device)
                
                self.optimizer.zero_grad()
                output = self.model(x)
                loss = nn.CrossEntropyLoss()(output.view(-1, output.size(-1)), y.view(-1))
                
                ewc_loss = self._compute_ewc_loss()
                total_loss_batch = loss + self.ewc_lambda * ewc_loss
                
                total_loss_batch.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.optimizer.step()
                
                total_loss += loss.item()
            
            print(f"  Época {epoch+1}: pérdida = {total_loss/len(loader):.4f}")
        
        self._save_checkpoint()
    
    def _compute_fisher(self):
        """Calcular Fisher Information"""
        self.fisher_dict = {}
        self.model.eval()
        
        for n, p in self.model.named_parameters():
            self.fisher_dict[n] = torch.zeros_like(p)
        
        for conv in self.conversations[-100:]:
            full_text = f"Usuario: {conv['input']}\nAsistente: {conv['output']}"
            tokens = self.tokenizer.encode(full_text)
            if len(tokens) < 3:
                continue
                
            x = torch.tensor([tokens[:-1]]).to(self.device)
            self.model.zero_grad()
            output = self.model(x)
            loss = nn.CrossEntropyLoss()(output.view(-1, output.size(-1)), 
                                        torch.tensor([tokens[1:]]).to(self.device).view(-1))
            loss.backward()
            
            for n, p in self.model.named_parameters():
                if p.grad is not None:
                    self.fisher_dict[n] += p.grad.pow(2) / len(self.conversations[-100:])
    
    def _compute_ewc_loss(self):
        """Penalización EWC"""
        loss = 0
        for n, p in self.model.named_parameters():
            if n in self.fisher_dict and n in self.optimal_params:
                loss += (self.fisher_dict[n] * (p - self.optimal_params[n]).pow(2)).sum()
        return loss
    
    def _save_checkpoint(self):
        import os
        os.makedirs("checkpoints", exist_ok=True)
        torch.save({
            'model': self.model.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'conversations': len(self.conversations),
            'fisher': self.fisher_dict,
            'optimal': self.optimal_params
        }, f"checkpoints/bebe_checkpoint_{len(self.conversations)}.pt")
