#!/usr/bin/env python3
"""Autoupdate: keeps the live page current BY ITSELF, every 10 minutes, with no one at the keyboard.

Hannah, Wed Oct 21, 2026: "I need the program to continually scan for the latest news. The Wainwright story is not
the most up to date" and "you have not kept the page up to date. I want you to create a code that does this."

GitHub Actions (.github/workflows/autoupdate.yml) runs this every 10 minutes:

    python3 tools/autoupdate.py --page index.html --out live/auto.json

It reads every feed and front page in tools/wire_scan.py (about 85 newsrooms and official sources) and writes
live/auto.json, which the page fetches every 2 minutes and shows straight away:

  stories  for each Breaking/Developing story on the page: every report on it published AFTER the story's last
           development (data-lastdev / newest timeline line) that the page does not link yet, newest first, with the
           outlet's own time, headline and link. The page lists them under the story's summary as
           "Newest reports · checked automatically".
           Plus the newest news photo on the story, with its own caption and credit, posted after the page's photo
           (same rules as tools/auto_photo.py: caption + credit, at least 900 px, not a file or archive photo, caption
           about this story). The image is saved in live/img/ so it loads from our own site.
  wire     the newest headlines (last 3 hours) from every newsroom, one per story, that the page does not have yet,
           exactly as the outlet wrote them. The page puts any newer than its own newest wire item at the top.
  blogs    for each live blog in LIVENOW: its real newest-post time (dateModified), so the page shows the right
           "Newest post" time and keeps an active blog up.

Rules kept: real headlines, times, captions and links only (nothing written or guessed); The Globe and Mail is never
listed (subscribers only, never the first click); Yahoo links only for The Canadian Press; no X/Instagram/LinkedIn;
English-language outlets only on the wire and story lists. The agent runs (full update / live check) still read the
reports and write the story copy; this keeps the page fresh between them.
"""
import argparse
import glob
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wire_scan as w  # noqa: E402
import photo_scan as ps  # noqa: E402
import auto_photo as apx  # noqa: E402
import gap_check as gc  # noqa: E402

FRENCH = re.compile(r"Radio-Canada|La Presse|Le Devoir|Journal de Montréal|TVA Nouvelles|Le Soleil", re.I)
US = re.compile(r"CBS|ABC News|NBC|PBS|Fox News|The Hill\b", re.I)
WORLDO = re.compile(r"Al Jazeera|BBC|Guardian|Euronews|Japan Times|Kyiv Independent|Middle East Eye", re.I)
OPINION = re.compile(r"^[A-Z][\w.'’-]+ [A-Z][\w.'’-]+: |\| ?Opinion|^Opinion[:|]|/opinion/|/editorials?/|/columnists?/|/letters/", re.I)
SOFT = re.compile(r"jackpot|\bcaptain\b|signs with|rugby|hockey|soccer|golf|tennis|playoffs?|season opener|lotto|lottery|recipe|horoscope|Birkin|photography competition|burger|deals?\b|sale\b|celebrity|royal family|"
                  r"/(arts?|culture|entertainment|lifestyle|life|style|food|travel|shopping|sports?|wellness|living|fashion|movies|music|tv)/", re.I)
DESKS = re.compile(r"^(CBC News|CTV News|Global News|The Canadian Press|Toronto Star|National Post|APTN News|Prime Minister|"
                   r"Bank of Canada|CBS News|ABC News|NBC News|PBS NewsHour|BBC News|Al Jazeera|The Guardian)", re.I)
# regional pages of the national networks: local stories, wire-worthy only when other newsrooms carry them too
LOCALPATH = re.compile(r"ctvnews\.ca/(?!politics|world|business|canada|health|climate|sci-tech)[a-z-]+/|cbc\.ca/news/canada/[a-z-]+/|"
                       r"globalnews\.ca/news/\d+/[^/]*-(?:toronto|ottawa|calgary|edmonton|winnipeg|bc|halifax|montreal)")
SPONSORED = re.compile(r"sponsored|partner content|advertorial|Shine a Spotlight", re.I)
CANADA = re.compile(r"\b(Canad\w*|Ottawa|Carney|Poilievre|Ontario|Quebec|Québec|Alberta|B\.C\.|British Columbia|Manitoba|Saskatchewan|"
                    r"Nova Scotia|N\.S\.|New Brunswick|N\.B\.|P\.E\.I\.|Newfoundland|Yukon|Nunavut|N\.W\.T\.|Toronto|Montreal|Vancouver|"
                    r"Calgary|Edmonton|Winnipeg|Halifax|Regina|Saskatoon|Victoria|RCMP|Ont\.|Alta\.|Sask\.|Man\.|Que\.)\b")
USA = re.compile(r"\b(Trump|U\.S\.|White House|Congress|Senate|Republican|Democrat|Ohio|Texas|California|Florida|New York|Washington|Pentagon|FBI)\b")
STORY_HOURS = 12
WIRE_HOURS = 3


