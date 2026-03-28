"""
Tokenizador simple BPE
"""
import json
import re
from collections import defaultdict

class SimpleTokenizer:
    def __init__(self, vocab_size=5000):
        self.vocab_size = vocab_size
        self.vocab = {"<pad>": 0, "<unk>": 1, "<sos>": 2, "<eos>": 3, "<mask>": 4}
        self.inverse_vocab = {v: k for k, v in self.vocab.items()}
        self.merges = []
        
    def train(self, texts):
        """Entrena BPE en textos iniciales"""
        print("🍼 Entrenando tokenizador (modo bebé)...")
        
        word_freqs = defaultdict(int)
        for text in texts:
            words = re.findall(r'\w+|[^\w\s]', text.lower())
            for word in words:
                word_freqs[' '.join(list(word)) + ' </w>'] += 1
        
        for i in range(self.vocab_size - len(self.vocab)):
            pairs = defaultdict(int)
            for word, freq in word_freqs.items():
                symbols = word.split()
                for j in range(len(symbols) - 1):
                    pairs[(symbols[j], symbols[j+1])] += freq
            
            if not pairs:
                break
                
            best = max(pairs, key=pairs.get)
            self.merges.append(best)
            
            new_token = ''.join(best)
            if new_token not in self.vocab:
                idx = len(self.vocab)
                self.vocab[new_token] = idx
                self.inverse_vocab[idx] = new_token
            
            new_word_freqs = {}
            for word in word_freqs:
                new_word = word.replace(' '.join(best), new_token)
                new_word_freqs[new_word] = word_freqs[word]
            word_freqs = new_word_freqs
            
            if i % 500 == 0:
                print(f"  Merge {i}/{self.vocab_size}: {best} -> {new_token}")
        
        print(f"✅ Vocabulario: {len(self.vocab)} tokens")
        
    def encode(self, text):
        """Texto -> IDs"""
        tokens = []
        words = re.findall(r'\w+|[^\w\s]', text.lower())
        
        for word in words:
            word = word + '</w>'
            word_tokens = list(word)
            for merge in self.merges:
                i = 0
                while i < len(word_tokens) - 1:
                    if word_tokens[i] == merge[0] and word_tokens[i+1] == merge[1]:
                        word_tokens = word_tokens[:i] + [''.join(merge)] + word_tokens[i+2:]
                    else:
                        i += 1
            
            for token in word_tokens:
                tokens.append(self.vocab.get(token, self.vocab["<unk>"]))
        
        return [self.vocab["<sos>"]] + tokens + [self.vocab["<eos>"]]
    
    def decode(self, ids):
        """IDs -> Texto"""
        tokens = []
        for idx in ids:
            if idx in [self.vocab["<pad>"], self.vocab["<sos>"], self.vocab["<eos>"]]:
                continue
            token = self.inverse_vocab.get(idx, "<unk>")
            tokens.append(token)
        
        text = ''.join(tokens).replace('</w>', ' ').strip()
        return text
    
    def save(self, path):
        with open(path, 'w') as f:
            json.dump({
                'vocab': self.vocab,
                'merges': self.merges
            }, f)
    
    def load(self, path):
        with open(path) as f:
            data = json.load(f)
            self.vocab = {k: int(v) for k, v in data['vocab'].items()}
            self.merges = [tuple(m) for m in data['merges']]
            self.inverse_vocab = {v: k for k, v in self.vocab.items()}
