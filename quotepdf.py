import re, os
from fpdf import FPDF

COMPANY   = "CHORLEY CONCRETE"        # EDIT
ADDR_LINE = "Chorley, Lancashire"     # EDIT
CONTACT   = "Tel 01257 000000   saleschorleyconcrete@gmail.com"  # EDIT
VAT_RATE  = 0.20
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PDF_DIR   = os.path.join(BASE_DIR, "pdfs")
LOGO      = os.path.join(BASE_DIR, "static", "logo.png")

def ascii_only(s):
    if not s:
        return ""
    s = str(s)
    for a, b in (("\u2014","-"),("\u2013","-"),("\u2018","'"),("\u2019","'"),
                 ("\u201c",'"'),("\u201d",'"'),("\u00b2","2"),("\u00b3","3"),
                 ("\u00a3","GBP ")):
        s = s.replace(a, b)
    return re.sub(r"[^\x20-\x7e\n]", "", s)

class Quote(FPDF):
    def header(self):
        if os.path.exists(LOGO):
            self.image(LOGO, x=10, y=8, w=34)
        self.set_xy(10, 31)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(90, 90, 90)
        self.cell(0, 5, ADDR_LINE, new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 5, CONTACT, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(3)
        self.set_draw_color(0, 0, 0)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, "Page %s" % self.page_no(), align="C")

def _kv(p, k, v):
    p.set_font("Helvetica", "B", 10)
    p.cell(32, 6, ascii_only(k))
    p.set_font("Helvetica", "", 10)
    p.multi_cell(0, 6, ascii_only(v), new_x="LMARGIN", new_y="NEXT")

def _block(p, title, body):
    if not body:
        return
    p.ln(2)
    p.set_font("Helvetica", "B", 11)
    p.cell(0, 7, ascii_only(title), new_x="LMARGIN", new_y="NEXT")
    p.set_font("Helvetica", "", 10)
    for line in ascii_only(body).split("\n"):
        line = line.strip()
        if not line:
            p.ln(2); continue
        p.multi_cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

def build(q):
    p = Quote()
    p.set_auto_page_break(True, 18)
    p.add_page()

    p.set_font("Helvetica", "B", 14)
    p.cell(0, 8, "QUOTATION " + ascii_only(q["quote_no"]), new_x="LMARGIN", new_y="NEXT")
    p.ln(2)

    _kv(p, "Customer", q["customer"])
    _kv(p, "Site", (q["site_address"] or "") + "  " + (q["postcode"] or ""))
    if q["contact_phone"]:
        _kv(p, "Contact", q["contact_phone"])
    _kv(p, "Issued", q["date_issued"])
    _kv(p, "Valid until", q["valid_until"])

    _block(p, "Work to be carried out", q["work_desc"])
    _block(p, "Extras", q["extras"])
    _block(p, "Not included", q["exclusions"])

    p.ln(4)
    net = float(q["price"] or 0)
    p.set_draw_color(0, 0, 0)
    p.line(10, p.get_y(), 200, p.get_y())
    p.ln(3)
    p.set_font("Helvetica", "B", 11)
    if q["vat"]:
        vat = round(net * VAT_RATE, 2)
        p.cell(0, 6, "Price          GBP %s + VAT" % ("%.2f" % net), new_x="LMARGIN", new_y="NEXT")
        p.set_font("Helvetica", "", 10)
        p.cell(0, 6, "VAT at 20%%    GBP %s" % ("%.2f" % vat), new_x="LMARGIN", new_y="NEXT")
        p.set_font("Helvetica", "B", 11)
        p.cell(0, 6, "Total          GBP %s" % ("%.2f" % (net + vat)), new_x="LMARGIN", new_y="NEXT")
    else:
        p.cell(0, 6, "Price          GBP %s" % ("%.2f" % net), new_x="LMARGIN", new_y="NEXT")

    _block(p, "Terms", (
        "This quotation is valid until the date shown above. Past that date the "
        "price needs re-confirming.\n"
        "Slope or falls must be agreed and signed by the customer BEFORE pouring. "
        "It cannot be changed after.\n"
        "Extras and variations are agreed with the office and signed before the "
        "work is carried out.\n"
        "Washout: nothing goes down a drain, gully, manhole or watercourse."))

    p.ln(8)
    p.set_font("Helvetica", "B", 11)
    p.cell(0, 7, "Acceptance", new_x="LMARGIN", new_y="NEXT")
    p.set_font("Helvetica", "", 10)
    p.cell(0, 6, "I accept this quotation and the terms above.", new_x="LMARGIN", new_y="NEXT")
    p.ln(6)
    p.cell(95, 8, "Signed ......................................")
    p.cell(0, 8, "Date ........................", new_x="LMARGIN", new_y="NEXT")
    p.ln(2)
    p.cell(0, 8, "Print name ......................................", new_x="LMARGIN", new_y="NEXT")

    path = os.path.join(PDF_DIR, "Quote_%s.pdf" % ascii_only(q["quote_no"]).replace(" ", "_"))
    p.output(path)
    return path
