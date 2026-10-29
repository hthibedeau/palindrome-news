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
DATELINES = {"Ottawa": "National", "Toronto": "Ontario", "Hamilton": "Ontario", "London": "Ontario", "Windsor": "Ontario",
             "Kingston": "Ontario", "Sudbury": "Ontario", "Thunder Bay": "Ontario", "Montreal": "Quebec", "Quebec": "Quebec",
             "Gatineau": "Quebec", "Winnipeg": "Manitoba", "Brandon": "Manitoba", "Regina": "Saskatchewan", "Saskatoon": "Saskatchewan",
             "Calgary": "Alberta", "Edmonton": "Alberta", "Lethbridge": "Alberta", "Red Deer": "Alberta", "Vancouver": "B.C.",
             "Victoria": "B.C.", "Kelowna": "B.C.", "Kamloops": "B.C.", "Halifax": "Nova Scotia", "Sydney": "Nova Scotia",
             "Fredericton": "New Brunswick", "Moncton": "New Brunswick", "Saint John": "New Brunswick", "Charlottetown": "P.E.I.",
             "St. John's": "N.L.", "St. John’s": "N.L.", "Whitehorse": "North", "Yellowknife": "North", "Iqaluit": "North"}
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


BLOG_CLOSED = re.compile(r"as it happened|this (?:live )?(?:page|blog) is (?:now )?closed|live coverage (?:has )?ended|we(?:'|’)ve (?:now )?(?:ended|closed|paused) (?:our|this) live|"
                         r"we(?:'|’)re (?:now )?(?:ending|closing|pausing) (?:our|this) live|(?:our|this) live (?:coverage|blog|page) (?:has )?(?:now )?(?:ended|closed)|"
                         r"thank you for following (?:our|this|along)|that(?:'|’)s (?:it|all) for (?:our|this|today(?:'|’)s) live", re.I)


def blog_state(x, now=None):
    """A live blog's real state, from the blog itself (Hannah, Wed Oct 28, 2026: "One of the live updates on the
    Israeli election ended 7 hours ago. That's not live."): the time of its newest POST (the page's "modified" time can
    change with no new post), and whether it has ended (a coverage end time already past, or the blog saying it closed).
    Returns {"updated": iso or None, "ended": bool}."""
    now = now or datetime.now(timezone.utc)
    ok = lambda d: d and d <= now + timedelta(minutes=5)
    posts = []
    for blk in re.findall(r'"liveBlogUpdate"\s*:\s*(\[.*?\])\s*[,}]', x, re.S):
        posts += [ps.to_utc(v) for v in re.findall(r'"datePublished"\s*:\s*"([^"]+)"', blk)]
    posts += [ps.to_utc(v) for v in re.findall(r'<time[^>]*datetime="([^"]+)"[^>]*>', x)][:40]
    posts = [d for d in posts if ok(d)]
    mods = [ps.to_utc(v) for v in re.findall(r'"dateModified"\s*:\s*"([^"]+)"', x)]
    mods += [ps.to_utc(v) for v in re.findall(r'property="article:modified_time" content="([^"]+)"', x)]
    mods = [d for d in mods if ok(d)]
    newest = max(posts) if posts else (max(mods) if mods else None)
    ends = [ps.to_utc(v) for v in re.findall(r'"coverageEndTime"\s*:\s*"([^"]+)"', x)]
    ended = any(d and d <= now for d in ends)
    title = " ".join(re.findall(r"<title>(.*?)</title>|property=\"og:title\" content=\"([^\"]+)\"", x)[0]) if re.search(r"<title>|og:title", x) else ""
    head = re.sub(r"<[^>]+>", " ", x[:200000])
    if BLOG_CLOSED.search(title) or re.search(r'"coverageEndTime"', x) and ended:
        ended = True
    elif BLOG_CLOSED.search(head[:60000]) and not (newest and (now - newest).total_seconds() < 1800):
        ended = True  # the blog says it has closed, and nothing was posted after that
    return {"updated": newest.isoformat() if newest else None, "ended": ended}


def blog_times(page):
    i = page.find("  const LIVENOW = [")
    blk = page[i: page.find("\n  ];", i)] if i >= 0 else ""
    out = []
    for url in re.findall(r"kind: 'updates',[^\n]*?url: '([^']+)'", blk):
        x = ps.curl(url) or ""
        if not x:
            continue
        st = blog_state(x)
        if st["updated"] or st["ended"]:
            out.append({"url": url, "updated": st["updated"], "ended": st["ended"]})
    return out


