#!/usr/bin/env python
"""Score a posting 0-100 against the master profile, and pick a job family.

Deliberately keyless. An API-key requirement would make the whole pipeline
stop working the day a key expires, and the signal that decides "is this
role a fit for a 2027 CS grad with these skills" is mostly lexical anyway.
`score_llm` is the optional upgrade for the shortlist, not the default path.

Scoring, out of 100:
    40  skill overlap, weighted -- a matched skill counts for more when it is
        rare across the corpus (a JD asking for MobileViT tells you far more
        than one asking for Python). Normalised against SKILL_TARGET matches,
        not against the whole inventory: nobody matches 60 skills, so dividing
        by the inventory compressed every score into a narrow low band.
    20  job-family keyword match
    30  fresher signal. Weighted this heavily on purpose -- a role closed to
        a 2027 graduate is worth zero regardless of how well the skills line
        up, and skill match alone was ranking SDE III roles to the top.
    10  bonus signals (research, publication, the domains Parth has shipped in)
"""
import math, re
from collections import Counter

SKILL_TARGET = 10   # matching this many confirmed skills earns full marks

# Listing cards on some sources carry no job description -- Internshala's
# average 41 characters against Greenhouse's 3,941. Skill overlap cannot score
# what is not there, so those postings were capped ~20 points below ATS ones
# and the highest-volume source sorted to the bottom of every digest. Below
# this length the skill component is redistributed across what IS measurable,
# and the row is marked partial so the number is not read as equivalent.
THIN_DESC = 300
PARTIAL_CEILING = 85    # not 100: a title-only match genuinely tells you less

WORD = re.compile(r"[a-z0-9+#.]+")
FRESHER = re.compile(r"\b(intern|internship|trainee|graduate|campus|fresher|entry[- ]level|new grad|university|apprentice)\b", re.I)
BONUS = re.compile(r"\b(research|publication|paper|computer vision|nlp|llm|rag|mlops|deep learning|machine learning|data pipeline|airflow|pytorch|fastapi)\b", re.I)


def tokens(text):
    return set(WORD.findall((text or "").lower()))


def profile_skills(master):
    """Every confirmed skill, lowercased. Inferred skills are excluded --
    scoring against a skill Parth has not confirmed would rank him into roles
    he cannot honestly claim."""
    out = set()
    for group in master["skills"].values():
        for s in group.get("confirmed", []):
            out.add(s.lower())
    return out


def build_idf(jobs):
    """Rarity weight per token across today's postings."""
    n = max(len(jobs), 1)
    df = Counter()
    for j in jobs:
        df.update(tokens(f"{j.get('title','')} {j.get('description','')}"))
    return {t: math.log(1 + n / (1 + c)) for t, c in df.items()}, n


# Postings abbreviate the very terms the families are keyed on.
ABBREV = {r"\bds\b": "data science", r"\bml\b": "machine learning",
          r"\bai\b": "artificial intelligence", r"\bcv\b": "computer vision",
          r"\bsde\b": "software engineer", r"\bswe\b": "software engineer",
          r"\bnlp\b": "natural language processing", r"\bde\b": "data engineer"}


def expand(text):
    t = (text or "").lower().replace("/", " / ")
    for pat, full in ABBREV.items():
        t = re.sub(pat, full, t)
    return t


def pick_family(job, master):
    blob = expand(f"{job.get('title','')} {job.get('description','')}")
    best, best_hits = None, 0
    for fam in master["job_families"]:
        t = expand(job.get("title", ""))
        hits = sum(3 if k in t else 1
                   for k in fam["keywords"] if k in blob)
        if hits > best_hits:
            best, best_hits = fam["id"], hits
    return best or "fam_backend"


def score(job, master, idf, skills=None):
    skills = skills if skills is not None else profile_skills(master)
    title = job.get("title", "")
    blob = f"{title}\n{job.get('description','')}"
    # Expanded, not raw: pick_family() expands "AI"/"ML"/"SDE" but this path
    # read the raw text, so family keywords never matched on the abbreviated
    # titles that dominate Internshala. Only the fresher signal was firing.
    bl = expand(blob)

    # 1. weighted skill overlap, normalised against a realistic match count
    matched, weight = [], 0.0
    for s in skills:
        if s in bl:
            matched.append(s)
            weight += max((idf.get(t, 1.0) for t in WORD.findall(s)), default=1.0)
    avg_idf = (sum(idf.values()) / len(idf)) if idf else 1.0
    skill_pts = 40 * min(weight / (SKILL_TARGET * avg_idf), 1.0) ** 0.7

    # 2. family keywords
    fam_id = pick_family(job, master)
    fam = next(f for f in master["job_families"] if f["id"] == fam_id)
    hits = sum(1 for k in fam["keywords"] if k in bl)
    fam_pts = 20 * min(hits / 3, 1.0)

    # 3. is this actually open to a fresher
    fresh_pts = 30 if FRESHER.search(title) else (12 if FRESHER.search(bl) else 0)

    # 4. domains Parth has shipped in
    bonus_pts = 10 * min(len(set(m.group(0).lower() for m in BONUS.finditer(bl))) / 4, 1.0)

    thin = len(job.get("description") or "") < THIN_DESC
    if thin:
        measurable = 20 + 30 + 10           # family + fresher + bonus
        raw = fam_pts + fresh_pts + bonus_pts
        total_score = round(raw * (PARTIAL_CEILING / measurable))
    else:
        total_score = round(skill_pts + fam_pts + fresh_pts + bonus_pts)

    return (min(total_score, 100), fam_id,
            sorted(matched, key=len, reverse=True)[:8],
            "partial" if thin else "full")


def score_all(jobs, master):
    idf, _ = build_idf(jobs)
    skills = profile_skills(master)
    out = []
    for j in jobs:
        s, fam, matched, conf = score(j, master, idf, skills)
        out.append({**j, "score": s, "family": fam,
                    "matched_skills": matched, "confidence": conf})
    return sorted(out, key=lambda j: -j["score"])
