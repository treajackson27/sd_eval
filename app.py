from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = 'shindo_final_final_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shindo_eval.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    leader = db.Column(db.String(50))
    topic = db.Column(db.String(200))

class Evaluator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    code = db.Column(db.String(20), unique=True)

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluator_id = db.Column(db.String(20))
    team_id = db.Column(db.Integer)
    report = db.Column(db.Integer, default=0)      # 탐구 보고서 (60)
    delivery = db.Column(db.Integer, default=0)    # 주제 전달력 (10)
    expression = db.Column(db.Integer, default=0)  # 언어적 표현 (10)
    teamwork = db.Column(db.Integer, default=0)    # 구성원 간의 협동 (10)
    vision = db.Column(db.Integer, default=0)      # 소감 및 비전 제시 (10)
    memo = db.Column(db.Text, default="")
    is_submitted = db.Column(db.Boolean, default=False)

admin_controls = {"timer_end": None, "notice": "평가가 곧 시작됩니다."}

@app.route('/')
def index():
    if 'role' in session:
        return redirect(url_for('admin_panel') if session['role'] == 'admin' else url_for('evaluator_panel'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    code = request.form.get('code', '').strip()
    if code == 'trea27':
        session['role'] = 'admin'
        return redirect(url_for('admin_panel'))
    ev = Evaluator.query.filter_by(code=code).first()
    if ev:
        session['role'] = 'evaluator'
        session['eval_id'] = ev.code
        session['eval_name'] = ev.name
        return redirect(url_for('evaluator_panel'))
    return "<script>alert('잘못된 코드입니다.'); history.back();</script>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/evaluator')
def evaluator_panel():
    if session.get('role') != 'evaluator': return redirect('/')
    teams = Team.query.all()
    my_scores = {s.team_id: s for s in Score.query.filter_by(evaluator_id=session['eval_id']).all()}
    return render_template('evaluator.html', teams=teams, scores=my_scores, controls=admin_controls, name=session['eval_name'])

@app.route('/admin')
def admin_panel():
    if session.get('role') != 'admin': return redirect('/')
    teams = Team.query.all()
    evaluators = Evaluator.query.all()
    score_map, team_averages = {}, {}
    for t in teams:
        score_map[t.id] = {}
        t_total_sum, t_count = 0, 0
        for e in evaluators:
            s = Score.query.filter_by(team_id=t.id, evaluator_id=e.code).first()
            if s:
                val = (s.report*0.6 + s.delivery*0.1 + s.expression*0.1 + s.teamwork*0.1 + s.vision*0.1)
                score_map[t.id][e.code] = {"val": round(val, 1), "is_submitted": s.is_submitted, "id": s.id}
                t_total_sum += val
                t_count += 1
        team_averages[t.id] = round(t_total_sum / t_count, 2) if t_count > 0 else 0
    return render_template('admin.html', teams=teams, evaluators=evaluators, score_map=score_map, team_averages=team_averages, controls=admin_controls)

@app.route('/admin/delete_score/<int:score_id>')
def delete_score(score_id):
    if session.get('role') != 'admin': return redirect('/')
    Score.query.filter_by(id=score_id).delete()
    db.session.commit()
    return redirect('/admin')

@app.route('/api/submit', methods=['POST'])
def submit_score():
    if session.get('role') != 'evaluator': return jsonify({"success": False}), 403
    data = request.json
    def v(val): return max(0, min(100, int(float(val or 0))))
    score = Score.query.filter_by(evaluator_id=session['eval_id'], team_id=data['team_id']).first()
    if not score:
        score = Score(evaluator_id=session['eval_id'], team_id=data['team_id'])
        db.session.add(score)
    if score.is_submitted: return jsonify({"success": False}), 400
    score.report = v(data.get('report'))
    score.delivery = v(data.get('delivery'))
    score.expression = v(data.get('expression'))
    score.teamwork = v(data.get('teamwork'))
    score.vision = v(data.get('vision'))
    score.memo = data.get('memo', '')
    score.is_submitted = data.get('final', False)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/admin/add_team', methods=['POST'])
def add_team():
    db.session.add(Team(name=request.form['name'], leader=request.form['leader'], topic=request.form['topic']))
    db.session.commit(); return redirect('/admin')

@app.route('/admin/delete_team/<int:id>')
def delete_team(id):
    Team.query.filter_by(id=id).delete(); Score.query.filter_by(team_id=id).delete()
    db.session.commit(); return redirect('/admin')

@app.route('/admin/add_evaluator', methods=['POST'])
def add_evaluator():
    code = request.form['code'].strip()
    if Evaluator.query.filter_by(code=code).first(): return "<script>alert('중복 코드'); history.back();</script>"
    db.session.add(Evaluator(name=request.form['name'], code=code)); db.session.commit(); return redirect('/admin')

@app.route('/admin/delete_evaluator/<int:id>')
def delete_evaluator(id):
    ev = Evaluator.query.get(id); 
    if ev: Score.query.filter_by(evaluator_id=ev.code).delete(); db.session.delete(ev); db.session.commit()
    return redirect('/admin')

@app.route('/admin/set_timer', methods=['POST'])
def set_timer():
    mins = int(request.form.get('minutes', 0))
    admin_controls['timer_end'] = (datetime.now() + timedelta(minutes=mins)).isoformat() if mins > 0 else None
    return redirect('/admin')

@app.route('/admin/set_notice', methods=['POST'])
def set_notice():
    admin_controls['notice'] = request.form.get('notice'); return redirect('/admin')

@app.route('/api/status')
def get_status(): return jsonify(admin_controls)

@app.route('/admin/download')
def download():
    data = []
    scores = Score.query.filter_by(is_submitted=True).all()
    for s in scores:
        t = Team.query.get(s.team_id)
        e = Evaluator.query.filter_by(code=s.evaluator_id).first()
        if t and e:
            total = (s.report*0.6 + s.delivery*0.1 + s.expression*0.1 + s.teamwork*0.1 + s.vision*0.1)
            data.append({"팀명": t.name, "심사위원": e.name, "보고서(60)": s.report, "전달(10)": s.delivery, "표현(10)": s.expression, "협동(10)": s.teamwork, "비전(10)": s.vision, "반영총점": round(total, 2), "메모": s.memo})
    df = pd.DataFrame(data)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer: df.to_excel(writer, index=False)
    out.seek(0)
    return send_file(out, download_name="final_results.xlsx", as_attachment=True)

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(host='0.0.0.0', debug=True, port=5000)