def all_items():
    jobs = [(w.rss, (o, u)) for o, u in w.FEEDS] + [(w.front, (o, u, m, b)) for o, u, m, b in w.FRONTS]
    out = []
    with ThreadPoolExecutor(16) as ex:
        for got in ex.map(lambda j: _safe(j[0], j[1]), jobs):
            out += got
    return out


def _safe(f, args):
    try:
        return f(*args) or []
    except Exception:
        return []


def ok_item(outlet, link):
    if "theglobeandmail.com" in link or "subscribers" in outlet or FRENCH.search(outlet):
        return False
    if "yahoo.com" in link and "Canadian Press" not in outlet:
        return False
    return not re.search(r"(twitter|x|instagram|linkedin)\.com/", link)


def clean_outlet(o):
    return re.sub(r"\s*\((?:politics|Canada|subscribers)\)$", "", o)


def kind_of(outlet, link, title=""):
    if CANADA.search(title) and not re.search(r"/world|/us/|/u-s", link):
        return "Politics" if re.search(r"/politics", link) else "Canada"
    if USA.search(title):
        return "U.S."
    if re.search(r"/business|/money|financialpost|bnnbloomberg|thelogic", link) or "Bank of Canada" in outlet:
        return "Business"
    if re.search(r"/politics", link) or "Prime Minister" in outlet:
        return "Politics"
    if re.search(r"/world", link) or WORLDO.search(outlet):
        return "World"
    return "Latest"


def story_since(page, st, now):
    """When the story last developed on the page (UTC)."""
    if st["where"].startswith("Top"):
        m = re.search(r'data-lastdev="([^"]*)"', page)
        return ps.to_utc(m.group(1)) if m else None
    ev = st["where"].split("UPNEXT ")[-1].rstrip(")")
    blk = page[page.find("{ id: '%s'" % ev):]
    blk = blk[: blk.find("schedule: [")]
    best = None
    for lbl in re.findall(r"\['((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2}:\d{2} [ap]\.m\.)'", blk):
        d = label_to_utc(lbl, now)
        if d and (best is None or d > best):
            best = d
    return best


def label_to_utc(lbl, now):
    m = re.match(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d{1,2}):(\d{2}) (a|p)\.m\.", lbl)
    if not m:
        return None
    off = timedelta(hours=-4 if _dst(now) else -5)
    loc = now + off
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    back = (loc.weekday() - days.index(m.group(1))) % 7
    h = int(m.group(2)) % 12 + (12 if m.group(4) == "p" else 0)
    d = (loc - timedelta(days=back)).replace(hour=h, minute=int(m.group(3)), second=0, microsecond=0)
    return d - off


def _dst(dt):
    y = dt.year
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    return mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7, hours=7) <= dt < nov1 + timedelta(days=(6 - nov1.weekday()) % 7, hours=6)


def best_photo(page, st, since, now, outdir, skip):
    """Newest qualifying photo on the story (auto_photo rules), saved under live/img/. None if nothing newer."""
    words = apx.story_words(page, st)
    rx = re.compile("|".join(re.escape(x) for x in words), re.I)
    for c in apx.candidates(st):
        if c["src"] in skip or (since and c["when"] <= since) or (now - c["when"]).total_seconds() > 36 * 3600:
            continue
        if apx.old_photo(c, now) or not rx.search(c["caption"]) or re.search(r"handout video|campaign", c["credit"], re.I):
            continue
        im = apx.fetch_ok(c["src"])
        if im is None:
            continue
        outlet = apx.outlet_name(c["outlet"], c["url"])
        fn = f"{apx.slug(outlet)}-{apx.slug(st['name'])}-{c['when']:%m%d-%H%M}.jpg"
        path = os.path.join(outdir, fn)
        if not os.path.exists(path):
            im.convert("RGB").save(path, quality=84)
        return {"src": "live/img/" + fn, "orig": c["src"], "caption": f"{c['caption'].rstrip('.')}. ({c['credit']}) — via {outlet}",
                "credit": f"{c['credit']}, via {outlet}", "alt": c["caption"][:160], "outlet": outlet, "url": c["url"],
                "when": c["when"].isoformat(), "t": w.eastern(c["when"])}
    return None


