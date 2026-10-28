#!/usr/bin/env python3
"""Autopilot: the code runs the page, not Claude (Hannah, Tue Oct 27, 2026: "I dont want to rely on claude to run my
site. I want the code to do it" and "everything that we have built should be put into the code").

Called by tools/autoupdate.py every 10 minutes on GitHub Actions. Adds to live/auto.json:

  auto    The two biggest stories right now, built with no one at the keyboard: ranked by tools/lead_check.py (National
          Newswatch order, CBC's front page, how many newsrooms carry it). For each: the newest report's own headline
          and summary, credited and linked; "First reported by"; the newest photo with its own caption and credit;
          every newsroom carrying it, newest first. "Breaking" for an hour after the newest report, then "Developing".
          takeover = true when the hand-written top story has had no development for TAKEOVER_HOURS: the page then
          shows the auto top story in its place, so the top of the page is never stale.
  clips   New uploads (last 36 hours) from the networks' official YouTube channels, checked against the channel's own
          name on YouTube, Canadian and U.S. networks first. The page adds them to Watch with a "New" badge.
  ledes   "What America's newsrooms are leading with": the top story in each U.S. newsroom's top-stories feed, with
          its own headline, picture and time.

Nothing is written or guessed: every headline, summary, caption, time and picture is the outlet's own, credited.
"""
import hashlib
import html as _h
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wire_scan as w  # noqa: E402
import photo_scan as ps  # noqa: E402

TAKEOVER_HOURS = 3      # hand-written top story with nothing new for this long gives way to the auto top story
BREAKING_MIN = 60       # newest report within this many minutes: "Breaking"; otherwise "Developing"
MIN_OUTLETS = 3         # an auto story needs at least this many newsrooms
CLIP_HOURS = 36
WEAK = set("""here's here’s what what's why how who when watch live breaking update updates opinion analysis says said new
canada canadian canadians ottawa u.s us america american trump carney the a this that it's state states department
president minister government police city court federal provincial premier mayor report reports""".split())
SPORT = re.compile(r"football|basketball|baseball|\bNHL\b|\bNFL\b|\bNBA\b|\bMLB\b|World Series|Stanley Cup|Blue Jays|Maple Leafs|Raptors|quarterback|/sports?/", re.I)
FRENCH_TEXT = re.compile(r"\b(les|des|une|pour|avec|dans|sur|qui|est|au|aux|du)\b.*\b(les|des|une|pour|avec|dans|sur|qui|est|au|aux|du)\b", re.I)
PARTY = set("liberal liberals conservative conservatives ndp bloc green greens party parties caucus".split())
VIDEO = re.compile(r"/videos?/|/player/|/watch|^Watch:|^WATCH:|^Video:", re.I)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# Official YouTube channels: (network as shown on Palindrome, address, region). The channel's own name on its page
# must match OFFICIAL in tools/network_youtube.py, or the channel is skipped (protects against a wrong address).
CHANNELS = [
    ("CBC News", "@CBCNews", "ca"), ("CTV News", "@CTVNews", "ca"), ("Global News", "@globalnews", "ca"),
    ("CityNews", "@CityNews", "ca"), ("CP24", "@CP24", "ca"), ("CPAC", "@CPAC", "ca"), ("APTN News", "@APTNNews", "ca"),
    ("CBS News", "@CBSNews", "us"), ("NBC News", "@NBCNews", "us"), ("ABC News", "@ABCNews", "us"),
    ("PBS NewsHour", "@PBSNewsHour", "us"), ("CNN", "channel/UCupvZG-5ko_eiXAupbDfxWw", "us"), ("Fox News", "@FoxNews", "us"),
    ("CNBC", "@CNBCtelevision", "us"), ("C-SPAN", "@cspan", "us"), ("Associated Press", "@AssociatedPress", "us"),
    ("Bloomberg", "channel/UCIALMKvObZNtJ6AmdCLP7Lg", "us"),
    ("BBC News", "@BBCNews", "world"), ("Reuters", "@Reuters", "world"), ("Sky News", "@SkyNews", "world"),
    ("DW News", "@dwnews", "world"), ("Al Jazeera", "@aljazeeraenglish", "world"),
]
CLIPS_PER_NET = 2
SKIP_CLIP = re.compile(r"#shorts|\blive\b.*\b24/7\b|lottery|horoscope|\bNFL\b|\bNBA\b|\bNHL\b|\bMLB\b|highlights|recipe|full game", re.I)

