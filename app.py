import os
import re
import io
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ✅ Cargar variables de entorno ANTES de leerlas
load_dotenv()

from backend.qa_engine import answer_question, list_sections, ensure_index

# --- Optional STT (Whisper) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        openai_client = None

# --- PDF export ---
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")

DATA_DIR = Path("data"); DATA_DIR.mkdir(exist_ok=True)
UPLOAD_FOLDER = Path("uploads"); UPLOAD_FOLDER.mkdir(exist_ok=True)
CONVO_FOLDER = Path("conversations"); CONVO_FOLDER.mkdir(exist_ok=True)
HISTORY_DIR = Path("logs/conversations"); HISTORY_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"

SLUG_TO_VERSION = {
    "RelativityOne": "RelativityOne",
    "Server2024": "Server2024",
    "Server2023": "Server2023",
}
VERSION_TITLES = {
    "RelativityOne": "Relativity One",
    "Server2024": "Server 2024",
    "Server2023": "Server 2023",
}
DOC_SOURCE = {
    "RelativityOne": "Relativity One documentation",
    "Server2024": "Server 2024 documentation",
    "Server2023": "Server 2023 documentation",
}

DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "demo@example.com")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "demo123")

def _load_users():
    if not USERS_FILE.exists():
        USERS_FILE.write_text(json.dumps({}, indent=2), encoding="utf-8")
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

def _ensure_default_admin():
    users = _load_users()
    if DEFAULT_ADMIN_EMAIL not in users:
        users[DEFAULT_ADMIN_EMAIL] = {
            "display_name": DEFAULT_ADMIN_EMAIL.split("@")[0],
            "password_hash": generate_password_hash(DEFAULT_ADMIN_PASSWORD)
        }
        _save_users(users)

_ensure_default_admin()

# -------- Warmup --------
_warmed_up = False
def _do_warmup():
    global _warmed_up
    if _warmed_up: return
    try:
        ensure_index("Server2023", force=True)      # reindex con tus links
        ensure_index("RelativityOne", force=False)
        ensure_index("Server2024", force=False)
    except Exception as e:
        print("Warmup failed:", e)
    finally:
        _warmed_up = True

@app.before_request
def _warmup_once_middleware():
    if not _warmed_up:
        _do_warmup()

with app.app_context():
    try:
        _do_warmup()
    except Exception as e:
        print("Startup warmup failed:", e)

# ----------------- helpers -----------------
def is_logged_in():
    return bool(session.get("user"))