def todays_canada(page, now, links, per_region=2, total=18):
    """Today's Canada desk (Hannah, Wed Oct 21, 2026: "some of the stories in the Canada section are too old. Make them
    all today stories"). Regional stories published TODAY (Eastern), from every province and territory
    (tools/canada_scan.py), not already on the page, one per story, up to `per_region` per region, most widely
    carried first; each with the outlet's own summary (og:description) and picture (og:image), exactly as published."""
    import html as _h
    import canada_scan as cs
    day = w.eastern(now).split()[0]
    rows = [r for r in cs.collect(18, now) if w.eastern(r[0]).split()[0] == day]
    rows = [r for r in rows if r[4].split("?")[0].rstrip("/") not in links and not FRENCH.search(r[2])
            and not OPINION.search(r[3] + " " + r[4]) and not SOFT.search(r[3] + " " + r[4]) and not re.search(gc.SKIP, r[3], re.I)
            and not re.search(r"/community/|jackpot|Lotto", r[3] + " " + r[4], re.I)]
    rows.sort(key=lambda r: (-len(r[5]), -r[0].timestamp()))
    out, per, seen_words = [], {}, []
    for dt, region, outlet, title, url, others in rows:
        ws = cs.words(title)
        if any(len(ws & x) >= 3 for x in seen_words) or per.get(region, 0) >= per_region:
            continue
        x = ps.curl(url) or ""
        desc = ps.meta(x, "og:description") or ps.meta(x, "description") or ""
        img = ps.meta(x, "og:image") or ""
        desc = " ".join(_h.unescape(desc).split())
        if len(desc) < 40 or not (cs.words(desc) & ws):
            continue  # no summary, or the site's tagline instead of the story's own
        # wire copy in a local feed: the dateline says where the story is ("FRIDAY HARBOR - ...", "OTTAWA - ...")
        dl = re.match(r"([A-Z][A-Z .'’-]{2,30}?)(?:,\s*[A-Za-z. ]+)?\s*[-–—]\s", desc)
        if dl:
            place = dl.group(1).strip().title()
            reg = DATELINES.get(place)
            if reg is None:
                continue  # a story from outside Canada
            region = reg
        seen_words.append(ws)
        per[region] = per.get(region, 0) + 1
        src = ", ".join([outlet] + sorted(o for o in others if not FRENCH.search(o))[:2])
        out.append({"t": w.eastern(dt), "iso": dt.isoformat(), "region": "National" if region == "Canada" else region,
                    "title": _h.unescape(title), "summary": desc, "outlet": src, "url": url, "img": _h.unescape(img)})
        if len(out) >= total:
            break
    out.sort(key=lambda r: r["iso"], reverse=True)
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
    breaking = []
    prev_photos = {s.get("key"): s.get("photo") for s in prev.get("stories", []) if s.get("photo")}
    for st in ps.breaking_stories(a.page):
        key = "top" if st["where"].startswith("Top") else st["where"].split("UPNEXT ")[-1].rstrip(")")
        words = apx.story_words(page, st)
        breaking.append((st, words))
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
        # every newsroom covering it in the last 24 hours (newest report each), for the "newsrooms on this story" strip.
        # A report counts when it names the story (acronyms like MAID only in capitals) and shares a name with the
        # story's current headline and summary, so a word like "interference" alone never pulls in another story.
        if key == "top":
            hm = re.search(r'<section class="breaking tap" id="breaking".*?<h2[^>]*>(.*?)</h2>.*?class="bk-dek"[^>]*>(.*?)</p>', page, re.S)
            head = re.sub(r"<[^>]+>", " ", " ".join(hm.groups())) if hm else ""
        else:
            blk = page[page.find("{ id: '%s'" % key):][:8000]
            head = " ".join(m_.group(1) for m_ in re.finditer(r"\b(?:h|dek): '((?:[^'\\]|\\.)*)'", blk))
        hnames = gc.names(head) - {"canada", "trump", "u.s", "carney", "ottawa"}
        parts = [r"\b%s\b" % re.escape(x) if x.isupper() else "(?i:%s)" % re.escape(x) for x in words]
        rx2 = re.compile("|".join(parts)) if parts else rx
        cov, seen_o = [], set()
        for dt, outlet, title, link, k in items:
            if (now - dt).total_seconds() > 24 * 3600:
                break
            o = clean_outlet(outlet)
            if o in seen_o or OPINION.search(title + " " + link) or FRENCH.search(o):
                continue
            if not (rx2.search(title) or len(gc.names(title) & hnames) >= 2) or (hnames and not gc.names(title) & hnames):
                continue
            seen_o.add(o)
            cov.append({"outlet": o, "url": link, "iso": dt.isoformat(), "t": w.eastern(dt)})
        try:  # repeats folded into the first-posted report, primary sources first (Hannah, Thu Oct 29, 2026)
            import autopilot
            reps = autopilot.dedupe_reports(reps)
        except Exception as e:
            print("dedupe failed:", e)
        stories.append({"key": key, "name": st["name"], "since": since.isoformat() if since else None, "reports": reps, "photo": photo, "coverage": cov})
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

    # what should lead: National Newswatch + CBC's front + coverage (tools/lead_check.py), for the agent runs
    groups = []
    try:
        import lead_check
        groups = lead_check.rank([(d, o, t, l) for d, o, t, l, _ in items], now)
        leads = [{"score": g["score"], "title": g["lead"][0], "url": g["lead"][1], "outlets": len(g["outlets"]), "why": g["why"], "theme": g.get("theme", "")}
                 for g in groups[:10]]
    except Exception as e:  # never block the run
        print("lead check failed:", e)
        leads = []
    try:
        canada = todays_canada(page, now, links)
    except Exception as e:  # never block the run
        print("canada failed:", e)
        canada = []
    out = {"checked": now.isoformat(), "checkedLabel": w.eastern(now), "stories": stories,
           "wire": [r["row"] for r in rows], "blogs": blog_times(page), "leads": leads, "canada": canada}
    # the code runs the page (Hannah, Tue Oct 27, 2026): auto top stories, Watch clips, U.S. front pages
    import autopilot
    out.update(autopilot.run(page, items, groups, breaking, now, imgdir, prev))
    os.makedirs(root, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    # keep only the photos still in use
    used = {os.path.basename(s["photo"]["src"]) for s in stories + (out.get("auto") or {}).get("stories", []) if s.get("photo")}
    used |= {os.path.basename(b["img"]) for b in out.get("bds") or [] if b.get("img")}
    for f in glob.glob(os.path.join(imgdir, "*.jpg")):
        if os.path.basename(f) not in used:
            os.remove(f)
    print(f"wrote {a.out}: {len(stories)} stories, {len(out['wire'])} wire items, {len(out['blogs'])} blogs")


if __name__ == "__main__":
    main()