US_FEEDS = [
    ("CBS News", "https://www.cbsnews.com/latest/rss/main"),
    ("ABC News", "https://abcnews.go.com/abcnews/topstories"),
    ("NBC News", "https://feeds.nbcnews.com/nbcnews/public/news"),
    ("PBS News", "https://www.pbs.org/newshour/feeds/rss/headlines"),
    ("Fox News", "https://moxie.foxnews.com/google-publisher/latest.xml"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
    ("The Hill", "https://thehill.com/homenews/feed/"),
]


def curl(url, timeout=25):
    r = subprocess.run(["curl", "-sL", "-m", str(timeout), "-A", UA, "-H", "Accept-Language: en-CA,en;q=0.9", "--", url], capture_output=True)
    return r.stdout.decode("utf-8", "ignore") if r.returncode == 0 else ""


def clean(s):
    return " ".join(_h.unescape(s or "").split())


# Same owner counts as one newsroom (house rule 1); identical wire headlines count once too.
OWNERS = {"CTV News": "Bell", "CP24": "Bell", "BNN Bloomberg": "Bell", "CityNews": "Rogers", "Global News": "Corus",
          "National Post": "Postmedia", "Toronto Sun": "Postmedia", "Ottawa Citizen": "Postmedia", "Calgary Herald": "Postmedia",
          "Edmonton Journal": "Postmedia", "Vancouver Sun": "Postmedia", "The Province": "Postmedia", "Financial Post": "Postmedia",
          "Toronto Star": "Torstar", "Times Colonist": "Glacier", "Winnipeg Free Press": "FP", "The Canadian Press": "CP"}
INFO_CACHE = {}


def owner(outlet):
    o = re.sub(r" \(.*\)$", "", outlet)
    for k, v in OWNERS.items():
        if o.startswith(k):
            return v
    return o


def independent(reps):
    """How many independent newsrooms: one per owner, and copies of the same wire headline count once."""
    seen_t, owners = set(), set()
    for r in reps:
        t = re.sub(r"\W", "", r[2].lower())
        if t in seen_t:
            continue
        seen_t.add(t)
        owners.add(owner(r[1]))
    return len(owners)


def page_info(url):
    if url in INFO_CACHE:
        return INFO_CACHE[url]
    INFO_CACHE[url] = got = _page_info(url)
    return got


def _page_info(url):
    """The article's own summary, picture (with caption and credit if it states them) and site name."""
    x = curl(url)
    if not x:
        return {}
    info = {"desc": clean(ps.meta(x, "og:description") or ps.meta(x, "description")),
            "img": clean(ps.meta(x, "og:image")), "alt": clean(ps.meta(x, "og:image:alt")), "caption": "", "credit": ""}
    acc = []
    for b in ps.ld_blocks(x):
        ps.walk(b, acc)
    for a in acc:
        if a.get("caption") and a.get("src") and ps.key(ps.best_src(a["src"])) == ps.key(ps.best_src(info["img"] or "")):
            info["caption"] = clean(a.get("caption"))
            info["credit"] = clean(a.get("credit")) if isinstance(a.get("credit"), str) else ""
            break
    return info


def save_photo(src, outdir, tag):
    try:
        from PIL import Image
        import io
    except ImportError:
        return None
    data = subprocess.run(["curl", "-sL", "-m", "25", "-A", UA, "--", src], capture_output=True).stdout
    try:
        im = Image.open(io.BytesIO(data))
    except Exception:
        return None
    if im.size[0] < 600:
        return None
    if im.size[0] > 1280:
        im = im.resize((1280, round(im.size[1] * 1280 / im.size[0])))
    fn = f"{tag}-{hashlib.md5(src.encode()).hexdigest()[:10]}.jpg"
    path = os.path.join(outdir, fn)
    if not os.path.exists(path):
        im.convert("RGB").save(path, quality=82)
    return "live/img/" + fn


def _ok(outlet, link, title):
    import autoupdate as au
    return au.ok_item(outlet, link) and not au.OPINION.search(title + " " + link) and not au.FRENCH.search(outlet)


def core_rows(g):
    """The reports in a ranked group that are really this one story (newest first), or [] if it isn't one story."""
    import gap_check as gc
    from collections import Counter
    rows = sorted({r[3].split("?")[0]: r for r in g["rows"] if _ok(r[1], r[3], r[2]) and not SPORT.search(r[2] + " " + r[3])}.values(), reverse=True)
    freq = Counter(x for r in rows for x in gc.names(r[2]) if x not in WEAK)
    if not freq or freq.most_common(1)[0][1] < 3:
        return None
    anchor = freq.most_common(1)[0][0]
    co = Counter(x for r in rows if anchor in gc.names(r[2]) for x in gc.names(r[2]) if x not in WEAK)
    core = {anchor} | {x for x, n in co.items() if n >= 2}
    return [r for r in rows if anchor in gc.names(r[2]) or len(gc.names(r[2]) & core) >= 2], core


def build_story(g, now, imgdir, prev):
    import autoupdate as au
    import gap_check as gc
    from collections import Counter
    got = core_rows(g)
    if not got or not got[0]:
        return None
    rows, core = got
    if not rows:
        return None
    per = {}
    for r in rows:  # newest report from each newsroom
        per.setdefault(au.clean_outlet(r[1]), r)
    reps = sorted(per.values(), reverse=True)
    if len(reps) < MIN_OUTLETS:
        return None
    first = min(rows)
    names = sorted(core or g["n"], key=len, reverse=True)[:6]
    key = "auto-" + hashlib.md5(first[3].encode()).hexdigest()[:8]
    old = next((s for s in prev if s.get("first", {}).get("url") == first[3]), None)
    # headline and summary: the newest report that has its own summary
    lead, info = reps[0], {}
    for r in [x for x in reps if not VIDEO.search(x[3] + " " + x[2])][:5]:
        pi = page_info(r[3])
        if len(pi.get("desc", "")) >= 40:
            lead, info = r, pi
            break
    photo = None
    for r in [lead] + [x for x in reps[:6] if x is not lead]:
        pi = info if r is lead else page_info(r[3])
        if not pi.get("img"):
            continue
        if old and old.get("photo") and old["photo"].get("orig") == pi["img"] and os.path.exists(os.path.join(imgdir, os.path.basename(old["photo"]["src"]))):
            photo = old["photo"]
            break
        src = save_photo(pi["img"], imgdir, key)
        if not src:
            continue
        outlet = au.clean_outlet(r[1])
        cap = pi.get("caption") or pi.get("alt") or ""
        credit = pi.get("credit") or ""
        caption = (cap.rstrip(".") + "." if cap else "Photo") + (f" ({credit})" if credit else "") + f" — via {outlet}"
        photo = {"src": src, "orig": pi["img"], "caption": caption, "alt": cap[:160] or r[2], "outlet": outlet, "url": r[3]}
        break
    newest = reps[0][0]
    # What each newsroom reports: every outlet's own lead sentence (og:description), side by side
    with ThreadPoolExecutor(6) as ex:
        infos = list(ex.map(lambda r: page_info(r[3]), reps[:8]))
    descs, seen_d = {}, set()
    for r, pi in zip(reps[:8], infos):
        d = (pi or {}).get("desc", "")
        k = re.sub(r"\W", "", d.lower())[:80]
        if len(d) >= 40 and k not in seen_d:
            seen_d.add(k)
            descs[r[3]] = d if len(d) <= 300 else d[:300].rsplit(" ", 1)[0] + "…"
    return {
        "key": key, "words": names, "score": g["score"], "outlets": len(per),
        "tag": "Breaking" if (now - newest).total_seconds() < BREAKING_MIN * 60 else "Developing",
        "title": clean(lead[2]), "url": lead[3], "outlet": au.clean_outlet(lead[1]), "t": w.eastern(lead[0]), "iso": lead[0].isoformat(),
        "summary": info.get("desc", ""),
        "first": {"outlet": au.clean_outlet(first[1]), "url": first[3], "t": w.eastern(first[0]), "title": clean(first[2])},
        "newest": newest.isoformat(), "photo": photo,
        "independent": independent(reps),
        "reports": [{"t": w.eastern(r[0]), "iso": r[0].isoformat(), "outlet": au.clean_outlet(r[1]), "title": clean(r[2]), "url": r[3],
                     "desc": descs.get(r[3], "")} for r in reps[:14]],
    }


def auto_stories(groups, page, breaking, now, imgdir, prev):
    """The two biggest stories, built from the outlets' own reports. Skips a story already in the Breaking segment
    unless the hand-written top story is stale (then the auto version replaces it)."""
    m = re.search(r'data-lastdev="([^"]*)"', page)
    lastdev = ps.to_utc(m.group(1)) if m else None
    stale = lastdev is None or (now - lastdev).total_seconds() > TAKEOVER_HOURS * 3600
    rxs = []
    for st, words in breaking:
        if words:
            rxs.append((st, re.compile("|".join(re.escape(x) for x in words), re.I)))
    out = []
    for g in groups[:12]:
        hits = [st for st, rx in rxs if sum(1 for r in g["rows"] if rx.search(r[2])) >= 2]
        on_top = any(st["where"].startswith("Top") for st in hits)
        on_event = any(not st["where"].startswith("Top") for st in hits)
        if on_event or (on_top and not stale):
            continue  # the page already carries it, kept current by hand
        try:
            s = build_story(g, now, imgdir, prev)
        except Exception as e:
            print("auto story failed:", e)
            s = None
        if s:
            s["replaces_top"] = on_top
            out.append(s)
        if len(out) >= 2:
            break
    return {"takeover": bool(stale and out), "stale_since": lastdev.isoformat() if lastdev else None, "stories": out}


def yt_uploads(addr):
    x = curl("https://www.youtube.com/" + addr + "/videos")
    m = re.search(r'var ytInitialData = (\{.*?\});</script>', x)
    name = clean(ps.meta(x, "og:title"))
    if not m:
        return name, []
    d = json.loads(m.group(1))
    out = []

    def walk(o):
        if isinstance(o, dict):
            if "lockupViewModel" in o:
                v = o["lockupViewModel"]
                md = v.get("metadata", {}).get("lockupMetadataViewModel", {})
                parts = [p.get("text", {}).get("content", "") for row in md.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
                         for p in row.get("metadataParts", [])]
                dur = ""
                for b in re.findall(r'"thumbnailBadgeViewModel":\{"text":"([^"]+)"', json.dumps(v))[:1]:
                    dur = b
                out.append((v.get("contentId"), md.get("title", {}).get("content", ""), parts, dur))
            for y in o.values():
                walk(y)
        elif isinstance(o, list):
            for y in o:
                walk(y)
    walk(d)
    return name, out


def age_minutes(parts):
    for p in parts:
        m = re.match(r"(?:Streamed )?(\d+)\s*(second|sec|minute|min|hour|h|day|d|week|w)s?\b\.? ago", (p or "").replace("\xa0", " "), re.I)
        if m:
            n, u = int(m.group(1)), m.group(2).lower()
            return n * {"second": 0, "sec": 0, "minute": 1, "min": 1, "hour": 60, "h": 60, "day": 1440, "d": 1440, "week": 10080, "w": 10080}[u]
    return None


def clips(page, prev_clips, now):
    import network_youtube as ny
    have = set(re.findall(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})", page))
    prev = {c["id"]: c for c in prev_clips}
    out = []

    def one(ch):
        net, addr, region = ch
        try:
            name, ups = yt_uploads(addr)
        except Exception:
            return []
        if name.lower() not in [n.lower() for n in ny.OFFICIAL.get(net, [])] and name.lower() != net.lower():
            print(f"clips: skipped {net}: channel page says {name!r}")
            return []
        got = []
        for vid, title, parts, dur in ups:
            mins = age_minutes(parts)
            if not vid or mins is None or mins > CLIP_HOURS * 60 or SKIP_CLIP.search(title) or vid in have:
                continue
            if re.fullmatch(r"\d+:\d\d:\d\d", dur or "") and int(dur.split(":")[0]) >= 3:
                continue  # a long livestream recording, not a clip
            up = now - timedelta(minutes=mins)
            p = prev.get(vid, {})
            got.append({"id": vid, "r": region, "o": net, "t": clean(title), "d": dur if re.fullmatch(r"\d{1,2}:\d\d(:\d\d)?", dur or "") else "",
                        "u": f"https://www.youtube.com/watch?v={vid}", "img": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                        "up": (up - timedelta(hours=4 if _dst(up) else 5)).date().isoformat(),
                        "added": p.get("added") or now.isoformat(), "pic": "globe"})
            if len(got) >= CLIPS_PER_NET:
                break
        return got

    with ThreadPoolExecutor(8) as ex:
        for got in ex.map(one, CHANNELS):
            out += got
    order = {"ca": 0, "us": 1, "world": 2}
    out.sort(key=lambda c: (order[c["r"]], c["added"]), reverse=False)
    return out


def _dst(dt):
    import autoupdate as au
    return au._dst(dt)


def ledes(now, prev):
    prevm = {l["u"]: l for l in prev}
    out = []

    def one(f):
        outlet, url = f
        for dt, o, title, link in w.rss(outlet, url)[:6]:
            if not dt or (now - dt).total_seconds() > 18 * 3600 or re.search(r"/opinion|/video/|/podcast|/sports?/|/entertainment", link):
                continue
            if link in prevm:
                return prevm[link]
            info = page_info(link)
            return {"o": outlet, "h": clean(title), "u": link, "img": info.get("img", ""), "w": w.eastern(dt), "iso": dt.isoformat()}
        return None

    with ThreadPoolExecutor(7) as ex:
        out = [x for x in ex.map(one, US_FEEDS) if x]
    return out


# ===== Think tanks & white papers: newest publications from institutes across the spectrum (their own titles and
# summaries), at most 2 per institute, last 14 days.
THINK_TANKS = [
    ("C.D. Howe Institute", "Toronto", "https://cdhowe.org/feed/"), ("Fraser Institute", "Vancouver", "https://www.fraserinstitute.org/rss.xml"),
    ("Macdonald-Laurier Institute", "Ottawa", "https://macdonaldlaurier.ca/feed/"),
    ("Canadian Centre for Policy Alternatives", "Ottawa", "https://www.policyalternatives.ca/feed/"),
    ("Public Policy Forum", "Ottawa", "https://ppforum.ca/feed/"), ("Broadbent Institute", "Ottawa", "https://www.broadbentinstitute.ca/feed"),
    ("Frontier Centre for Public Policy", "Winnipeg", "https://fcpp.org/feed/"), ("IRPP", "Montreal", "https://irpp.org/feed/"),
    ("Montreal Economic Institute", "Montreal", "https://www.iedm.org/feed/"), ("CIGI", "Waterloo", "https://www.cigionline.org/rss/"),
    ("AEI", "Washington", "https://www.aei.org/feed/"), ("Heritage Foundation", "Washington", "https://www.heritage.org/rss"),
    ("Brookings", "Washington", "https://www.brookings.edu/feed/"), ("CSIS", "Washington", "https://www.csis.org/rss.xml"),
    ("Atlantic Council", "Washington", "https://www.atlanticcouncil.org/feed/"), ("Peterson Institute", "Washington", "https://www.piie.com/rss/update.xml"),
    ("Pew Research Center", "Washington", "https://www.pewresearch.org/feed/"), ("Bruegel", "Brussels", "https://www.bruegel.org/rss.xml"),
    ("Lowy Institute", "Sydney", "https://www.lowyinstitute.org/the-interpreter/rss.xml"),
]
NOT_PAPER = re.compile(r"^(Test|Session \d|\d{4}$|Podcast|Event|Webinar|Watch|Video|Lines that landed)|/events?/|/podcasts?/|/video/|/media-coverage/|/in-the-media/", re.I)


def rss_desc(url):
    """Items with their own descriptions: [(dt, title, link, description)]."""
    x = curl(url)
    out = []
    for it in re.findall(r"<item\b.*?</item>|<entry\b.*?</entry>", x, re.S):
        g = lambda tag: (re.search(r"<%s\b[^>]*>(.*?)</%s>" % (tag, tag), it, re.S) or [None, ""])[1]
        title = clean(re.sub(r"<!\[CDATA\[|\]\]>", "", g("title")))
        link = clean(re.sub(r"<!\[CDATA\[|\]\]>", "", g("link"))) or (re.search(r'<link[^>]+href="([^"]+)"', it) or [None, ""])[1]
        desc = re.sub(r"<[^>]+>", " ", _h.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", g("description") or g("summary"))))
        dt = w.to_utc(g("pubDate") or g("published") or g("updated") or g("dc:date"))
        if title and link:
            out.append((dt, title, link, clean(desc)))
    return out


def papers(page, now):
    def one(t):
        inst, place, url = t
        got = []
        for dt, title, link, desc in rss_desc(url):
            if not dt or (now - dt).days > 14 or NOT_PAPER.search(title) or NOT_PAPER.search(link) or link in page or FRENCH_TEXT.search(title):
                continue
            g = desc if len(desc) >= 40 else ""
            if len(g) > 320:
                g = g[:320].rsplit(" ", 1)[0] + "…"
            day = dt - timedelta(hours=4 if _dst(dt) else 5)
            got.append({"inst": inst, "place": place, "kind": "Publication", "by": "", "date": day.strftime("%b. ") + str(day.day) + day.strftime(", %Y"),
                        "d": day.date().isoformat(), "pic": "chart", "u": link, "t": title, "g": g, "auto": True})
            if len(got) >= 2:
                break
        return got
    out = []
    with ThreadPoolExecutor(10) as ex:
        for got in ex.map(one, THINK_TANKS):
            out += got
    out.sort(key=lambda p: p["d"], reverse=True)
    return out[:14]


# ===== Editorials: the day's editorials and columns, one per outlet, left and right, Canadian first. Their own headlines.
OPINION_FEEDS = [
    ("Toronto Star", "https://www.thestar.com/search/?f=rss&t=article&c=opinion*&l=50&s=start_time&sd=desc"),
    ("National Post", "https://nationalpost.com/category/opinion/feed"), ("Toronto Sun", "https://torontosun.com/category/opinion/feed"),
    ("Ottawa Citizen", "https://ottawacitizen.com/category/opinion/feed"), ("Calgary Herald", "https://calgaryherald.com/category/opinion/feed"),
    ("Edmonton Journal", "https://edmontonjournal.com/category/opinion/feed"), ("Vancouver Sun", "https://vancouversun.com/category/opinion/feed"),
    ("The Globe and Mail (subscribers)", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/opinion/editorials/"),
    ("The Hub", "https://thehub.ca/feed/"),
    ("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Opinion.xml"), ("Fox News", "https://moxie.foxnews.com/google-publisher/opinion.xml"),
    ("The Wall Street Journal (subscribers)", "https://feeds.content.dowjones.io/public/rss/RSSOpinion"),
    ("Washington Examiner", "https://www.washingtonexaminer.com/section/opinion/feed/"), ("The Guardian", "https://www.theguardian.com/commentisfree/rss"),
]


def editorials(page, now):
    def one(f):
        outlet, url = f
        best = None
        for dt, o, title, link in w.rss(outlet, url):
            if not dt or (now - dt).total_seconds() > 30 * 3600 or re.search(r"/video/|/podcast|Lines that landed|letters?\b", link + " " + title, re.I):
                continue
            ed = bool(re.search(r"/editorials?/|^Editorial|The Guardian view|^Opinion \| The Post’s View|Star editorial", link + " " + title, re.I))
            m = re.match(r"^([A-Z][\w.'’-]+(?: [A-Z][\w.'’-]+)?):\s+(.*)$", title)
            if m and m.group(1).lower() in ("editorial", "opinion", "analysis", "letters"):
                ed = ed or m.group(1).lower() == "editorial"
                kind, head = ("Editorial" if ed else m.group(1).title()), m.group(2)
            elif m:
                kind, head = "Column · " + m.group(1).title(), m.group(2)
            else:
                kind, head = ("Editorial" if ed else "Opinion"), re.sub(r"\s*\|\s*Opinion$", "", title)
            row = [outlet, kind, clean(head), link, dt.isoformat()]
            if ed:
                return row
            best = best or row
        return best
    with ThreadPoolExecutor(8) as ex:
        out = [x for x in ex.map(one, OPINION_FEEDS) if x and x[3] not in page]
    return out[:10]


# ===== Canada and the U.S.: the newest reports on the relationship, and how U.S. newsrooms are covering Canada.
CANUS = re.compile(r"CUSMA|USMCA|tariff|softwood|Hoekstra|LeBlanc|trade (?:talks|deal|war)|51st state|Canada-U\.S\.|Canada–U\.S\.|"
                   r"Canadian (?:steel|aluminum|lumber|dairy)|Keystone|NORAD|border", re.I)
CANADA_WORD = re.compile(r"\bCanad(?:a|ian|ians|a's|a’s)\b|\bCarney\b|\bOttawa\b|\bAlberta\b|\bQuebec\b|\bOntario\b|\bToronto\b|\bB\.C\.\b|British Columbia")
US_OUTLETS = re.compile(r"^(CBS News|ABC News|NBC News|PBS NewsHour|Fox News|The Hill|NPR|Axios|CNN|The Associated Press)", re.I)


def canus(items, now):
    import autoupdate as au
    talks, usm, seen = [], [], set()
    for dt, outlet, title, link, k in items:
        if (now - dt).total_seconds() > 4 * 86400 or not au.ok_item(outlet, link) or au.OPINION.search(title + " " + link):
            continue
        t = re.sub(r"\W", "", title.lower())
        if t in seen:
            continue
        if US_OUTLETS.search(outlet) and CANADA_WORD.search(title):
            seen.add(t)
            usm.append({"t": w.eastern(dt), "iso": dt.isoformat(), "outlet": au.clean_outlet(outlet), "title": clean(title), "url": link})
        elif CANUS.search(title) and (CANADA_WORD.search(title) or "Hoekstra" in title or "CUSMA" in title) and not au.FRENCH.search(outlet):
            seen.add(t)
            talks.append({"t": w.eastern(dt), "iso": dt.isoformat(), "outlet": au.clean_outlet(outlet), "title": clean(title), "url": link})
    return {"talks": talks[:8], "usmedia": usm[:8]}


# ===== The 60-second brief, by itself: the biggest stories now, each attributed to the newsroom whose headline it reads.
def brief(groups, now):
    import autoupdate as au
    loc = now - timedelta(hours=4 if _dst(now) else 5)
    part = "morning" if loc.hour < 12 else ("evening" if loc.hour < 21 else "night")
    edition = f"{loc:%A} {part}, {loc:%B} {loc.day}"
    ca, other = [], []
    for g in groups[:16]:
        got = core_rows(g)
        rows = [r for r in (got[0] if got else []) if not VIDEO.search(r[3] + " " + r[2])]
        if len({au.clean_outlet(r[1]) for r in rows}) < MIN_OUTLETS:
            continue
        r = rows[0]
        line = f"{au.clean_outlet(r[1])} reports: {clean(r[2]).rstrip('.')}."
        (ca if au.CANADA.search(" ".join(x[2] for x in rows[:4])) else other).append(line)
    stories = (ca[:4] + other[:3])[:6]
    if len(stories) < 3:
        return None
    lines = [("Good morning." if part == "morning" else "Good evening.") + " I’m Hannah Thibedeau, and this is your Palindrome News brief."]
    lines += [x.replace("'", "’") for x in stories]
    lines.append("That’s your brief. We’ll keep watching, so you don’t have to.")
    return {"edition": edition, "lines": lines}


# ===== The breakdown, by itself: any story carried by 6 or more independent newsrooms (house rule 1) gets a breakdown
# built from what each newsroom reports, in its own words, each line credited and linked. Never the top stories.
BD_MAX = 4


def auto_breakdowns(groups, page, now, imgdir, skip_urls, prev):
    import autoupdate as au
    out = []
    for g in groups[:20]:
        if any(r[3] in skip_urls for r in g.get("rows", [])):
            continue
        rows = (core_rows(g) or [[]])[0]
        if independent(rows) < 6 or any(r[3].split("?")[0].rstrip("/") in page for r in rows[:3]):
            continue
        try:
            s = build_story(g, now, imgdir, prev)
        except Exception as e:
            print("auto breakdown failed:", e)
            s = None
        if not s or s.get("independent", 0) < 6:
            continue
        reps = [r for r in s["reports"] if r.get("desc")]
        if len(reps) < 3:
            continue
        src = [[r["outlet"], r["title"], r["url"]] for r in s["reports"]]
        idx = {r["url"]: i + 1 for i, r in enumerate(s["reports"])}
        canada = au.CANADA.search(" ".join(r["title"] for r in s["reports"][:5]))
        usa = au.USA.search(" ".join(r["title"] for r in s["reports"][:5]))
        out.append({
            "id": "bd-" + s["key"], "auto": True, "desk": "Canada" if canada else ("United States" if usa else "World"),
            "status": "Developing" if (now - datetime.fromisoformat(s["newest"])).total_seconds() < 6 * 3600 else "Ongoing",
            "at": s["newest"], "exact": True, "img": s["photo"]["src"] if s.get("photo") else "", "credit": ("via " + s["photo"]["outlet"]) if s.get("photo") else "",
            "pic": "globe", "h": s["title"], "lede": s["summary"], "newl": f"Now carried by {s['independent']} independent newsrooms.",
            "rows": [[r["outlet"], r["desc"], [idx[r["url"]]]] for r in reps[:6]], "src": src, "lead": idx.get(s["url"], 1),
        })
        if len(out) >= BD_MAX:
            break
    return out


# ===== On the record, by itself: statements from official sources the code can read (no X, Instagram or LinkedIn,
# which block automated reading). Each card links to the statement itself.
OFFICIAL_FEEDS = [
    ("Mark Carney", "Prime Minister of Canada", "pm", "MC", "https://www.pm.gc.ca/en/news.rss"),
    ("Government of Canada", "Official news releases", "mp", "GC", "https://api.io.canada.ca/io-server/gc/news/en/v2?type=newsreleases&sort=publishedDate&orderBy=desc&pick=20&format=atom"),
    ("Government of Ontario", "Premier Doug Ford’s government", "premier", "ON", "https://news.ontario.ca/newsroom/en/rss/allnews.rss"),
    ("Government of Alberta", "Premier Danielle Smith’s government", "premier", "AB", "https://www.alberta.ca/news.rss"),
    ("Government of B.C.", "Provincial government news", "premier", "BC", "https://news.gov.bc.ca/feed"),
    ("The White House", "President of the United States", "us", "WH", "https://www.whitehouse.gov/feed/"),
    ("United Nations", "UN News", "intl", "UN", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
]


def on_the_record(page, now):
    def one(f):
        name, role, cat, ini, url = f
        got = []
        for dt, title, link, desc in rss_desc(url):
            if not dt or (now - dt).total_seconds() > 48 * 3600 or link in page or re.search(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), \w+ \d|Fine for|Fined|Injury Results", title):
                continue
            day = dt - timedelta(hours=4 if _dst(dt) else 5)
            g = desc if len(desc) >= 30 else ""
            if len(g) > 240:
                g = g[:240].rsplit(" ", 1)[0] + "…"
            got.append({"cat": cat, "media": "none", "initials": ini, "name": name, "role": role, "date": day.strftime("%b ") + str(day.day),
                        "platform": "Official statement", "handle": re.sub(r"^https?://(www\.)?", "", link).split("/")[0], "hed": clean(title),
                        "summary": g, "href": link, "report": False, "iso": dt.isoformat(), "auto": True})
            if len(got) >= 2:
                break
        return got
    out = []
    with ThreadPoolExecutor(7) as ex:
        for got in ex.map(one, OFFICIAL_FEEDS):
            out += got
    out.sort(key=lambda p: p["iso"], reverse=True)
    return out[:8]


# ===== Live video, by itself (Hannah: "the new television of this century"): streams that are live NOW on the networks'
# official YouTube channels, and the ones they have scheduled, named by story. 24-hour channel streams go in one line.
ALWAYS_ON = re.compile(r"24/7|🔴|English \| Live|English Live|News NOW\b|^Watch .* live\b|News Live\b|LIVE:? Latest|live stream of|livestream|Live News|Breaking News Live|news channel", re.I)


EVENT = re.compile(r"news conference|press conference|briefing|address|speech|speaks|statement|debate|Question Period|hearing|"
                   r"testif|vote|results|election|announce|funeral|memorial|summit|ceremony|rally|town hall|update on", re.I)


def yt_streams(addr):
    x = curl("https://www.youtube.com/" + addr + "/streams")
    m = re.search(r'var ytInitialData = (\{.*?\});</script>', x)
    if not m:
        return []
    out = []

    def walk(o):
        if isinstance(o, dict):
            if "lockupViewModel" in o:
                v = o["lockupViewModel"]
                j = json.dumps(v)
                md = v.get("metadata", {}).get("lockupMetadataViewModel", {})
                title = clean(md.get("title", {}).get("content", ""))
                state = "live" if "BADGE_STYLE_LIVE" in j else ("upcoming" if "Scheduled for" in j or '"Upcoming"' in j else "")
                watching = (re.search(r'"content": ?"([\d.,K]+) watching"', j) or [None, ""])[1]
                sched = (re.search(r'Scheduled for ([0-9/]+, [0-9:]+(?:\\u202f|\s)?[AP]M)', j) or [None, ""])[1].replace("\\u202f", " ")
                if state:
                    out.append({"id": v.get("contentId"), "title": title, "state": state, "watching": watching, "sched": sched})
            for y in o.values():
                walk(y)
        elif isinstance(o, list):
            for y in o:
                walk(y)
    walk(json.loads(m.group(1)))
    return out


def start_time(vid):
    x = curl(f"https://www.youtube.com/watch?v={vid}")
    m = re.search(r'"startTimestamp":"([^"]+)"', x) or re.search(r'"scheduledStartTime":"(\d+)"', x)
    if not m:
        return None
    v = m.group(1)
    return datetime.fromtimestamp(int(v), timezone.utc) if v.isdigit() else w.to_utc(v)


def sched_time(txt):
    """YouTube shows an anonymous visitor scheduled times in U.S. Pacific time ("Scheduled for 10/28/26, 11:15 AM" for
    CBC's 2:15 p.m. ET Question Period). Returns UTC, or None."""
    from zoneinfo import ZoneInfo
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2}), (\d{1,2}):(\d{2}) ?([AP])M", (txt or "").strip())
    if not m:
        return None
    mo, d, y, h, mi, ap_ = m.groups()
    h = int(h) % 12 + (12 if ap_ == "P" else 0)
    return datetime(2000 + int(y), int(mo), int(d), h, int(mi), tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(timezone.utc)


def name_story(title, named):
    for nm in named:
        name, rx, need = (nm + (1,))[:3]
        if len({m.group(0).lower() for m in rx.finditer(title)}) >= need:
            return name
    t = re.sub(r"^(LIVE|WATCH LIVE|LIVE NOW)\s*(@\s*[\d:]+\s*(?:a\.?m\.?|p\.?m\.?)?\s*[EPMCA]T)?\s*[:|-]\s*", "", title, flags=re.I)
    t = re.split(r"\s+[|–—]\s+", t)[0]
    return t[:70]


# Live-only channels, besides CHANNELS: U.S. live-event networks, government channels (each checked against the
# channel's own name on YouTube; the PM's is the one pm.gc.ca links to) and more world networks.
LIVE_EXTRA = [
    ("Prime Minister of Canada", "@CanadianPM", "ca"), ("BNN Bloomberg", "@BNNBloomberg", "ca"),
    ("Bank of Canada - Banque du Canada", "channel/UCY4EvEbIox0M4JuEsu5OKnQ", "ca"), ("Federal Reserve", "@federalreserve", "us"),
    ("LiveNOW from FOX", "@LiveNOWFOX", "us"), ("NewsNation", "@NewsNation", "us"), ("MS NOW", "@MSNOW", "us"),
    ("Scripps News", "@ScrippsNews", "us"), ("Forbes Breaking News", "@ForbesBreakingNews", "us"),
    ("The White House", "@WhiteHouse", "us"), ("U.S. Department of State", "@StateDept", "us"),
    ("FRANCE 24 English", "channel/UCQfwfsi5VrQ8yKZ-UWmAEFg", "world"), ("euronews", "@euronews", "world"),
    ("ABC News (Australia)", "@abcnewsaustralia", "world"), ("CNA", "channel/UC83jt4dlz1Gjl58fzQrrKZg", "world"),
    ("10 Downing Street", "@10DowningStreet", "world"), ("NATO", "@NATO", "world"),
]


def live_video(page, named, now):
    import network_youtube as ny
    res = {"now": [], "upcoming": [], "always": []}

    def one(ch):
        net, addr, region = ch
        try:
            if ch in LIVE_EXTRA:
                x = curl("https://www.youtube.com/" + addr)
                if clean(ps.meta(x, "og:title")).lower() != net.lower():
                    print(f"live: skipped {net}: not the official channel name")
                    return net, region, []
            return net, region, yt_streams(addr)
        except Exception:
            return net, region, []
    with ThreadPoolExecutor(8) as ex:
        got = list(ex.map(one, CHANNELS + LIVE_EXTRA))
    for net, region, streams in got:
        for st in streams[:12]:
            if re.search(r"#shorts|\bNFL\b|\bNBA\b|\bNHL\b|\bMLB\b|highlights", st["title"], re.I):
                continue
            item = {"net": net, "r": region, "title": st["title"], "url": f"https://www.youtube.com/watch?v={st['id']}",
                    "img": f"https://i.ytimg.com/vi/{st['id']}/hqdefault.jpg", "story": name_story(st["title"], named)}
            if st["state"] == "live":
                item["watching"] = st["watching"]
                (res["always"] if ALWAYS_ON.search(st["title"]) else res["now"]).append(item)
            elif st["state"] == "upcoming" and len(res["upcoming"]) < 24 and (EVENT.search(st["title"]) or any(nm[1].search(st["title"]) for nm in named)):
                t = sched_time(st.get("sched", ""))
                if t and 0 < (t - now).total_seconds() < 36 * 3600:
                    item["when"] = t.isoformat()
                    res["upcoming"].append(item)
    try:
        for ev in ctv_events(now):
            ev["story"] = name_story(ev["title"], named)
            res["now" if ev.get("live") and not ev.get("when") else "upcoming"].append(ev)
    except Exception as e:
        print("live: CTV events failed:", e)
    res["now"] = group_events(res["now"], live=True)
    res["upcoming"] = group_events(res["upcoming"], live=False)
    order = {"ca": 0, "us": 1, "world": 2}
    res["now"].sort(key=lambda i: (-len(i.get("also", [])), order[i["r"]]))
    res["upcoming"].sort(key=lambda i: i["when"])
    seen_net, alw = set(), []
    for i in res["always"]:
        if i["net"] not in seen_net:
            seen_net.add(i["net"])
            alw.append({"net": i["net"], "url": i["url"]})
    res["always"] = alw[:10]
    return res


# ===== Coming up: the Prime Minister's public events with media from his own itinerary (pm.gc.ca), times as announced.
PM_MEDIA = re.compile(r"media availability|news conference|press conference|statement|address|remarks|announcement|"
                      r"will speak|will deliver|will make", re.I)


def pm_itinerary(now):
    out = []
    for dt, title, link, desc in rss_desc("https://www.pm.gc.ca/en/news.rss")[:6]:
        m = re.match(r"(?:UPDATE\s*[–-]\s*)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), (\w+ \d{1,2}, \d{4})", title)
        if not m:
            continue
        try:
            day = datetime.strptime(m.group(1), "%B %d, %Y")
        except ValueError:
            continue
        if "National Capital Region" not in desc:
            continue  # times are local wherever he is; only Ottawa days are certain to be Eastern time
        for hh, mm, ap_, what in re.findall(r"(\d{1,2}):(\d{2}) (a|p)\.m\. (The Prime Minister will .*?)(?=\s\d{1,2}:\d{2} [ap]\.m\. |$)", desc):
            if not PM_MEDIA.search(what):
                continue
            h = int(hh) % 12 + (12 if ap_ == "p" else 0)
            loc = day.replace(hour=h, minute=int(mm))
            off = timedelta(hours=4 if _dst(loc.replace(tzinfo=timezone.utc)) else 5)
            when = (loc + off).replace(tzinfo=timezone.utc)
            if (when - now).total_seconds() < -3600:
                continue
            sentence = re.split(r"(?<=\.)\s", what)[0]
            out.append({"story": "Prime Minister Mark Carney", "net": "Prime Minister’s Office", "what": sentence,
                        "where": "From the Prime Minister’s itinerary", "when": when.isoformat(), "url": link})
    return out[:6]


# ===== Related stories (Hannah, Tue Oct 27: "for the top stories, find other stories that would tie to that one and
# add it in"): for each top story, the newest reports on the people, places and issues that run through it, which are
# not the story itself. One per related story, newest first, plus analysis and opinion that names it.
def related(items, stories, now, eds, papers, groups=()):
    import autoupdate as au
    import gap_check as gc
    from collections import Counter
    out = {}
    gidx = {r[3]: i for i, g in enumerate(groups) for r in g.get("rows", [])}
    recent = [x for x in items if (now - x[0]).total_seconds() < 48 * 3600 and au.ok_item(x[1], x[3]) and not au.FRENCH.search(x[1])]
    import lead_check
    themes = {t[0]: (t[2], t[3]) for t in lead_check.THEMES}
    for st_ in stories:
        key, words, own = st_[:3]
        name = st_[3] if len(st_) > 3 else ""
        if not words:
            continue
        if name in themes:
            # a running theme (e.g. Canada and the U.S.): everything on both sides of it is connected
            ra, rb = themes[name]
            rx0 = re.compile("|".join(re.escape(x) for x in words), re.I)
            picked, used = [], set()
            for dt, outlet, title, link, k in recent:
                if not (ra.search(title) and rb.search(title)) or au.OPINION.search(title + " " + link) or VIDEO.search(link) or SPORT.search(title):
                    continue
                g_ = gidx.get(link)
                if g_ is not None and g_ in used:
                    continue
                if g_ is not None:
                    used.add(g_)
                if any(re.sub(r"\W", "", p_["title"].lower()) == re.sub(r"\W", "", title.lower()) for p_ in picked):
                    continue
                picked.append({"t": w.eastern(dt), "iso": dt.isoformat(), "outlet": au.clean_outlet(outlet), "title": clean(title), "url": link, "tie": name})
                if len(picked) >= 8:
                    break
            views = [{"outlet": e[0], "kind": e[1], "title": e[2], "url": e[3]} for e in (eds or []) if ra.search(e[2]) and rb.search(e[2])][:2]
            views += [{"outlet": p_["inst"], "kind": "Think tank", "title": p_["t"], "url": p_["u"]} for p_ in (papers or []) if ra.search(p_["t"]) and rb.search(p_["t"])][:2]
            if picked or views:
                out[key] = {"ties": [name], "stories": picked, "views": views}
            continue
        rx = re.compile("|".join(re.escape(x) for x in words), re.I)
        # an auto story is exactly its own reports; a hand-written story is every report naming it
        mine = [x for x in recent if x[3] in own] if own else [x for x in recent if rx.search(x[2])]
        if own:
            rx = re.compile("|".join(re.escape(x) for x in words[:3]), re.I)
        co = Counter(n.replace("’s", "").replace("'s", "") for x in mine for n in gc.names(x[2]))
        co = Counter({n: c for n, c in co.items() if n not in WEAK and n not in PARTY and not rx.search(n)})
        def proper(n):  # capitalized somewhere other than the first word: a name, not "Drone kills…"
            cap = n[:1].upper() + n[1:]
            return any(re.search(r"[a-z,]\s+" + re.escape(cap) + r"\b", x[2]) for x in mine)
        ties = [n for n, c in co.most_common(10) if c >= 2 and len(n) > 3 and proper(n)][:5]
        own_groups = {gi for x in mine for gi in [gidx.get(x[3])] if gi is not None}
        topkeys = {k_ for k_, c in Counter(k_ for x in mine for k_ in gc.keys(x[2])).items() if c >= 2}
        topnames = {n for n, c in co.most_common(3)}
        if not ties:
            continue
        trx = re.compile(r"\b(" + "|".join(re.escape(t[:1].upper() + t[1:]) for t in ties) + r")\b")
        picked, seen, used_groups = [], [], set()
        for dt, outlet, title, link, k in recent:
            if rx.search(title) or link in own or au.OPINION.search(title + " " + link) or SPORT.search(title + " " + link) or VIDEO.search(link):
                continue
            m = trx.search(title)
            if not m:
                continue
            if gidx.get(link) in own_groups or gidx.get(link) in used_groups:
                continue
            if len(gc.keys(title) & topkeys) >= 2 or len({n.replace("’s", "").replace("'s", "") for n in gc.names(title)} & topnames) >= 2:
                continue  # the story itself, told another way
            n = gc.names(title) | gc.keys(title)
            if any(len(n & s_) >= 3 for s_ in seen):
                continue
            seen.append(n)
            if gidx.get(link) is not None:
                used_groups.add(gidx[link])
            picked.append({"t": w.eastern(dt), "iso": dt.isoformat(), "outlet": au.clean_outlet(outlet), "title": clean(title), "url": link, "tie": m.group(1)})
            if len(picked) >= 5:
                break
        views = [{"outlet": e[0], "kind": e[1], "title": e[2], "url": e[3]} for e in (eds or []) if rx.search(e[2]) or trx.search(e[2])][:2]
        views += [{"outlet": p_["inst"], "kind": "Think tank", "title": p_["t"], "url": p_["u"]} for p_ in (papers or []) if rx.search(p_["t"]) or trx.search(p_["t"])][:2]
        if picked or views:
            out[key] = {"ties": ties, "stories": picked, "views": views}
    return out


# ===== Most read across Canada: built from the newsrooms' own most-read / trending lists (whichever publish one on
# their front page), ranked by how high and how widely each story sits on them.
MOST_READ_SITES = [
    ("Toronto Star", "https://www.thestar.com/"), ("Winnipeg Free Press", "https://www.winnipegfreepress.com/"),
    ("The Tyee", "https://thetyee.ca/"), ("Global News", "https://globalnews.ca/"), ("Nunatsiaq News", "https://nunatsiaq.com/"),
    ("Daily Hive", "https://dailyhive.com/vancouver"), ("National Post", "https://nationalpost.com/"), ("Ottawa Citizen", "https://ottawacitizen.com/"),
    ("Calgary Herald", "https://calgaryherald.com/"), ("Edmonton Journal", "https://edmontonjournal.com/"), ("Vancouver Sun", "https://vancouversun.com/"),
    ("Times Colonist", "https://www.timescolonist.com/"), ("Castanet", "https://www.castanet.net/"), ("Halifax Examiner", "https://www.halifaxexaminer.ca/"),
    ("CTV News", "https://www.ctvnews.ca/"), ("CBC News", "https://www.cbc.ca/news"), ("Cabin Radio", "https://cabinradio.ca/"),
]
NOT_STORY = re.compile(r"subscribe|sign in|newsletter|horoscope|crossword|obituar|contest|/sponsored|/partners?/|lotto|lottery", re.I)


def most_read_list(name, url):
    x = curl(url)
    host = url.split("/")[2]
    for m in re.finditer(r">\s*(Most[ -](?:Read|Popular|Viewed)|Trending(?: Now| Stories)?|Popular)\s*<", x, re.I):
        seg = x[m.end(): m.end() + 20000]
        out = []
        for a in re.finditer(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', seg, re.S):
            t = clean(re.sub(r"<[^>]+>", " ", a.group(2)))
            t = re.sub(r"^(Dished|Lifestyle|News|Canada|World|Crime|Entertainment|Politics|Business|Local)\s+(?=[A-Z‘'“])", "", t)
            t = re.sub(r"\s+(Crime|World|Entertainment|Canada|Politics|Business|Health|Sports?|Money)\s+\d+\s*(h|hr|hours?|min|d)\b.*$", "", t)
            u = a.group(1) if a.group(1).startswith("http") else "https://" + host + a.group(1)
            if len(t) < 30 or NOT_STORY.search(t + " " + u) or any(o[1] == t for o in out):
                continue
            out.append((u, t))
            if len(out) >= 5:
                break
        if len(out) >= 3:
            return name, out
    return name, []


def most_read(now):
    import gap_check as gc
    with ThreadPoolExecutor(8) as ex:
        lists = [x for x in ex.map(lambda f: most_read_list(*f), MOST_READ_SITES) if x[1]]
    stories = []
    for outlet, rows in lists:
        for rank, (u, t) in enumerate(rows, 1):
            n = gc.names(t) | gc.keys(t)
            for st in stories:
                if len(n & st["n"]) >= 3:
                    break
            else:
                st = {"n": set(), "h": t, "u": u, "o": [], "score": 0, "best": 99}
                stories.append(st)
            st["n"] |= n
            if rank < st["best"]:
                st["best"], st["h"], st["u"] = rank, t, u
            if all(o[0] != outlet for o in st["o"]):
                st["o"].append([outlet, rank, u])
                st["score"] += 6 - rank
    stories.sort(key=lambda s_: (-s_["score"], s_["best"]))
    return {"sites": [o for o, _ in lists], "list": [{"h": s_["h"], "u": s_["u"], "o": s_["o"]} for s_ in stories[:10]]}


# ===== Smaller newsrooms: today's top five from independent and northern newsrooms, the Arctic first (Hannah: give
# smaller publications prestige, Arctic and northern ones in particular). Their own headlines, summaries and pictures.
SMALL = [("Nunatsiaq News", "Nunavut", True), ("Cabin Radio", "N.W.T.", True), ("Yukon News", "Yukon", True),
         ("IndigiNews", "Indigenous", False), ("The Narwhal", "Environment", False), ("The Tyee", "British Columbia", False),
         ("Halifax Examiner", "Nova Scotia", False), ("Canada's National Observer", "National", False),
         ("Lethbridge Herald", "Alberta", False), ("Medicine Hat News", "Alberta", False), ("CKOM / PAnow", "Saskatchewan", False)]
SMALL_FEEDS = [("Yellowknifer (NNSL)", "https://www.nnsl.com/feed/", "N.W.T.", True), ("APTN News", "https://www.aptnnews.ca/feed/", "Indigenous", False)]


def smaller(items, page, now, imgdir):
    import autoupdate as au
    pool = []
    names = {n: (reg, arc) for n, reg, arc in SMALL}
    for dt, outlet, title, link, k in items:
        o = au.clean_outlet(outlet)
        if o in names and (now - dt).total_seconds() < 30 * 3600:
            pool.append((dt, o, title, link) + names[o])
    for o, url, reg, arc in SMALL_FEEDS:
        try:
            for dt, _, title, link in w.rss(o, url)[:8]:
                if dt and (now - dt).total_seconds() < 30 * 3600:
                    pool.append((dt, o, title, link, reg, arc))
        except Exception:
            pass
    pool = [p_ for p_ in pool if not au.OPINION.search(p_[2] + " " + p_[3]) and not SPORT.search(p_[2] + " " + p_[3])
            and not re.search(r"/community/|/events?/|obituar|horoscope|Please Advise", p_[2] + " " + p_[3], re.I)]
    from collections import Counter
    copies = Counter(re.sub(r"\W", "", x[2].lower()) for x in items)
    pool = [p_ for p_ in pool if copies[re.sub(r"\W", "", p_[2].lower())] <= 1 and "/national-news/" not in p_[3]]  # their own stories, not wire copy
    pool.sort(key=lambda p_: (not p_[5], -p_[0].timestamp()))  # Arctic first, then newest
    out, used = [], set()
    for dt, o, title, link, reg, arc in pool:
        if o in used:
            continue
        info = page_info(link)
        used.add(o)
        out.append({"o": o, "region": reg, "arctic": arc, "h": clean(title), "u": link, "t": w.eastern(dt),
                    "desc": (info.get("desc") or "")[:240], "img": info.get("img", "")})
        if len(out) >= 5:
            break
    return out


# ===== Live blogs, by themselves: any newsroom's live-updates page in the feeds (last 6 hours), named by story.
LIVE_BLOG = re.compile(r"live updates|live blog|liveblog|as it happened|\blive:|^live\b|— live|- live$|live coverage|live results", re.I)


def live_blogs(items, named, now):
    import autoupdate as au
    out, seen = [], set()
    for dt, outlet, title, link, k in items:
        if (now - dt).total_seconds() > 6 * 3600 or not au.ok_item(outlet, link) or au.FRENCH.search(outlet):
            continue
        if not (LIVE_BLOG.search(title) or re.search(r"/live(blog|-updates|-blog)?/|liveblog|live-updates|/live$", link)):
            continue
        if VIDEO.search(link) or SPORT.search(title + " " + link):
            continue
        story = name_story(title, named)
        key = (au.clean_outlet(outlet), story)
        if key in seen:
            continue
        seen.add(key)
        out.append({"net": au.clean_outlet(outlet), "story": story, "title": clean(title), "url": link, "updated": dt.isoformat()})
    named_first = [o for o in out if any(nm[1].search(o["title"]) for nm in named)]
    out = (named_first + [o for o in out if o not in named_first])[:12]
    with ThreadPoolExecutor(6) as ex:  # a picture for every tile: the blog's own share image
        for o, info in zip(out, ex.map(lambda o: page_info(o["url"]), out)):
            o["img"] = (info or {}).get("img", "")
    return out


# ===== Every place an event is live (Hannah, Wed Oct 28: "there has to be more places the bank of canada is coming up
# live"). The same event on several networks becomes ONE tile with every place to watch it: Canadian networks first
# (CTV before CBC), then the institution's own webcast.
NET_ORDER = ["CTV News", "CBC News", "Global News", "CPAC", "CP24", "BNN Bloomberg", "CityNews", "APTN News", "Prime Minister of Canada",
             "Bank of Canada - Banque du Canada"]
OFFICIAL_WEBCASTS = [
    (re.compile(r"Bank of Canada|Macklem|Banque du Canada", re.I), "Bank of Canada webcast", "https://www.bankofcanada.ca/press/speeches/webcasts/"),
    (re.compile(r"Federal Reserve|\bFed\b|FOMC|Warsh|Powell", re.I), "Federal Reserve live broadcast", "https://www.federalreserve.gov/live-broadcast.htm"),
    (re.compile(r"Question Period|House of Commons|Commons committee", re.I), "House of Commons (ParlVU)", "https://parlvu.parl.gc.ca/Harmony/en/"),
    (re.compile(r"White House|press secretary|Leavitt", re.I), "The White House live", "https://www.whitehouse.gov/live/"),
]
EVENT_STOP = set("""live watch news full coverage special stream streaming update updates latest breaking today tonight video
the a an and of on in at to for with as by from is are be will his her their after before about over says ctv cbc global
need know what's here's how what why who everything impact could would should this that these your you top headlines
day week year new more most first last get gets""".split())


def institution(text):
    for i, (rx, name, url) in enumerate(OFFICIAL_WEBCASTS):
        if rx.search(text):
            return i
    return None


def event_words(title):
    import unicodedata
    title = "".join(c for c in unicodedata.normalize("NFKD", title) if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s'’.-]", " ", title.lower())
    return {w_ for w_ in re.findall(r"[a-zà-ÿ][\w'’.-]+", t) if len(w_) > 2 and w_ not in EVENT_STOP}


def group_events(items, live):
    groups = []
    for it in items:
        ws = event_words(it["title"])
        inst = institution(it["title"] + " " + it["net"])
        proper = {w_ for w_ in event_words(" ".join(re.findall(r"\b[A-ZÀ-Ý][\wÀ-ÿ'’-]{4,}", it["title"])))}
        t = datetime.fromisoformat(it["when"]) if it.get("when") else None
        for g in groups:
            close = (t is None and g["t"] is None) if live else (t and g["t"] and abs((t - g["t"]).total_seconds()) <= 2 * 3600)
            shared = ws & g["w"]
            same = len(shared) >= 3 or (len(shared) >= 2 and shared & (proper | g["p"])) or (inst is not None and inst == g["i"])
            if close and same:
                g["p"] |= proper
                g["items"].append(it)
                g["w"] |= ws
                break
        else:
            groups.append({"w": set(ws), "t": t, "items": [it], "i": inst, "p": proper})
    out = []
    for g in groups:
        its = sorted(g["items"], key=lambda i: NET_ORDER.index(i["net"]) if i["net"] in NET_ORDER else 50)
        main = dict(its[0])
        if not main.get("img"):
            main["img"] = next((i["img"] for i in its if i.get("img")), "")
        also, seen = [], {main["net"]}
        for i in its[1:]:
            if i["net"] not in seen:
                seen.add(i["net"])
                also.append({"net": i["net"], "url": i["url"]})
        text = " ".join(i["title"] for i in its)
        for rx, name, url in OFFICIAL_WEBCASTS:
            if rx.search(text) and name not in seen:
                also.append({"net": name, "url": url, "official": True})
                break
        if also:
            main["also"] = also
        if not live:
            main["when"] = min(i["when"] for i in its)
        out.append(main)
    return out


def ctv_events(now):
    """CTV's own live event pages (ctvnews.ca/video/live/), e.g. 'LIVE 10:30 ET: Bank of Canada governor ...'. CTV's
    reusable 'LIVEn digital channel' slots are skipped: they keep saying live and later play something else."""
    x = curl("https://www.ctvnews.ca/video/live/")
    out, seen = [], set()
    for m in re.finditer(r'"canonical_url":"(/video/live/(\d{4})/(\d\d)/(\d\d)/(live-[^"/]+)/)"', x):
        path, y, mo, d, slug = m.groups()
        if path in seen or "digital-channel" in slug or "news-channel" in slug:
            continue
        seen.add(path)
        day = datetime(int(y), int(mo), int(d))
        if (now.replace(tzinfo=None) - day).days > 1:
            continue
        url = "https://www.ctvnews.ca" + path
        info = page_info(url)
        title = clean(re.sub(r"\s*\|\s*CTV News.*$", "", ps.meta(curl(url), "og:title") or "")) or slug.replace("-", " ").capitalize()
        tm = re.match(r"live-(\d{1,2})(\d\d)-(et|pt|mt|ct|at)-", slug)
        loc = now - timedelta(hours=4 if _dst(now) else 5)
        y, mo, d = loc.year, loc.month, loc.day  # CTV posts an event page the day before; the time is today's
        ev = {"net": "CTV News", "r": "ca", "title": title, "url": url, "img": info.get("img", "")}
        if tm:
            h, mi = int(tm.group(1)), int(tm.group(2))
            h = h + 12 if h < 7 else h  # "130" is 1:30 p.m.
            off = {"et": 4, "at": 3, "ct": 5, "mt": 6, "pt": 7}[tm.group(3)] + (0 if _dst(now) else 1)
            when = datetime(int(y), int(mo), int(d), h, mi, tzinfo=timezone.utc) + timedelta(hours=off)
            if when > now:
                ev["when"] = when.isoformat()
            elif (now - when).total_seconds() < 2 * 3600:
                ev["live"] = True
            else:
                continue
        else:
            continue  # no time in the address: can't be sure it is today's event
        out.append(ev)
    return out


def attach_reports(lv, items, now):
    """Every newsroom telling the story of each live event (Hannah, Wed Oct 28: "other outlets have the story ... it
    checks and adds other places telling the story too"): reports from the last 18 hours on the same event, newest
    report from each newsroom, their own headlines, one tap to each."""
    import autoupdate as au
    for ev in (lv.get("now") or []) + (lv.get("upcoming") or []):
        text = ev["title"] + " " + " ".join(a["net"] for a in ev.get("also", []))
        ws = event_words(ev["title"]) - {"announce", "announces", "holds", "speaks", "discusses", "decision", "conference", "press"}
        inst = institution(text)
        got, seen = [], set()
        for dt, outlet, title, link, k in items:
            if (now - dt).total_seconds() > 18 * 3600:
                break
            o = au.clean_outlet(outlet)
            if o in seen or not au.ok_item(outlet, link) or au.FRENCH.search(o) or VIDEO.search(link) or au.OPINION.search(title + " " + link):
                continue
            tw = event_words(title)
            hit = len(tw & ws) >= 3 or (inst is not None and institution(title) == inst and len(tw & ws) >= 1)
            if not hit:
                continue
            seen.add(o)
            got.append({"outlet": o, "title": clean(title), "url": link, "t": w.eastern(dt), "iso": dt.isoformat()})
            if len(got) >= 8:
                break
        if got:
            ev["reports"] = got


def run(page, items, groups, breaking, now, imgdir, prev):
    res = {}
    for name, f in [("auto", lambda: auto_stories(groups, page, breaking, now, imgdir, (prev.get("auto") or {}).get("stories", []))),
                    ("clips", lambda: clips(page, prev.get("clips", []), now)),
                    ("ledes", lambda: ledes(now, prev.get("ledes", []))),
                    ("papers", lambda: papers(page, now)), ("eds", lambda: editorials(page, now)),
                    ("canus", lambda: canus(items, now)), ("brief", lambda: brief(groups, now)),
                    ("otr", lambda: on_the_record(page, now)), ("mostread", lambda: most_read(now)),
                    ("smaller", lambda: smaller(items, page, now, imgdir))]:
        try:
            res[name] = f()
        except Exception as e:  # never block the run
            print(f"autopilot {name} failed:", e)
            res[name] = prev.get(name) or ({} if name in ("auto", "canus", "mostread") else None if name == "brief" else [])
    a = res.get("auto") or {}
    named = [(st["name"], re.compile("|".join(re.escape(x) for x in words), re.I)) for st, words in breaking if words]
    named += [(s_["title"][:60], re.compile(r"\b(" + "|".join(re.escape(x) for x in s_["words"]) + r")\b", re.I), 2) for s_ in a.get("stories", []) if s_.get("words")]
    for name, f in [("live", lambda: live_video(page, named, now)), ("pm", lambda: pm_itinerary(now)), ("blogs_auto", lambda: live_blogs(items, named, now))]:
        try:
            res[name] = f()
        except Exception as e:
            print(f"autopilot {name} failed:", e)
            res[name] = prev.get(name) or ({} if name == "live" else [])
    try:
        attach_reports(res.get("live") or {}, items, now)
    except Exception as e:
        print("autopilot live reports failed:", e)
    print(f"autopilot live blogs: {len(res.get('blogs_auto') or [])}")
    try:
        keyed = [("top" if st["where"].startswith("Top") else st["where"].split("UPNEXT ")[-1].rstrip(")"), words, set(), st["name"]) for st, words in breaking]
        keyed += [(s_["key"], s_.get("words") or [], {r["url"] for r in s_["reports"]}) for s_ in a.get("stories", [])]
        res["related"] = related(items, keyed, now, res.get("eds"), res.get("papers"), groups)
    except Exception as e:
        print("autopilot related failed:", e)
        res["related"] = prev.get("related") or {}
    try:
        skip = {r["url"] for st in a.get("stories", []) for r in st.get("reports", [])}
        res["bds"] = auto_breakdowns(groups, page, now, imgdir, skip, (prev.get("auto") or {}).get("stories", []))
    except Exception as e:
        print("autopilot bds failed:", e)
        res["bds"] = prev.get("bds") or []
    print(f"autopilot: {len(a.get('stories', []))} auto stories (takeover {a.get('takeover')}), {len(res['clips'])} clips, {len(res['ledes'])} U.S. ledes, "
          f"{len(res['papers'])} papers, {len(res['eds'])} editorials, canus {len((res['canus'] or {}).get('talks', []))}/{len((res['canus'] or {}).get('usmedia', []))}, brief {bool(res['brief'])}, {len(res['bds'])} breakdowns, {len(res['otr'])} on the record, live {len((res['live'] or {}).get('now', []))} now / {len((res['live'] or {}).get('upcoming', []))} upcoming, PM events {len(res['pm'])}, related for {len(res['related'])} stories, most read {len((res['mostread'] or {}).get('list', []))} from {len((res['mostread'] or {}).get('sites', []))} sites, smaller {len(res['smaller'])}")
    return res
