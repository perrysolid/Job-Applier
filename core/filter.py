#!/usr/bin/env python
"""Hard gates, applied before anything reaches the LLM.

These are cheap booleans that eliminate roles Parth is categorically not
eligible for. Running them first cuts LLM spend by roughly 80% -- there is no
point paying a model to score a Staff Engineer role for a 2027 graduate.
"""
import datetime, re

YEARS = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?year", re.I)
# Seniority encoded as a level rather than a word: "SDE III", "Engineer II",
# "L5". These slipped through substring matching on the title terms.
LEVEL = re.compile(r"\b(?:i{2,3}|iv|v|[2-9])\b(?!\s*(?:years?|yrs?))|\bl[3-9]\b", re.I)
INTERNISH = re.compile(r"\b(intern|internship|trainee|graduate|campus|fresher|entry[- ]level|new grad|university)\b", re.I)


def min_years_required(text):
    """Smallest experience requirement stated anywhere in the posting.

    Postings routinely say both "0-2 years" and "3+ years preferred"; the
    smallest number is the one that decides eligibility.
    """
    vals = [int(m) for m in YEARS.findall(text or "") if m.isdigit() and int(m) <= 20]
    return min(vals) if vals else None


def passes(job, cfg):
    """Return (ok, reason). reason is None when the job passes."""
    f = cfg["search"]["filters"]
    title = (job.get("title") or "")
    tl = title.lower()
    blob = f"{title}\n{job.get('description') or ''}"

    # Word-boundary, not substring: plain `in` made "lead" match "Leading"
    # and "Lead Generation", which threw away thousands of valid postings.
    for term in f["exclude_title_terms"]:
        t = term.lower()
        pat = re.escape(t) if not t[-1].isalnum() else r"\b" + re.escape(t) + r"\b"
        if re.search(pat, tl):
            return False, f"title contains '{term}'"

    if LEVEL.search(title) and not INTERNISH.search(title):
        return False, "senior level in title"

    for co in f.get("exclude_companies") or []:
        if co.lower() in (job.get("company") or "").lower():
            return False, f"excluded company '{co}'"

    yrs = min_years_required(blob)
    if yrs is not None and yrs > f["max_experience_years"] and not INTERNISH.search(title):
        return False, f"requires {yrs}+ years"

    posted = job.get("posted_at")
    if posted and f.get("posted_within_days"):
        try:
            age = (datetime.date.today() - datetime.date.fromisoformat(posted[:10])).days
            if age > f["posted_within_days"]:
                return False, f"posted {age}d ago"
        except ValueError:
            pass

    locs = [l.lower() for l in cfg["search"]["locations"]]
    jl = (job.get("location") or "").lower()
    if jl and not any(l in jl for l in locs) and "remote" not in jl:
        return False, f"location '{job.get('location')}'"

    return True, None


def apply_all(jobs, cfg):
    kept, dropped = [], {}
    for j in jobs:
        ok, why = passes(j, cfg)
        if ok:
            kept.append(j)
        else:
            key = why.split("'")[0].strip()
            dropped[key] = dropped.get(key, 0) + 1
    return kept, dropped
