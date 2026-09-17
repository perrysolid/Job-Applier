#!/usr/bin/env python
"""Phase 1 -- discovery. Fetch, dedupe, filter, score, store, report.

Read-only against every source. Nothing here submits an application.

    ./.venv/bin/python run.py                # full run
    ./.venv/bin/python run.py --digest-only  # re-print today's digest
"""
import argparse, concurrent.futures as cf, datetime, json, pathlib, sys, yaml

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from core import db, filter as filt, score as scorer
from sources.ats import fetch

REGISTRY = ROOT / "sources" / "boards.json"


def load_cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_master():
    return yaml.safe_load((ROOT / "profile" / "master.yaml").read_text())


def harvest(boards, workers=16):
    """Pull every registered board in parallel. A dead board is reported, not fatal."""
    jobs, dead = [], []

    def one(b):
        got, err = fetch(b["board"], b["slug"])
        return b, got, err

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for b, got, err in ex.map(one, boards):
            if err or not got:
                dead.append(f"{b['board']}/{b['slug']} ({err or 'empty'})")
            jobs += got
    return jobs, dead


def digest(con, cfg, limit=40):
    apply_at = cfg["scoring"]["min_score_to_apply"]
    short_at = cfg["scoring"]["min_score_to_shortlist"]
    rows = con.execute(
        "SELECT * FROM jobs WHERE status='new' AND score >= ?"
        " ORDER BY score DESC LIMIT ?", (short_at, limit)).fetchall()

    if not rows:
        print("\nNothing above the shortlist threshold today.")
        return

    print(f"\n{'='*78}\n  TOP MATCHES  ({len(rows)} shown, apply threshold {apply_at})\n{'='*78}")
    for r in rows:
        mark = "APPLY " if r["score"] >= apply_at else "look  "
        loc = (r["location"] or "-")[:26]
        print(f"\n[{mark}{r['score']:3d}]  {r['title'][:58]}")
        print(f"          {r['company'][:28]:28s} {loc:26s} {r['family']}")
        print(f"          {r['url']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--digest-only", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args()

    cfg, master = load_cfg(), load_master()
    con = db.connect()

    if not a.digest_only:
        boards = json.loads(REGISTRY.read_text())
        print(f"harvesting {len(boards)} boards...")
        raw, dead = harvest(boards)
        print(f"  {len(raw):,} postings fetched"
              + (f"  ({len(dead)} boards dead/empty)" if dead else ""))

        kept, dropped = filt.apply_all(raw, cfg)
        print(f"  {len(kept):,} pass hard filters")
        for why, n in sorted(dropped.items(), key=lambda kv: -kv[1])[:6]:
            print(f"      -{n:<5,} {why}")

        scored = scorer.score_all(kept, master)
        new = db.upsert_jobs(con, scored)
        for j in scored:
            con.execute("UPDATE jobs SET score=?, family=? WHERE fingerprint=?",
                        (j["score"], j["family"],
                         db.fingerprint(j["company"], j["title"], j.get("location", ""))))
        con.commit()
        dupes = len(scored) - new
        print(f"  {new:,} new, {dupes:,} already seen")

    digest(con, cfg, a.limit)
    total = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    print(f"\n{total:,} jobs tracked in data/jobs.db")


if __name__ == "__main__":
    main()
