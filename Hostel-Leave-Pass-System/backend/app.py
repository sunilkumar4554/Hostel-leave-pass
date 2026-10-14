from __future__ import annotations

import base64
import csv
import io
import os
import secrets
import smtplib
import string
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from typing import Any

import qrcode
from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, abort, g, jsonify, request, send_file, send_from_directory, session
from openpyxl import Workbook
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="/assets")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "development-only-change-this-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/")
DB_NAME = os.getenv("MONGO_DB_NAME", "hostel_leave_system")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1800, connectTimeoutMS=1800)
db = client[DB_NAME]
_db_initialized = False
ALLOWED_PROOF_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_PROOF_BYTES = 5 * 1024 * 1024


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utc_now().isoformat(timespec="seconds")


def mongo_to_json(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat(timespec="seconds")
    if isinstance(value, dict):
        return {key: mongo_to_json(val) for key, val in value.items() if key != "password_hash"}
    if isinstance(value, list):
        return [mongo_to_json(item) for item in value]
    return value


def public_user(user: dict | None) -> dict | None:
    if not user:
        return None
    keys = [
        "_id", "name", "email", "role", "registration_no", "branch", "hostel_type",
        "hostel_name", "year", "room_no", "phone", "created_at", "active"
    ]
    return {key: mongo_to_json(user[key]) for key in keys if key in user}


def public_leave(leave: dict) -> dict:
    result = mongo_to_json(leave)
    result.pop("proof_storage_name", None)
    return result


def init_database() -> None:
    """Create indexes and local demo accounts when MongoDB is available."""
    global _db_initialized
    if _db_initialized:
        return
    db.command("ping")
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.users.create_index([("registration_no", ASCENDING)], unique=True, sparse=True)
    db.leaves.create_index([("leave_id", ASCENDING)], unique=True)
    db.leaves.create_index([("student_id", ASCENDING), ("created_at", DESCENDING)])
    db.leaves.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db.password_reset_otps.create_index("expires_at", expireAfterSeconds=0)

    seed_accounts = [
        {"name": "Demo Warden", "email": "warden@hostel.local", "password": "Warden@123", "role": "warden"},
        {"name": "Demo Guard", "email": "guard@hostel.local", "password": "Guard@123", "role": "guard"},
    ]
    for account in seed_accounts:
        if not db.users.find_one({"email": account["email"]}):
            db.users.insert_one({
                "name": account["name"],
                "email": account["email"],
                "password_hash": generate_password_hash(account["password"]),
                "role": account["role"],
                "active": True,
                "created_at": utc_now(),
            })
    _db_initialized = True


@app.before_request
def check_database_before_api() -> Any:
    # Let the homepage load even if MongoDB is not installed/running, but explain
    # the issue clearly for API requests instead of crashing the application.
    if request.path.startswith("/api/"):
        try:
            init_database()
        except Exception:
            return jsonify({
                "error": "Cannot connect to MongoDB. Start MongoDB Community Server, then connect MongoDB Compass to mongodb://127.0.0.1:27017/.",
                "code": "MONGODB_UNAVAILABLE",
            }), 503
    return None


def login_required(*roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"error": "Please log in first."}), 401
            try:
                user = db.users.find_one({"_id": ObjectId(user_id), "active": {"$ne": False}})
            except Exception:
                user = None
            if not user:
                session.clear()
                return jsonify({"error": "Your session has expired. Please log in again."}), 401
            if roles and user.get("role") not in roles:
                return jsonify({"error": "You do not have permission to perform this action."}), 403
            g.current_user = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_json() -> dict:
    return request.get_json(silent=True) or {}


def make_leave_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d")
    return f"LP-{stamp}-{secrets.token_hex(4).upper()}"


def make_qr_png(leave_id: str) -> bytes:
    image = qrcode.make(leave_id)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def allowed_proof(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_PROOF_EXTENSIONS


def send_reset_email(to_email: str, otp: str) -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", username or "")
    if not all([host, username, password, sender]):
        raise RuntimeError("Email delivery is not configured. Set SMTP values in the .env file.")
    message = EmailMessage()
    message["Subject"] = "Hostel Leave System password reset code"
    message["From"] = sender
    message["To"] = to_email
    message.set_content(f"Your password-reset OTP is {otp}. It expires in 10 minutes. If you did not request this, ignore this email.")
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)


