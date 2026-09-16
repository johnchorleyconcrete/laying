import os, re, base64
from fpdf import FPDF

ORANGE = (221, 106, 45)
DARK   = (48, 52, 62)
GREY   = (240, 240, 238)
PINK   = (250, 243, 241)
LOGO   = "/home/SalesChorleyConcrete/laying/static/logo.png"
PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdfs")
ADDR = ["Appley Lane North, Appley Bridge, Wigan, WN6 9DR",
        "01257 781221   tommy@chorleyconcrete.co.uk"]
FOOT = "Chorley Concrete Ltd   VAT Reg. No. 219 2725 08   Company's House Reg: 10062785"
DECLARATION = ("I confirm that the works described on this job sheet have been carried out "
               "and completed to a satisfactory standard, and that the times and details "
               "recorded are correct.")

def ascii_only(s):
    if not s:
        return ""
    s = str(s)
    for a, b in (("\u2014","-"),("\u2013","-"),("\u2018","'"),("\u2019","'"),
                 ("\u201c",'"'),("\u201d",'"'),("\u00b2","2"),("\u00b3","3"),
                 ("\u00a3","GBP ")):
        s = s.replace(a, b)
    return re.sub(r"[^\x20-\x7e\n]", "", s)

class Sheet(FPDF):
    def header(self):
        if os.path.exists(LOGO):
            self.image(LOGO, x=10, y=8, w=34)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(60, 60, 60)
        self.set_xy(110, 9)
        for line in ADDR:
            self.cell(90, 4.5, ascii_only(line), align="R", new_x="LEFT", new_y="NEXT")
            self.set_x(110)
        self.set_xy(10, 33)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(130, 130, 130)
        self.cell(0, 4, FOOT)

def band(p, text):
    p.ln(3.5)
    p.set_font("Helvetica", "B", 9.5)
    p.set_text_color(*DARK)
    p.cell(0, 5.5, ascii_only(text).upper(), new_x="LMARGIN", new_y="NEXT")
    p.set_draw_color(*ORANGE)
    p.set_line_width(0.5)
    p.line(10, p.get_y(), 200, p.get_y())
    p.ln(2)
    p.set_text_color(0, 0, 0)
    p.set_line_width(0.2)

def kvtable(p, pairs):
    """Two columns of label/value boxes, like the scanned sheets."""
    p.set_draw_color(190, 190, 190)
    for i in range(0, len(pairs), 2):
        row = pairs[i:i+2]
        y = p.get_y()
        h = 7
        for n, (k, v) in enumerate(row):
            x = 10 + n * 95
            p.set_fill_color(*GREY)
            p.rect(x, y, 28, h, "DF")
            p.set_xy(x + 1.5, y)
            p.set_font("Helvetica", "B", 8)
            p.cell(26, h, ascii_only(k))
            p.rect(x + 28, y, 67, h)
            p.set_xy(x + 29.5, y)
            p.set_font("Helvetica", "", 8.5)
            p.cell(64, h, ascii_only(v)[:46])
        p.set_y(y + h)
    p.ln(1)

