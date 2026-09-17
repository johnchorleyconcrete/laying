import os, sys, ssl, smtplib, zipfile, shutil
from datetime import date, datetime
from email.message import EmailMessage

BASE = "/home/SalesChorleyConcrete/laying"
sys.path.insert(0, BASE)

from recipients import BACKUP_TO as TO
MAX_MB = 20

for _env in ("/home/SalesChorleyConcrete/laying/.env",
             "/home/SalesChorleyConcrete/GenieAgg/.env"):
    if os.path.exists(_env):
        for _l in open(_env):
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

def run():
    stamp = date.today().isoformat()
    tmp = "/tmp/laying_backup"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)

    import sqlite3
    src = sqlite3.connect(os.path.join(BASE, "laying.db"))
    dbcopy = os.path.join(tmp, "laying_%s.db" % stamp)
    dst = sqlite3.connect(dbcopy)
    src.backup(dst)
    dst.close(); src.close()

    zpath = os.path.join(tmp, "laying_files_%s.zip" % stamp)
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for folder in ["pdfs", "static/job_photos", "static/enquiry_photos"]:
            d = os.path.join(BASE, folder)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                fp = os.path.join(d, f)
                if os.path.isfile(fp) and not f.startswith("_"):
                    z.write(fp, os.path.join(folder, f))
                    n += 1

    attach = [dbcopy]
    zmb = os.path.getsize(zpath) / 1048576.0
    note = ""
    if zmb <= MAX_MB:
        attach.append(zpath)
    else:
        note = ("<p style='color:#C0392B'><b>The files zip is %.1f MB and was too big to "
                "email.</b> Download it from the Files tab instead - it is at %s</p>"
                % (zmb, zpath))
        shutil.copy(zpath, os.path.join(BASE, os.path.basename(zpath)))

    c = sqlite3.connect(dbcopy)
    try:
        counts = {}
        for t in ["jobs", "quotes", "enquiries", "job_photos", "users", "blocks"]:
            try:
                counts[t] = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            except Exception:
                counts[t] = "-"
    finally:
        c.close()

    rows = "".join("<tr><td style='padding:3px 14px 3px 0'>%s</td><td><b>%s</b></td></tr>"
                   % (k, v) for k, v in counts.items())
    html = ("<div style='font-family:Segoe UI,Arial,sans-serif'>"
            "<h2 style='font-size:18px;margin:0 0 4px'>Laying system backup - %s</h2>"
            "<p style='color:#5A6670;font-size:13px;margin:0 0 12px'>"
            "Database plus %d file(s). Keep this email, or save the attachments "
            "somewhere off PythonAnywhere.</p><table style='font-size:14px'>%s</table>%s</div>"
            % (stamp, n, rows, note))

    m = EmailMessage()
    m["From"] = os.environ.get("GMAIL_USER")
    m["To"] = ", ".join(TO)
    m["Subject"] = "Laying system backup - %s" % stamp
    m.set_content("Laying system backup for %s. %d files." % (stamp, n))
    m.add_alternative(html, subtype="html")
    for fp in attach:
        with open(fp, "rb") as fh:
            m.add_attachment(fh.read(), maintype="application", subtype="octet-stream",
                             filename=os.path.basename(fp))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD"))
        s.send_message(m)
    print("backup sent -", n, "files, zip %.1f MB" % zmb)
    shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    run()
