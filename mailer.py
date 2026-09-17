"""Single place for outgoing email config and sending. Used to be five
separate copies of the same .env-loading loop and SMTP login/send block
spread across auth.py, notify.py, weekview.py, backup.py and quotepdf.py -
now there's one place to change if the mail provider or credentials ever
change again.

Provider-agnostic on purpose: works with any SMTP login (a real mailbox
like the Microsoft 365 setup this started with, or a transactional relay
like SMTP2GO/SendGrid/Mailgun where the SMTP login is a separate API
account, not a real mailbox) - see MAIL_FROM below.
"""
import os, ssl, smtplib

for _env in ("/home/SalesChorleyConcrete/laying/.env",
             "/home/SalesChorleyConcrete/GenieAgg/.env"):
    if os.path.exists(_env):
        for _l in open(_env):
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
# The address recipients see as the sender. Not necessarily the same as
# MAIL_USER - a transactional relay's SMTP login is usually a separate
# API key/account name, authorized (via the relay's own SPF/DKIM setup)
# to send as a real address without being that address. Falls back to
# MAIL_USER for a provider (like a real mailbox) where they're the same.
MAIL_FROM = os.environ.get("MAIL_FROM") or MAIL_USER
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))


def send(m):
    """Sends an already-built email.message.EmailMessage. Fills in From
    with MAIL_FROM if the caller hasn't set one."""
    if not m.get("From"):
        m["From"] = MAIL_FROM
    if SMTP_PORT == 465:
        # Implicit SSL, as opposed to STARTTLS on a plaintext connection -
        # some relays offer this as an alternative port.
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as s:
            s.login(MAIL_USER, MAIL_PASSWORD)
            s.send_message(m)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(MAIL_USER, MAIL_PASSWORD)
            s.send_message(m)
