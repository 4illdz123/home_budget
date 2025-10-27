from flask import Flask, request, jsonify
import json
import threading
import time
import schedule
from datetime import datetime

app = Flask(__name__)

USERS_FILE = "users.json"
EXPENSES_FILE = "expenses.json"

# ======= أدوات مساعدة =======

def load_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ======= المستخدمين =======

@app.route("/users", methods=["GET"])
def get_users():
    users = load_json(USERS_FILE)
    return jsonify(users)

@app.route("/add_user", methods=["POST"])
def add_user():
    new_user = request.json
    if not new_user or "username" not in new_user or "password" not in new_user:
        return jsonify({"error": "بيانات المستخدم غير صالحة"}), 400

    users = load_json(USERS_FILE)
    for user in users:
        if user["username"] == new_user["username"]:
            return jsonify({"error": "اسم المستخدم موجود بالفعل"}), 400

    users.append(new_user)
    save_json(USERS_FILE, users)
    return jsonify({"message": "تمت إضافة المستخدم بنجاح"}), 200

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "بيانات تسجيل الدخول ناقصة"}), 400

    users = load_json(USERS_FILE)
    for user in users:
        if user["username"] == data["username"] and user["password"] == data["password"]:
            return jsonify({"message": "تسجيل الدخول ناجح"}), 200

    return jsonify({"error": "اسم المستخدم أو كلمة المرور غير صحيحة"}), 401

# ======= المصاريف =======

@app.route("/add_expense", methods=["POST"])
def add_expense():
    expense = request.json
    if not expense or "amount" not in expense or "description" not in expense:
        return jsonify({"error": "بيانات المصروف غير صالحة"}), 400

    expenses = load_json(EXPENSES_FILE)
    expense["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expenses.append(expense)
    save_json(EXPENSES_FILE, expenses)
    return jsonify({"message": "تمت إضافة المصروف"}), 200

@app.route("/expenses", methods=["GET"])
def get_expenses():
    return jsonify(load_json(EXPENSES_FILE))

# ======= التقارير التلقائية =======

def weekly_report():
    expenses = load_json(EXPENSES_FILE)
    total = sum(float(e["amount"]) for e in expenses)
    print(f"[تقرير أسبوعي] مجموع المصاريف حتى الآن: {total} د.ج")

def run_scheduler():
    schedule.every().sunday.at("20:00").do(weekly_report)
    while True:
        schedule.run_pending()
        time.sleep(60)

# ======= بدء السيرفر =======

if __name__ == "__main__":
    threading.Thread(target=run_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
