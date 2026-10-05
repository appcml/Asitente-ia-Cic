"""
Colegio interno de CicBrain.
Copiar a modules/tutor_loop.py

CicBrain es el alumno. El maestro es el LLM externo (Groq u otro).
El examinador genera preguntas, compara y solo promueve lo que está
apoyado en una fuente y no empeora el examen fijo.

No llama al maestro en cada mensaje del chat. Corre por ciclo.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger('cic_tutor')

# Tope por corrida. Evita quemar la cuota del maestro.
DEFAULT_QUESTIONS_PER_CYCLE = 5
FIXED_EXAM_SIZE = 30
PROMOTE_GRADE = 2          # solo nota máxima entra a memoria
MIN_ANSWER_CHARS = 40


GENERATE_QUESTIONS_PROMPT = """Genera {n} preguntas que una persona haría sobre el texto.
Responde solo un JSON array de strings, en español, sin markdown.
Cada pregunta debe poder responderse con el texto. No inventes temas de fuera.

TEXTO:
{source}
"""

GRADE_PROMPT = """Califica si la respuesta del alumno contesta la pregunta usando solo la fuente.
Nota:
- 2 = correcta y apoyada en la fuente
- 1 = parcial o incompleta
- 0 = incorrecta, inventada o no responde
Responde solo JSON: {{"grade": 0, "reason": "una frase"}}

PREGUNTA: {question}
FUENTE: {source}
RESPUESTA_ALUMNO: {answer}
"""

TEACH_PROMPT = """Responde la pregunta en español, solo con la fuente. Si la fuente no alcanza, di "no está en la fuente".
Máximo 120 palabras.

