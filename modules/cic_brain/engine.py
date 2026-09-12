"""
CicBrain v1 — Motor de lenguaje propio de Cic_IA
=================================================
Arquitectura:
  1. Índice de conocimiento propio (datasets + conversaciones guardadas)
  2. Recuperación semántica por similitud de palabras clave (sin GPU)
  3. Generador de respuesta basado en contexto propio
  4. Aprendizaje continuo: cada conversación retroalimenta el índice
  5. Integración transparente con cic_ia_mejorado.py

Cuando CicBrain NO sabe responder → delega al LLM externo (Groq/Anthropic)
y GUARDA esa respuesta para aprender de ella.
"""

import os
import re
import json
import math
import logging
import threading
from datetime import datetime, date
from collections import defaultdict, Counter

logger = logging.getLogger('cic_brain')

# ─────────────────────────────────────────────
# Utilidades de texto
# ─────────────────────────────────────────────

STOPWORDS_ES = {
    'de','la','el','en','y','a','que','es','un','una','los','las',
    'del','al','se','por','con','para','como','más','pero','su','sus',
    'lo','le','les','me','te','nos','si','no','ya','hay','ser','está',
    'son','fue','han','muy','así','también','sobre','entre','hasta',
    'desde','sin','cuando','todo','esta','este','ese','eso','qué',
    'cómo','cuál','quién','dónde','cuándo','mi','tu','yo','tú','él',
    'eres','soy','tienes','tengo','puede','puedo','hacer','hago'
}

def tokenize(text: str) -> list[str]:
    """Limpia y tokeniza texto en español."""
    text = text.lower()
    text = re.sub(r'[^\w\sáéíóúüñ]', ' ', text)
    tokens = text.split()
    return [t for t in tokens if len(t) > 2 and t not in STOPWORDS_ES]

def tfidf_score(query_tokens: list, doc_tokens: list, doc_freq: dict, total_docs: int) -> float:
    """Calcula similitud TF-IDF simple entre query y documento."""
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_counter = Counter(doc_tokens)
    score = 0.0
    for token in query_tokens:
        tf = doc_counter.get(token, 0) / max(len(doc_tokens), 1)
        df = doc_freq.get(token, 0)
        idf = math.log((total_docs + 1) / (df + 1)) + 1
        score += tf * idf
    return score

def bigrams(tokens: list) -> list[str]:
    """Genera bigramas para capturar frases."""
    return [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens)-1)]


# ─────────────────────────────────────────────
# Índice de conocimiento
# ─────────────────────────────────────────────

