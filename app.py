import os, sqlite3, calendar as calmod
from datetime import date, datetime, timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, send_file, send_from_directory, abort, flash)
from models import conn, job_no_for
from auth import (login_required, role_required, current_user,
                  hash_pw, check_pw, send_setup_email, new_token,
                  csrf_token, csrf_ok, login_locked_until,
                  record_failed_login, clear_failed_login)
import quotepdf, sheetpdf

app = Flask(__name__)

# A weak/default secret key lets anyone forge a session cookie and log in as
# anyone (Flask sessions are signed, not encrypted). This used to silently
# fall back to a hardcoded string if LAYING_SECRET wasn't set - refusing to
# start is safer than running wide open. Set LAYING_SECRET to a long random
# value in the PythonAnywhere Web tab's environment variables (or in
# wsgi.py before importing this module) - see wsgi_snippet.txt.
_INSECURE_SECRETS = {"", "change-me-in-env", "PUT-A-LONG-RANDOM-STRING-HERE"}
_secret = os.environ.get("LAYING_SECRET", "")
if _secret in _INSECURE_SECRETS or len(_secret) < 20:
    raise RuntimeError(
        "LAYING_SECRET is missing or too weak. Set a long random string as "
        "the LAYING_SECRET environment variable before starting this app - "
        "a default/short secret key lets anyone forge a login session.")
app.secret_key = _secret

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB per request (photo uploads)
app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

