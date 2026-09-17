import os, sys, ssl, smtplib, argparse
from datetime import date, timedelta, datetime
from email.message import EmailMessage

sys.path.insert(0, "/home/SalesChorleyConcrete/laying")
from models import conn
from recipients import WEEKVIEW_TO as TO

for _env in ("/home/SalesChorleyConcrete/laying/.env",
             "/home/SalesChorleyConcrete/GenieAgg/.env"):
    if os.path.exists(_env):
        for _l in open(_env):
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

ORANGE, INK, MUTED, LINE = "#E8642A", "#1F2329", "#5A6670", "#D5DBDF"

def cell(booked, blocked):
    if blocked:
        return ("<td style='border:1px solid %s;padding:5px 7px;background:#EFF1F2;"
                "color:%s;font-size:11px'>%s</td>" % (LINE, MUTED, blocked))
    if booked:
        return ("<td style='border:1px solid %s;padding:5px 7px;background:#fff;"
                "font-size:11px'><b>%s</b><br><span style='color:%s'>%s</span></td>"
                % (LINE, booked[0], MUTED, booked[1]))
    return ("<td style='border:1px solid %s;padding:5px 7px;background:#FBEEE6;"
            "color:%s;font-weight:700;font-size:11px'>FREE</td>" % (LINE, ORANGE))

def run(start=None, dry=False):
    d0 = date.fromisoformat(start) if start else date.today() + timedelta(days=1)
    days = []
    d = d0
    while len(days) < 6:
        if d.weekday() != 6:
            days.append(d)
        d += timedelta(days=1)

    with conn() as c:
        crew = c.execute("SELECT * FROM crew WHERE active=1 ORDER BY id").fetchall()
        jobs = c.execute("""SELECT * FROM jobs WHERE status='booked'
                            AND job_date BETWEEN ? AND ?""",
                         (days[0].isoformat(), days[-1].isoformat())).fetchall()
        blks = c.execute("""SELECT * FROM blocks WHERE block_date BETWEEN ? AND ?""",
                         (days[0].isoformat(), days[-1].isoformat())).fetchall()

    grid, free = {}, 0
    for m in crew:
        for d in days:
            for slot in ("AM", "PM"):
                grid[(m["code"], d.isoformat(), slot)] = (None, None)
    for j in jobs:
        for code in [x for x in (j["crew"] or "").split(",") if x]:
            slots = ("AM", "PM") if j["slot"] == "ALL" else (j["slot"],)
            for sl in slots:
                k = (code, j["job_date"], sl)
                if k in grid:
                    grid[k] = ((j["job_no"], j["postcode"] or j["customer"] or ""), None)
    for b in blks:
        for code in [x for x in (b["crew"] or "").split(",") if x]:
            slots = ("AM", "PM") if b["slot"] == "ALL" else (b["slot"],)
            for sl in slots:
                k = (code, b["block_date"], sl)
                if k in grid and not grid[k][0]:
                    grid[k] = (None, b["reason"])

    h = ["<div style='font-family:Segoe UI,Arial,sans-serif;color:%s'>" % INK]
    h.append("<h2 style='margin:0 0 2px;font-size:19px'>Laying diary - what is free</h2>")
    h.append("<p style='margin:0 0 14px;color:%s;font-size:13px'>%s to %s</p>"
             % (MUTED, days[0].strftime("%a %d %b"), days[-1].strftime("%a %d %b")))
    h.append("<table style='border-collapse:collapse'>")
    h.append("<tr><th style='border:1px solid %s;padding:6px 8px;background:#F4F6F7;"
             "font-size:11px;text-align:left'>Man</th>" % LINE)
    for d in days:
        h.append("<th colspan='2' style='border:1px solid %s;padding:6px 8px;"
                 "background:#F4F6F7;font-size:11px'>%s</th>" % (LINE, d.strftime("%a %d")))
    h.append("</tr><tr><td style='border:1px solid %s'></td>" % LINE)
    for d in days:
        for sl in ("AM", "PM"):
            h.append("<td style='border:1px solid %s;padding:3px 7px;background:#FAFBFB;"
                     "font-size:10px;color:%s;font-weight:700'>%s</td>" % (LINE, MUTED, sl))
    h.append("</tr>")

    for m in crew:
        h.append("<tr><td style='border:1px solid %s;padding:6px 8px;font-size:12px;"
                 "font-weight:700;white-space:nowrap'>%s%s</td>"
                 % (LINE, m["name"], " *" if m["subcontractor"] else ""))
        for d in days:
            for sl in ("AM", "PM"):
                bk, bl = grid[(m["code"], d.isoformat(), sl)]
                if not bk and not bl:
                    free += 1
                h.append(cell(bk, bl))
        h.append("</tr>")
    h.append("</table>")
    h.append("<p style='margin-top:12px;font-size:14px'><b>%d free half day(s)</b> "
             "across the next 6 working days.</p>" % free)
    h.append("<p style='color:%s;font-size:11px'>* subcontractor. Greyed cells are "
             "time off or away working. Full diary: "
             "https://laying-saleschorleyconcrete.pythonanywhere.com</p>" % MUTED)
    h.append("</div>")
    html = "".join(h)

    if dry:
        print(html[:1500])
        print("\n... %d free half days" % free)
        return

    m = EmailMessage()
    m["From"] = os.environ.get("GMAIL_USER")
    m["To"] = ", ".join(TO)
    m["Subject"] = "Laying diary - %d free half days from %s" % (free, days[0].strftime("%a %d %b"))
    m.set_content("This needs an HTML mail client. See %s" %
                  "https://laying-saleschorleyconcrete.pythonanywhere.com")
    m.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD"))
        s.send_message(m)
    print("sent -", free, "free half days")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--from", dest="start")
    a = p.parse_args()
    run(a.start, a.dry_run)