@app.get("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<page>.html")
def pages(page: str):
    permitted = {"student-login", "warden-login", "guard-login", "register", "student-dashboard", "warden-dashboard", "guard-dashboard", "forgot-password"}
    if page not in permitted:
        abort(404)
    return send_from_directory(FRONTEND_DIR, f"{page}.html")


@app.get("/api/health")
def health():
    try:
        db.command("ping")
        return jsonify({"ok": True, "database": DB_NAME, "mongodb": "connected"})
    except Exception:
        return jsonify({"ok": False, "database": DB_NAME, "mongodb": "not connected"}), 503


@app.post("/api/register")
def register():
    data = get_json()
    required = ["name", "email", "password", "registration_no", "branch", "hostel_type", "hostel_name", "year", "room_no", "phone"]
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        return jsonify({"error": "Please complete all required fields.", "fields": missing}), 400
    email = str(data["email"]).strip().lower()
    registration_no = str(data["registration_no"]).strip().upper()
    password = str(data["password"])
    if len(password) < 8:
        return jsonify({"error": "Password must contain at least 8 characters."}), 400
    if "@" not in email:
        return jsonify({"error": "Enter a valid email address."}), 400
    if db.users.find_one({"$or": [{"email": email}, {"registration_no": registration_no}]}):
        return jsonify({"error": "This email or registration number is already registered."}), 409
    user = {
        "name": str(data["name"]).strip(),
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": "student",
        "registration_no": registration_no,
        "branch": str(data["branch"]).strip(),
        "hostel_type": str(data["hostel_type"]).strip(),
        "hostel_name": str(data["hostel_name"]).strip(),
        "year": str(data["year"]).strip(),
        "room_no": str(data["room_no"]).strip(),
        "phone": str(data["phone"]).strip(),
        "active": True,
        "created_at": utc_now(),
    }
    try:
        result = db.users.insert_one(user)
    except DuplicateKeyError:
        return jsonify({"error": "This email or registration number is already registered."}), 409
    session.clear()
    session["user_id"] = str(result.inserted_id)
    return jsonify({"message": "Registration successful.", "user": public_user(user)}), 201


@app.post("/api/login")
def login():
    data = get_json()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    requested_role = str(data.get("role", "")).lower()
    if not email or not password or requested_role not in {"student", "warden", "guard"}:
        return jsonify({"error": "Email, password and portal role are required."}), 400
    user = db.users.find_one({"email": email, "active": {"$ne": False}})
    if not user or user.get("role") != requested_role or not check_password_hash(user.get("password_hash", ""), password):
        return jsonify({"error": "Email, password or selected portal is incorrect."}), 401
    session.clear()
    session["user_id"] = str(user["_id"])
    return jsonify({"message": "Login successful.", "user": public_user(user)})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully."})


@app.get("/api/me")
@login_required()
def me():
    return jsonify({"user": public_user(g.current_user)})


@app.post("/api/auth/forgot-password")
def forgot_password():
    data = get_json()
    email = str(data.get("email", "")).strip().lower()
    user = db.users.find_one({"email": email, "active": {"$ne": False}})
    # Avoid confirming whether an account exists. SMTP setup errors are reported
    # only when an actual account requested the reset.
    if not user:
        return jsonify({"message": "If the account exists, a reset code will be sent."})
    otp = "".join(secrets.choice(string.digits) for _ in range(6))
    db.password_reset_otps.delete_many({"email": email})
    db.password_reset_otps.insert_one({
        "email": email,
        "otp_hash": generate_password_hash(otp),
        "expires_at": utc_now() + timedelta(minutes=10),
        "created_at": utc_now(),
    })
    try:
        send_reset_email(email, otp)
    except Exception as exc:
        db.password_reset_otps.delete_many({"email": email})
        return jsonify({"error": str(exc)}), 503
    return jsonify({"message": "A reset code has been sent to your email."})