SLOTS = ["AM", "PM", "ALL"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(BASE_DIR, "static", "job_photos")
ENQUIRY_PHOTO_DIR = os.path.join(BASE_DIR, "static", "enquiry_photos")
MIN_PHOTOS = 2


@app.before_request
def _csrf_protect():
    if request.method == "POST" and not csrf_ok():
        flash("That page had gone stale - please try again")
        return redirect(request.referrer or url_for("calendar"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("pw") or ""
        locked = login_locked_until(email)
        if locked:
            flash("Too many wrong attempts on that account - try again in a few minutes")
            return render_template("login.html")
        with conn() as c:
            u = c.execute("SELECT * FROM users WHERE lower(email)=? AND active=1",
                          (email,)).fetchone()
        if u and check_pw(pw, u["pw_hash"], u["pw_salt"]):
            clear_failed_login(email)
            session.clear()
            session["uid"] = u["id"]
            session.permanent = True
            with conn() as c:
                c.execute("UPDATE users SET last_login=? WHERE id=?",
                          (datetime.now().isoformat(timespec="seconds"), u["id"]))
            return redirect(request.args.get("next") or url_for("calendar"))
        record_failed_login(email)
        flash("Wrong email or password")
    return render_template("login.html")


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        with conn() as c:
            u = c.execute("SELECT * FROM users WHERE lower(email)=? AND active=1",
                          (email,)).fetchone()
        if u:
            try:
                send_setup_email(u["email"], u["name"], new_token(u["id"]), reset=True)
            except Exception as e:
                print("reset email failed:", e)
        flash("If that email is on the system, a link has been sent to it")
        return redirect(url_for("login"))
    return render_template("forgot.html")


@app.route("/setup/<token>", methods=["GET", "POST"])
def setup(token):
    with conn() as c:
        u = c.execute("SELECT * FROM users WHERE setup_token=? AND active=1",
                      (token,)).fetchone()
    if not u or not u["token_expires"] or u["token_expires"] < datetime.now().isoformat():
        return render_template("setup.html", expired=True)
    if request.method == "POST":
        pw = request.form.get("pw") or ""
        if len(pw) < 8:
            flash("Password needs to be at least 8 characters")
            return render_template("setup.html", u=u, token=token)
        if pw != request.form.get("pw2"):
            flash("The two passwords do not match")
            return render_template("setup.html", u=u, token=token)
        h, salt = hash_pw(pw)
        with conn() as c:
            c.execute("""UPDATE users SET pw_hash=?, pw_salt=?, setup_token=NULL,
                         token_expires=NULL WHERE id=?""", (h, salt, u["id"]))
        flash("Password set - you can log in now")
        return redirect(url_for("login"))
    return render_template("setup.html", u=u, token=token)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/users", methods=["GET", "POST"])
@role_required("owner")
def users_page():
    with conn() as c:
        if request.method == "POST":
            f = request.form
            if f.get("resend_id"):
                u = c.execute("SELECT * FROM users WHERE id=?", (f["resend_id"],)).fetchone()
                try:
                    send_setup_email(u["email"], u["name"], new_token(u["id"]))
                    flash("Link sent to " + u["email"])
                except Exception as e:
                    flash("Could not send: %s" % e)
            elif f.get("deactivate_id"):
                c.execute("UPDATE users SET active=0 WHERE id=? AND role != 'owner'",
                          (f["deactivate_id"],))
                flash("Account turned off")
            else:
                email = (f.get("email") or "").strip()
                if not email:
                    flash("Email required")
                elif c.execute("SELECT 1 FROM users WHERE lower(email)=?",
                               (email.lower(),)).fetchone():
                    flash("That email already has an account")
                else:
                    c.execute("""INSERT INTO users (email,name,role,crew_code,created_at)
                                 VALUES (?,?,?,?,?)""",
                              (email, f.get("name","").strip(), f.get("role","crew"),
                               f.get("crew_code") or None,
                               datetime.now().isoformat(timespec="seconds")))
                    u = c.execute("SELECT * FROM users WHERE lower(email)=?",
                                  (email.lower(),)).fetchone()
                    try:
                        send_setup_email(u["email"], u["name"], new_token(u["id"]))
                        flash("Account made, setup link sent")
                    except Exception as e:
                        flash("Account made but email failed: %s" % e)
            return redirect(url_for("users_page"))
        rows = c.execute("SELECT * FROM users ORDER BY role, name").fetchall()
        crew = c.execute("SELECT code, name FROM crew WHERE active=1").fetchall()
    return render_template("users.html", users=rows, crew=crew)


@app.route("/")
@login_required
def calendar():
    u = current_user()
    if u["role"] == "crew":
        return redirect(url_for("my_jobs"))
    today = date.today()
    try:
        y = int(request.args.get("y", today.year))
        m = int(request.args.get("m", today.month))
        first = date(y, m, 1)
    except (ValueError, TypeError):
        flash("That is not a month I understand")
        y, m = today.year, today.month
        first = date(y, m, 1)
    last = date(y, m, calmod.monthrange(y, m)[1])
    with conn() as c:
        rows = c.execute("""SELECT * FROM jobs WHERE job_date BETWEEN ? AND ?
                            AND status != 'cancelled' ORDER BY job_date, slot""",
                         (first.isoformat(), last.isoformat())).fetchall()
        blks = c.execute("""SELECT * FROM blocks WHERE block_date BETWEEN ? AND ?
                            ORDER BY block_date""",
                         (first.isoformat(), last.isoformat())).fetchall()
        upcoming = c.execute("""SELECT * FROM jobs WHERE job_date >= ?
                                AND status != 'cancelled'
                                ORDER BY job_date, slot LIMIT 15""",
                             (today.isoformat(),)).fetchall()
    by_day, blk_day = {}, {}
    for r in rows:
        by_day.setdefault(r["job_date"], []).append(r)
    for b in blks:
        blk_day.setdefault(b["block_date"], []).append(b)
    weeks = calmod.Calendar(0).monthdatescalendar(y, m)
    prev_m = (first - timedelta(days=1))
    next_m = (last + timedelta(days=1))
    return render_template("calendar.html", weeks=weeks, by_day=by_day, blk_day=blk_day,
                           y=y, m=m, month_name=first.strftime("%B %Y"), today=today,
                           prev_m=prev_m, next_m=next_m, upcoming=upcoming)


@app.route("/enquiries")
@role_required("owner", "office")
def enquiries():
    show = request.args.get("show", "open")
    with conn() as c:
        if show == "all":
            rows = c.execute("SELECT * FROM enquiries ORDER BY id DESC LIMIT 200").fetchall()
        else:
            rows = c.execute("""SELECT * FROM enquiries WHERE status='new'
                                ORDER BY id DESC""").fetchall()
    pix = {}
    if os.path.isdir(ENQUIRY_PHOTO_DIR):
        for f in sorted(os.listdir(ENQUIRY_PHOTO_DIR)):
            if f.startswith("enq"):
                try:
                    eid = int(f[3:].split("_")[0])
                except Exception:
                    continue
                pix.setdefault(eid, []).append(f)
    return render_template("enquiries.html", enquiries=rows, pix=pix, show=show)


@app.route("/enquiries/<int:eid>/park", methods=["POST"])
@role_required("owner", "office")
def enquiry_park(eid):
    with conn() as c:
        c.execute("UPDATE enquiries SET status=? WHERE id=?",
                  (request.form.get("status", "parked"), eid))
    return redirect(url_for("enquiries"))


@app.route("/quotes")
@role_required("owner", "office")
def quotes():
    with conn() as c:
        rows = c.execute("SELECT * FROM quotes ORDER BY id DESC LIMIT 100").fetchall()
    return render_template("quotes.html", quotes=rows, today=date.today().isoformat())

@app.route("/quotes/new", methods=["GET", "POST"])
@role_required("owner", "office")
def quote_new():
    if request.method == "POST":
        f = request.form
        issued = f.get("date_issued") or date.today().isoformat()
        try:
            valid = f.get("valid_until") or (date.fromisoformat(issued) + timedelta(days=30)).isoformat()
            price = float(f.get("price") or 0)
        except ValueError:
            flash("Check the date and price fields - one of them isn't valid")
            return render_template("quote_form.html", today=date.today().isoformat(),
                                   valid=(date.today() + timedelta(days=30)).isoformat(),
                                   pre=dict(f))
        with conn() as c:
            cur = c.execute("""INSERT INTO quotes
                (quote_no,customer,site_address,postcode,contact_phone,contact_email,
                 date_issued,valid_until,work_desc,extras,exclusions,price,vat,
                 status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?)""",
                (f["quote_no"].strip(), f["customer"].strip(), f.get("site_address",""),
                 f.get("postcode","").upper(), f.get("contact_phone",""),
                 f.get("contact_email",""), issued, valid, f.get("work_desc",""),
                 f.get("extras",""), f.get("exclusions",""),
                 price, 1 if f.get("vat") else 0,
                 datetime.now().isoformat(timespec="seconds")))
            if f.get("enquiry_id"):
                c.execute("UPDATE enquiries SET status='quoted', quote_id=? WHERE id=?",
                          (cur.lastrowid, f["enquiry_id"]))
                c.execute("UPDATE quotes SET enquiry_id=? WHERE id=?",
                          (f["enquiry_id"], cur.lastrowid))
        return redirect(url_for("quote_view", qid=cur.lastrowid))
    pre = {}
    eid = request.args.get("from_enquiry")
    if eid:
        with conn() as c:
            e = c.execute("SELECT * FROM enquiries WHERE id=?", (eid,)).fetchone()
        if e:
            dims = []
            if e["l"] and e["w"]:
                dims.append("%s x %s" % (e["l"], e["w"]))
            if e["d"]:
                dims.append("%smm deep" % e["d"])
            if e["area"]:
                dims.append("%s m2" % e["area"])
            if e["vol"]:
                dims.append("%s m3" % e["vol"])
            desc = []
            if e["svc"]:
                desc.append(e["svc"])
            if e["type"]:
                desc.append(e["type"] + " screed")
            line = ". ".join([x for x in [" - ".join(desc), ", ".join(dims)] if x])
            if e["notes"]:
                line += "\n\n" + e["notes"]
            pre = {"customer": e["name"] or "", "contact_phone": e["phone"] or "",
                   "site_address": e["addr"] or "", "postcode": e["pc"] or "",
                   "work_desc": line, "enquiry_id": e["id"]}
    return render_template("quote_form.html", today=date.today().isoformat(),
                           valid=(date.today() + timedelta(days=30)).isoformat(),
                           pre=pre)

@app.route("/quotes/<int:qid>")
@role_required("owner", "office")
def quote_view(qid):
    with conn() as c:
        q = c.execute("SELECT * FROM quotes WHERE id=?", (qid,)).fetchone()
        job = c.execute("SELECT * FROM jobs WHERE quote_id=?", (qid,)).fetchone()
        crew = c.execute("SELECT * FROM crew WHERE active=1").fetchall()
    return render_template("quote_view.html", q=q, job=job, crew=crew,
                           slots=SLOTS, today=date.today().isoformat())

@app.route("/quotes/<int:qid>/pdf")
@role_required("owner", "office")
def quote_pdf_route(qid):
    with conn() as c:
        q = c.execute("SELECT * FROM quotes WHERE id=?", (qid,)).fetchone()
    return send_file(quotepdf.build(q), as_attachment=True)

@app.route("/quotes/<int:qid>/status", methods=["POST"])
@role_required("owner", "office")
def quote_status(qid):
    with conn() as c:
        c.execute("UPDATE quotes SET status=? WHERE id=?",
                  (request.form["status"], qid))
    return redirect(url_for("quote_view", qid=qid))

@app.route("/quotes/<int:qid>/book", methods=["POST"])
@role_required("owner", "office")
def quote_book(qid):
    f = request.form
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        q = c.execute("SELECT * FROM quotes WHERE id=?", (qid,)).fetchone()
        if c.execute("SELECT 1 FROM jobs WHERE quote_id=?", (qid,)).fetchone():
            flash("Already booked")
            return redirect(url_for("quote_view", qid=qid))
        jn = job_no_for(c, q["quote_no"], q["customer"])
        try:
            cur = c.execute("""INSERT INTO jobs
                (job_no,quote_id,customer,site_address,postcode,contact_phone,
                 job_date,slot,crew,work_desc,notes,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'booked',?)""",
                (jn, qid, q["customer"], q["site_address"], q["postcode"],
                 q["contact_phone"], f["job_date"], f.get("slot","ALL"),
                 ",".join(f.getlist("crew")), q["work_desc"], f.get("notes",""),
                 datetime.now().isoformat(timespec="seconds")))
        except sqlite3.IntegrityError:
            flash("Already booked")
            return redirect(url_for("quote_view", qid=qid))
        c.execute("UPDATE quotes SET status='accepted' WHERE id=?", (qid,))
    return redirect(url_for("job_view", jid=cur.lastrowid))

@app.route("/jobs/new", methods=["GET", "POST"])
@role_required("owner", "office")
def job_new():
    if request.method == "POST":
        f = request.form
        if not (f.get("job_date") or "").strip():
            flash("Date is required")
            with conn() as c:
                crew = c.execute("SELECT * FROM crew WHERE active=1").fetchall()
            return render_template("job_form.html", crew=crew, slots=SLOTS,
                                   d=date.today().isoformat())
        with conn() as c:
            c.execute("BEGIN IMMEDIATE")
            jn = job_no_for(c, f.get("quote_no",""), f["customer"])
            cur = c.execute("""INSERT INTO jobs
                (job_no,customer,site_address,postcode,contact_phone,job_date,
                 slot,crew,work_desc,notes,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'booked',?)""",
                (jn, f["customer"].strip(), f.get("site_address",""),
                 f.get("postcode","").upper(), f.get("contact_phone",""),
                 f["job_date"], f.get("slot","ALL"), ",".join(f.getlist("crew")),
                 f.get("work_desc",""), f.get("notes",""),
                 datetime.now().isoformat(timespec="seconds")))
        return redirect(url_for("job_view", jid=cur.lastrowid))
    with conn() as c:
        crew = c.execute("SELECT * FROM crew WHERE active=1").fetchall()
    return render_template("job_form.html", crew=crew, slots=SLOTS,
                           d=request.args.get("d", date.today().isoformat()))

@app.route("/myjobs")
@login_required
def my_jobs():
    u = current_user()
    today = date.today()
    with conn() as c:
        if u["role"] == "crew":
            rows = c.execute("""SELECT * FROM jobs WHERE status != 'cancelled'
                                AND job_date BETWEEN ? AND ?
                                AND (crew = ? OR crew LIKE ? OR crew LIKE ? OR crew LIKE ?)
                                ORDER BY job_date, slot""",
                             ((today - timedelta(days=7)).isoformat(),
                              (today + timedelta(days=14)).isoformat(),
                              u["crew_code"], u["crew_code"] + ",%",
                              "%," + u["crew_code"], "%," + u["crew_code"] + ",%")).fetchall()
        else:
            rows = c.execute("""SELECT * FROM jobs WHERE status != 'cancelled'
                                AND job_date >= ? ORDER BY job_date LIMIT 30""",
                             (today.isoformat(),)).fetchall()
    return render_template("myjobs.html", jobs=rows, today=today)


def _can_see(u, j):
    if u["role"] in ("owner", "office"):
        return True
    return u["crew_code"] in [x for x in (j["crew"] or "").split(",") if x]


@app.route("/jobs/<int:jid>", methods=["GET", "POST"])
@login_required
def job_view(jid):
    u = current_user()
    with conn() as c:
        j = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not j or not _can_see(u, j):
            flash("That job is not one of yours")
            return redirect(url_for("my_jobs"))
        if request.method == "POST":
            if j["signed_at"]:
                flash("This job is signed off and locked - it can no longer be edited")
                return redirect(url_for("job_view", jid=jid))
            f = request.form
            status = f.get("status", "booked")
            if status not in ("booked", "cancelled"):
                # 'done' only ever gets set by the /sign flow, which also
                # enforces the photo/signature requirements - a plain edit
                # here must not be able to mark a job done without those.
                status = j["status"]
            c.execute("""UPDATE jobs SET job_date=?, slot=?, crew=?, notes=?,
                         status=?, work_desc=?, quantities=?, kit=?, m3=?,
                         start_time=?, tick_list=?, check_who=?, check_first=?
                         WHERE id=?""",
                      (f["job_date"], f["slot"], ",".join(f.getlist("crew")),
                       f.get("notes",""), status,
                       f.get("work_desc",""), f.get("quantities",""),
                       f.get("kit",""), f.get("m3",""), f.get("start_time",""),
                       f.get("tick_list",""), f.get("check_who",""),
                       f.get("check_first",""), jid))
            return redirect(url_for("job_view", jid=jid))
        crew = c.execute("SELECT * FROM crew WHERE active=1").fetchall()
        sent = c.execute("""SELECT * FROM notify_log WHERE job_id=?
                            ORDER BY sent_at""", (jid,)).fetchall()
    return render_template("job_view.html", j=j, crew=crew, slots=SLOTS, sent=sent,
                           u=u, pics=job_photos(jid), min_photos=MIN_PHOTOS)

@app.route("/blocks", methods=["GET", "POST"])
@role_required("owner", "office")
def blocks_page():
    with conn() as c:
        if request.method == "POST":
            f = request.form
            if f.get("delete_id"):
                c.execute("DELETE FROM blocks WHERE id=?", (f["delete_id"],))
                return redirect(url_for("blocks_page"))
            try:
                start = date.fromisoformat(f["date_from"])
                end = date.fromisoformat(f["date_to"])
            except (KeyError, ValueError):
                flash("Those dates don't look right")
                return redirect(url_for("blocks_page"))
            if end < start:
                flash("End date is before the start date")
                return redirect(url_for("blocks_page"))
            codes = f.getlist("crew")
            if not codes:
                flash("Pick at least one person")
                return redirect(url_for("blocks_page"))
            subs = {r["code"]: r["subcontractor"]
                    for r in c.execute("SELECT code, subcontractor FROM crew")}
            n, skipped = 0, 0
            d = start
            while d <= end:
                if f.get("skip_sundays") and d.weekday() == 6:
                    d += timedelta(days=1); continue
                for code in codes:
                    reason = f["reason"]
                    if subs.get(code) and reason == "Holiday":
                        reason = "Not available"
                    if c.execute("""SELECT 1 FROM blocks WHERE block_date=? AND crew=?
                                    AND slot=?""", (d.isoformat(), code, f.get("slot","ALL"))).fetchone():
                        skipped += 1; continue
                    c.execute("""INSERT INTO blocks (block_date,slot,crew,reason,note,created_at)
                                 VALUES (?,?,?,?,?,?)""",
                              (d.isoformat(), f.get("slot","ALL"), code, reason,
                               f.get("note",""), datetime.now().isoformat(timespec="seconds")))
                    n += 1
                d += timedelta(days=1)
            flash("Added %d day(s)%s" % (n, ", %d already blocked" % skipped if skipped else ""))
            return redirect(url_for("blocks_page"))
        crew = c.execute("SELECT * FROM crew WHERE active=1 ORDER BY id").fetchall()
        rows = c.execute("""SELECT * FROM blocks WHERE block_date >= date('now','-7 days')
                            ORDER BY block_date, crew""").fetchall()
    return render_template("blocks.html", crew=crew, blocks=rows,
                           today=date.today().isoformat(), slots=SLOTS)


def job_photos(jid):
    with conn() as c:
        return c.execute("""SELECT * FROM job_photos WHERE job_id=?
                            ORDER BY id""", (jid,)).fetchall()


# Only these are ever written to disk - if Pillow can't decode an upload as
# an image, it is rejected outright rather than saved as whatever extension
# the client claimed. Previously a non-image upload (e.g. a crafted .svg or
# .html file) that failed to parse fell back to trusting the client's
# filename extension and writing the raw, unvalidated bytes straight into
# the public static/ folder - a stored-content risk.
def _save_photo(raw):
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(raw))
    im.load()
    im = im.convert("RGB")
    im.thumbnail((1600, 1600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78)
    return buf.getvalue()


@app.route("/jobs/<int:jid>/photos", methods=["POST"])
@login_required
def job_photo_upload(jid):
    u = current_user()
    with conn() as c:
        j = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not j or not _can_see(u, j):
            flash("That job is not one of yours")
            return redirect(url_for("my_jobs"))
        if j["signed_at"]:
            flash("Job is signed off - photos are locked")
            return redirect(url_for("job_view", jid=jid))
    os.makedirs(PHOTO_DIR, exist_ok=True)
    n, rejected = 0, 0
    for up in request.files.getlist("photos"):
        if not up or not up.filename:
            continue
        raw = up.read()
        if not raw:
            continue
        try:
            jpg = _save_photo(raw)
        except Exception as e:
            print("photo rejected (not a readable image):", up.filename, e)
            rejected += 1
            continue
        with conn() as c:
            cur = c.execute("""INSERT INTO job_photos
                               (job_id,filename,caption,uploaded_by,uploaded_at)
                               VALUES (?,'',?,?,?)""",
                            (jid, request.form.get("caption", ""), u["name"],
                             datetime.now().isoformat(timespec="seconds")))
            pid = cur.lastrowid
            fn = "job%d_%d.jpg" % (jid, pid)
            with open(os.path.join(PHOTO_DIR, fn), "wb") as fh:
                fh.write(jpg)
            c.execute("UPDATE job_photos SET filename=? WHERE id=?", (fn, pid))
        n += 1
    if n:
        flash("%d photo(s) added" % n)
    elif rejected:
        flash("Those files were not readable images - nothing was added")
    else:
        flash("No photos were added")
    return redirect(url_for("job_view", jid=jid))


@app.route("/jobs/<int:jid>/photos/<int:pid>/delete", methods=["POST"])
@login_required
def job_photo_delete(jid, pid):
    u = current_user()
    with conn() as c:
        j = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not j or not _can_see(u, j) or j["signed_at"]:
            flash("Cannot remove that")
            return redirect(url_for("job_view", jid=jid))
        row = c.execute("SELECT * FROM job_photos WHERE id=? AND job_id=?",
                        (pid, jid)).fetchone()
        if row:
            try:
                os.remove(os.path.join(PHOTO_DIR, row["filename"]))
            except Exception:
                pass
            c.execute("DELETE FROM job_photos WHERE id=?", (pid,))
    return redirect(url_for("job_view", jid=jid))


# Job/enquiry photos used to be served straight out of /static, which Flask
# serves to anyone with no login check at all - completed-job site photos
# (and, once a job's signed, its printed sheet details) were reachable by
# anyone who could guess or was handed a filename. These routes put the
# same access rules the rest of the app uses in front of the files.
@app.route("/photos/job/<path:filename>")
@login_required
def job_photo_file(filename):
    u = current_user()
    with conn() as c:
        row = c.execute("SELECT * FROM job_photos WHERE filename=?", (filename,)).fetchone()
        j = c.execute("SELECT * FROM jobs WHERE id=?", (row["job_id"],)).fetchone() if row else None
    if not row or not j or not _can_see(u, j):
        abort(404)
    return send_from_directory(PHOTO_DIR, filename)


@app.route("/photos/enquiry/<path:filename>")
@role_required("owner", "office")
def enquiry_photo_file(filename):
    return send_from_directory(ENQUIRY_PHOTO_DIR, filename)


@app.route("/jobs/<int:jid>/sign", methods=["GET", "POST"])
@login_required
def job_sign(jid):
    u = current_user()
    with conn() as c:
        j = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not j or not _can_see(u, j):
            flash("That job is not one of yours")
            return redirect(url_for("my_jobs"))
        if request.method == "POST":
            if j["signed_at"]:
                flash("Already signed - cannot be signed twice")
                return redirect(url_for("job_view", jid=jid))
            if len(job_photos(jid)) < MIN_PHOTOS:
                flash("You need at least %d photos of the finished job before it can be "
                      "signed off" % MIN_PHOTOS)
                return redirect(url_for("job_view", jid=jid))
            name = (request.form.get("signed_name") or "").strip()
            sig = request.form.get("signature") or ""
            if not name or len(sig) < 100:
                flash("Need a printed name and a signature")
                return redirect(url_for("job_sign", jid=jid))
            now = datetime.now().isoformat(timespec="seconds")
            c.execute("""UPDATE jobs SET signed_at=?, signed_name=?, signature_png=?,
                         status='done', completed_at=?, signed_by=? WHERE id=?""",
                      (now, name, sig, now, u["name"], jid))
            j2 = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            try:
                path = sheetpdf.build(j2, sig)
                c.execute("UPDATE jobs SET signed_pdf=? WHERE id=?",
                          (os.path.basename(path), jid))
                flash("Signed and saved")
            except Exception as e:
                # The sign-off itself (the part that matters legally) is
                # already committed above - a PDF rendering hiccup (bad
                # signature data, a missing photo file) shouldn't leave the
                # crew looking at a raw error after the customer has just
                # signed. The PDF gets rebuilt on demand by job_sheet_pdf/
                # completed_pdf if signed_pdf is still blank.
                print("sheetpdf build failed after sign-off for job", jid, ":", e)
                flash("Signed and saved (the printable sheet will be generated "
                      "next time you open it)")
            return redirect(url_for("completed"))
    pics = job_photos(jid)
    if len(pics) < MIN_PHOTOS:
        flash("Add at least %d photos of the finished job first" % MIN_PHOTOS)
        return redirect(url_for("job_view", jid=jid))
    return render_template("sign.html", j=j, pics=pics)


@app.route("/jobs/<int:jid>/sheet")
@login_required
def job_sheet_pdf(jid):
    u = current_user()
    with conn() as c:
        j = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not j or not _can_see(u, j):
            flash("That job is not one of yours")
            return redirect(url_for("my_jobs"))
    if j["signed_at"] and j["signed_pdf"]:
        path = os.path.join(BASE_DIR, "pdfs", j["signed_pdf"])
        if os.path.exists(path):
            return send_file(path, as_attachment=True)
    return send_file(sheetpdf.build(j), as_attachment=True)


@app.route("/completed")
@login_required
def completed():
    u = current_user()
    with conn() as c:
        if u["role"] == "crew":
            rows = c.execute("""SELECT * FROM jobs WHERE signed_at IS NOT NULL
                                AND (crew = ? OR crew LIKE ? OR crew LIKE ? OR crew LIKE ?)
                                ORDER BY signed_at DESC""",
                             (u["crew_code"], u["crew_code"] + ",%",
                              "%," + u["crew_code"], "%," + u["crew_code"] + ",%")).fetchall()
        else:
            rows = c.execute("""SELECT * FROM jobs WHERE signed_at IS NOT NULL
                                ORDER BY signed_at DESC""").fetchall()
    return render_template("completed.html", jobs=rows)


@app.route("/completed/<int:jid>/pdf")
@login_required
def completed_pdf(jid):
    u = current_user()
    with conn() as c:
        j = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not j or not _can_see(u, j):
            flash("That job is not one of yours")
            return redirect(url_for("my_jobs"))
    path = os.path.join(BASE_DIR, "pdfs", j["signed_pdf"]) if j["signed_pdf"] else None
    if not path or not os.path.exists(path):
        path = sheetpdf.build(j, j["signature_png"])
    return send_file(path, as_attachment=True)


@app.route("/crew", methods=["GET", "POST"])
@role_required("owner", "office")
def crew_page():
    with conn() as c:
        if request.method == "POST":
            for cid in request.form.getlist("id"):
                c.execute("UPDATE crew SET phone=?, email=? WHERE id=?",
                          (request.form.get("phone_" + cid, ""),
                           request.form.get("email_" + cid, ""), cid))
            return redirect(url_for("crew_page"))
        rows = c.execute("SELECT * FROM crew ORDER BY id").fetchall()
    return render_template("crew.html", crew=rows)

@app.context_processor
def inject_user():
    return {"u": current_user(), "csrf_token": csrf_token}


if __name__ == "__main__":
    app.run(debug=bool(os.environ.get("FLASK_DEBUG")))
