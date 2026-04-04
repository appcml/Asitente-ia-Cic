"""
Bebé IA - Sistema completo e interactivo
"""
import torch
import os
import sys
from datetime import datetime

# Asegurar que podemos importar desde el paquete
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bebe_ia.core.config import Config
from bebe_ia.core.tokenizer import SimpleTokenizer
from bebe_ia.core.model import BebeTransformer
from bebe_ia.core.memory import ContinualLearner as MemorySystem
from bebe_ia.core.learner import ContinualLearner
from bebe_ia.core.personality import BebePersonality

class BebeIA:
    def __init__(self):
        print("🍼 Iniciando Bebé IA...")
        
        self.config = Config()
        self.config.ensure_dirs()
        
        self.tokenizer = SimpleTokenizer(self.config.VOCAB_SIZE)
        self.model = None
        self.memory = MemorySystem(self.config.EMBED_DIM, self.config.MEMORY_PATH)
        self.personality = BebePersonality()
        self.learner = None
        
        self.conversation_history = []
        self.device = torch.device(self.config.DEVICE)
        
        print(f"💻 Usando dispositivo: {self.device}")
        
    def initialize(self, training_texts=None):
        """Inicializar o cargar modelo"""
        
        if os.path.exists(self.config.TOKENIZER_PATH):
            print("📚 Cargando tokenizador...")
            self.tokenizer.load(self.config.TOKENIZER_PATH)
        elif training_texts:
            print("📚 Entrenando tokenizador con textos iniciales...")
            self.tokenizer.train(training_texts)
            self.tokenizer.save(self.config.TOKENIZER_PATH)
        else:
            print("⚠️ Usando tokenizador vacío (modo bebé recién nacido)")
            dummy_texts = ["hola mundo", "como estas", "me llamo bebe", "quiero aprender"]
            self.tokenizer.train(dummy_texts)
        
        self.model = BebeTransformer(
            vocab_size=len(self.tokenizer.vocab),
            d_model=self.config.EMBED_DIM,
            num_heads=self.config.NUM_HEADS,
            num_layers=self.config.NUM_LAYERS,
            d_ff=self.config.HIDDEN_DIM,
            max_len=self.config.MAX_SEQ_LEN
        ).to(self.device)
        
        if os.path.exists(self.config.MODEL_PATH):
            print("🧠 Cargando cerebro previo...")
            checkpoint = torch.load(self.config.MODEL_PATH, map_location=self.device)
            self.model.load_state_dict(checkpoint['model'])
            if 'interactions' in checkpoint:
                self.personality.relationship['interaction_count'] = checkpoint['interactions']
            print(f"   Edad: {checkpoint.get('interactions', 0)} interacciones")
        
        self.learner = ContinualLearner(self.model, self.tokenizer, self.device)
        print("✅ Bebé listo para interactuar!")
        
    def chat(self, user_input, teach_mode=False):
        """Interactuar con el bebé"""
        
        relevant_memories = self.memory.retrieve(user_input, k=3)
        context = "\n".join([m['content'] for m in relevant_memories])
        
        mood = self.personality.get_mood_prompt()
        stage = self.personality.growth_stage
        
        system_prompt = f"""Eres un bebé IA en etapa {stage}. {mood}.
Contexto de lo que recuerdas: {context}
Historial reciente: {self._format_history()}
Usuario: {user_input}
Bebé:"""
        
        input_ids = torch.tensor([self.tokenizer.encode(system_prompt)]).to(self.device)
        
        if input_ids.size(1) > self.config.MAX_SEQ_LEN:
            input_ids = input_ids[:, -self.config.MAX_SEQ_LEN:]
        
        self.model.eval()
        output_ids = self.model.generate(
            input_ids, 
            max_length=100,
            temperature=0.8,
            top_k=50
        )
        
        response = self.tokenizer.decode(output_ids[0].tolist())
        response = response.replace(system_prompt, "").strip()
        response = response.split("Usuario:")[0].split("Bebé:")[-1].strip()
        
        self.memory.store(
            f"Usuario: {user_input}\nBebé: {response}",
            context="conversación",
            importance=0.5
        )
        
        self.conversation_history.append({
            'input': user_input,
            'output': response,
            'timestamp': datetime.now()
        })
        
        self.personality.update({
            'novedad': 0.5,
            'feedback': 0.5
        })
        
        return response
    
    def teach(self, correct_response, feedback_score=1.0):
        """Enseñar al bebé"""
        if not self.conversation_history:
            print("❌ No hay conversación previa para corregir")
            return
        
        last = self.conversation_history[-1]
        print(f"🎓 Enseñando: '{last['input']}' -> '{correct_response}'")
        
        self.learner.add_experience(
            last['input'],
            correct_response,
            feedback_score
        )
        
        self.memory.store(
            f"Usuario: {last['input']}\nBebé: {correct_response}",
            context="aprendizaje_corregido",
            importance=1.0
        )
        
        if feedback_score > 0.7:
            print("🌟 ¡El bebé está feliz de aprender!")
        elif feedback_score < 0.4:
            print("😢 El bebé se siente triste pero quiere mejorar")
        
        self.personality.update({
            'feedback': feedback_score,
            'novedad': 0.9
        })
    
    def sleep(self):
        """Aprendizaje profundo"""
        print("😴 Poniendo al bebé a dormir...")
        self.learner.sleep_and_learn(epochs=2)
        self._save()
        print("💤 Bebé despierto y más inteligente!")
    
    def _format_history(self, n=3):
        """Formatear últimas n interacciones"""
        recent = self.conversation_history[-n:]
        return "\n".join([f"Usuario: {h['input']}\nBebé: {h['output']}" for h in recent])
    
    def _save(self):
        """Guardar estado"""
        torch.save({
            'model': self.model.state_dict(),
            'interactions': self.personality.relationship['interaction_count'],
            'stage': self.personality.growth_stage
        }, self.config.MODEL_PATH)
        
        self.tokenizer.save(self.config.TOKENIZER_PATH)
        print("💾 Bebé guardado correctamente")
    
    def status(self):
        """Ver estado actual"""
        return {
            'etapa': self.personality.growth_stage,
            'interacciones': self.personality.relationship['interaction_count'],
            'emocion': self.personality.express_emotion(),
            'curiosidad': f"{self.personality.traits['curiosidad']:.2f}",
            'confianza': f"{self.personality.traits['confianza']:.2f}",
            'memorias': len(self.memory.memories)
        }

