# app.py
import os
from datetime import datetime, timedelta, date
from io import BytesIO
from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from functools import wraps
import smtplib
from email.message import EmailMessage
from apscheduler.schedulers.background import BackgroundScheduler
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# -------------------- Config --------------------
DATABASE_FILE = 'budget.db'
JWT_SECRET = os.environ.get('JWT_SECRET', 'change_me_please')
EMAIL_ADDRESS = os.environ.get('hhomebudget@gmail.com')  # your Gmail address
EMAIL_PASSWORD = os.environ.get('homebudget123')  # your Gmail App Password
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 465))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_FILE}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------- Models --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    balance_dz = db.Column(db.Float, default=0.0)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_name = db.Column(db.String(200))
    price_dz = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))
    date = db.Column(db.DateTime, default=datetime.utcnow)

class ReportLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    report_type = db.Column(db.String(20))  # weekly / monthly
    total = db.Column(db.Float)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

# -------------------- Utilities --------------------
def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.headers.get('Authorization', None)
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            current_user = User.query.get(data['id'])
            if not current_user:
                raise Exception('User not found')
        except Exception as e:
            return jsonify({'message': 'Token is invalid', 'error': str(e)}), 401
        return f(current_user, *args, **kwargs)
    return decorator

def generate_pdf_report(user: User, purchases, title='تقرير المصاريف'):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, title)
    y -= 30
    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"المستخدم: {user.name} -- الإيميل: {user.email}")
    y -= 20
    c.drawString(50, y, f"تاريخ التوليد: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}")
    y -= 30
    total = 0.0
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "التفاصيل:")
    y -= 20
    c.setFont("Helvetica", 10)
    for p in purchases:
        line = f"{p.date.strftime('%Y-%m-%d')} | {p.category or '-'} | {p.item_name} | {p.price_dz:.2f} د.ج"
        c.drawString(50, y, line)
        y -= 15
        total += p.price_dz
        if y < 80:
            c.showPage()
            y = height - 50
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"الإجمالي: {total:.2f} د.ج")
    c.save()
    buffer.seek(0)
    return buffer, total

def send_email_with_pdf(to_email: str, subject: str, body: str, pdf_bytes: BytesIO, pdf_filename='report.pdf'):
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        raise RuntimeError("EMAIL_ADDRESS and EMAIL_PASSWORD must be set in environment")
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    msg.set_content(body)
    pdf_data = pdf_bytes.read()
    msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=pdf_filename)
    # send via SMTP SSL
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

# -------------------- Routes --------------------
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'email and password required'}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'Email already registered'}), 400
    user = User(name=data.get('name',''), email=data['email'], balance_dz=float(data.get('balance_dz',0)))
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'registered successfully'})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'email and password required'}), 400
    user = User.query.filter_by(email=data['email']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'message': 'invalid credentials'}), 401
    token = jwt.encode({'id': user.id, 'exp': datetime.utcnow() + timedelta(days=7)}, JWT_SECRET, algorithm='HS256')
    return jsonify({'token': token, 'user': {'id': user.id, 'name': user.name, 'email': user.email, 'balance_dz': user.balance_dz}})

@app.route('/add_purchase', methods=['POST'])
@token_required
def add_purchase(current_user):
    data = request.json
    try:
        item_name = data['item_name']
        price_dz = float(data['price_dz'])
        category = data.get('category', None)
        dt = datetime.strptime(data['date'], '%Y-%m-%d') if data.get('date') else datetime.utcnow()
    except Exception as e:
        return jsonify({'message': 'invalid data', 'error': str(e)}), 400
    p = Purchase(user_id=current_user.id, item_name=item_name, price_dz=price_dz, category=category, date=dt)
    current_user.balance_dz -= price_dz  # update balance immediately
    db.session.add(p)
    db.session.commit()
    return jsonify({'message': 'purchase added', 'balance_dz': current_user.balance_dz})

@app.route('/purchases', methods=['GET'])
@token_required
def get_purchases(current_user):
    # optional query params: start, end (YYYY-MM-DD)
    start = request.args.get('start')
    end = request.args.get('end')
    q = Purchase.query.filter_by(user_id=current_user.id)
    if start:
        sdt = datetime.strptime(start, '%Y-%m-%d')
        q = q.filter(Purchase.date >= sdt)
    if end:
        edt = datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)
        q = q.filter(Purchase.date < edt)
    purchases = q.order_by(Purchase.date.desc()).all()
    out = []
    for p in purchases:
        out.append({'id': p.id, 'item_name': p.item_name, 'price_dz': p.price_dz, 'category': p.category, 'date': p.date.strftime('%Y-%m-%d')})
    return jsonify(out)