@app.post("/api/auth/reset-password")
def reset_password():
    data = get_json()
    email = str(data.get("email", "")).strip().lower()
    otp = str(data.get("otp", "")).strip()
    new_password = str(data.get("new_password", ""))
    if not email or not otp or len(new_password) < 8:
        return jsonify({"error": "Email, OTP and a new password of at least 8 characters are required."}), 400
    record = db.password_reset_otps.find_one({"email": email}, sort=[("created_at", DESCENDING)])
    expires_at = record.get("expires_at") if record else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not record or not expires_at or expires_at < utc_now() or not check_password_hash(record["otp_hash"], otp):
        return jsonify({"error": "Invalid or expired OTP."}), 400
    db.users.update_one({"email": email}, {"$set": {"password_hash": generate_password_hash(new_password)}})
    db.password_reset_otps.delete_many({"email": email})
    return jsonify({"message": "Password reset successful. You can now log in."})


@app.post("/api/leaves")
@login_required("student")
def apply_leave():
    user = g.current_user
    reason = request.form.get("reason", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    return_time = request.form.get("return_time", "").strip()
    notes = request.form.get("notes", "").strip()
    if reason not in {"Home", "Medical", "Emergency", "Personal", "Family Function", "Other"}:
        return jsonify({"error": "Select a valid leave reason."}), 400
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Enter valid leave dates."}), 400
    if end < start:
        return jsonify({"error": "Return date cannot be before the start date."}), 400
    if start < date.today():
        return jsonify({"error": "Leave start date cannot be in the past."}), 400
    if not return_time:
        return jsonify({"error": "Please provide your expected return time."}), 400
    proof = request.files.get("proof")
    proof_storage_name = None
    original_filename = None
    if proof and proof.filename:
        original_filename = secure_filename(proof.filename)
        if not allowed_proof(original_filename):
            return jsonify({"error": "Proof must be a PDF, PNG or JPG/JPEG file."}), 400
        proof_bytes = proof.read(MAX_PROOF_BYTES + 1)
        if len(proof_bytes) > MAX_PROOF_BYTES:
            return jsonify({"error": "Proof file must be 5 MB or smaller."}), 400
        extension = original_filename.rsplit(".", 1)[1].lower()
        proof_storage_name = f"{secrets.token_hex(16)}.{extension}"
        (UPLOAD_DIR / proof_storage_name).write_bytes(proof_bytes)
    leave = {
        "leave_id": make_leave_id(),
        "student_id": str(user["_id"]),
        "student_name": user.get("name", ""),
        "email": user.get("email", ""),
        "registration_no": user.get("registration_no", ""),
        "branch": user.get("branch", ""),
        "hostel_type": user.get("hostel_type", ""),
        "hostel_name": user.get("hostel_name", ""),
        "room_no": user.get("room_no", ""),
        "reason": reason,
        "start_date": start_date,
        "end_date": end_date,
        "return_time": return_time,
        "notes": notes,
        "proof_filename": original_filename,
        "proof_storage_name": proof_storage_name,
        "status": "Pending",
        "created_at": utc_now(),
        "decision_at": None,
        "decision_by": None,
        "rejection_reason": None,
        "checked_out_at": None,
        "checked_in_at": None,
        "extension_request": None,
    }
    db.leaves.insert_one(leave)
    db.audit_logs.insert_one({"actor_id": str(user["_id"]), "actor_role": "student", "action": "leave_submitted", "leave_id": leave["leave_id"], "created_at": utc_now()})
    return jsonify({"message": "Leave application submitted.", "leave": public_leave(leave)}), 201


@app.get("/api/leaves/my")
@login_required("student")
def my_leaves():
    found = db.leaves.find({"student_id": str(g.current_user["_id"])}).sort("created_at", DESCENDING)
    return jsonify({"leaves": [public_leave(item) for item in found]})


@app.get("/api/dashboard/student")
@login_required("student")
def student_dashboard():
    uid = str(g.current_user["_id"])
    year_month = datetime.now().strftime("%Y")
    all_leaves = list(db.leaves.find({"student_id": uid}))
    return jsonify({
        "total_leaves": sum(1 for item in all_leaves if str(item.get("created_at", "")).startswith(year_month)),
        "pending": sum(1 for item in all_leaves if item.get("status") == "Pending" or item.get("extension_request", {}).get("status") == "Pending"),
        "approved": sum(1 for item in all_leaves if item.get("status") in {"Approved", "Outside", "Completed"}),
        "outside": sum(1 for item in all_leaves if item.get("status") == "Outside"),
    })


@app.get("/api/leaves/<leave_id>/qr")
@login_required("student", "warden", "guard")
def leave_qr(leave_id: str):
    leave = db.leaves.find_one({"leave_id": leave_id})
    if not leave:
        return jsonify({"error": "Leave pass not found."}), 404
    user = g.current_user
    if user.get("role") == "student" and leave.get("student_id") != str(user["_id"]):
        return jsonify({"error": "You cannot view another student's pass."}), 403
    if leave.get("status") not in {"Approved", "Outside", "Completed"}:
        return jsonify({"error": "A QR pass is available only after approval."}), 409
    return send_file(io.BytesIO(make_qr_png(leave_id)), mimetype="image/png", download_name=f"{leave_id}.png", max_age=0)


@app.get("/api/leaves/<leave_id>/proof")
@login_required("student", "warden")
def leave_proof(leave_id: str):
    leave = db.leaves.find_one({"leave_id": leave_id})
    if not leave:
        return jsonify({"error": "Leave application not found."}), 404
    user = g.current_user
    if user.get("role") == "student" and leave.get("student_id") != str(user["_id"]):
        return jsonify({"error": "You cannot view another student's document."}), 403
    storage_name = leave.get("proof_storage_name")
    if not storage_name or not (UPLOAD_DIR / storage_name).exists():
        return jsonify({"error": "No uploaded proof is available."}), 404
    return send_file(UPLOAD_DIR / storage_name, as_attachment=False, download_name=leave.get("proof_filename") or "proof")


@app.get("/api/warden/dashboard")
@login_required("warden")
def warden_dashboard():
    all_leaves = list(db.leaves.find({}, {"status": 1, "start_date": 1, "end_date": 1, "extension_request.status": 1}))
    today = date.today().isoformat()
    outside = sum(1 for item in all_leaves if item.get("status") == "Outside")
    return jsonify({
        "total_students": db.users.count_documents({"role": "student", "active": {"$ne": False}}),
        "pending": sum(1 for item in all_leaves if item.get("status") == "Pending" or item.get("extension_request", {}).get("status") == "Pending"),
        "approved": sum(1 for item in all_leaves if item.get("status") == "Approved"),
        "outside": outside,
        "completed": sum(1 for item in all_leaves if item.get("status") == "Completed"),
        "due_today": sum(1 for item in all_leaves if item.get("status") == "Outside" and item.get("end_date", "") <= today),
    })


@app.get("/api/warden/leaves")
@login_required("warden")
def warden_leaves():
    status = request.args.get("status", "all").strip()
    query = {}
    if status.lower() == "extension pending":
        query["extension_request.status"] = "Pending"
    elif status.lower() != "all":
        query["status"] = status.title()
        if status.title() == "Pending":
            query["extension_request.status"] = {"$ne": "Pending"}
    results = db.leaves.find(query).sort("created_at", DESCENDING).limit(500)
    output = []
    for item in results:
        public = public_leave(item)
        public["review_status"] = "Extension Pending" if item.get("extension_request", {}).get("status") == "Pending" else item.get("status")
        output.append(public)
    return jsonify({"leaves": output})


@app.post("/api/warden/leaves/<leave_id>/decision")
@login_required("warden")
def decide_leave(leave_id: str):
    data = get_json()
    decision = str(data.get("decision", "")).lower()
    rejection_reason = str(data.get("rejection_reason", "")).strip()
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "Decision must be approve or reject."}), 400
    leave = db.leaves.find_one({"leave_id": leave_id})
    if not leave:
        return jsonify({"error": "Leave application not found."}), 404
    extension_pending = leave.get("extension_request", {}).get("status") == "Pending"
    if not extension_pending and leave.get("status") != "Pending":
        return jsonify({"error": "Only pending applications or pending extensions can be reviewed."}), 409
    now = utc_now()
    if extension_pending:
        update = {
            "extension_request.status": "Approved" if decision == "approve" else "Rejected",
            "extension_request.decision_at": now,
            "extension_request.decision_by": str(g.current_user["_id"]),
        }
        if decision == "approve":
            update["end_date"] = leave["extension_request"].get("new_end_date", leave.get("end_date"))
        else:
            update["extension_request.rejection_reason"] = rejection_reason or "No reason provided."
        new_status = "Extension approved" if decision == "approve" else "Extension rejected"
    else:
        new_status = "Approved" if decision == "approve" else "Rejected"
        update = {"status": new_status, "decision_at": now, "decision_by": str(g.current_user["_id"])}
        if decision == "reject":
            update["rejection_reason"] = rejection_reason or "No reason provided."
    db.leaves.update_one({"_id": leave["_id"]}, {"$set": update})
    db.audit_logs.insert_one({"actor_id": str(g.current_user["_id"]), "actor_role": "warden", "action": f"leave_{decision}d", "leave_id": leave_id, "created_at": utc_now()})
    updated = db.leaves.find_one({"_id": leave["_id"]})
    return jsonify({"message": f"Leave {new_status.lower()}.", "leave": public_leave(updated)})