class KnowledgeIndex:
    """
    Índice en memoria de todo el conocimiento de Cic_IA.
    Se reconstruye al arrancar desde PostgreSQL y se actualiza en caliente.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.docs: list[dict] = []          # [{id, source, question, answer, tokens, score}]
        self.doc_freq: dict[str, int] = {}  # frecuencia de token en todos los docs
        self._built = False

    def add(self, doc_id: str, source: str, question: str, answer: str, quality: float = 1.0):
        """Agrega un documento al índice."""
        combined = f"{question} {answer}"
        tokens = tokenize(combined) + bigrams(tokenize(combined))
        with self._lock:
            # Evitar duplicados por id
            existing_ids = {d['id'] for d in self.docs}
            if doc_id in existing_ids:
                return
            self.docs.append({
                'id':       doc_id,
                'source':   source,     # 'dataset', 'conversation', 'external_learned'
                'question': question,
                'answer':   answer,
                'tokens':   tokens,
                'quality':  quality,    # 0.0-1.0 — conversaciones buenas pesan más
                'added_at': datetime.utcnow().isoformat()
            })
            for t in set(tokens):
                self.doc_freq[t] = self.doc_freq.get(t, 0) + 1

    def search(self, query: str, top_k: int = 5, min_score: float = 0.05) -> list[dict]:
        """Busca los documentos más relevantes para una query."""
        q_tokens = tokenize(query) + bigrams(tokenize(query))
        if not q_tokens:
            return []
        with self._lock:
            total = len(self.docs)
            if total == 0:
                return []
            scored = []
            for doc in self.docs:
                raw = tfidf_score(q_tokens, doc['tokens'], self.doc_freq, total)
                final = raw * doc['quality']
                if final >= min_score:
                    scored.append((final, doc))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in scored[:top_k]]

    def size(self) -> int:
        with self._lock:
            return len(self.docs)

    def stats(self) -> dict:
        with self._lock:
            sources = Counter(d['source'] for d in self.docs)
            return {
                'total_docs':    len(self.docs),
                'unique_tokens': len(self.doc_freq),
                'by_source':     dict(sources)
            }


# ─────────────────────────────────────────────
# Generador de respuesta propio
# ─────────────────────────────────────────────

class ResponseGenerator:
    """
    Genera respuestas a partir del índice propio.
    NO usa LLM externo — combina los documentos más relevantes.
    Retorna None si la confianza es muy baja (delega al externo).
    """

    CONFIDENCE_THRESHOLD = 0.15  # Score mínimo para responder solo

    def generate(self, query: str, results: list[dict]) -> dict | None:
        """
        Intenta construir una respuesta propia.
        Retorna dict con 'answer' y 'confidence', o None si no puede.
        """
        if not results:
            return None

        top = results[0]
        top_score_approx = self._estimate_confidence(query, results)

        if top_score_approx < self.CONFIDENCE_THRESHOLD:
            return None  # No sabe suficiente → delega

        # Caso 1: match casi exacto con una pregunta del dataset
        q_sim = self._question_similarity(query, top['question'])
        if q_sim > 0.6:
            return {
                'answer':     top['answer'],
                'confidence': min(q_sim, 0.95),
                'source':     top['source'],
                'method':     'direct_match'
            }

        # Caso 2: combinar las 2-3 respuestas más relevantes
        if len(results) >= 2:
            combined = self._synthesize(query, results[:3])
            if combined:
                return {
                    'answer':     combined,
                    'confidence': top_score_approx * 0.8,
                    'source':     'synthesis',
                    'method':     'synthesis'
                }

        # Caso 3: usar la mejor respuesta con contexto
        if top_score_approx > 0.2:
            return {
                'answer':     top['answer'],
                'confidence': top_score_approx,
                'source':     top['source'],
                'method':     'best_match'
            }

        return None

    def _estimate_confidence(self, query: str, results: list) -> float:
        """Estima confianza basada en overlap de tokens."""
        if not results:
            return 0.0
        q_tokens = set(tokenize(query))
        top_tokens = set(results[0]['tokens'])
        if not q_tokens:
            return 0.0
        overlap = len(q_tokens & top_tokens)
        return min(overlap / len(q_tokens), 1.0)

    def _question_similarity(self, q1: str, q2: str) -> float:
        """Similitud Jaccard entre dos preguntas."""
        t1 = set(tokenize(q1))
        t2 = set(tokenize(q2))
        if not t1 or not t2:
            return 0.0
        return len(t1 & t2) / len(t1 | t2)

    def _synthesize(self, query: str, docs: list) -> str | None:
        """Combina múltiples respuestas relevantes en una sola."""
        q_tokens = set(tokenize(query))
        answers = []
        seen = set()
        for doc in docs:
            ans = doc['answer'].strip()
            # Evitar respuestas duplicadas o muy similares
            key = ans[:60]
            if key in seen:
                continue
            seen.add(key)
            # Solo incluir si hay overlap con la query
            ans_tokens = set(tokenize(ans))
            if q_tokens & ans_tokens or len(answers) == 0:
                answers.append(ans)

        if not answers:
            return None
        if len(answers) == 1:
            return answers[0]

        # Unir con conector natural
        return answers[0] + ' ' + answers[1]


# ─────────────────────────────────────────────
# Motor principal — CicBrain
# ─────────────────────────────────────────────

class CicBrain:
    """
    Motor de lenguaje propio de Cic_IA.

    Uso en cic_ia_mejorado.py:
    --------------------------
    from modules.cic_brain import CicBrain
    cic_brain = CicBrain(app, db)

    # En la función de chat, antes de llamar al LLM externo:
    brain_result = cic_brain.respond(user_message, user_id)
    if brain_result['answered']:
        return brain_result['answer']   # respuesta propia
    else:
        # llamar a Groq/Anthropic normalmente
        external_answer = llm.chat(...)
        # y enseñarle lo que aprendió del externo:
        cic_brain.learn_from_external(user_message, external_answer)
    """

    VERSION = 'v1.0'

    def __init__(self, app=None, db=None):
        self.app   = app
        self.db    = db
        self.index = KnowledgeIndex()
        self.gen   = ResponseGenerator()
        self._ready = False

        if app and db:
            self._bootstrap()

    # ── Inicialización ──────────────────────────────────────────────

    def _bootstrap(self):
        """Carga todo el conocimiento existente desde PostgreSQL al arrancar."""
        thread = threading.Thread(target=self._load_from_db, daemon=True)
        thread.start()

    def _load_from_db(self):
        """Carga ManualKnowledge, Conversation y Memory al índice."""
        try:
            with self.app.app_context():
                self._load_manual_knowledge()
                self._load_conversations()
                self._load_memories()
                self._ready = True
                stats = self.index.stats()
                logger.info(
                    f"[CicBrain] Índice listo — {stats['total_docs']} docs | "
                    f"{stats['unique_tokens']} tokens | fuentes: {stats['by_source']}"
                )
        except Exception as e:
            logger.error(f"[CicBrain] Error en bootstrap: {e}")

    def _load_manual_knowledge(self):
        """Carga datasets / conocimiento manual."""
        try:
            from sqlalchemy import text
            with self.db.engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT id, title, content, category FROM manual_knowledge WHERE active = true"
                )).fetchall()
            for row in rows:
                # Dividir contenido largo en chunks de ~500 chars
                chunks = self._chunk_text(str(row[2]), size=500)
                for i, chunk in enumerate(chunks):
                    self.index.add(
                        doc_id   = f"mk_{row[0]}_{i}",
                        source   = 'dataset',
                        question = str(row[1]),
                        answer   = chunk,
                        quality  = 1.0
                    )
            logger.info(f"[CicBrain] ManualKnowledge: {len(rows)} registros cargados")
        except Exception as e:
            logger.warning(f"[CicBrain] No se pudo cargar ManualKnowledge: {e}")

    def _load_conversations(self):
        """Carga conversaciones reales como pares pregunta/respuesta."""
        try:
            from sqlalchemy import text
            with self.db.engine.connect() as conn:
                rows = conn.execute(text(
                    """SELECT id, user_message, bot_response, tokens_used
                       FROM conversation
                       WHERE LENGTH(bot_response) > 50
                       ORDER BY timestamp DESC
                       LIMIT 2000"""
                )).fetchall()
            loaded = 0
            for row in rows:
                quality = self._quality_score(str(row[1]), str(row[2]))
                if quality < 0.3:
                    continue  # Descarta respuestas cortas o de mala calidad
                self.index.add(
                    doc_id   = f"conv_{row[0]}",
                    source   = 'conversation',
                    question = str(row[1]),
                    answer   = str(row[2]),
                    quality  = quality
                )
                loaded += 1
            logger.info(f"[CicBrain] Conversaciones: {loaded}/{len(rows)} cargadas (filtradas por calidad)")
        except Exception as e:
            logger.warning(f"[CicBrain] No se pudo cargar Conversations: {e}")

    def _load_memories(self):
        """Carga memorias del sistema."""
        try:
            from sqlalchemy import text
            with self.db.engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT id, topic, content FROM memory ORDER BY created_at DESC LIMIT 500"
                )).fetchall()
            for row in rows:
                self.index.add(
                    doc_id   = f"mem_{row[0]}",
                    source   = 'memory',
                    question = str(row[1]) if row[1] else 'general',
                    answer   = str(row[2]),
                    quality  = 0.8
                )
            logger.info(f"[CicBrain] Memories: {len(rows)} registros cargados")
        except Exception as e:
            logger.warning(f"[CicBrain] No se pudo cargar Memories: {e}")

    # ── Responder ───────────────────────────────────────────────────

    def respond(self, user_message: str, user_id: int = None) -> dict:
        """
        Intenta responder con conocimiento propio.
        Retorna:
          {'answered': True,  'answer': '...', 'confidence': 0.85, 'method': '...'}
          {'answered': False, 'reason': '...', 'context': [...docs relevantes...]}
        """
        if not self._ready:
            return {'answered': False, 'reason': 'index_loading'}

        results = self.index.search(user_message, top_k=5)
        if not results:
            return {'answered': False, 'reason': 'no_results'}

        response = self.gen.generate(user_message, results)
        if response:
            return {
                'answered':   True,
                'answer':     response['answer'],
                'confidence': response['confidence'],
                'source':     response['source'],
                'method':     response['method']
            }

        # No puede responder solo — devuelve el contexto para enriquecer el prompt externo
        return {
            'answered': False,
            'reason':   'low_confidence',
            'context':  results[:3]  # para inyectar en el system prompt del LLM externo
        }

    # ── Aprender ────────────────────────────────────────────────────

    def learn_from_conversation(self, question: str, answer: str, quality: float = None):
        """
        Aprende de una conversación nueva (respondida por Cic_IA o por LLM externo).
        Llamar DESPUÉS de guardar en BD para que el índice se actualice en tiempo real.
        """
        if not question or not answer or len(answer) < 30:
            return
        if quality is None:
            quality = self._quality_score(question, answer)
        if quality < 0.25:
            return  # No aprender de respuestas malas

        # ID temporal hasta que se guarde en BD
        doc_id = f"live_{hash(question + answer) & 0xFFFFFF}"
        self.index.add(
            doc_id   = doc_id,
            source   = 'conversation',
            question = question,
            answer   = answer,
            quality  = quality
        )
        logger.debug(f"[CicBrain] Aprendido de conversación (quality={quality:.2f})")

    def learn_from_external(self, question: str, external_answer: str, provider: str = 'groq'):
        """
        Aprende de la respuesta que dio un LLM externo (Groq, Anthropic, etc).
        El externo enseña al motor propio — exactamente lo que pediste.
        """
        if not external_answer or len(external_answer) < 40:
            return
        quality = self._quality_score(question, external_answer) * 0.9  # ligeramente menor que conversaciones propias
        doc_id = f"ext_{provider}_{hash(question) & 0xFFFFFF}"
        self.index.add(
            doc_id   = doc_id,
            source   = f'external_learned_{provider}',
            question = question,
            answer   = external_answer,
            quality  = quality
        )
        logger.debug(f"[CicBrain] Aprendido de {provider} (quality={quality:.2f})")

    def learn_from_dataset(self, pairs: list[dict]):
        """
        Carga masiva desde un dataset [{pregunta: ..., respuesta: ...}].
        Se llama cuando el usuario sube un archivo al módulo Dataset Training.
        """
        loaded = 0
        for i, pair in enumerate(pairs):
            q = pair.get('pregunta') or pair.get('question') or pair.get('input') or ''
            a = pair.get('respuesta') or pair.get('answer') or pair.get('output') or ''
            if not q or not a:
                continue
            self.index.add(
                doc_id   = f"ds_{i}_{hash(q) & 0xFFFFFF}",
                source   = 'dataset',
                question = q.strip(),
                answer   = a.strip(),
                quality  = 1.0  # datasets curados = calidad máxima
            )
            loaded += 1
        logger.info(f"[CicBrain] Dataset: {loaded}/{len(pairs)} pares cargados")
        return loaded

    # ── Utilidades ──────────────────────────────────────────────────

    def get_context_for_llm(self, query: str, max_docs: int = 3) -> str:
        """
        Retorna contexto del índice propio para inyectar en el system prompt del LLM externo.
        Así el externo responde con el conocimiento de Cic_IA.
        """
        results = self.index.search(query, top_k=max_docs)
        if not results:
            return ''
        parts = ['=== CONOCIMIENTO PROPIO DE CIC_IA (usa esto como base) ===']
        for doc in results:
            parts.append(f"P: {doc['question'][:150]}\nR: {doc['answer'][:400]}")
        return '\n\n'.join(parts)

    def status(self) -> dict:
        """Estado del motor para mostrar en el panel de Cic_IA."""
        stats = self.index.stats()
        return {
            'version':      self.VERSION,
            'ready':        self._ready,
            'total_docs':   stats['total_docs'],
            'unique_tokens': stats['unique_tokens'],
            'by_source':    stats['by_source'],
            'threshold':    self.gen.CONFIDENCE_THRESHOLD
        }

    def _quality_score(self, question: str, answer: str) -> float:
        """
        Estima la calidad de un par pregunta/respuesta.
        Factores: largo de respuesta, diversidad de tokens, no es error.
        """
        if not answer:
            return 0.0
        # Penalizar respuestas de error
        error_signals = ['lo siento', 'no puedo', 'error', 'no tengo acceso', 'disculpa']
        ans_lower = answer.lower()
        if any(s in ans_lower for s in error_signals):
            return 0.2
        # Score por largo (más largo = más informativo, hasta cierto punto)
        length_score = min(len(answer) / 500, 1.0)
        # Score por diversidad de tokens
        tokens = tokenize(answer)
        diversity = len(set(tokens)) / max(len(tokens), 1)
        return round((length_score * 0.6 + diversity * 0.4), 2)

    def _chunk_text(self, text: str, size: int = 500) -> list[str]:
        """Divide texto largo en chunks por oraciones."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks, current = [], ''
        for s in sentences:
            if len(current) + len(s) > size and current:
                chunks.append(current.strip())
                current = s
            else:
                current += ' ' + s
        if current.strip():
            chunks.append(current.strip())
        return chunks or [text[:size]]