def shaded(p, lines, fill=PINK):
    body = [ascii_only(l).strip() for l in lines if l and l.strip()]
    if not body:
        return
    p.set_fill_color(*fill)
    p.set_draw_color(215, 205, 200)
    y0 = p.get_y()
    p.set_font("Helvetica", "", 9)
    h = 0
    for l in body:
        h += 5 * max(1, len(l) // 105 + 1)
    p.rect(10, y0, 190, h + 4, "DF")
    p.set_xy(12, y0 + 2)
    for l in body:
        p.set_x(12)
        p.multi_cell(186, 5, l, new_x="LMARGIN", new_y="NEXT")
    p.set_y(y0 + h + 6)

def ticktable(p, items, initials=False):
    p.set_draw_color(190, 190, 190)
    y = p.get_y()
    p.set_fill_color(*DARK)
    p.set_text_color(255, 255, 255)
    p.set_font("Helvetica", "B", 8)
    w_done = 20
    w_ini = 20 if initials else 0
    w_item = 190 - w_done - w_ini
    p.rect(10, y, w_item, 6.5, "F"); p.set_xy(11.5, y); p.cell(w_item, 6.5, "Work item")
    p.rect(10 + w_item, y, w_done, 6.5, "F")
    p.set_xy(11.5 + w_item, y); p.cell(w_done, 6.5, "Done")
    if initials:
        p.rect(10 + w_item + w_done, y, w_ini, 6.5, "F")
        p.set_xy(11.5 + w_item + w_done, y); p.cell(w_ini, 6.5, "Initials")
    p.set_y(y + 6.5)
    p.set_text_color(0, 0, 0)
    p.set_font("Helvetica", "", 9)
    for it in items:
        it = ascii_only(it).strip()
        if not it:
            continue
        y = p.get_y()
        h = max(9, 5 * (len(it) // 95 + 1) + 4)
        p.rect(10, y, w_item, h)
        p.rect(10 + w_item, y, w_done, h)
        if initials:
            p.rect(10 + w_item + w_done, y, w_ini, h)
        p.set_xy(12, y + 2)
        p.multi_cell(w_item - 4, 5, it, new_x="LMARGIN", new_y="NEXT")
        p.set_y(y + h)
    p.ln(1)

def build(j, sig_png_b64=None):
    g = lambda k: (j[k] if k in j.keys() else None)
    p = Sheet()
    p.set_auto_page_break(True, 16)
    p.add_page()

    p.set_font("Helvetica", "B", 15)
    p.cell(40, 9, "JOB SHEET")
    p.set_font("Helvetica", "B", 12)
    p.set_text_color(*ORANGE)
    p.cell(0, 9, ascii_only(j["job_no"]), new_x="LMARGIN", new_y="NEXT")
    p.set_text_color(0, 0, 0)
    p.set_draw_color(*ORANGE)
    p.set_line_width(0.5)
    p.line(10, p.get_y(), 200, p.get_y())
    p.set_line_width(0.2)
    p.ln(3)

    kvtable(p, [
        ("Customer", j["customer"] or ""),
        ("Date of works", j["job_date"] + ("" if j["slot"] == "ALL" else "  " + j["slot"])),
        ("Site", (j["site_address"] or "") + " " + (j["postcode"] or "")),
        ("On site", g("start_time") or ""),
        ("Contact", j["contact_phone"] or ""),
        ("Team", (j["crew"] or "").replace(",", " / ")),
    ])

    title = "The job"
    if g("m3"):
        title += " - " + ascii_only(g("m3"))
    band(p, title)
    shaded(p, (j["work_desc"] or "").split("\n"))

    if g("quantities"):
        band(p, "Quantities")
        shaded(p, g("quantities").split("\n"), fill=(245, 245, 243))

    if g("kit"):
        band(p, "Kit and plant")
        p.set_font("Helvetica", "", 9)
        p.multi_cell(0, 5, ascii_only(g("kit")), new_x="LMARGIN", new_y="NEXT")

    ticks = [x for x in (g("tick_list") or "").split("\n") if x.strip()]
    if ticks:
        band(p, "Tick off as you go")
        ticktable(p, ticks)

    if g("check_first"):
        who = ascii_only(g("check_who") or "").strip()
        band(p, ("Check with %s before you start" % who) if who else "Check before you start")
        shaded(p, g("check_first").split("\n"))
        p.set_font("Helvetica", "I", 8)
        p.set_text_color(90, 90, 90)
        p.multi_cell(0, 4.5, "Anything extra - ring the office and get it agreed before you do it. "
                     "Write it in the notes below and get it signed.",
                     new_x="LMARGIN", new_y="NEXT")
        p.set_text_color(0, 0, 0)

    band(p, "Notes, extra work and sketch")
    y = p.get_y()
    p.set_draw_color(190, 190, 190)
    box = 30
    p.rect(10, y, 190, box)
    if j["notes"]:
        p.set_xy(12, y + 2)
        p.set_font("Helvetica", "", 9)
        p.multi_cell(186, 5, ascii_only(j["notes"]), new_x="LMARGIN", new_y="NEXT")
    p.set_y(y + box + 2)

    band(p, "Times and sign-off")
    y = p.get_y()
    p.set_fill_color(*DARK)
    p.set_text_color(255, 255, 255)
    p.set_font("Helvetica", "B", 8)
    for n, lab in enumerate(["On site", "Pour started", "Pour finished", "Off site"]):
        x = 10 + n * 47.5
        p.rect(x, y, 47.5, 6.5, "F")
        p.set_xy(x + 1.5, y)
        p.cell(47.5, 6.5, lab)
    p.set_text_color(0, 0, 0)
    for n in range(4):
        p.rect(10 + n * 47.5, y + 6.5, 47.5, 11)
    p.set_y(y + 19)

    band(p, "Customer sign-off")
    p.set_font("Helvetica", "", 8.5)
    p.multi_cell(0, 4.5, DECLARATION, new_x="LMARGIN", new_y="NEXT")
    p.ln(3)

    if sig_png_b64:
        raw = base64.b64decode(sig_png_b64.split(",")[-1])
        tmp = os.path.join(PDF_DIR, "_sig_tmp.png")
        open(tmp, "wb").write(raw)
        y = p.get_y()
        p.image(tmp, x=12, y=y, w=62)
        os.remove(tmp)
        p.set_y(y + 24)
    else:
        p.ln(20)

    y = p.get_y()
    p.set_draw_color(*DARK)
    p.set_font("Helvetica", "B", 8)
    p.set_fill_color(*DARK)
    p.set_text_color(255, 255, 255)
    for n, (lab, w) in enumerate([("Customer signature", 80), ("Print name", 60), ("Date", 50)]):
        x = 10 + sum([80, 60][:n])
        p.rect(x, y, w, 6.5, "F")
        p.set_xy(x + 1.5, y)
        p.cell(w, 6.5, lab)
    p.set_text_color(0, 0, 0)
    p.set_draw_color(190, 190, 190)
    p.rect(10, y + 6.5, 80, 10)
    p.rect(90, y + 6.5, 60, 10)
    p.rect(150, y + 6.5, 50, 10)
    p.set_font("Helvetica", "", 9)
    if g("signed_name"):
        p.set_xy(92, y + 9); p.cell(56, 5, ascii_only(g("signed_name")))
    if g("signed_at"):
        p.set_xy(152, y + 9); p.cell(46, 5, g("signed_at")[:10])
    p.set_y(y + 19)

    if g("signed_at"):
        p.set_font("Helvetica", "", 7)
        p.set_text_color(130, 130, 130)
        by = (" Taken by %s." % ascii_only(g("signed_by"))) if g("signed_by") else ""
        p.multi_cell(0, 4, "Signed electronically on site at %s.%s"
                     % (g("signed_at").replace("T", " "), by),
                     new_x="LMARGIN", new_y="NEXT")

    if g("signed_at"):
        import sqlite3 as _sq
        _db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "laying.db")
        _c = _sq.connect(_db)
        _c.row_factory = _sq.Row
        pics = _c.execute("SELECT * FROM job_photos WHERE job_id=? ORDER BY id",
                          (j["id"],)).fetchall()
        _c.close()
        if pics:
            p.add_page()
            band(p, "Photos of the finished job")
            pdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "static", "job_photos")
            col, y0 = 0, p.get_y()
            for n, pic in enumerate(pics):
                fp = os.path.join(pdir, pic["filename"])
                if not os.path.exists(fp):
                    continue
                x = 10 + col * 95
                try:
                    p.image(fp, x=x, y=y0, w=90)
                except Exception:
                    continue
                col += 1
                if col == 2:
                    col = 0
                    y0 += 72
                    if y0 > 230:
                        p.add_page()
                        y0 = p.get_y()

    stem = "Signed" if g("signed_at") else "JobSheet"
    name = "%s_%s_%s.pdf" % (stem, ascii_only(j["job_no"]).replace(" ", "_"), j["job_date"])
    path = os.path.join(PDF_DIR, name)
    p.output(path)
    return path
