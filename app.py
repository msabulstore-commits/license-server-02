from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
import hmac
import hashlib
import base64
import secrets
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))

# ============================================================
# CONFIGURATION - Change these!
# ============================================================
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # Change this!
LICENSE_SECRET = os.environ.get("LICENSE_SECRET", "ChangeThisToAVeryLongRandomSecretKey-AtLeast32Characters!").encode()
MAX_ACTIVATIONS_PER_KEY = 1   # How many computers one key can activate
DATABASE = "licenses.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            product_id TEXT NOT NULL,
            customer_note TEXT,
            max_activations INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            expires_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            activated_at TEXT NOT NULL,
            last_check TEXT,
            UNIQUE(license_key, machine_id)
        )
    """)
    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def generate_key_string(product_id: str, days_valid: int = 365) -> str:
    """Generate a random-looking signed key."""
    random_part = secrets.token_hex(8).upper()
    expiry = ""
    if days_valid > 0:
        expiry = (datetime.utcnow() + timedelta(days=days_valid)).strftime("%Y%m%d")

    data = f"{product_id}|{random_part}|{expiry}".encode()
    signature = hmac.new(LICENSE_SECRET, data, hashlib.sha256).digest()
    sig_part = base64.b32encode(signature[:10]).decode().rstrip("=")[:12]

    key = f"{product_id}-{sig_part[:4]}-{sig_part[4:8]}-{sig_part[8:12]}-{random_part}"
    if expiry:
        key += f"-{expiry}"
    return key


# ===================== ADMIN PAGES =====================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin"))
        error = "Wrong password"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def admin():
    conn = get_db()
    licenses = conn.execute("""
        SELECT l.*, 
               (SELECT COUNT(*) FROM activations a WHERE a.license_key = l.license_key) as used
        FROM licenses l
        ORDER BY l.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("admin.html", licenses=licenses)


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    product_id = request.form.get("product_id", "MyApp").strip()
    customer_note = request.form.get("customer_note", "").strip()
    days = int(request.form.get("days_valid", 365) or 365)
    max_act = int(request.form.get("max_activations", 1) or 1)

    key = generate_key_string(product_id, days)
    expires_at = None
    if days > 0:
        expires_at = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")

    conn = get_db()
    conn.execute(
        "INSERT INTO licenses (license_key, product_id, customer_note, max_activations, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (key, product_id, customer_note, max_act, datetime.utcnow().isoformat(), expires_at)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/toggle/<int:lic_id>")
@login_required
def toggle(lic_id):
    conn = get_db()
    row = conn.execute("SELECT is_active FROM licenses WHERE id = ?", (lic_id,)).fetchone()
    if row:
        new_val = 0 if row["is_active"] else 1
        conn.execute("UPDATE licenses SET is_active = ? WHERE id = ?", (new_val, lic_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/delete/<int:lic_id>")
@login_required
def delete(lic_id):
    conn = get_db()
    key_row = conn.execute("SELECT license_key FROM licenses WHERE id = ?", (lic_id,)).fetchone()
    if key_row:
        key = key_row["license_key"]
        conn.execute("DELETE FROM activations WHERE license_key = ?", (key,))
        conn.execute("DELETE FROM licenses WHERE id = ?", (lic_id,))
        conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/activations/<license_key>")
@login_required
def view_activations(license_key):
    conn = get_db()
    acts = conn.execute(
        "SELECT * FROM activations WHERE license_key = ? ORDER BY activated_at DESC",
        (license_key,)
    ).fetchall()
    conn.close()
    return render_template("activations.html", license_key=license_key, activations=acts)


# ===================== PUBLIC API (for your apps) =====================

@app.route("/api/activate", methods=["POST"])
def api_activate():
    """
    Called by your software to activate a license on a machine.
    Body JSON: { "license_key": "...", "machine_id": "...", "product_id": "..." }
    """
    data = request.get_json() or {}
    license_key = (data.get("license_key") or "").strip()
    machine_id = (data.get("machine_id") or "").strip()
    product_id = (data.get("product_id") or "").strip()

    if not license_key or not machine_id:
        return jsonify({"ok": False, "message": "license_key and machine_id required"}), 400

    conn = get_db()
    lic = conn.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not lic:
        conn.close()
        return jsonify({"ok": False, "message": "Invalid license key"}), 403

    if not lic["is_active"]:
        conn.close()
        return jsonify({"ok": False, "message": "License has been disabled"}), 403

    if lic["expires_at"]:
        if datetime.utcnow().date() > datetime.strptime(lic["expires_at"], "%Y-%m-%d").date():
            conn.close()
            return jsonify({"ok": False, "message": "License has expired"}), 403

    if product_id and lic["product_id"] != product_id:
        conn.close()
        return jsonify({"ok": False, "message": "Product ID mismatch"}), 403

    # Check existing activations
    existing = conn.execute(
        "SELECT * FROM activations WHERE license_key = ? AND machine_id = ?",
        (license_key, machine_id)
    ).fetchone()

    if existing:
        # Already activated on this machine → refresh last_check
        conn.execute(
            "UPDATE activations SET last_check = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), existing["id"])
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "Already activated on this machine", "status": "active"})

    # Count current activations
    count = conn.execute(
        "SELECT COUNT(*) as c FROM activations WHERE license_key = ?", (license_key,)
    ).fetchone()["c"]

    if count >= lic["max_activations"]:
        conn.close()
        return jsonify({
            "ok": False,
            "message": f"This key is already activated on the maximum number of computers ({lic['max_activations']})"
        }), 403

    # New activation
    conn.execute(
        "INSERT INTO activations (license_key, machine_id, activated_at, last_check) VALUES (?, ?, ?, ?)",
        (license_key, machine_id, datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "message": "License activated successfully", "status": "active"})


@app.route("/api/check", methods=["POST"])
def api_check():
    """
    Quick check (can be called periodically).
    Body JSON: { "license_key": "...", "machine_id": "..." }
    """
    data = request.get_json() or {}
    license_key = (data.get("license_key") or "").strip()
    machine_id = (data.get("machine_id") or "").strip()

    if not license_key or not machine_id:
        return jsonify({"ok": False, "message": "Missing data"}), 400

    conn = get_db()
    lic = conn.execute("SELECT * FROM licenses WHERE license_key = ?", (license_key,)).fetchone()

    if not lic or not lic["is_active"]:
        conn.close()
        return jsonify({"ok": False, "message": "License invalid or disabled"}), 403

    if lic["expires_at"]:
        if datetime.utcnow().date() > datetime.strptime(lic["expires_at"], "%Y-%m-%d").date():
            conn.close()
            return jsonify({"ok": False, "message": "License expired"}), 403

    act = conn.execute(
        "SELECT * FROM activations WHERE license_key = ? AND machine_id = ?",
        (license_key, machine_id)
    ).fetchone()

    if not act:
        conn.close()
        return jsonify({"ok": False, "message": "Not activated on this machine"}), 403

    # Update last check time
    conn.execute(
        "UPDATE activations SET last_check = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), act["id"])
    )
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "message": "License is valid", "status": "active"})


# ===================== START =====================

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  Online License Server")
    print(f"  Admin panel: http://127.0.0.1:{port}")
    print(f"  Default password: {ADMIN_PASSWORD}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=False)
else:
    # When running on Render / production
    init_db()
