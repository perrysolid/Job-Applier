#!/usr/bin/env python
"""Render a job-family-tailored resume from the fact-locked master profile.

    python tailor/build.py --family fam_ml
    python tailor/build.py --all

Fact-lock enforcement:
  * fields carrying `status: ASK` are dropped, never guessed
  * skills under `inferred:` are dropped until confirmed
  * every bullet emitted is copied verbatim from master.yaml — this script
    does no generation. Per-job keyword injection happens downstream, and is
    restricted to reordering and to terms already in skills.confirmed.
"""
import argparse, pathlib, subprocess, sys, yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "resumes"


def asked(v):
    """True if the value is an unconfirmed placeholder."""
    return isinstance(v, dict) and v.get("status") == "ASK"


def clean(v):
    return None if asked(v) else v


def load():
    return yaml.safe_load((ROOT / "profile" / "master.yaml").read_text())


def build_education(m):
    out = []
    for e in m["education"]:
        if not e.get("on_resume"):
            continue
        hl = []
        if e.get("cgpa"):
            hl.append(f"CGPA: {e['cgpa']}/{e.get('cgpa_scale', 10)}")
        hl += e.get("honors", [])
        area = e.get("field") or e.get("qualification")
        if e.get("degree"):
            area = f"{e['degree']} in {area}"
        out.append({
            "institution": e["institution"],
            "area": area,
            "location": clean(e.get("location")),
            "date": f"{e['start']} \u2013 {e['end']}",
            "highlights": hl or None,
        })
    return out


def build_experience(m, order):
    items = {e["id"]: e for e in m["experience"]}
    # recruiters read the top entry first — reverse-chronological unless the
    # job family explicitly promotes a role.
    chrono = sorted(items, key=lambda i: str(items[i]["start"]), reverse=True)
    ids = [i for i in order if i in items] + [i for i in chrono if i not in order]
    out = []
    for i in ids:
        e = items[i]
        out.append({
            "company": e["org"],
            "position": e["title"],
            "location": clean(e.get("location")),
            "start_date": str(e["start"]),
            "end_date": str(e["end"]),
            "highlights": [" ".join(b["text"].split()) for b in e["bullets"]],
        })
    return out


def build_publications(m):
    return [{
        "title": p["title"],
        "authors": ["*Parth Mishra*"],
        "journal": f"{p['venue']}, {p['publisher']}",
        "date": "2025-11",
        "summary": " ".join(p["bullets"][1]["text"].split()),
    } for p in m.get("publications", [])]


def build_projects(m, order):
    items = {p["id"]: p for p in m["projects"] if p.get("on_resume", True)}
    ids = [i for i in order if i in items] + [i for i in items if i not in order]
    out = []
    for i in ids:
        p = items[i]
        name = f"[{p['name']}]({p['url']})" if p.get("url") else p["name"]
        entry = {"name": name,
                 "highlights": [" ".join(b["text"].split()) for b in p["bullets"]]}
        d = clean(p.get("date"))
        if d:
            entry["date"] = str(d)
        elif p.get("date_range"):
            s, _, e = p["date_range"].partition(" to ")
            entry["start_date"], entry["end_date"] = s, e
        out.append(entry)
    return out


def build_achievements(m, max_bullets=99):
    out = []
    for a in m["achievements"]:
        if a.get("see_project") or not a.get("on_resume", True):
            continue
        for b in a.get("bullets", [])[:max_bullets]:
            out.append({"bullet": " ".join(b["text"].split())})
    return out


def build_skills(m, fam=None, max_per_line=99):
    labels = {
        "languages": "Programming & Query Languages",
        "ml_dl": "Machine Learning & Deep Learning",
        "llm_nlp": "LLM, RAG & NLP",
        "data_eng_backend": "Data Engineering & Backend",
        "cloud_devops": "Cloud, MLOps & DevOps",
        "analysis_viz": "Data Analysis & Visualization",
    }
    kw = [k.lower() for k in (fam or {}).get("keywords", [])]

    def relevance(skill):
        """Surface skills the job description actually asked for."""
        sl = skill.lower()
        return -sum(1 for k in kw if k in sl or sl in k)

    out = []
    for key, label in labels.items():
        confirmed = m["skills"].get(key, {}).get("confirmed", [])
        if not confirmed:
            continue
        ranked = sorted(confirmed, key=relevance)[:max_per_line]
        # restore the author's ordering within the kept subset
        kept = [s for s in confirmed if s in ranked]
        out.append({"label": label, "details": ", ".join(kept)})
    return out