PREGUNTA: {question}
FUENTE: {source}
"""


class TutorLoop:
    def __init__(self, app, db, cic_brain, llm_engine, models: dict):
        self.app = app
        self.db = db
        self.brain = cic_brain
        self.llm = llm_engine
        self.ExamQuestion = models['ExamQuestion']
        self.ExamRun = models['ExamRun']
        self.LearningCycle = models['LearningCycle']
        self._stop = threading.Event()
        self._thread = None
        self.frozen = False
        self.last_fixed_score = None

    # ── Arranque ────────────────────────────────────────────────────

    def start(self, interval_seconds: int = 4 * 3600, questions_per_cycle: int = DEFAULT_QUESTIONS_PER_CYCLE):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_forever,
            args=(interval_seconds, questions_per_cycle),
            daemon=True,
            name='cic-tutor-loop',
        )
        self._thread.start()
        logger.info('[Tutor] ciclo interno cada %ss', interval_seconds)

    def stop(self):
        self._stop.set()

    def _run_forever(self, interval_seconds: int, questions_per_cycle: int):
        # Primera corrida a los 90s, para no chocar con el bootstrap del índice.
        if self._stop.wait(90):
            return
        while not self._stop.is_set():
            try:
                self.run_cycle(questions_per_cycle)
            except Exception:
                logger.exception('[Tutor] el ciclo falló')
            self._stop.wait(interval_seconds)

    # ── Un ciclo ────────────────────────────────────────────────────

    def run_cycle(self, questions_per_cycle: int = DEFAULT_QUESTIONS_PER_CYCLE) -> dict:
        cycle_id = uuid.uuid4().hex[:12]
        with self.app.app_context():
            self.db.create_all()
            row = self.LearningCycle(cycle_id=cycle_id, started_at=datetime.utcnow())
            self.db.session.add(row)
            self.db.session.commit()

            if self.frozen:
                row.frozen = True
                row.note = 'promoción congelada: el examen fijo bajó'
                row.finished_at = datetime.utcnow()
                self.db.session.commit()
                logger.warning('[Tutor] congelado, no se promueve')
                return {'cycle_id': cycle_id, 'frozen': True}

            seeds = self._seeds(questions_per_cycle)
            asked = student_only = promoted = rejected = 0

            for seed in seeds:
                questions = self._questions_from_seed(seed, n=1)
                for question in questions:
                    result = self._examine(cycle_id, question, seed)
                    asked += 1
                    student_only += int(result['student_only'])
                    promoted += int(result['status'] == 'promovido')
                    rejected += int(result['status'] == 'rechazado')

            fixed = self._run_fixed_exam(cycle_id)
            dropped = (
                self.last_fixed_score is not None
                and fixed is not None
                and fixed + 0.05 < self.last_fixed_score
            )
            if dropped:
                self.frozen = True
                row.frozen = True
                row.note = 'examen fijo bajó; promoción congelada hasta revisión'
                logger.warning('[Tutor] examen fijo %.2f -> %.2f, congelado', self.last_fixed_score, fixed)
            if fixed is not None:
                self.last_fixed_score = fixed

            row.asked = asked
            row.student_only = student_only
            row.promoted = promoted
            row.rejected = rejected
            row.fixed_score = fixed
            row.finished_at = datetime.utcnow()
            self.db.session.commit()
            logger.info(
                '[Tutor] ciclo %s asked=%s solo=%s promovidos=%s rechazados=%s fijo=%s',
                cycle_id, asked, student_only, promoted, rejected, fixed,
            )
            return {
                'cycle_id': cycle_id,
                'asked': asked,
                'student_only': student_only,
                'promoted': promoted,
                'rejected': rejected,
                'fixed_score': fixed,
                'frozen': self.frozen,
            }

    # ── Examen de una pregunta ──────────────────────────────────────

    def _examine(self, cycle_id: str, question: str, seed: dict) -> dict:
        student = self.brain.respond(question) if self.brain else {'answered': False}
        answered = bool(student.get('answered'))
        student_answer = (student.get('answer') or '').strip()
        confidence = float(student.get('confidence') or 0.0)

        teacher_answer = ''
        provider = ''
        grade = 0
        reason = 'sin maestro'
        status = 'rechazado'

        if answered and confidence >= 0.6:
            grade, reason = self._grade(question, seed.get('text', ''), student_answer)
            status = 'promovido' if grade >= PROMOTE_GRADE else 'rechazado'
            # Ya estaba en memoria. No se vuelve a copiar.
        else:
            teacher_answer, provider = self._teach(question, seed.get('text', ''))
            grounded = (
                teacher_answer
                and len(teacher_answer) >= MIN_ANSWER_CHARS
                and 'no está en la fuente' not in teacher_answer.lower()
                and 'no esta en la fuente' not in teacher_answer.lower()
            )
            if not grounded:
                status = 'rechazado'
                reason = 'el maestro no pudo apoyar la respuesta en la fuente'
            else:
                grade, reason = self._grade(question, seed.get('text', ''), teacher_answer)
                if grade >= PROMOTE_GRADE:
                    status = 'promovido'
                    self._promote(question, teacher_answer, provider or 'teacher')
                else:
                    status = 'cuarentena'
                    reason = reason or 'queda en cuarentena'

        qrow = self.ExamQuestion(
            question=question,
            expected=teacher_answer or None,
            source_url=seed.get('url'),
            source_title=seed.get('title'),
            kind='generated',
        )
        self.db.session.add(qrow)
        self.db.session.flush()
        self.db.session.add(self.ExamRun(
            cycle_id=cycle_id,
            question_id=qrow.id,
            question=question,
            student_answer=student_answer,
            student_confidence=confidence,
            student_answered=answered,
            teacher_answer=teacher_answer,
            teacher_provider=provider,
            grade=grade,
            grade_reason=reason,
            status=status,
            source_url=seed.get('url'),
        ))
        self.db.session.commit()
        return {'status': status, 'student_only': answered and status == 'promovido'}

    def _promote(self, question: str, answer: str, provider: str):
        # Entra al índice del alumno y a manual_knowledge para sobrevivir reinicios.
        try:
            self.brain.learn_from_external(question, answer, provider=provider)
        except Exception:
            logger.exception('[Tutor] no se pudo enseñar al índice')
        try:
            self.db.session.execute(text(
                """INSERT INTO manual_knowledge (title, content, category, priority, active, created_at, updated_at)
                   VALUES (:title, :content, 'tutor', 2, true, :now, :now)"""
            ), {
                'title': question[:180],
                'content': answer,
                'now': datetime.utcnow(),
            })
        except Exception:
            logger.exception('[Tutor] no se pudo persistir en manual_knowledge')

    # ── Maestro ─────────────────────────────────────────────────────

    def _ask_teacher(self, system: str, user: str) -> str:
        if not self.llm:
            return ''
        result = self.llm.chat(user, system, max_tokens=500)
        if not result or not result.get('success'):
            return ''
        return (result.get('response') or result.get('text') or result.get('answer') or '').strip()

    def _questions_from_seed(self, seed: dict, n: int = 1) -> list[str]:
        raw = self._ask_teacher(
            'Eres un examinador. Solo devuelves JSON.',
            GENERATE_QUESTIONS_PROMPT.format(n=n, source=(seed.get('text') or '')[:1500]),
        )
        questions = _parse_string_list(raw)
        if questions:
            return questions[:n]
        title = seed.get('title') or 'este tema'
        return [f'¿Qué dice el material sobre {title}?']

    def _teach(self, question: str, source: str) -> tuple[str, str]:
        answer = self._ask_teacher(
            'Respondes solo con la fuente dada.',
            TEACH_PROMPT.format(question=question, source=(source or '')[:2000]),
        )
        provider = 'groq'
        try:
            provider = getattr(self.llm, 'groq_model', None) and 'groq' or 'teacher'
        except Exception:
            provider = 'teacher'
        return answer, provider

    def _grade(self, question: str, source: str, answer: str) -> tuple[int, str]:
        raw = self._ask_teacher(
            'Eres un corrector. Solo devuelves JSON.',
            GRADE_PROMPT.format(question=question, source=(source or '')[:1500], answer=(answer or '')[:1200]),
        )
        data = _parse_object(raw)
        try:
            grade = int(data.get('grade', 0))
        except (TypeError, ValueError):
            grade = 0
        grade = max(0, min(2, grade))
        return grade, str(data.get('reason') or '')[:300]

    # ── Semillas y examen fijo ──────────────────────────────────────

    def _seeds(self, limit: int) -> list[dict]:
        rows = []
        try:
            rows = self.db.session.execute(text(
                """SELECT id, title, content
                   FROM manual_knowledge
                   WHERE active = true AND content IS NOT NULL
                   ORDER BY priority DESC, id DESC
                   LIMIT :limit"""
            ), {'limit': limit}).fetchall()
        except Exception:
            logger.exception('[Tutor] sin semillas en manual_knowledge')
        seeds = []
        for row in rows:
            seeds.append({
                'title': row[1],
                'text': row[2],
                'url': f'manual_knowledge:{row[0]}',
            })
        return seeds

    def _run_fixed_exam(self, cycle_id: str):
        fixed = self.ExamQuestion.query.filter_by(kind='fixed', active=True).limit(FIXED_EXAM_SIZE).all()
        if not fixed:
            return None
        ok = 0
        for item in fixed:
            student = self.brain.respond(item.question) if self.brain else {'answered': False}
            answer = (student.get('answer') or '').strip()
            grade = 0
            if student.get('answered') and item.expected:
                grade, _ = self._grade(item.question, item.expected, answer)
            ok += int(grade >= PROMOTE_GRADE)
            self.db.session.add(self.ExamRun(
                cycle_id=cycle_id,
                question_id=item.id,
                question=item.question,
                student_answer=answer,
                student_confidence=float(student.get('confidence') or 0.0),
                student_answered=bool(student.get('answered')),
                grade=grade,
                status='promovido' if grade >= PROMOTE_GRADE else 'rechazado',
                grade_reason='examen fijo',
            ))
        self.db.session.commit()
        return round(ok / max(len(fixed), 1), 3)

    def unfreeze(self):
        self.frozen = False
        logger.info('[Tutor] promoción reactivada a mano')


def _parse_string_list(raw: str) -> list[str]:
    import json
    if not raw:
        return []
    start, end = raw.find('['), raw.rfind(']')
    if start < 0 or end < 0:
        return []
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []
    return [str(x).strip() for x in data if str(x).strip()]


def _parse_object(raw: str) -> dict:
    import json
    if not raw:
        return {}
    start, end = raw.find('{'), raw.rfind('}')
    if start < 0 or end < 0:
        return {}
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
