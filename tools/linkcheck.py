#!/usr/bin/env python3
"""Link check, by itself, every hour (Hannah: "always check for errors and then find a working source").

GitHub Actions (.github/workflows/linkcheck.yml) runs:

    python3 tools/linkcheck.py --page index.html --out live/links.json

It opens every outlet link on the page (story pages, videos, live blogs, sources) and writes live/links.json:
  dead   {url: when it was first found dead}. Only a 404 or 410 answer counts, found on two checks in a row, so a site
         that is slow, blocks robots or is down for a minute is never treated as dead.
The page reads it and hides any card, wire item, clip or list item whose link is dead, so a reader never taps into an
error page. The Breaking story itself is never hidden; its dead links are listed in the file for the next edit.
"""
import argparse
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
SKIP = re.compile(r"\.(jpg|jpeg|png|webp|gif|svg|mp3|mp4|js|css|woff2?|json)(\?|$)|i\.ytimg|/resizer/|fonts\.(googleapis|gstatic)|cdnjs|"
                  r"jsdelivr|unpkg|raw\.githubusercontent|hthibedeau\.github|github\.com|claude\.ai|w3\.org|schema\.org|"
                  r"(twitter|x|instagram|linkedin|facebook|tiktok)\.com", re.I)


def status(url):
    for method in (["-I"], []):
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-L", "-m", "20", "-A", UA, "-w", "%{http_code}"] + method + ["--", url],
                           capture_output=True, text=True)
        code = r.stdout.strip()[-3:]
        if code in ("200", "404", "410") or (code.isdigit() and int(code) < 400):
            return int(code)
    return int(code) if code.isdigit() else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--out", default="live/links.json")
    a = ap.parse_args()
    page = open(a.page, encoding="utf-8").read()
    urls = sorted({u.rstrip(".,;") for u in re.findall(r"""https?://[^\s"'<>\\)]+""", page) if not SKIP.search(u)})
    try:
        prev = json.load(open(a.out, encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    suspect_before = prev.get("suspect", {})
    dead_before = prev.get("dead", {})
    now = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(32) as ex:
        codes = dict(zip(urls, ex.map(status, urls)))
    dead, suspect = {}, {}
    for u, c in codes.items():
        if c in (404, 410):
            if u in dead_before or u in suspect_before:
                dead[u] = dead_before.get(u) or suspect_before[u]
            else:
                suspect[u] = now
    out = {"checked": now, "count": len(urls), "dead": dead, "suspect": suspect}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"checked {len(urls)} links: {len(dead)} dead, {len(suspect)} suspect")
    for u in dead:
        print("DEAD", u)


if __name__ == "__main__":
    main()
