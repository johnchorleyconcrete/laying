import os, ssl, smtplib, secrets, hashlib
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from flask import session, redirect, url_for, request, flash
from models import conn

SITE = "https://laying-saleschorleyconcrete.pythonanywhere.com"

_env = "/home/SalesChorleyConcrete/GenieAgg/.env"
if os.path.exists(_env):
    for _l in open(_env):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

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
    m["From"] = os.environ.get("GMAIL_USER")
    m["To"] = email
    m["Subject"] = "Chorley Concrete laying system - %s" % what
    m.set_content("Open this link to %s: %s" % (what, link))
    m.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD"))
        s.send_message(m)
    return link

def new_token(user_id):
    tok = secrets.token_urlsafe(32)
    with conn() as c:
        c.execute("UPDATE users SET setup_token=?, token_expires=? WHERE id=?",
                  (tok, (datetime.now() + timedelta(days=7)).isoformat(timespec="seconds"),
                   user_id))
    return tok