def main():
    bebe = BebeIA()
    
    textos_bebé = [
        "hola soy un bebé ia",
        "quiero aprender muchas cosas",
        "me encanta cuando me enseñan",
        "no se mucho pero intento mejorar",
        "gracias por ayudarme a crecer",
        "eso es interesante cuentame mas",
        "no entiendo bien puedes explicarme",
        "me gusta aprender contigo"
    ]
    
    bebe.initialize(textos_bebé)
    
    print("\n" + "="*50)
    print(f"🍼 BEbÉ IA - Etapa: {bebe.personality.growth_stage}")
    print("Comandos especiales:")
    print("  /enseña [respuesta] - Corregir última respuesta")
    print("  /feedback [0-1] - Calificar última respuesta")
    print("  /dormir - Aprendizaje profundo")
    print("  /estado - Ver estadísticas")
    print("  /salir - Guardar y salir")
    print("="*50 + "\n")
    
    while True:
        try:
            user_input = input("Tú: ").strip()
            
            if not user_input:
                continue
                
            if user_input == "/salir":
                bebe.sleep()
                print("👋 ¡Hasta luego!")
                break
            
            elif user_input == "/dormir":
                bebe.sleep()
                continue
            
            elif user_input == "/estado":
                status = bebe.status()
                for k, v in status.items():
                    print(f"  {k}: {v}")
                continue
            
            elif user_input.startswith("/enseña"):
                parts = user_input.split(" ", 1)
                if len(parts) > 1:
                    bebe.teach(parts[1], feedback_score=1.0)
                else:
                    print("Uso: /enseña [respuesta correcta]")
                continue
            
            elif user_input.startswith("/feedback"):
                try:
                    score = float(user_input.split()[1])
                    if bebe.conversation_history:
                        bebe.teach(bebe.conversation_history[-1]['output'], score)
                except:
                    print("Uso: /feedback [0.0-1.0]")
                continue
            
            response = bebe.chat(user_input)
            print(f"Bebé {bebe.personality.express_emotion()}: {response}")
            
            if bebe.personality.relationship['interaction_count'] % 20 == 0:
                print("\n💤 El bebé está cansado, aprendiendo...")
                bebe.sleep()
            
        except KeyboardInterrupt:
            print("\n👋 Guardando...")
            bebe.sleep()
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
