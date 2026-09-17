#!/usr/bin/env python
"""Discovery adapter for Internshala.

Listing pages are served fully rendered over plain HTTPS and need no login to
read, so discovery here is a straight parse. Applying is a different matter and
lives in apply/ -- this module only reads.

Internshala is the highest-volume source for Indian off-campus fresher roles,
which is precisely why it matters more than the ATS tier for hitting a daily
application target.
"""
import gzip, html, re, time, urllib.parse, urllib.request

BASE = "https://internshala.com"
UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip",
}

# One card per posting. Non-greedy up to the next card start.
CARD = re.compile(r'<div class="container-fluid individual_internship.*?(?=<div class="container-fluid individual_internship|<div id=.internship_list_container)', re.S)
TITLE = re.compile(r'class="job-title-href"[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', re.S)
COMPANY = re.compile(r'class="company-name"[^>]*>(.*?)</p>', re.S)
LOCATION = re.compile(r'class="row-1-item locations".*?<span>\s*<a[^>]*>(.*?)</a>', re.S)
STIPEND = re.compile(r'stipend[^>]*>(?:<[^>]+>)*\s*([^<]{2,40})', re.I)
POSTED = re.compile(r'status-(?:success|info)[^>]*>\s*(.*?)\s*<', re.S)
EMP_TYPE = re.compile(r'employment_type="([^"]+)"')


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return " ".join(html.unescape(s).split())


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return raw.decode("utf-8", "ignore")


def parse(page_html):
    out = []
    for card in CARD.findall(page_html):
        t = TITLE.search(card)
        c = COMPANY.search(card)
        if not t or not c:
            continue
        href = t.group(1)
        loc = LOCATION.search(card)
        stip = STIPEND.search(card)
        posted = POSTED.search(card)
        emp = EMP_TYPE.search(card)
        out.append({
            "source": "internshala",
            "company": _clean(c.group(1)),
            "title": _clean(t.group(2)),
            "location": _clean(loc.group(1)) if loc else None,
            "url": urllib.parse.urljoin(BASE, href),
            "apply_url": urllib.parse.urljoin(BASE, href),
            # The card carries no description; the detail page does. Discovery
            # scores on what the card gives and the apply step fetches the rest,
            # so one HTTP request per posting is not spent during discovery.
            "description": " ".join(filter(None, [
                _clean(t.group(2)),
                f"stipend {_clean(stip.group(1))}" if stip else "",
                (emp.group(1) if emp else ""),
            ])),
            "posted_at": None,
            "posted_label": _clean(posted.group(1)) if posted else None,
            "employment_type": emp.group(1) if emp else None,
        })
    return out


def search(category="computer-science-internship", pages=3, delay=2.0):
    """Walk N pages of one Internshala category."""
    jobs = []
    for page in range(1, pages + 1):
        url = f"{BASE}/internships/{category}/page-{page}/"
        try:
            got = parse(_get(url))
        except Exception as e:
            print(f"  internshala page-{page}: {type(e).__name__}")
            break
        if not got:
            break
        jobs += got
        time.sleep(delay)          # deliberate: this is someone else's server
    return jobs


CATEGORIES = [
    "computer-science-internship",
    "machine-learning-internship",
    "data-science-internship",
    "artificial-intelligence-internship",
    "python-django-internship",
    "software-development-internship",
    "backend-development-internship",
    "data-analytics-internship",
]


def fetch_all(categories=None, pages=2):
    seen, out = set(), []
    for cat in (categories or CATEGORIES):
        for j in search(cat, pages=pages):
            if j["url"] in seen:
                continue
            seen.add(j["url"])
            out.append(j)
    return out


if __name__ == "__main__":
    jobs = search("machine-learning-internship", pages=1)
    print(f"{len(jobs)} internships parsed\n")
    for j in jobs[:6]:
        print(f"  {j['title'][:50]:50s} | {j['company'][:22]:22s} | {j['location']}")
