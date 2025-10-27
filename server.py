from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import smtplib
import schedule
import threading
import time

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///budget.db'
db = SQLAlchemy(app)

# ----------------- جداول قاعدة البيانات -----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(100))
    balance_dz = db.Column(db.Float, default=0.0)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    item_name = db.Column(db.String(200))
    price_dz = db.Column(db.Float)
    category = db.Column(db.String(100))
    date = db.Column(db.DateTime, default=datetime.now)

# ----------------- إنشاء المستخدم -----------------
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    user = User(
        name=data['name'],
        email=data['email'],
        password=data['password'],
        balance_dz=data.get('balance_dz', 0)
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User registered successfully!"})

# ----------------- إضافة مشتريات -----------------
@app.route('/add_purchase', methods=['POST'])
def add_purchase():
    data = request.get_json()
    purchase = Purchase(
        user_id=data['user_id'],
        item_name=data['item_name'],
        price_dz=data['price_dz'],
        category=data.get('category', 'Other')
    )
    db.session.add(purchase)
    db.session.commit()
    return jsonify({"message": "Purchase added!"})

# ----------------- الحصول على تقارير -----------------
@app.route('/get_report/<int:user_id>', methods=['GET'])
def get_report(user_id):
    purchases = Purchase.query.filter_by(user_id=user_id).all()
    total = sum(p.price_dz for p in purchases)
    return jsonify({
        "user_id": user_id,
        "total_spent_dz": total,
        "count": len(purchases)
    })

# ----------------- إرسال البريد -----------------
def send_email(to_email, subject, body):
    sender = "hhomebudget@gmail.com"  # ← ضع هنا بريدك
    password = "homebudget123"        # ← كلمة مرور تطبيق Gmail (وليس العادية)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(sender, password)
            msg = f"Subject: {subject}\n\n{body}"
            smtp.sendmail(sender, to_email, msg)
        print("📧 Email sent successfully!")
    except Exception as e:
        print("Error sending email:", e)

# ----------------- تقارير أسبوعية وشهرية -----------------
def weekly_report():
    users = User.query.all()
    for u in users:
        purchases = Purchase.query.filter_by(user_id=u.id).all()
        total = sum(p.price_dz for p in purchases)
        send_email(u.email, "تقرير المصاريف الأسبوعي",
                   f"مجموع مصاريفك هذا الأسبوع: {total} د.ج")

def run_scheduler():
    schedule.every().sunday.at("20:00").do(weekly_report)
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_scheduler, daemon=True).start()

# ----------------- تشغيل السيرفر -----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)