def blog_times(page):
    i = page.find("  const LIVENOW = [")
    blk = page[i: page.find("\n  ];", i)] if i >= 0 else ""
    out = []
    for url in re.findall(r"kind: 'updates',[^\n]*?url: '([^']+)'", blk):
        x = ps.curl(url) or ""
        ds = [ps.to_utc(v) for v in re.findall(r'"dateModified"\s*:\s*"([^"]+)"', x)]
        ds += [ps.to_utc(v) for v in re.findall(r'property="article:modified_time" content="([^"]+)"', x)]
        ds = [d for d in ds if d and d <= datetime.now(timezone.utc) + timedelta(minutes=5)]
        if ds:
            out.append({"url": url, "updated": max(ds).isoformat()})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--out", default="live/auto.json")
    ap.add_argument("--no-photos", action="store_true")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    page = open(a.page, encoding="utf-8").read()
    root = os.path.dirname(os.path.abspath(a.out))
    imgdir = os.path.join(root, "img")
    os.makedirs(imgdir, exist_ok=True)
    try:
        prev = json.load(open(a.out, encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    links = set(u.split("?")[0].rstrip("/") for u in re.findall(r"https?://[^\s\"'<>]+", page))
    items = []
    seen = set()
    for dt, outlet, title, link in all_items():
        k = link.split("?")[0].rstrip("/")
        if not dt or k in seen or (dt - now).total_seconds() > 600 or not ok_item(outlet, link):
            continue
        seen.add(k)
        items.append((dt, clean_outlet(outlet), title, link, k))
    items.sort(reverse=True)

    stories = []
    prev_photos = {s.get("key"): s.get("photo") for s in prev.get("stories", []) if s.get("photo")}
    for st in ps.breaking_stories(a.page):
        key = "top" if st["where"].startswith("Top") else st["where"].split("UPNEXT ")[-1].rstrip(")")
        words = apx.story_words(page, st)
        rx = re.compile("|".join(re.escape(x) for x in words), re.I)
        since = story_since(page, st, now)
        reps = []
        for dt, outlet, title, link, k in items:
            if k in links or not rx.search(title) or (now - dt).total_seconds() > STORY_HOURS * 3600 or OPINION.search(title + " " + link):
                continue
            if any(r["title"].lower() == title.lower() for r in reps):
                continue
            if since and dt <= since:
                continue
            reps.append({"t": w.eastern(dt), "iso": dt.isoformat(), "outlet": outlet, "title": title, "url": link})
            if len(reps) >= 8:
                break
        # photo: newer than the page's own photo
        if key == "top":
            m = re.search(r'data-photo-set="([^"]*)"', page)
        else:
            blk = page[page.find("{ id: '%s'" % key):]
            m = re.search(r"photoSet: '([^']*)'", blk[: blk.find("schedule: [")])
        pset = ps.to_utc(m.group(1)) if m else None
        photo = None if a.no_photos else best_photo(page, st, pset, now, imgdir, set())
        old = prev_photos.get(key)
        if not photo and old and os.path.exists(os.path.join(root, "..", old["src"])) and (not pset or ps.to_utc(old["when"]) > pset):
            photo = old
        stories.append({"key": key, "name": st["name"], "since": since.isoformat() if since else None, "reports": reps, "photo": photo})
        print(f"{st['name']}: {len(reps)} newer report(s); photo {'NEW ' + photo['src'] if photo else 'none newer'}")

    # wire: one item per story, not on the page, last WIRE_HOURS
    # group the last WIRE_HOURS by story (gap_check's rule); a story makes the wire when 2+ newsrooms carry it or a
    # national news desk does; opinion, lifestyle, sports and the like never do. Newest report of each story, newest first.
    groups = []
    for dt, outlet, title, link, k in items:
        if (now - dt).total_seconds() > WIRE_HOURS * 3600:
            continue
        if re.search(gc.SKIP, title, re.I) or SOFT.search(title + " " + link) or OPINION.search(title + " " + link):
            continue
        n, kk = gc.names(title), gc.keys(title)
        for g in groups:
            if len(n & g["n"]) >= 2 or (len(n & g["n"]) >= 1 and len(kk & g["k"]) >= 2) or len(kk & g["k"]) >= 4:
                g["rows"].append((dt, outlet, title, link, k)); g["n"] |= n; g["k"] |= kk
                break
        else:
            groups.append({"n": set(n), "k": set(kk), "rows": [(dt, outlet, title, link, k)]})
    in_stories = {r["url"] for st in stories for r in st["reports"]}
    rows = []
    for g in groups:
        if any(r[4] in links or r[3] in in_stories for r in g["rows"]):
            continue  # the page already carries this story
        outlets = {r[1] for r in g["rows"]}
        desk = [r for r in g["rows"] if DESKS.search(r[1]) and not SPONSORED.search(r[2])]
        if len(outlets) >= 2:
            lead = (desk or g["rows"])[0]
        else:
            lead = next((r for r in desk if not LOCALPATH.search(r[3])), None)
        if not lead:
            continue
        dt, outlet, title, link, k = lead
        rows.append([w.eastern(dt), kind_of(outlet, link, title), title, outlet, link, dt.isoformat(), len(outlets)])
    rows.sort(key=lambda r: r[5], reverse=True)
    rows = [{"row": r} for r in rows[:25]]

    out = {"checked": now.isoformat(), "checkedLabel": w.eastern(now), "stories": stories,
           "wire": [r["row"] for r in rows], "blogs": blog_times(page)}
    os.makedirs(root, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    # keep only the photos still in use
    used = {os.path.basename(s["photo"]["src"]) for s in stories if s.get("photo")}
    for f in glob.glob(os.path.join(imgdir, "*.jpg")):
        if os.path.basename(f) not in used:
            os.remove(f)
    print(f"wrote {a.out}: {len(stories)} stories, {len(out['wire'])} wire items, {len(out['blogs'])} blogs")


if __name__ == "__main__":
    main()
