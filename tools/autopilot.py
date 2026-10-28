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


def page_info(url):
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


def build_story(g, now, imgdir, prev):
    import autoupdate as au
    import gap_check as gc
    from collections import Counter
    rows = sorted({r[3].split("?")[0]: r for r in g["rows"] if _ok(r[1], r[3], r[2])}.values(), reverse=True)
    # a ranked group can hold a stray headline (a news wrap, a shared common name): keep the reports that name the
    # story's core: the names most of its headlines share
    freq = Counter(x for r in rows for x in gc.names(r[2]) if x not in WEAK)
    if not freq or freq.most_common(1)[0][1] < 3:
        return None  # no name shared by 3+ headlines: not one story
    anchor = freq.most_common(1)[0][0]
    co = Counter(x for r in rows if anchor in gc.names(r[2]) for x in gc.names(r[2]) if x not in WEAK)
    core = {anchor} | {x for x, n in co.items() if n >= 2}
    rows = [r for r in rows if anchor in gc.names(r[2]) or len(gc.names(r[2]) & core) >= 2]
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
    return {
        "key": key, "words": names, "score": g["score"], "outlets": len(per),
        "tag": "Breaking" if (now - newest).total_seconds() < BREAKING_MIN * 60 else "Developing",
        "title": clean(lead[2]), "url": lead[3], "outlet": au.clean_outlet(lead[1]), "t": w.eastern(lead[0]), "iso": lead[0].isoformat(),
        "summary": info.get("desc", ""),
        "first": {"outlet": au.clean_outlet(first[1]), "url": first[3], "t": w.eastern(first[0]), "title": clean(first[2])},
        "newest": newest.isoformat(), "photo": photo,
        "reports": [{"t": w.eastern(r[0]), "iso": r[0].isoformat(), "outlet": au.clean_outlet(r[1]), "title": clean(r[2]), "url": r[3]} for r in reps[:14]],
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


def run(page, items, groups, breaking, now, imgdir, prev):
    res = {}
    for name, f in [("auto", lambda: auto_stories(groups, page, breaking, now, imgdir, (prev.get("auto") or {}).get("stories", []))),
                    ("clips", lambda: clips(page, prev.get("clips", []), now)),
                    ("ledes", lambda: ledes(now, prev.get("ledes", [])))]:
        try:
            res[name] = f()
        except Exception as e:  # never block the run
            print(f"autopilot {name} failed:", e)
            res[name] = prev.get(name) or ({} if name == "auto" else [])
    a = res.get("auto") or {}
    print(f"autopilot: {len(a.get('stories', []))} auto stories (takeover {a.get('takeover')}), {len(res['clips'])} clips, {len(res['ledes'])} U.S. ledes")
    return res
