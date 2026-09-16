import os, sqlite3
from datetime import datetime, date, timedelta

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "laying.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY,
    quote_no TEXT NOT NULL,
    customer TEXT NOT NULL,
    site_address TEXT,
    postcode TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    date_issued TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    work_desc TEXT,
    extras TEXT,
    exclusions TEXT,
    price REAL NOT NULL DEFAULT 0,
    vat INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    job_no TEXT NOT NULL,
    quote_id INTEGER,
    customer TEXT NOT NULL,
    site_address TEXT,
    postcode TEXT,
    contact_phone TEXT,
    job_date TEXT NOT NULL,
    slot TEXT NOT NULL DEFAULT 'ALL',
    crew TEXT NOT NULL DEFAULT '',
    work_desc TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'booked',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_date ON jobs(job_date);
CREATE TABLE IF NOT EXISTS notify_log (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL,
    job_date TEXT NOT NULL,
    channel TEXT NOT NULL,
    target TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    UNIQUE(job_id, job_date, channel, target)
);
CREATE TABLE IF NOT EXISTS crew (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    subcontractor INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
"""

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    with conn() as c:
        c.executescript(SCHEMA)
        c.execute("INSERT OR IGNORE INTO crew (code,name,subcontractor) VALUES ('josh','Josh Halton',0)")
        c.execute("INSERT OR IGNORE INTO crew (code,name,subcontractor) VALUES ('matt','Matt Ashurst',1)")
    print("Initialised", DB)

def job_no_for(quote_no, customer):
    """With a quote the sheet takes the quote number. Without, JS + 3 letters
    of the customer surname + running number."""
    if quote_no:
        return "JS-" + str(quote_no).strip().upper().replace("JS-", "")
    parts = [p for p in str(customer).split() if p.isalpha()]
    stem = (parts[-1] if parts else "XXX")[:3].upper().ljust(3, "X")
    with conn() as c:
        n = c.execute("SELECT COUNT(*) FROM jobs WHERE job_no LIKE ?",
                      ("JS-" + stem + "-%",)).fetchone()[0]
    return "JS-%s-%02d" % (stem, n + 1)

if __name__ == "__main__":
    init()
