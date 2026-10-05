"""
Panel del aprendizaje de CicBrain.
Copiar a modules/learning_panel.py

Muestra si el alumno está creciendo o solo archivando.
No es el chat.
"""

from flask import Blueprint, jsonify, render_template_string


PANEL_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Aprendizaje CicBrain</title>
  <style>
    body { font-family: sans-serif; margin: 32px; background: #0f1419; color: #e7ecf1; }
    h1 { font-size: 22px; }
    .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .card { background: #1b242e; padding: 14px; border-radius: 8px; }
    .num { font-size: 28px; }
    table { width: 100%; border-collapse: collapse; margin-top: 18px; }
    td, th { border-bottom: 1px solid #2c3947; text-align: left; padding: 8px; font-size: 14px; }
    .bad { color: #ff8b7b; }
    .ok { color: #8bd17c; }
    a { color: #9ec1ff; }
  </style>
</head>
<body>
  <h1>CicBrain — colegio interno</h1>
  <p>El alumno es CicBrain. El maestro solo entra si el alumno no alcanza. Nada se promueve si el examen fijo baja.</p>
  <div class="grid">
    <div class="card"><div>Estado</div><div class="num">{{ 'congelado' if frozen else 'activo' }}</div></div>
    <div class="card"><div>Solo el alumno</div><div class="num">{{ student_rate }}%</div></div>
    <div class="card"><div>Promovidos</div><div class="num">{{ promoted }}</div></div>
    <div class="card"><div>Examen fijo</div><div class="num">{{ fixed }}</div></div>
  </div>
  <h2>Últimos ciclos</h2>
  <table>
    <tr><th>Ciclo</th><th>Preguntas</th><th>Solo</th><th>Promovidos</th><th>Rechazados</th><th>Fijo</th><th>Nota</th></tr>
    {% for c in cycles %}
    <tr>
      <td>{{ c.cycle_id }}</td>
      <td>{{ c.asked }}</td>
      <td>{{ c.student_only }}</td>
      <td>{{ c.promoted }}</td>
      <td>{{ c.rejected }}</td>
      <td>{{ c.fixed_score if c.fixed_score is not none else '—' }}</td>
      <td class="{{ 'bad' if c.frozen else 'ok' }}">{{ c.note or '' }}</td>
    </tr>
    {% endfor %}
  </table>
  <h2>Últimos casos</h2>
  <table>
    <tr><th>Estado</th><th>Nota</th><th>Pregunta</th><th>Alumno</th><th>Por qué</th></tr>
    {% for r in runs %}
    <tr>
      <td>{{ r.status }}</td>
      <td>{{ r.grade }}</td>
      <td>{{ r.question[:140] }}</td>
      <td>{{ 'sí' if r.student_answered else 'no' }}</td>
      <td>{{ (r.grade_reason or '')[:140] }}</td>
    </tr>
    {% endfor %}
  </table>
  <p><a href="/aprendizaje/estado">JSON</a> · correr a mano: POST /aprendizaje/ciclo</p>
</body>
</html>
"""


def create_learning_blueprint(db, models, tutor_loop):
    bp = Blueprint('learning_panel', __name__)
    ExamRun = models['ExamRun']
    LearningCycle = models['LearningCycle']

    @bp.route('/aprendizaje')
    def panel():
        cycles = LearningCycle.query.order_by(LearningCycle.id.desc()).limit(12).all()
        runs = ExamRun.query.order_by(ExamRun.id.desc()).limit(20).all()
        promoted = ExamRun.query.filter_by(status='promovido').count()
        total = ExamRun.query.count() or 1
        solo = ExamRun.query.filter_by(student_answered=True, status='promovido').count()
        last = cycles[0] if cycles else None
        return render_template_string(
            PANEL_HTML,
            frozen=bool(tutor_loop and tutor_loop.frozen),
            student_rate=round(100 * solo / total),
            promoted=promoted,
            fixed=(last.fixed_score if last and last.fixed_score is not None else '—'),
            cycles=cycles,
            runs=runs,
        )

    @bp.route('/aprendizaje/estado')
    def estado():
        last = LearningCycle.query.order_by(LearningCycle.id.desc()).first()
        return jsonify({
            'frozen': bool(tutor_loop and tutor_loop.frozen),
            'last_cycle': last.cycle_id if last else None,
            'fixed_score': last.fixed_score if last else None,
            'promoted': ExamRun.query.filter_by(status='promovido').count(),
            'cuarentena': ExamRun.query.filter_by(status='cuarentena').count(),
            'rechazado': ExamRun.query.filter_by(status='rechazado').count(),
        })

    @bp.route('/aprendizaje/ciclo', methods=['POST'])
    def correr():
        if not tutor_loop:
            return jsonify({'ok': False, 'error': 'tutor no iniciado'}), 503
        result = tutor_loop.run_cycle()
        return jsonify({'ok': True, **result})

    @bp.route('/aprendizaje/descongelar', methods=['POST'])
    def descongelar():
        if tutor_loop:
            tutor_loop.unfreeze()
        return jsonify({'ok': True, 'frozen': False})

    return bp
