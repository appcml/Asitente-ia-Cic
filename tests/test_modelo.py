"""
Tests básicos del modelo
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from bebe_ia.core.model import BebeTransformer
from bebe_ia.core.tokenizer import SimpleTokenizer

def test_modelo_crea():
    """Test que el modelo se crea"""
    model = BebeTransformer(vocab_size=100, d_model=64, num_heads=4, num_layers=2)
    assert model is not None
    print("✅ Modelo creado correctamente")

def test_tokenizador():
    """Test del tokenizador"""
    tok = SimpleTokenizer(vocab_size=100)
    tok.train(["hola mundo", "test"])
    ids = tok.encode("hola")
    assert len(ids) > 0
    text = tok.decode(ids)
    assert "hola" in text
    print("✅ Tokenizador funciona")

def test_forward_pass():
    """Test de forward pass"""
    model = BebeTransformer(vocab_size=50, d_model=64, num_heads=4, num_layers=2)
    x = torch.randint(0, 50, (2, 10))
    out = model(x)
    assert out.shape == (2, 10, 50)
    print("✅ Forward pass correcto")

if __name__ == "__main__":
    test_modelo_crea()
    test_tokenizador()
    test_forward_pass()
    print("\n🍼 Todos los tests pasaron!")