def _now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _safe(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", s)

def _history_path(email: str, version_key: str) -> Path:
    return HISTORY_DIR / f"{_safe(email)}_{_safe(version_key)}.jsonl"

def _history_append(email: str, version_key: str, role: str, content: str, citations=None, confidence=None):
    try:
        p = _history_path(email, version_key)
        rec = {"ts": _now_iso(), "version": version_key, "role": role, "content": content}
        if citations is not None: rec["citations"] = citations
        if confidence is not None: rec["confidence"] = confidence
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ----------------- routes: auth -----------------
@app.get("/login")
def login():
    if is_logged_in():
        return redirect(url_for("version_page", slug="RelativityOne"))
    return render_template("login.html")

@app.post("/login")
def do_login():
    email = (request.form.get("email") or "").strip().lower()
    password = (request.form.get("password") or "").strip()
    users = _load_users()
    u = users.get(email)
    if not u or not check_password_hash(u.get("password_hash",""), password):
        return render_template("login.html", error="Invalid email or password.")
    session["user"] = {"email": email, "display_name": u.get("display_name") or email.split("@")[0]}
    return redirect(url_for("version_page", slug="RelativityOne"))

@app.get("/register")
def register():
    if is_logged_in():
        return redirect(url_for("version_page", slug="RelativityOne"))
    return render_template("register.html")

@app.post("/register")
def do_register():
    email = (request.form.get("email") or "").strip().lower()
    display = (request.form.get("display_name") or "").strip()
    password = (request.form.get("password") or "").strip()
    confirm = (request.form.get("confirm") or "").strip()

    if not email or "@" not in email:
        return render_template("register.html", error="Please enter a valid email.", email=email, display_name=display)
    if not display:
        display = email.split("@")[0]
    if not password or len(password) < 6:
        return render_template("register.html", error="Password must be at least 6 characters.", email=email, display_name=display)
    if password != confirm:
        return render_template("register.html", error="Passwords do not match.", email=email, display_name=display)

    users = _load_users()
    if email in users:
        return render_template("register.html", error="This email is already registered.", email=email, display_name=display)

    users[email] = {"display_name": display, "password_hash": generate_password_hash(password)}
    _save_users(users)

    session["user"] = {"email": email, "display_name": display}
    return redirect(url_for("version_page", slug="RelativityOne"))

@app.get("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# ----------------- routes: app -----------------
@app.get("/")
def root():
    if not is_logged_in():
        return redirect(url_for("login"))
    return redirect(url_for("version_page", slug="RelativityOne"))

@app.get("/v/<slug>")
def version_page(slug: str):
    if not is_logged_in():
        return redirect(url_for("login"))
    if slug not in SLUG_TO_VERSION:
        return redirect(url_for("version_page", slug="RelativityOne"))
    engine_version = SLUG_TO_VERSION[slug]
    return render_template(
        "chat.html",
        user=session["user"],
        version_slug=slug,
        version_title={"RelativityOne":"Relativity One","Server2024":"Server 2024","Server2023":"Server 2023"}[slug],
        engine_version=engine_version,
        docs_source={"RelativityOne":"Relativity One documentation","Server2024":"Server 2024 documentation","Server2023":"Server 2023 documentation"}[slug],
    )

@app.post("/api/ask")
def api_ask():
    if not is_logged_in():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(force=True)
    msg = data.get("message","").strip()
    version_key = data.get("version","RelativityOne").strip()
    if not msg:
        return jsonify({"error":"empty message"}), 400

    _history_append(session["user"]["email"], version_key, "user", msg)
    result = answer_question(msg, version=version_key, top_k=5)
    _history_append(session["user"]["email"], version_key, "assistant", result["answer"],
                    citations=result.get("citations"), confidence=result.get("confidence"))

    return jsonify({
        "answer": result["answer"],
        "citations": result["citations"],
        "confidence": result["confidence"],
        "should_collect_contact": result.get("should_collect_contact", False)
    })

@app.get("/api/sections")
def api_sections():
    version_key = request.args.get("version","RelativityOne")
    try:
        sections = list_sections(version_key)
    except Exception:
        sections = []
    return jsonify({"sections": sections})

@app.get("/api/history")
def api_history():
    if not is_logged_in():
        return jsonify({"error":"unauthorized"}), 401
    version_key = request.args.get("version","RelativityOne").strip()
    p = _history_path(session["user"]["email"], version_key)
    items = []
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                try: items.append(json.loads(line))
                except: pass
    return jsonify({"items": items})

@app.post("/api/clear_history")
def api_clear_history():
    if not is_logged_in():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(force=True)
    version_key = (data.get("version") or "RelativityOne").strip()
    p = _history_path(session["user"]["email"], version_key)
    if p.exists():
        p.unlink()
    return jsonify({"ok": True})

@app.post("/api/delete_account")
def api_delete_account():
    if not is_logged_in():
        return jsonify({"error":"unauthorized"}), 401
    email = session["user"]["email"]
    users = _load_users()
    if email in users:
        del users[email]
        _save_users(users)
    for f in HISTORY_DIR.glob(f"{_safe(email)}_*.jsonl"):
        try: f.unlink()
        except: pass
    session.pop("user", None)
    return jsonify({"ok": True})

@app.post("/api/save_conversation")
def api_save_conversation():
    if not is_logged_in():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(force=True)
    convo = data.get("conversation", [])
    version_key = data.get("version", "RelativityOne")
    ts = data.get("timestamp") or "conversation"
    filename = CONVO_FOLDER / f"{_safe(session['user']['email'])}_{_safe(version_key)}_{_safe(ts)}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(convo, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "path": str(filename)})

# -------- PDF export --------
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit

@app.post("/api/save_conversation_pdf")
def api_save_conversation_pdf():
    if not is_logged_in():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(force=True)
    convo = data.get("conversation", [])
    version_key = data.get("version", "RelativityOne")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER

    margin = 0.75 * inch
    x = margin
    y = height - margin
    line_h = 14
    max_w = width - 2*margin

    def draw_wrapped(text, font="Helvetica", size=11):
        nonlocal y
        c.setFont(font, size)
        for line in simpleSplit(text, font, size, max_w):
            if y < margin + line_h:
                c.showPage()
                y = height - margin
                c.setFont(font, size)
            c.drawString(x, y, line)
            y -= line_h

    c.setTitle(f"Conversation - {version_key}")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, f"Chatbot — {version_key}")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Exported: {datetime.utcnow().isoformat(timespec='seconds')}Z")
    y -= 18
    c.line(margin, y, width - margin, y); y -= 10

    for turn in convo:
        role = "User" if turn.get("role") == "user" else "Bot"
        content = re.sub(r"<[^>]+>", "", turn.get("content",""))
        c.setFont("Helvetica-Bold", 11); draw_wrapped(f"{role}:")
        c.setFont("Helvetica", 11); draw_wrapped(content)
        cites = turn.get("citations") or []
        for ci in cites:
            url = ci.get("url","")
            if url: draw_wrapped(f"Source: {url}", size=9)
        y -= 6

    c.showPage(); c.save()
    buf.seek(0)
    filename = f"conversation_{_safe(version_key)}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)

@app.post("/api/upload_avatar")
def api_upload_avatar():
    if not is_logged_in():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if "avatar" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded."}), 400
    f = request.files["avatar"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Invalid file."}), 400
    filename = secure_filename(f.filename)
    out = Path("uploads") / f"{_safe(session['user']['email'])}_{int(time.time())}_{filename}"
    f.save(out)
    return jsonify({"ok": True, "url": url_for("get_upload", name=out.name)})

@app.get("/uploads/<path:name>")
def get_upload(name):
    p = Path("uploads") / name
    if not p.exists():
        return "Not found", 404
    return send_file(p, as_attachment=False)

# -------- STT (server) --------
@app.post("/api/stt")
def api_stt():
    if not is_logged_in():
        return jsonify({"error":"unauthorized"}), 401
    if openai_client is None:
        return jsonify({"ok": False, "error": "Speech-to-text requires OPENAI_API_KEY configured on the server."}), 400
    if "audio" not in request.files:
        return jsonify({"ok": False, "error": "No audio uploaded."}), 400
    f = request.files["audio"]
    suffix = ".webm"
    if f.mimetype and "ogg" in f.mimetype: suffix = ".ogg"
    elif f.mimetype and "wav" in f.mimetype: suffix = ".wav"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as af:
            resp = openai_client.audio.transcriptions.create(model="whisper-1", file=af)
        text = (getattr(resp, "text", None) or "").strip()
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": f"STT failed: {e}"}), 400

# --- Redirect any 404 to root (evita pantallas Not Found) ---
@app.errorhandler(404)
def not_found(_e):
    return redirect(url_for("root"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055, debug=True)
