import os, sys, argparse, re
from datetime import date, timedelta, datetime
from email.message import EmailMessage

sys.path.insert(0, "/home/SalesChorleyConcrete/laying")
sys.path.insert(0, "/home/SalesChorleyConcrete/GenieAgg")

from models import conn
from recipients import OFFICE
import mailer

CHECKS = [
    "Falls agreed and signed by the customer BEFORE pouring",
    "Fibres confirmed to the driver BEFORE he starts batching",
    "Washout: nothing down a drain, gully, manhole or watercourse",
    "Hired kit: record the date finished with for off hire",
    "Extras and variations agreed with the office and signed first",
]

def ascii_only(s):
    if not s:
        return ""
    s = str(s)
    for a, b in (("—","-"),("–","-"),("‘","'"),("’","'"),
                 ("“",'"'),("”",'"'),("²","2"),("³","3"),
                 ("£","GBP ")):
        s = s.replace(a, b)
    return re.sub(r"[^\x20-\x7e\n]", "", s)

def send_email(to, subject, html):
    to = [t for t in to if t]
    if not to:
        return
    m = EmailMessage()
    m["To"] = ", ".join(to)
    m["Subject"] = subject
    m.set_content("This job sheet needs an HTML mail client.")
    m.add_alternative(html, subtype="html")
    mailer.send(m)

GENIE_API_KEY = os.environ.get("GENIE_API_KEY")

def send_sms(contact_id, body):
    import requests
    if not contact_id:
        print("  no genie id, skipping sms")
        return False
    r = requests.post("https://services.leadconnectorhq.com/conversations/messages",
        headers={"Authorization": "Bearer " + GENIE_API_KEY,
                 "Version": "2021-07-28", "Content-Type": "application/json"},
        json={"type": "SMS", "contactId": contact_id, "message": body}, timeout=20)
    r.raise_for_status()
    return True

def sheet_html(j, label):
    def row(k, v):
        return "<tr><td style='padding:3px 12px 3px 0'><b>%s</b></td><td>%s</td></tr>" % (k, v)
    h = ["<div style='font-family:Arial,sans-serif;font-size:14px'>"]
    h.append("<h2 style='margin:0'>JOB SHEET %s</h2>" % j["job_no"])
    h.append("<div style='color:#555;margin:2px 0 12px'>%s &nbsp; %s</div>" % (label, j["slot"]))
    h.append("<table cellspacing='0' cellpadding='0'>")
    h.append(row("Customer", j["customer"] or ""))
    h.append(row("Site", (j["site_address"] or "") + " " + (j["postcode"] or "")))
    if j["contact_phone"]:
        h.append(row("Contact", j["contact_phone"]))
    h.append(row("On the job", (j["crew"] or "").replace(",", ", ")))
    h.append("</table>")
    if j["work_desc"]:
        h.append("<h3>Work</h3><div style='white-space:pre-wrap'>%s</div>" % j["work_desc"])
    if j["notes"]:
        h.append("<h3>Notes</h3><div style='white-space:pre-wrap'>%s</div>" % j["notes"])
    h.append("<h3>Before you pour</h3><ul>")
    for c in CHECKS:
        h.append("<li>%s</li>" % c)
    h.append("</ul><div style='margin-top:16px;color:#555'>Times, materials used, "
             "notes and signatures on site. Sheet back to the office the same week.</div></div>")
    return "".join(h)

def sms_line(j, label):
    head = "CHORLEY LAYING %s%s. %s %s, %s" % (
        label, "" if j["slot"] == "ALL" else " " + j["slot"],
        j["job_no"], j["customer"] or "", j["postcode"] or "")
    desc = ascii_only(j["work_desc"] or "").replace("\n", " ")
    room = 158 - len(head)
    if room > 25 and desc:
        head += ". " + desc[:room].rstrip(" ,.")
    return ascii_only(head)