@app.get("/api/warden/students")
@login_required("warden")
def search_students():
    query_text = request.args.get("q", "").strip()
    query = {"role": "student"}
    if query_text:
        import re
        safe = re.escape(query_text)
        query["$or"] = [
            {"name": {"$regex": safe, "$options": "i"}},
            {"email": {"$regex": safe, "$options": "i"}},
            {"registration_no": {"$regex": safe, "$options": "i"}},
            {"room_no": {"$regex": safe, "$options": "i"}},
        ]
    results = db.users.find(query).sort("name", ASCENDING).limit(100)
    students = []
    for user in results:
        item = public_user(user)
        item["leave_count"] = db.leaves.count_documents({"student_id": str(user["_id"])})
        item["outside"] = db.leaves.count_documents({"student_id": str(user["_id"]), "status": "Outside"}) > 0
        students.append(item)
    return jsonify({"students": students})


@app.get("/api/warden/students/<student_id>/leaves")
@login_required("warden")
def student_leave_history(student_id: str):
    if not ObjectId.is_valid(student_id):
        return jsonify({"error": "Invalid student ID."}), 400
    user = db.users.find_one({"_id": ObjectId(student_id), "role": "student"})
    if not user:
        return jsonify({"error": "Student not found."}), 404
    leaves = db.leaves.find({"student_id": student_id}).sort("created_at", DESCENDING)
    return jsonify({"student": public_user(user), "leaves": [public_leave(item) for item in leaves]})


