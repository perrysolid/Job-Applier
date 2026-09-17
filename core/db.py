#!/usr/bin/env python
"""SQLite store for discovered jobs and submitted applications.

One row per job, keyed by a content fingerprint so the same posting found on
three different sources collapses to one entry. `applications` records what was
actually submitted, which is what enforces the per-company cooldown.
"""
import hashlib, pathlib, re, sqlite3, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    fingerprint   TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    location      TEXT,
    url           TEXT NOT NULL,
    apply_url     TEXT,
    description   TEXT,
    posted_at     TEXT,
    discovered_at TEXT NOT NULL,
    score         INTEGER,
    family        TEXT,
    status        TEXT NOT NULL DEFAULT 'new',
    reason        TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_score   ON jobs(score DESC);

CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT NOT NULL REFERENCES jobs(fingerprint),
    company       TEXT NOT NULL,
    source        TEXT NOT NULL,
    applied_at    TEXT NOT NULL,
    resume_used   TEXT,
    outcome       TEXT DEFAULT 'submitted',
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_app_company ON applications(company);
CREATE INDEX IF NOT EXISTS idx_app_date    ON applications(applied_at);

CREATE TABLE IF NOT EXISTS answers_seen (
    question   TEXT PRIMARY KEY,
    answer     TEXT NOT NULL,
    source     TEXT,
    confirmed  INTEGER DEFAULT 0,
    updated_at TEXT
);
"""

STOP = re.compile(r"\b(intern|internship|trainee|fresher|i|ii|remote|hybrid|onsite|full[- ]time|part[- ]time)\b")


def normalize(s):
    s = (s or "").lower()
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s)      # drop "(Remote)", "[2026]"
    s = STOP.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())


def fingerprint(company, title, location=""):
    """Same role on Naukri, LinkedIn and the company's own board -> one row."""
    key = f"{normalize(company)}|{normalize(title)}|{normalize(location).split(',')[0]}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert_jobs(con, jobs):
    """Insert new jobs; never clobber a row we've already scored or acted on."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    new = 0
    for j in jobs:
        fp = fingerprint(j["company"], j["title"], j.get("location", ""))
        cur = con.execute(
            "INSERT INTO jobs (fingerprint, source, company, title, location, url,"
            " apply_url, description, posted_at, discovered_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO NOTHING",
            (fp, j["source"], j["company"], j["title"], j.get("location"), j["url"],
             j.get("apply_url"), j.get("description"), j.get("posted_at"), now))
        new += cur.rowcount
    con.commit()
    return new


def company_on_cooldown(con, company, days):
    row = con.execute(
        "SELECT MAX(applied_at) AS last FROM applications WHERE company = ? COLLATE NOCASE",
        (company,)).fetchone()
    if not row or not row["last"]:
        return False
    last = datetime.datetime.fromisoformat(row["last"])
    return (datetime.datetime.now() - last).days < days


def applied_today(con, source):
    today = datetime.date.today().isoformat()
    return con.execute(
        "SELECT COUNT(*) FROM applications WHERE source = ? AND applied_at LIKE ?",
        (source, today + "%")).fetchone()[0]


def record_application(con, fp, company, source, resume, notes=None):
    con.execute(
        "INSERT INTO applications (fingerprint, company, source, applied_at, resume_used, notes)"
        " VALUES (?,?,?,?,?,?)",
        (fp, company, source, datetime.datetime.now().isoformat(timespec="seconds"), resume, notes))
    con.execute("UPDATE jobs SET status='applied' WHERE fingerprint=?", (fp,))
    con.commit()


if __name__ == "__main__":
    con = connect()
    n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
         for t in ("jobs", "applications", "answers_seen")}
    print(f"db ready at {DB.relative_to(ROOT)} -> {n}")