def already(c, jid, jdate, chan, target):
    return c.execute("""SELECT 1 FROM notify_log WHERE job_id=? AND job_date=?
                        AND channel=? AND target=?""",
                     (jid, jdate, chan, target)).fetchone() is not None

def mark(c, jid, jdate, chan, target):
    c.execute("""INSERT OR IGNORE INTO notify_log
                 (job_id,job_date,channel,target,sent_at) VALUES (?,?,?,?,?)""",
              (jid, jdate, chan, target, datetime.now().isoformat(timespec="seconds")))

def run(dry, day):
    d = date.fromisoformat(day) if day else date.today() + timedelta(days=1)
    jdate = d.isoformat()
    label = d.strftime("%a %d %b")
    # A single failed send (bad contact id, a timeout, the SMS API being
    # down) used to raise straight out of this loop and abort the whole
    # run - everyone after that point in the job list got no notification
    # at all, with nothing telling the office it happened. Now one bad
    # send is logged and skipped so everyone else still gets theirs; the
    # notify_log dedup means a re-run after fixing the cause will only
    # (and safely) retry what actually failed.
    failures = []
    with conn() as c:
        jobs = c.execute("""SELECT * FROM jobs WHERE job_date=? AND status='booked'
                            ORDER BY slot""", (jdate,)).fetchall()
        crew = {r["code"]: r for r in c.execute("SELECT * FROM crew WHERE active=1")}

        if not jobs:
            print("Nothing booked for", jdate)
            if not dry:
                try:
                    send_email([e for e, _ in OFFICE], "Laying - NOTHING BOOKED for " + label,
                               "<p>No jobs on the board for %s. If that is wrong, "
                               "the diary has not been filled in.</p>" % label)
                except Exception as e:
                    print("could not send the nothing-booked warning:", e)
            return

        for j in jobs:
            html = sheet_html(j, label)
            sms = sms_line(j, label)
            subj = "Job sheet %s - %s - %s %s" % (j["job_no"], j["customer"], label, j["slot"])
            targets = []
            for code in [x for x in (j["crew"] or "").split(",") if x]:
                m = crew.get(code)
                if not m:
                    print("WARN unknown crew code", code, "on job", j["id"])
                    continue
                targets.append((m["email"], m["genie_id"]))
            for e, ph in OFFICE:
                targets.append((e, ph))

            for email, cid in targets:
                if email and not already(c, j["id"], jdate, "email", email):
                    if dry:
                        print("[dry] EMAIL", email, "|", subj)
                    else:
                        try:
                            send_email([email], subj, html)
                            mark(c, j["id"], jdate, "email", email)
                        except Exception as e:
                            print("EMAIL FAILED", email, j["job_no"], "-", e)
                            failures.append("Email to %s for job %s failed: %s"
                                            % (email, j["job_no"], e))
                if cid and not already(c, j["id"], jdate, "sms", cid):
                    if dry:
                        print("[dry] SMS", cid, "|", len(sms), "chars |", sms)
                    else:
                        try:
                            send_sms(cid, sms)
                            mark(c, j["id"], jdate, "sms", cid)
                        except Exception as e:
                            print("SMS FAILED", cid, j["job_no"], "-", e)
                            failures.append("SMS to contact %s for job %s failed: %s"
                                            % (cid, j["job_no"], e))
    print("Done -", len(jobs), "job(s) for", jdate)
    if failures and not dry:
        try:
            send_email([e for e, _ in OFFICE],
                       "Laying - some notifications for %s FAILED" % label,
                       "<p>These did not go out - send them by hand:</p><ul>" +
                       "".join("<li>%s</li>" % ascii_only(f) for f in failures) +
                       "</ul>")
        except Exception as e:
            print("could not even send the failure summary email:", e)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--day", help="YYYY-MM-DD, defaults to tomorrow")
    a = p.parse_args()
    run(a.dry_run, a.day)