@app.get("/api/warden/reports/monthly.xlsx")
@login_required("warden")
def monthly_report():
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        return jsonify({"error": "Month must use YYYY-MM format."}), 400
    month_start = datetime.strptime(month, "%Y-%m")
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    leaves = list(db.leaves.find({"created_at": {"$gte": month_start, "$lt": next_month}}).sort("created_at", DESCENDING))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Leave Report"
    headers = ["Leave ID", "Student Name", "Registration No", "Branch", "Hostel", "Room", "Reason", "Start Date", "End Date", "Return Time", "Status", "Applied At", "Checked Out At", "Checked In At"]
    sheet.append(headers)
    for leave in leaves:
        sheet.append([
            leave.get("leave_id"), leave.get("student_name"), leave.get("registration_no"), leave.get("branch"),
            leave.get("hostel_name"), leave.get("room_no"), leave.get("reason"), leave.get("start_date"),
            leave.get("end_date"), leave.get("return_time"), leave.get("status"),
            mongo_to_json(leave.get("created_at")), mongo_to_json(leave.get("checked_out_at")), mongo_to_json(leave.get("checked_in_at")),
        ])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column_cells in sheet.columns:
        max_len = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 12), 32)
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"hostel-leave-report-{month}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/warden/students/import")
@login_required("warden")
def bulk_import_students():
    upload = request.files.get("file")
    temporary_password = request.form.get("temporary_password", "").strip()
    if not upload or not upload.filename or not upload.filename.lower().endswith(".csv"):
        return jsonify({"error": "Upload a CSV file."}), 400
    if len(temporary_password) < 8:
        return jsonify({"error": "Set a temporary password with at least 8 characters."}), 400
    try:
        text_file = io.TextIOWrapper(upload.stream, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_file)
        required = {"name", "email", "registration_no", "branch", "hostel_type", "hostel_name", "year", "room_no", "phone"}
        if not reader.fieldnames or not required.issubset({header.strip().lower() for header in reader.fieldnames}):
            return jsonify({"error": "CSV headers must include: " + ", ".join(sorted(required))}), 400
        # Normalize column header case and spaces for each row.
        added, skipped = 0, 0
        for row in reader:
            normalized = {str(k).strip().lower(): str(v or "").strip() for k, v in row.items() if k is not None}
            if not normalized.get("name") or not normalized.get("email") or not normalized.get("registration_no"):
                skipped += 1
                continue
            email = normalized["email"].lower()
            reg = normalized["registration_no"].upper()
            if db.users.find_one({"$or": [{"email": email}, {"registration_no": reg}]}):
                skipped += 1
                continue
            doc = {
                "name": normalized["name"], "email": email, "registration_no": reg,
                "branch": normalized["branch"], "hostel_type": normalized["hostel_type"],
                "hostel_name": normalized["hostel_name"], "year": normalized["year"],
                "room_no": normalized["room_no"], "phone": normalized["phone"],
                "password_hash": generate_password_hash(temporary_password), "role": "student",
                "active": True, "created_at": utc_now(), "imported_by": str(g.current_user["_id"]),
            }
            try:
                db.users.insert_one(doc)
                added += 1
            except DuplicateKeyError:
                skipped += 1
        db.audit_logs.insert_one({"actor_id": str(g.current_user["_id"]), "actor_role": "warden", "action": "bulk_student_import", "added": added, "skipped": skipped, "created_at": utc_now()})
        return jsonify({"message": "CSV import finished.", "added": added, "skipped": skipped})
    except UnicodeDecodeError:
        return jsonify({"error": "CSV must be saved as UTF-8."}), 400
    except Exception as exc:
        return jsonify({"error": f"Could not import CSV: {exc}"}), 400


