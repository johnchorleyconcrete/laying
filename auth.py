import os, secrets, hashlib
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from flask import session, redirect, url_for, request, flash
from models import conn
import mailer

SITE = "https://laying-saleschorleyconcrete.pythonanywhere.com"

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000)
    return h.hex(), salt

def check_pw(pw, pw_hash, salt):
    if not pw_hash or not salt:
        return False
    h, _ = hash_pw(pw, salt)
    return secrets.compare_digest(h, pw_hash)

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return w

def role_required(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = current_user()
            if not u:
                return redirect(url_for("login", next=request.path))
            if u["role"] not in roles:
                flash("You do not have access to that")
                return redirect(url_for("calendar"))
            return f(*a, **k)
        return w
    return deco

def send_setup_email(email, name, token, reset=False):
    link = "%s/setup/%s" % (SITE, token)
    what = "reset your password" if reset else "set your password"
    body = ("""<div style="font-family:Arial,sans-serif;font-size:14px">
<p>Hello %s,</p>
<p>Use the link below to %s for the Chorley Concrete laying system.</p>
<p><a href="%s" style="background:#1a1a1a;color:#fff;padding:10px 16px;
border-radius:4px;text-decoration:none;display:inline-block">Set my password</a></p>
<p style="color:#666;font-size:12px">Or paste this into your browser:<br>%s</p>
<p style="color:#666;font-size:12px">This link works once and expires in 7 days.
If you were not expecting this, ignore it and tell the office.</p>
</div>""" % (name, what, link, link))
    m = EmailMessage()
    m["To"] = email
    m["Subject"] = "Chorley Concrete laying system - %s" % what
    m.set_content("Open this link to %s: %s" % (what, link))
    m.add_alternative(body, subtype="html")
    mailer.send(m)
    return link

def new_token(user_id):
    tok = secrets.token_urlsafe(32)
    with conn() as c:
        c.execute("UPDATE users SET setup_token=?, token_expires=? WHERE id=?",
                  (tok, (datetime.now() + timedelta(days=7)).isoformat(timespec="seconds"),
                   user_id))
    return tok


# --- login lockout -----------------------------------------------------
# Internet-facing login with no rate limiting at all was a straightforward
# brute-force target. This is a simple per-email counter, not per-IP (no
# infra for that here) - a nuisance-level actor could lock out a known
# email on purpose, but a 15-minute lockout the office can see and clear
# is a fair trade for shutting down unattended password guessing.
MAX_FAILS = 8
LOCK_MINUTES = 15

def login_locked_until(email):
    if not email:
        return None
    with conn() as c:
        row = c.execute("SELECT locked_until FROM login_attempts WHERE email=?",
                        (email,)).fetchone()
    if row and row["locked_until"] and row["locked_until"] > datetime.now().isoformat(timespec="seconds"):
        return row["locked_until"]
    return None

def record_failed_login(email):
    if not email:
        return
    with conn() as c:
        row = c.execute("SELECT fail_count FROM login_attempts WHERE email=?", (email,)).fetchone()
        count = (row["fail_count"] if row else 0) + 1
        locked_until = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds") \
            if count >= MAX_FAILS else None
        c.execute("""INSERT INTO login_attempts (email, fail_count, locked_until) VALUES (?,?,?)
                     ON CONFLICT(email) DO UPDATE SET fail_count=excluded.fail_count,
                     locked_until=excluded.locked_until""", (email, count, locked_until))

def clear_failed_login(email):
    if not email:
        return
    with conn() as c:
        c.execute("DELETE FROM login_attempts WHERE email=?", (email,))


# --- CSRF ----------------------------------------------------------------
# No CSRF protection existed at all. This is a minimal same-session token
# check rather than pulling in Flask-WTF: csrf_token() mints/reuses one
# per session (call it from templates), csrf_ok() checks a submitted POST
# against it (call it from app.py's before_request).
def csrf_token():
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(24)
        session["_csrf"] = tok
    return tok

def csrf_ok():
    tok = session.get("_csrf")
    submitted = request.form.get("csrf_token", "")
    return bool(tok) and secrets.compare_digest(tok, submitted)