def render(m, fam, max_projects=99, max_ach_bullets=99,
           body_pt=9.4, line_spacing=0.55, max_skills=99, density=0):
    lead = fam["lead_with"]
    cv = {
        "name": m["personal"]["full_name"],
        "headline": fam["label"].split(" (")[0],
        "location": f"{m['location']['current']['city']}, {m['location']['current']['state']}",
        "email": m["personal"]["email"],
        "phone": m["personal"]["phone"],
        "social_networks": [
            {"network": "LinkedIn", "username": m["personal"]["linkedin"].rsplit("/", 1)[-1]},
            {"network": "GitHub", "username": m["personal"]["github"].rsplit("/", 1)[-1]},
        ],
        "sections": {
            "education": build_education(m),
            "experience": build_experience(m, lead),
            "publications": build_publications(m),
            "projects": build_projects(m, lead)[:max_projects],
            "achievements": build_achievements(m, max_ach_bullets),
            "skills": build_skills(m, fam, max_skills),
        },
    }
    # RenderCV's stock spacing burns ~4cm of an A4 page on header padding and
    # section gaps alone. `density` tightens those first, before font size.
    tiers = [
        # (name gap, headline gap, connections gap, sec above, sec below, entry gap)
        ("0.7cm", "0.7cm", "0.7cm", "0.5cm", "0.3cm", "1.2em"),   # 0 = stock
        ("0.35cm", "0.3cm", "0.4cm", "0.35cm", "0.2cm", "0.9em"),  # 1
        ("0.25cm", "0.2cm", "0.3cm", "0.28cm", "0.15cm", "0.7em"), # 2
        ("0.2cm", "0.15cm", "0.25cm", "0.22cm", "0.12cm", "0.55em"),  # 3
    ]
    nm, hl, cn, sa, sb, eg = tiers[density]
    design = {
        "theme": "classic",
        "page": {"size": "a4", "top_margin": "0.45in", "bottom_margin": "0.45in",
                 "left_margin": "0.55in", "right_margin": "0.55in",
                 "show_footer": False, "show_top_note": False},
        "colors": {k: "rgb(0, 0, 0)" for k in
                   ("name", "headline", "connections", "section_titles", "links")},
        "header": {"connections": {"phone_number_format": "international"},
                   "space_below_name": nm, "space_below_headline": hl,
                   "space_below_connections": cn},
        "section_titles": {"space_above": sa, "space_below": sb},
        "sections": {"space_between_regular_entries": eg},
        "typography": {"font_size": {"body": f"{body_pt}pt", "name": "24pt"},
                       "line_spacing": f"{line_spacing}em"},
    }
    return {"cv": cv, "design": design}


def page_count(pdf):
    from pypdf import PdfReader
    return len(PdfReader(str(pdf)).pages)


def emit(m, fam, fid, **kw):
    """Render one variant; return (ok, pdf_path)."""
    doc = render(m, fam, **kw)
    src = OUT / f"Parth_Mishra_{fid}.yaml"
    src.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000))
    pdf = OUT / f"Parth_Mishra_{fid}.pdf"
    r = subprocess.run(
        [str(ROOT / ".venv/bin/rendercv"), "render", str(src),
         "-o", str(OUT / "_build" / fid), "-nomd", "-nohtml", "-nopng", "-q",
         "-pdf", str(pdf)],
        capture_output=True, text=True)
    if r.returncode:
        print((r.stderr or r.stdout)[-1000:])
        return False, None
    return True, pdf


def fit_one_page(m, fam, fid):
    """Render, then tighten until it fits one page.

    The ladder spends typography before it spends content: a fresher resume
    that runs onto a second page reads as padding, but so does one that has
    had its best project cut to make room for a 25-item skills line.
    """
    n = len(m["projects"])
    ladder = [
        dict(density=1, body_pt=9.4, line_spacing=0.55, max_skills=99, max_projects=n, max_ach_bullets=99),
        dict(density=2, body_pt=9.4, line_spacing=0.55, max_skills=99, max_projects=n, max_ach_bullets=99),
        dict(density=2, body_pt=9.2, line_spacing=0.52, max_skills=14, max_projects=n, max_ach_bullets=99),
        dict(density=3, body_pt=9.0, line_spacing=0.50, max_skills=12, max_projects=n, max_ach_bullets=99),
        dict(density=3, body_pt=8.8, line_spacing=0.46, max_skills=10, max_projects=n, max_ach_bullets=1),
        dict(density=3, body_pt=8.6, line_spacing=0.44, max_skills=9,  max_projects=n - 1, max_ach_bullets=1),
    ]
    for step, kw in enumerate(ladder, 1):
        ok, pdf = emit(m, fam, fid, **kw)
        if not ok:
            return None
        pages = page_count(pdf)
        if pages == 1:
            return step, kw, pages
    return step, kw, pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-fit", action="store_true", help="skip the one-page fit loop")
    a = ap.parse_args()

    m = load()
    fams = {f["id"]: f for f in m["job_families"]}
    if not a.all and a.family not in fams:
        sys.exit(f"unknown family. choose from: {', '.join(fams)}")
    targets = list(fams) if a.all else [a.family]

    OUT.mkdir(parents=True, exist_ok=True)
    for fid in targets:
        if a.no_fit:
            ok, pdf = emit(m, fams[fid], fid)
            print(f"[{'ok' if ok else 'FAIL'}] {fid}")
            continue
        res = fit_one_page(m, fams[fid], fid)
        if res is None:
            print(f"[FAIL] {fid}")
            continue
        step, kw, pages = res
        note = "" if pages == 1 else f"  <-- STILL {pages}p, trim master.yaml"
        print(f"[ok] {fid:12s} {pages}p  step {step}/6 "
              f"(d{kw['density']}, {kw['body_pt']}pt, skills<={kw['max_skills']}, proj={kw['max_projects']})"
              f"  -> Parth_Mishra_{fid}.pdf{note}")


if __name__ == "__main__":
    main()
