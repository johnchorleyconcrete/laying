import os, sys, ssl, smtplib, argparse
from datetime import date, timedelta, datetime
from email.message import EmailMessage

sys.path.insert(0, "/home/SalesChorleyConcrete/laying")

from models import conn
from recipients import OFFICE
import quotepdf

FOLLOWUP_DAYS = 2

for _env in ("/home/SalesChorleyConcrete/laying/.env",
             "/home/SalesChorleyConcrete/GenieAgg/.env"):
    if os.path.exists(_env):
        for _l in open(_env):
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD")


def send_office_email(subject, html):
    to = [e for e, _ in OFFICE]
    m = EmailMessage()
    m["From"] = GMAIL_USER
    m["To"] = ", ".join(to)
    m["Subject"] = subject
    m.set_content("This needs an HTML mail client.")
    m.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(m)


def run(dry):
    # Only quotes actually emailed through the system (sent_at is set by
    # the "Email quote to customer" button) get chased, and only once -
    # followup_sent_at stops it firing again on the next run. A quote
    # that's since been accepted or declined is excluded by the
    # status='sent' check.
    cutoff = (date.today() - timedelta(days=FOLLOWUP_DAYS)).isoformat()
    failures = []
    with conn() as c:
        due = c.execute("""SELECT * FROM quotes WHERE status='sent'
                           AND sent_at IS NOT NULL AND followup_sent_at IS NULL
                           AND date(sent_at) <= date(?)""", (cutoff,)).fetchall()
        sent = 0
        for q in due:
            email = (q["contact_email"] or "").strip()
            if not email:
                continue
            if dry:
                print("[dry] FOLLOWUP", email, "| quote", q["quote_no"])
                continue
            try:
                quotepdf.send_quote_followup_email(q)
                c.execute("UPDATE quotes SET followup_sent_at=? WHERE id=?",
                          (datetime.now().isoformat(timespec="seconds"), q["id"]))
                sent += 1
            except Exception as e:
                print("FOLLOWUP FAILED", email, q["quote_no"], "-", e)
                failures.append("Follow-up to %s for quote %s failed: %s"
                                % (email, q["quote_no"], e))
    print("Done -", len(due), "quote(s) due,", sent if not dry else 0, "sent")
    if failures and not dry:
        try:
            send_office_email(
                "Laying - some quote follow-ups FAILED",
                "<p>These did not go out - send them by hand:</p><ul>" +
                "".join("<li>%s</li>" % f for f in failures) + "</ul>")
        except Exception as e:
            print("could not send the failure summary email:", e)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    run(a.dry_run)
