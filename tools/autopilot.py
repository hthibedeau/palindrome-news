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


def run(page, items, groups, breaking, now, imgdir, prev):
    res = {}
    for name, f in [("auto", lambda: auto_stories(groups, page, breaking, now, imgdir, (prev.get("auto") or {}).get("stories", []))),
                    ("clips", lambda: clips(page, prev.get("clips", []), now)),
                    ("ledes", lambda: ledes(now, prev.get("ledes", []))),
                    ("papers", lambda: papers(page, now)), ("eds", lambda: editorials(page, now)),
                    ("canus", lambda: canus(items, now)), ("brief", lambda: brief(groups, now)),
                    ("otr", lambda: on_the_record(page, now))]:
        try:
            res[name] = f()
        except Exception as e:  # never block the run
            print(f"autopilot {name} failed:", e)
            res[name] = prev.get(name) or ({} if name in ("auto", "canus") else None if name == "brief" else [])
    a = res.get("auto") or {}
    try:
        skip = {r["url"] for st in a.get("stories", []) for r in st.get("reports", [])}
        res["bds"] = auto_breakdowns(groups, page, now, imgdir, skip, (prev.get("auto") or {}).get("stories", []))
    except Exception as e:
        print("autopilot bds failed:", e)
        res["bds"] = prev.get("bds") or []
    print(f"autopilot: {len(a.get('stories', []))} auto stories (takeover {a.get('takeover')}), {len(res['clips'])} clips, {len(res['ledes'])} U.S. ledes, "
          f"{len(res['papers'])} papers, {len(res['eds'])} editorials, canus {len((res['canus'] or {}).get('talks', []))}/{len((res['canus'] or {}).get('usmedia', []))}, brief {bool(res['brief'])}, {len(res['bds'])} breakdowns, {len(res['otr'])} on the record")
    return res
