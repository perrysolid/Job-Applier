# Job-Applier

Automated off-campus job and internship pipeline: discover roles across job
boards and company ATS platforms, rank them against a fact-locked profile,
render a tailored one-page resume per job family, and apply.

Built for Indian off-campus fresher hiring (Naukri, Internshala, LinkedIn,
Greenhouse/Lever/Ashby company boards).

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Fact-locked master profile, resume-as-code, one-page fit | **done** |
| 1 | Discovery: ATS APIs + Naukri + Internshala, dedupe, LLM ranking, daily digest | next |
| 2 | Auto-apply: Internshala + Naukri | planned |
| 3 | LinkedIn Easy Apply (throttled, local only) | planned |
| 4 | Greenhouse / Lever / Ashby form submission | planned |
| 5 | Workday / iCIMS assisted queue | planned |

## The fact-lock rule

`profile/master.yaml` is the single source of truth. The tailoring engine may
**select, reorder and rephrase** what is in it. It may never introduce a claim,
number, tool or date that is not. Concretely:

- fields marked `status: ASK` are unverified and are dropped from all output
- skills listed under `inferred:` are held back until confirmed
- `core/validate.py` lists everything still unverified — run it before any
  apply phase goes live

An LLM inventing "led a team of 5" on your behalf is a problem you discover in
an interview. The constraint is the point.

## Setup

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt

cp profile/master.example.yaml  profile/master.yaml
cp profile/answers.example.yaml profile/answers.yaml
# fill in your own details — both files are gitignored
```

## Usage

```bash
./.venv/bin/python core/validate.py          # what's still unverified
./.venv/bin/python tailor/build.py --all     # render every job-family variant
./.venv/bin/python tailor/build.py --family fam_ml
./.venv/bin/python core/redact.py            # refresh the public templates
```

Resumes land in `data/resumes/` (gitignored).

### Job families

One cached base resume per family rather than one per job — 10x cheaper than
per-posting generation for ~95% of the benefit. Per-posting keyword injection
happens at apply time and is restricted to terms already in `skills.confirmed`.

`fam_ml` · `fam_ds` · `fam_mlops` · `fam_backend` · `fam_de` · `fam_cv`

### One-page fit

`tailor/build.py` renders, counts pages, and tightens until it fits on one.
The ladder spends typography before content: header and section spacing first,
then font size, and only then does it start dropping the lowest-priority
project. A fresher resume on two pages reads as padding — but so does one that
cut its best project to fit a 25-item skills line.

## Privacy

`profile/master.yaml` and `profile/answers.yaml` hold a home address, phone
number and date of birth. They are gitignored. **This repository is public** —
keep it that way only as long as those files stay untracked. `core/redact.py`
regenerates the committed `.example.yaml` templates with all PII stripped.

Credentials for job portals belong in the macOS Keychain, never in this repo.