@app.post("/api/leaves/<leave_id>/extension")
@login_required("student")
def request_extension(leave_id: str):
    data = get_json()
    new_end_date = str(data.get("new_end_date", "")).strip()
    reason = str(data.get("reason", "")).strip()
    try:
        datetime.strptime(new_end_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Enter a valid new return date."}), 400
    leave = db.leaves.find_one({"leave_id": leave_id, "student_id": str(g.current_user["_id"])})
    if not leave:
        return jsonify({"error": "Leave application not found."}), 404
    if leave.get("status") not in {"Approved", "Outside"} or new_end_date <= leave.get("end_date", ""):
        return jsonify({"error": "Extension must be requested for an approved leave with a later return date."}), 409
    db.leaves.update_one({"_id": leave["_id"]}, {"$set": {"extension_request": {"new_end_date": new_end_date, "reason": reason, "requested_at": utc_now(), "status": "Pending"}}})
    return jsonify({"message": "Extension request sent to the warden. Your current pass status remains unchanged until the warden reviews it."})


@app.post("/api/guard/validate")
@login_required("guard")
def guard_validate():
    data = get_json()
    leave_id = str(data.get("leave_id", "")).strip().upper()
    if not leave_id:
        return jsonify({"error": "Enter a Leave ID or scan a QR code."}), 400
    leave = db.leaves.find_one({"leave_id": leave_id})
    if not leave:
        return jsonify({"error": "Invalid pass: Leave ID was not found."}), 404
    today = date.today().isoformat()
    if leave.get("status") == "Approved":
        if today < leave.get("start_date", "") or today > leave.get("end_date", ""):
            return jsonify({"error": "Pass is outside its approved date range.", "leave": public_leave(leave)}), 409
        action = "Check-Out"
    elif leave.get("status") == "Outside":
        action = "Check-In"
    elif leave.get("status") == "Completed":
        return jsonify({"error": "This pass has already been completed.", "leave": public_leave(leave)}), 409
    else:
        return jsonify({"error": f"Pass is not valid. Current status: {leave.get('status', 'Unknown')}.", "leave": public_leave(leave)}), 409
    return jsonify({"message": f"Pass valid. Next action: {action}.", "action": action, "leave": public_leave(leave)})


@app.post("/api/guard/checkout")
@login_required("guard")
def guard_checkout():
    data = get_json()
    leave_id = str(data.get("leave_id", "")).strip().upper()
    leave = db.leaves.find_one({"leave_id": leave_id})
    if not leave:
        return jsonify({"error": "Leave pass not found."}), 404
    today = date.today().isoformat()
    if leave.get("status") != "Approved":
        return jsonify({"error": "Only an approved, not-yet-used pass can check out."}), 409
    if today < leave.get("start_date", "") or today > leave.get("end_date", ""):
        return jsonify({"error": "Pass is outside its approved date range."}), 409
    when = utc_now()
    transition = db.leaves.update_one({"_id": leave["_id"], "status": "Approved"}, {"$set": {"status": "Outside", "checked_out_at": when, "checkout_guard_id": str(g.current_user["_id"])}})
    if transition.modified_count != 1:
        return jsonify({"error": "This pass was already used or changed by another gate action. Validate it again."}), 409
    db.gate_logs.insert_one({"leave_id": leave_id, "student_id": leave["student_id"], "event": "check_out", "guard_id": str(g.current_user["_id"]), "created_at": when})
    db.audit_logs.insert_one({"actor_id": str(g.current_user["_id"]), "actor_role": "guard", "action": "student_checked_out", "leave_id": leave_id, "created_at": when})
    updated = db.leaves.find_one({"_id": leave["_id"]})
    return jsonify({"message": "Check-Out Successful.", "leave": public_leave(updated)})


@app.post("/api/guard/checkin")
@login_required("guard")
def guard_checkin():
    data = get_json()
    leave_id = str(data.get("leave_id", "")).strip().upper()
    leave = db.leaves.find_one({"leave_id": leave_id})
    if not leave:
        return jsonify({"error": "Leave pass not found."}), 404
    if leave.get("status") != "Outside":
        return jsonify({"error": "This student is not currently marked Outside for this pass."}), 409
    when = utc_now()
    transition = db.leaves.update_one({"_id": leave["_id"], "status": "Outside"}, {"$set": {"status": "Completed", "checked_in_at": when, "checkin_guard_id": str(g.current_user["_id"])}})
    if transition.modified_count != 1:
        return jsonify({"error": "This pass was already checked in or changed by another gate action. Validate it again."}), 409
    db.gate_logs.insert_one({"leave_id": leave_id, "student_id": leave["student_id"], "event": "check_in", "guard_id": str(g.current_user["_id"]), "created_at": when})
    db.audit_logs.insert_one({"actor_id": str(g.current_user["_id"]), "actor_role": "guard", "action": "student_checked_in", "leave_id": leave_id, "created_at": when})
    updated = db.leaves.find_one({"_id": leave["_id"]})
    return jsonify({"message": "Check-In Successful. Leave marked Completed.", "leave": public_leave(updated)})


@app.get("/api/guard/outside")
@login_required("guard", "warden")
def outside_students():
    found = db.leaves.find({"status": "Outside"}).sort("checked_out_at", DESCENDING).limit(300)
    return jsonify({"leaves": [public_leave(item) for item in found]})


@app.get("/api/guard/activity")
@login_required("guard", "warden")
def guard_activity():
    logs = list(db.gate_logs.find({}).sort("created_at", DESCENDING).limit(100))
    events = []
    for log in logs:
        leave = db.leaves.find_one({"leave_id": log.get("leave_id")}, {"student_name": 1, "registration_no": 1, "room_no": 1}) or {}
        events.append({
            "leave_id": log.get("leave_id"), "event": log.get("event"),
            "student_name": leave.get("student_name", "Unknown student"),
            "registration_no": leave.get("registration_no", ""),
            "room_no": leave.get("room_no", ""),
            "created_at": mongo_to_json(log.get("created_at")),
        })
    return jsonify({"events": events})


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "The upload is too large. Maximum request size is 6 MB."}), 413


if __name__ == "__main__":
    print("Hostel Leave Pass System starting...")
    print(f"MongoDB database: {DB_NAME}")
    print("Open http://127.0.0.1:5000 in your browser.")
    try:
        init_database()
        print(f"Connected to MongoDB database '{DB_NAME}'.")
        print("Demo warden: warden@hostel.local / Warden@123")
        print("Demo guard:  guard@hostel.local / Guard@123")
    except Exception as exc:
        print("MongoDB is not available yet. The app will remain running; start MongoDB Community Server and refresh.")
        print(f"Connection details: {exc}")
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