@app.route('/generate_report', methods=['POST'])
@token_required
def generate_report(current_user):
    # expects: { "type": "weekly" | "monthly", "send_email": true/false, "email": "..." }
    data = request.json
    rtype = data.get('type','weekly')
    today = date.today()
    if rtype == 'weekly':
        start = today - timedelta(days=today.weekday()+1)  # previous Sunday (optional adjust)
        end = start + timedelta(days=6)
    else:
        # monthly: first day of current month
        start = date(today.year, today.month, 1)
        # last day of month
        if today.month == 12:
            end = date(today.year, 12, 31)
        else:
            end = date(today.year, today.month+1, 1) - timedelta(days=1)
    purchases = Purchase.query.filter(Purchase.user_id==current_user.id, Purchase.date >= datetime.combine(start, datetime.min.time()), Purchase.date <= datetime.combine(end, datetime.max.time())).order_by(Purchase.date).all()
    pdf_buf, total = generate_pdf_report(current_user, purchases, title=f"تقرير ({rtype})")
    # log report
    rl = ReportLog(user_id=current_user.id, report_type=rtype, total=total, start_date=start, end_date=end)
    db.session.add(rl); db.session.commit()
    send_flag = data.get('send_email', False)
    if send_flag:
        to_email = data.get('email', current_user.email)
        subject = f"تقرير المصاريف - {rtype}"
        body = f"أرسل لك تقرير {rtype} للمصاريف من {start} إلى {end}. الإجمالي: {total:.2f} د.ج"
        try:
            send_email_with_pdf(to_email, subject, body, pdf_buf, pdf_filename=f"report_{rtype}_{start}_{end}.pdf")
        except Exception as e:
            return jsonify({'message': 'report generated but email failed', 'error': str(e)}), 500
        return jsonify({'message': 'report generated and emailed', 'total': total})
    # otherwise return pdf
    return send_file(pdf_buf, as_attachment=True, download_name=f"report_{rtype}_{start}_{end}.pdf", mimetype='application/pdf')

# -------------------- Scheduler (weekly/monthly) --------------------
def make_and_send_reports():
    # find all users
    users = User.query.all()
    for user in users:
        try:
            # weekly report (previous 7 days)
            today = date.today()
            # weekly: last 7 days
            start = today - timedelta(days=7)
            end = today
            purchases = Purchase.query.filter(Purchase.user_id==user.id, Purchase.date >= datetime.combine(start, datetime.min.time()), Purchase.date <= datetime.combine(end, datetime.max.time())).order_by(Purchase.date).all()
            pdf_buf, total = generate_pdf_report(user, purchases, title=f"تقرير أسبوعي من {start} إلى {end}")
            subject = f"تقرير أسبوعي للمصاريف ({start} — {end})"
            body = f"سلام، هذا تقرير المصاريف الأسبوعي للمستخدم {user.name}. الإجمالي: {total:.2f} د.ج"
            # send to user's email
            send_email_with_pdf(user.email, subject, body, pdf_buf, pdf_filename=f"weekly_{user.id}_{start}_{end}.pdf")
            rl = ReportLog(user_id=user.id, report_type='weekly', total=total, start_date=start, end_date=end)
            db.session.add(rl)
            db.session.commit()
        except Exception as e:
            print("Weekly report error for user", user.email, e)

    # monthly reports for those at month end
    # We'll check if today is the last day of the month; if so, send monthly
    t = date.today()
    next_day = t + timedelta(days=1)
    if next_day.day == 1:
        users = User.query.all()
        for user in users:
            try:
                # monthly: first to last day of previous month
                first = date(t.year, t.month, 1)
                last = t
                purchases = Purchase.query.filter(Purchase.user_id==user.id, Purchase.date >= datetime.combine(first, datetime.min.time()), Purchase.date <= datetime.combine(last, datetime.max.time())).order_by(Purchase.date).all()
                pdf_buf, total = generate_pdf_report(user, purchases, title=f"تقرير شهري من {first} إلى {last}")
                subject = f"تقرير شهري للمصاريف ({first} — {last})"
                body = f"سلام، هذا تقرير المصاريف الشهري للمستخدم {user.name}. الإجمالي: {total:.2f} د.ج"
                send_email_with_pdf(user.email, subject, body, pdf_buf, pdf_filename=f"monthly_{user.id}_{first}_{last}.pdf")
                rl = ReportLog(user_id=user.id, report_type='monthly', total=total, start_date=first, end_date=last)
                db.session.add(rl)
                db.session.commit()
            except Exception as e:
                print("Monthly report error for user", user.email, e)

# start scheduler
scheduler = BackgroundScheduler()
# run daily to check and send weekly/monthly as needed
scheduler.add_job(func=make_and_send_reports, trigger="interval", hours=24, id="reports_job")
scheduler.start()

# -------------------- Init DB --------------------
@app.before_first_request
def create_tables():
    db.create_all()

# -------------------- Run App --------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
