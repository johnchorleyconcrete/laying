import os, re, sqlite3
from datetime import datetime, date, timedelta

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "laying.db")

# This is the schema as it actually exists on the live database (checked
# against laying.db directly). CREATE TABLE IF NOT EXISTS is a no-op against
# an existing table, so columns that were added to a table after it first
# went live are bolted on separately below by _migrate(), which is safe to
# run repeatedly against an already-up-to-date database.
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
    created_at TEXT NOT NULL,
    enquiry_id INTEGER,
    sent_at TEXT,
    followup_sent_at TEXT
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
    created_at TEXT NOT NULL,
    start_time TEXT,
    m3 TEXT,
    kit TEXT,
    quantities TEXT,
    tick_list TEXT,
    check_who TEXT,
    check_first TEXT,
    signed_at TEXT,
    signed_name TEXT,
    signature_png TEXT,
    signed_pdf TEXT,
    signed_by TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_date ON jobs(job_date);
CREATE INDEX IF NOT EXISTS idx_jobs_job_no ON jobs(job_no);
-- Enforced going forward only: two duplicate job numbers already exist in
-- the live data (from the old count-then-insert race), so this can't be a
-- table-wide UNIQUE constraint without a manual data cleanup first.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_quote_unique
    ON jobs(quote_id) WHERE quote_id IS NOT NULL;
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
    genie_id TEXT,
    subcontractor INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    crew_code TEXT,
    pw_hash TEXT,
    pw_salt TEXT,
    setup_token TEXT,
    token_expires TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT
);
CREATE TABLE IF NOT EXISTS enquiries (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'screed',
    logged TEXT NOT NULL,
    taken_by TEXT,
    taken_dt TEXT,
    name TEXT,
    phone TEXT,
    addr TEXT,
    pc TEXT,
    w TEXT, l TEXT, d TEXT, area TEXT, vol TEXT,
    type TEXT, svc TEXT, whn TEXT, urgency TEXT,
    notes TEXT,
    photos INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    quote_id INTEGER
);
CREATE TABLE IF NOT EXISTS blocks (
    id INTEGER PRIMARY KEY,
    block_date TEXT NOT NULL,
    slot TEXT NOT NULL DEFAULT 'ALL',
    crew TEXT NOT NULL,
    reason TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocks_date ON blocks(block_date);
CREATE TABLE IF NOT EXISTS job_photos (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    caption TEXT,
    uploaded_by TEXT,
    uploaded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_photos_job ON job_photos(job_id);
CREATE TABLE IF NOT EXISTS login_attempts (
    email TEXT PRIMARY KEY,
    fail_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);
CREATE TABLE IF NOT EXISTS quote_amendments (
    id INTEGER PRIMARY KEY,
    quote_id INTEGER NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    changes TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quote_amendments_quote ON quote_amendments(quote_id);
"""

# (table, column, sqlite type) - for columns added to a table after it was
# first created live. Applied only if the column is missing.
_MIGRATIONS = [
    ("jobs", "start_time", "TEXT"),
    ("jobs", "m3", "TEXT"),
    ("jobs", "kit", "TEXT"),
    ("jobs", "quantities", "TEXT"),
    ("jobs", "tick_list", "TEXT"),
    ("jobs", "check_who", "TEXT"),
    ("jobs", "check_first", "TEXT"),
    ("jobs", "signed_at", "TEXT"),
    ("jobs", "signed_name", "TEXT"),
    ("jobs", "signature_png", "TEXT"),
    ("jobs", "signed_pdf", "TEXT"),
    ("jobs", "signed_by", "TEXT"),
    ("jobs", "completed_at", "TEXT"),
    ("crew", "genie_id", "TEXT"),
    ("quotes", "enquiry_id", "INTEGER"),
    ("quotes", "sent_at", "TEXT"),
    ("quotes", "followup_sent_at", "TEXT"),
    ("quotes", "revision", "INTEGER NOT NULL DEFAULT 0"),
    ("quotes", "amended_at", "TEXT"),
    ("quotes", "amended_by", "TEXT"),
]


class _Conn(sqlite3.Connection):
    """A sqlite3.Connection that actually closes itself when used as a
    context manager. The stdlib one only commits/rolls back on __exit__ and
    leaves the connection (and its file handle) open - see
    https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection --
    which meant every `with conn() as c:` in this codebase was leaking a
    connection. Using this as the connect() factory fixes every call site
    at once with no other code changes needed."""
    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def conn():
    c = sqlite3.connect(DB, timeout=15, factory=_Conn)
    c.row_factory = sqlite3.Row
    return c


def _migrate(c):
    existing = {}
    for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        existing[table] = {row[1] for row in c.execute("PRAGMA table_info(%s)" % table)}
    for table, col, coltype in _MIGRATIONS:
        if table in existing and col not in existing[table]:
            c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, coltype))


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        _migrate(c)
        c.execute("INSERT OR IGNORE INTO crew (code,name,subcontractor) VALUES ('josh','Josh Halton',0)")
        c.execute("INSERT OR IGNORE INTO crew (code,name,subcontractor) VALUES ('matt','Matt Ashurst',1)")
    print("Initialised", DB)


def next_quote_no(c):
    """Best guess at the next plain quote number, so the office doesn't have
    to remember where they got to. Looks at both quotes.quote_no and
    jobs.job_no (a job booked straight off a quote number is stored as
    "JS-<quote_no>") since a number might only show up in one of the two -
    e.g. today, quotes is empty but 4127 already exists as a job. Purely a
    suggestion: the field stays editable so a number from outside the
    system (or a non-numeric one) can still be typed in as before."""
    nums = []
    for (qn,) in c.execute("SELECT quote_no FROM quotes"):
        m = re.fullmatch(r"\d+", (qn or "").strip())
        if m:
            nums.append(int(m.group()))
    for (jn,) in c.execute("SELECT job_no FROM jobs WHERE job_no LIKE 'JS-%'"):
        m = re.fullmatch(r"JS-(\d+)", jn or "")
        if m:
            nums.append(int(m.group(1)))
    return str(max(nums) + 1) if nums else ""


def job_no_for(c, quote_no, customer):
    """With a quote the sheet takes the quote number. Without, JS + 3 letters
    of the customer surname + running number.

    Takes the same connection the caller is about to INSERT the job on, and
    must be called with that connection already holding a write lock (see
    callers in app.py, which open the transaction with BEGIN IMMEDIATE first)
    so the count-then-insert is atomic and two people booking at the same
    moment can't be handed the same job number."""
    if quote_no:
        return "JS-" + str(quote_no).strip().upper().replace("JS-", "")
    parts = [p for p in str(customer).split() if p.isalpha()]
    stem = (parts[-1] if parts else "XXX")[:3].upper().ljust(3, "X")
    n = c.execute("SELECT COUNT(*) FROM jobs WHERE job_no LIKE ?",
                  ("JS-" + stem + "-%",)).fetchone()[0]
    return "JS-%s-%02d" % (stem, n + 1)


if __name__ == "__main__":
    init()
