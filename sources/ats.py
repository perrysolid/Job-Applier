#!/usr/bin/env python
"""Discovery adapters for company-hosted ATS boards.

Greenhouse, Lever and Ashby all publish their job boards over zero-auth JSON
APIs intended for third-party use. No key, no anti-bot, no ToS grey area --
this is the clean tier, and it is where the jobs actually worth getting live.
"""
import hashlib, html, json, pathlib, random, re, time, urllib.error, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
TIMEOUT = 20
CACHE = pathlib.Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_TTL = 6 * 3600          # boards change slowly; a daily run needs one fetch
RETRIES = 3


def _get(url, use_cache=True):
    """Fetch with a disk cache and backoff.

    These APIs rate-limit an unauthenticated client that re-fetches the whole
    registry repeatedly -- boards start returning empty rather than erroring,
    which silently looks like "this company has no jobs". Caching plus backoff
    is what keeps a daily run honest.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".json")
    if use_cache and key.exists() and time.time() - key.stat().st_mtime < CACHE_TTL:
        return json.loads(key.read_text())

    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.load(r)
            key.write_text(json.dumps(data))
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (404, 403):        # dead slug -- retrying will not help
                raise
        except Exception as e:
            last = e
        time.sleep((2 ** attempt) + random.random())

    if key.exists():                        # serve stale rather than report empty
        return json.loads(key.read_text())
    raise last


def _text(s, limit=4000):
    """HTML description -> plain text, since that is what the scorer reads."""
    s = html.unescape(s or "")
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", s).strip()[:limit]


def greenhouse(slug):
    d = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    out = []
    for j in d.get("jobs", []):
        out.append({
            "source": "greenhouse",
            "company": j.get("company_name") or slug,
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name"),
            "url": j.get("absolute_url"),
            "apply_url": j.get("absolute_url"),
            "description": _text(j.get("content")),
            "posted_at": (j.get("updated_at") or "")[:10] or None,
        })
    return out


def lever(slug):
    d = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    out = []
    for j in d:
        cat = j.get("categories") or {}
        out.append({
            "source": "lever",
            "company": slug,
            "title": j.get("text", ""),
            "location": cat.get("location"),
            "url": j.get("hostedUrl"),
            "apply_url": j.get("applyUrl"),
            "description": _text(j.get("descriptionPlain") or j.get("description")),
            "posted_at": None,
        })
    return out


def ashby(slug):
    d = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    out = []
    for j in d.get("jobs", []):
        out.append({
            "source": "ashby",
            "company": slug,
            "title": j.get("title", ""),
            "location": j.get("location"),
            "url": j.get("jobUrl") or j.get("applyUrl"),
            "apply_url": j.get("applyUrl"),
            "description": _text(j.get("descriptionPlain") or j.get("descriptionHtml")),
            "posted_at": (j.get("publishedAt") or "")[:10] or None,
        })
    return out


ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


def fetch(board, slug):
    """Fetch one board. A dead slug is normal (companies migrate ATS) -- the
    caller gets an empty list and a reason rather than an exception."""
    try:
        return ADAPTERS[board](slug), None
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except Exception as e:
        return [], type(e).__name__


if __name__ == "__main__":
    for b, s in (("greenhouse", "razorpaysoftwareprivatelimited"), ("lever", "spotify"), ("ashby", "ramp")):
        jobs, err = fetch(b, s)
        print(f"{b:11s} {s:32s} {len(jobs):4d} jobs  {err or ''}")
        if jobs:
            j = jobs[0]
            print(f"            e.g. {j['title'][:60]!r} @ {j['location']}")
