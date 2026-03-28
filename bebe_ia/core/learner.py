"""
Sistema de aprendizaje continuo
"""
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from datetime import datetime

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
