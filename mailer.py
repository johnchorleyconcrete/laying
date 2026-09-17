"""Single place for outgoing email config and sending. Used to be five
separate copies of the same .env-loading loop and SMTP login/send block
spread across auth.py, notify.py, weekview.py, backup.py and quotepdf.py -
now there's one place to change if the mail provider or credentials ever
change again.

Sends via Microsoft 365 (smtp.office365.com) using an app password on
john@chorleyconcrete.co.uk, so outgoing mail is genuinely from that
mailbox rather than an alias/workaround.
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
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))


def send(m):
    """Sends an already-built email.message.EmailMessage. Fills in From
    with the mailbox being sent from if the caller hasn't set one."""
    if not m.get("From"):
        m["From"] = MAIL_USER
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(MAIL_USER, MAIL_PASSWORD)
        s.send_message(m)
