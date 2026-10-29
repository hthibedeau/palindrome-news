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
CANADIAN_WEIGHT = 8    # a Canadian story's edge over a story from abroad of the same size
MIN_OUTLETS = 3         # an auto story needs at least this many INDEPENDENT newsrooms (wire copies count once)
BREAKING_INDEPENDENT = 4  # "Breaking" also needs at least this many independent newsrooms
CANDIDATES = 8          # top-story candidates built each run; the two shown are picked by pick_by_canada()
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


def _words(t):
    return set(re.findall(r"[a-z0-9]+", t.lower().replace("’", "'"))) - {"the", "a", "an", "s", "of", "to", "in", "on", "as", "and", "for"}


def same_report(t1, t2):
    """Two headlines that are the same wire report republished (punctuation, curly quotes or a word or two changed)."""
    if re.sub(r"\W", "", t1.lower()) == re.sub(r"\W", "", t2.lower()):
        return True
    a, b = _words(t1), _words(t2)
    return bool(a and b) and len(a & b) / len(a | b) >= 0.75


def independent(reps):
    """How many independent newsrooms: one per owner, and copies of the same wire report count once (Hannah, Wed Oct 28:
    one Canadian Press report run by CTV News, BNN Bloomberg, the Times Colonist and CKOM is ONE report, not four)."""
    kept, owners = [], set()
    for r in reps:
        if any(same_report(r[2], k) for k in kept):
            continue
        kept.append(r[2])
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
    if g.get("theme") and g["theme"] not in SPLIT_THEMES and rows:
        # a theme kept whole (one event, e.g. the Canada-EU summit): only reports that name the event's other side.
        # A Montreal murder story was grouped in through "Montreal" and became the summit's headline (Thu Oct 29, 2026).
        try:
            import lead_check as lc
            rb = next(t[3] for t in lc.THEMES if t[0] == g["theme"])
            rows = [r for r in rows if rb.search(r[2])]
        except StopIteration:
            pass
    if g.get("theme") and rows:  # one story split out of a running theme (_split_themes): its reports already agree
        kc = Counter(x for r in rows for x in gc.keys(r[2]) | gc.names(r[2]) if x not in WEAK)
        return rows, {x for x, n in kc.most_common(6) if n >= 2} or {x for x, n in kc.most_common(3)}
    freq = Counter(x for r in rows for x in gc.names(r[2]) if x not in WEAK)
    if not freq or freq.most_common(1)[0][1] < 3:
        return None
    anchor = freq.most_common(1)[0][0]
    co = Counter(x for r in rows if anchor in gc.names(r[2]) for x in gc.names(r[2]) if x not in WEAK)
    core = {anchor} | {x for x, n in co.items() if n >= 2}
    return [r for r in rows if anchor in gc.names(r[2]) or len(gc.names(r[2]) & core) >= 2], core


WHY = ""  # why the last build_story() returned nothing (recorded for live/auto.json "considered")


def build_story(g, now, imgdir, prev):
    import autoupdate as au
    import gap_check as gc
    from collections import Counter
    global WHY
    got = core_rows(g)
    if not got or not got[0]:
        WHY = "its headlines don't share a name often enough to be sure they are one story"
        return None
    rows, core = got
    if not rows:
        WHY = "no usable reports"
        return None
    per = {}
    for r in rows:  # newest report from each newsroom
        per.setdefault(au.clean_outlet(r[1]), r)
    reps = sorted(per.values(), reverse=True)
    if len(reps) < MIN_OUTLETS or independent(reps) < MIN_OUTLETS:
        WHY = f"only {independent(reps)} independent report(s) ({len(reps)} sites)"
        return None  # one wire report republished by several sites is one report, not a top story
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
        "key": key, "words": names, "score": g["score"], "outlets": independent(reps), "carriers": len(per),
        # Breaking only when several newsrooms are reporting it on their own and the newest is under an hour old
        "tag": "Breaking" if independent(reps) >= BREAKING_INDEPENDENT and (now - newest).total_seconds() < BREAKING_MIN * 60 else "Developing",
        "title": clean(lead[2]), "url": lead[3], "outlet": au.clean_outlet(lead[1]), "t": w.eastern(lead[0]), "iso": lead[0].isoformat(),
        "summary": info.get("desc", ""),
        "first": {"outlet": au.clean_outlet(first[1]), "url": first[3], "t": w.eastern(first[0]), "title": clean(first[2])},
        "newest": newest.isoformat(), "photo": photo,
        "independent": independent(reps),
        "reports": [{"t": w.eastern(r[0]), "iso": r[0].isoformat(), "outlet": au.clean_outlet(r[1]), "title": clean(r[2]), "url": r[3],
                     "desc": descs.get(r[3], "")} for r in reps[:14]],
    }


SPLIT_THEMES = {"Canada and the U.S."}  # running themes made of many separate stories


def _split_themes(groups):
    """A running theme (e.g. Canada and the U.S.) is ranked as one group but holds many separate stories. Split it into
    its own stories (reports with near-identical headlines), biggest first, each keeping the theme's rank, so the
    Canada-U.S. stories of the day can be top stories (Hannah, Wed Oct 28: "so much coming out about the Canada-US
    relationship"). Only stories that name Canada are kept from a Canada theme."""
    import gap_check as gc
    out = []
    for g in groups:
        if not g.get("theme") or g["theme"] not in SPLIT_THEMES:
            out.append(g)  # an ordinary story, or a theme that is one event (the Canada-EU summit): kept whole
            continue
        clusters = []
        for r in sorted(g["rows"], reverse=True):
            k = gc.keys(r[2])
            for c in clusters:
                if len(k & c["k"]) >= 3 or re.sub(r"\W", "", r[2].lower()) == c["t"]:
                    c["rows"].append(r)
                    c["k"] |= k
                    break
            else:
                clusters.append({"rows": [r], "k": set(k), "t": re.sub(r"\W", "", r[2].lower())})
        subs = []
        for c in clusters:
            if not any(CAN_TIE.search(r[2]) for r in c["rows"]):
                continue
            subs.append({"rows": c["rows"], "n": set().union(*(gc.names(r[2]) for r in c["rows"])), "score": g["score"], "theme": g["theme"]})
        subs.sort(key=lambda c: len({r[1] for r in c["rows"]}), reverse=True)
        out += subs[:3]
    return out


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
    out, considered = [], []
    for g in _split_themes(groups[:16]):
        lead_t = (g.get("lead") or [""])[0] if g.get("lead") else (sorted(g.get("rows") or [], reverse=True)[:1] or [("", "", "")])[0][2]
        hits = [st for st, rx in rxs if sum(1 for r in g["rows"] if rx.search(r[2])) >= 2]
        on_top = any(st["where"].startswith("Top") for st in hits)
        events = [st["where"].split("UPNEXT ")[-1].rstrip(")") for st in hits if not st["where"].startswith("Top")]
        if on_top and not stale:
            considered.append({"title": lead_t, "score": g.get("score"), "why": "already the hand-written top story"})
            continue  # the page already carries it, kept current by hand
        # A story with its own Breaking event stays a candidate: the page drops it from the top pair only while that
        # event is actually showing (otherwise the biggest story could vanish from the top of the page altogether).
        try:
            s = build_story(g, now, imgdir, prev)
        except Exception as e:
            print("auto story failed:", e)
            s = None
        if not s:
            considered.append({"title": lead_t, "score": g.get("score"), "why": "not built: " + (WHY or "error")})
        if s:
            s["replaces_top"] = on_top
            s["events"] = events
            s["theme"] = g.get("theme") or ""
            out.append(s)
        if len(out) >= CANDIDATES:
            break  # more than two: pick_by_canada() keeps the two with Canadian ties first
    return {"takeover": bool(stale and out), "stale_since": lastdev.isoformat() if lastdev else None, "stories": out, "considered": considered}


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


# Hannah, Wed Oct 28, 2026: "I went to watch the BBC News, but it says the uploader wouldn't allow this in our country.
# If that is the case, don't make it available on the website." Every YouTube clip and live stream is checked against
# the countries its uploader allows (YouTube's own availableCountries list on the video's page). Not allowed in Canada:
# never shown. Readers are in Canada; these runs are not, so the list is what decides, never this run's own access.
GEO_CACHE = {"-NabWfv-VdA": "blocked"}  # BBC News live stream: Hannah found it blocked in Canada (Wed Oct 28, 2026)


def yt_check(vid):
    """Will this YouTube video actually play for a reader in Canada? (Hannah, Wed Oct 28, 2026: "in the code, check the
    video to make sure it will run before you put it on the site.") Read from the video's own YouTube page:
      ok         plays (status OK, not private or removed, no sign-in or age gate, allowed in Canada)
      blocked    the uploader does not allow it in Canada
      unplayable removed, private, members-only, age-restricted (needs a sign-in) or otherwise won't play
      unknown    YouTube's page could not be read this run
    Also records, in YT_INFO[vid]: live (on air now), offline (a stream that is not on air), embed (can play inside our page)."""
    if vid in GEO_CACHE:
        return GEO_CACHE[vid]
    x = ""
    for _ in range(2):
        x = curl(f"https://www.youtube.com/watch?v={vid}&hl=en&gl=CA")
        if '"playabilityStatus"' in x:
            break
    res = "unknown"
    info = {}
    if '"playabilityStatus"' in x:
        m = re.search(r'"availableCountries":\[([^\]]*)\]', x)
        ps_ = re.search(r'"playabilityStatus":\{"status":"(\w+)"(?:,"reason":"([^"]*)")?', x)
        status, reason = (ps_.group(1), ps_.group(2) or "") if ps_ else ("", "")
        info = {"live": '"isLiveNow":true' in x or '"isLive":true' in x, "offline": status == "LIVE_STREAM_OFFLINE",
                "embed": '"playableInEmbed":false' not in x, "status": status, "reason": reason}
        if m and m.group(1).strip() and '"CA"' not in m.group(1):
            res = "blocked"
        elif re.search(r"country", reason, re.I) or re.search(r"not (?:made this video )?available in your country|blocked it in your country", x, re.I):
            res = "blocked"
        elif BOT_WALL.search(reason) or BOT_WALL.search(x[:400000]) and status in ("LOGIN_REQUIRED", "ERROR", ""):
            res = "unknown"  # YouTube asked THIS run to prove it is not a bot; says nothing about the video
        elif status in ("ERROR", "UNPLAYABLE", "LOGIN_REQUIRED", "AGE_CHECK_REQUIRED", "CONTENT_CHECK_REQUIRED") and DEAD_REASON.search(reason):
            res = "unplayable"  # removed, private, members-only or age-restricted: a reader can't play it either
        elif status in ("OK", "LIVE_STREAM_OFFLINE"):
            res = "ok"
    if res == "unknown":
        res = oembed_check(vid)
        info = info or {}
        info.setdefault("embed", res != "noembed")
        if res == "noembed":
            res = "ok"
    YT_INFO[vid] = info
    GEO_CACHE[vid] = res
    return res


YT_INFO = {}
BOT_WALL = re.compile(r"confirm (?:you(?:'|’)re|that you(?:'|’)re|you are) not a bot|unusual traffic|Sign in to confirm", re.I)
DEAD_REASON = re.compile(r"private|removed|no longer available|terminated|deleted|members|age|inappropriate|copyright|does not exist|unavailable", re.I)


def oembed_check(vid):
    """When YouTube won't show this run the video page, its oEmbed answer still says whether the video exists and may be
    played in other sites: 200 ok, 401/403 exists but not embeddable, 404/400 gone. Country limits are not in it, so a
    video only this says is fine stays 'unknown' for the country check (see geo_filter)."""
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "15", "-A", UA, "-w", "%{http_code}",
                        f"https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True)
    code = r.stdout.strip()
    return {"200": "unknown", "401": "noembed", "403": "noembed", "404": "unplayable", "400": "unplayable"}.get(code, "unknown")


yt_in_canada = yt_check  # older name, used by tools/network_youtube.py


def geo_filter(items, key, label, keep_unknown=None):
    """Keep only the videos that will play: never one that is blocked in Canada or removed, private or gated. A video
    whose page YouTube walled off from this run is kept only when oEmbed confirms it exists and plays."""
    ids = [key(i) for i in items]
    with ThreadPoolExecutor(8) as ex:
        verdicts = dict(zip(ids, ex.map(lambda v: yt_check(v) if v else "ok", ids)))
    kept = []
    for i in items:
        v = verdicts.get(key(i))
        if v == "ok" or v == "unknown":  # unknown = exists and plays elsewhere; country could not be read this run
            kept.append(i)
        else:
            why = {"blocked": "not available in Canada", "unplayable": "won't play: " + (YT_INFO.get(key(i), {}).get("reason") or YT_INFO.get(key(i), {}).get("status") or "")}.get(v, "could not be checked yet")
            print(f"{label}: held back ({why}): {i.get('o') or i.get('net')}: {(i.get('t') or i.get('title') or '')[:70]}")
    return kept


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
            rec = bool(re.match(r"\s*(?:🔴\s*)?(?:LIVE|Live|WATCH LIVE|Watch live)\b\s*(?:@[^:|]*)?[:|\-–—]", title))
            if rec:  # "Live: …" on a finished upload is a recording of a stream that has ended, not live
                title = re.sub(r"^\s*(?:🔴\s*)?(?:LIVE|Live|WATCH LIVE|Watch live)\b\s*(?:@[^:|]*)?[:|\-–—]\s*", "", title)
            got.append({"id": vid, "r": region, "o": net, "t": clean(title), "rec": rec, "d": dur if re.fullmatch(r"\d{1,2}:\d\d(:\d\d)?", dur or "") else "",
                        "u": f"https://www.youtube.com/watch?v={vid}", "img": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                        "up": (up - timedelta(hours=4 if _dst(up) else 5)).date().isoformat(),
                        "added": p.get("added") or now.isoformat(), "pic": "globe"})
            if len(got) >= CLIPS_PER_NET:
                break
        return got

    with ThreadPoolExecutor(8) as ex:
        for got in ex.map(one, CHANNELS):
            out += got
    for c in out:  # a clip already checked on an earlier run keeps its verdict
        if prev.get(c["id"], {}).get("geo") in ("ok", "blocked"):
            GEO_CACHE.setdefault(c["id"], prev[c["id"]]["geo"])
    out = geo_filter(out, lambda c: c["id"], "clips", keep_unknown=lambda c: prev.get(c["id"], {}).get("geo") == "ok")
    for c in out:
        c["geo"] = GEO_CACHE.get(c["id"], "unknown")
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
        if independent(rows) < MIN_OUTLETS:
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
    vid_of = lambda i: (re.search(r"[?&]v=([A-Za-z0-9_-]{11})", i.get("url", "")) or [None, None])[1]
    for k in ("now", "always", "upcoming"):  # only streams that will play in Canada
        res[k] = geo_filter(res[k], vid_of, "live")
    for k in ("now", "always"):  # "live" must mean on air right now
        keep = []
        for i in res[k]:
            inf = YT_INFO.get(vid_of(i) or "", {})
            if vid_of(i) and inf and inf.get("offline"):
                print(f"live: dropped (not on air): {i['net']}: {i['title'][:70]}")
                continue
            if inf and not inf.get("embed", True):
                i["noembed"] = True  # plays on YouTube, but not inside our page: the page links to it instead
            keep.append(i)
        res[k] = keep
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
PLACES = re.compile(r"^(canada|ottawa|toronto|montreal|vancouver|calgary|edmonton|winnipeg|halifax|quebec|ontario|alberta|manitoba|"
                    r"saskatchewan|nova|scotia|brunswick|newfoundland|labrador|yukon|nunavut|regina|saskatoon|victoria|hamilton|"
                    r"london|paris|berlin|brussels|rome|madrid|washington|york|chicago|california|texas|florida|beijing|moscow|"
                    r"kyiv|ukraine|russia|china|india|israel|gaza|iran|europe|european|america|american|africa|asia|north|south|"
                    r"east|west|central|island|islands|city|county|province|state|states)$", re.I)


def is_place(t):
    """A city, province, country or region: never enough on its own to connect two stories."""
    t = t.replace("’s", "").replace("'s", "")
    return bool(PLACES.match(t) or CAN_TIE.fullmatch(t[:1].upper() + t[1:]))


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
            own_rows = [x for x in recent if x[3] in own]
            picked, used = [], set()
            for dt, outlet, title, link, k in recent:
                if not (ra.search(title) and rb.search(title)) or au.OPINION.search(title + " " + link) or VIDEO.search(link) or SPORT.search(title):
                    continue
                if link in own or any(same_report(title, x[2]) or len(gc.keys(title) & gc.keys(x[2])) >= 4 for x in own_rows):
                    continue  # the story's own reports, or the same report from another newsroom: already listed under it
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
        # Hannah, Thu Oct 29, 2026: "All the 'Connected to this story' do not actually connect to canada eu." The summit
        # is in Montreal, so "Montreal" was a tie and every Montreal story (a strike vote, a car crash) was "connected".
        # A connected story must share a person, organization or issue with this one, not just a place, and share at
        # least one more of its names or key words.
        story_words = {x for x in topkeys | set(co) | {k_ for x in mine for k_ in gc.keys(x[2])} if x not in WEAK}
        def connected(title):
            found = {m_.group(1).lower() for m_ in trx.finditer(title)}
            people = {t for t in found if not is_place(t)}
            if not people:
                return False
            extra = ({n.replace("’s", "").replace("'s", "") for n in gc.names(title)} | gc.keys(title)) & story_words
            return len(found) >= 2 or len(extra - found) >= 1
        picked, seen, used_groups = [], [], set()
        for dt, outlet, title, link, k in recent:
            if rx.search(title) or link in own or au.OPINION.search(title + " " + link) or SPORT.search(title + " " + link) or VIDEO.search(link):
                continue
            m = trx.search(title)
            if not m or not connected(title):
                continue
            m = next((m_ for m_ in trx.finditer(title) if not is_place(m_.group(1).lower())), m)
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
        views = [{"outlet": e[0], "kind": e[1], "title": e[2], "url": e[3]} for e in (eds or []) if rx.search(e[2]) or connected(e[2])][:2]
        views += [{"outlet": p_["inst"], "kind": "Think tank", "title": p_["t"], "url": p_["u"]} for p_ in (papers or []) if rx.search(p_["t"]) or connected(p_["t"])][:2]
        if picked or views:
            out[key] = {"ties": [t for t in ties if not is_place(t)] or ties, "stories": picked, "views": views}
    return out


# ===== The Canadian angle (Hannah, Wed Oct 28, 2026: "when there is a top headline from another country, if there is
# canadian angle that can be tied to it somehow …add it into it by putting it in a sidebar ... make sure this is written
# into the code"). For every top story that is about another country, the newest reports that tie it to Canada:
# Canadians caught up in it, Ottawa's response, the Prime Minister and Global Affairs, the effect on Canadian trade,
# travel or communities, and official Canadian statements. Each line is the outlet's own headline, credited and linked;
# nothing is written or guessed. No Canadian angle in the news: no sidebar.
CAN_TIE = re.compile(r"\b(Canad(?:a|ian|ians|a's|a’s)|Ottawa|Carney|Anand|Global Affairs|Poilievre|RCMP|CSIS|Canadian Armed Forces|"
                     r"Ontario|Quebec|Québec|Alberta|British Columbia|B\.C\.|Manitoba|Saskatchewan|Nova Scotia|New Brunswick|"
                     r"P\.E\.I\.|Newfoundland|Yukon|Nunavut|N\.W\.T\.|Toronto|Montreal|Vancouver|Calgary|Edmonton|Winnipeg|Halifax|"
                     r"Doug Ford|Legault|David Eby|Danielle Smith|Olivia Chow|Hoekstra)(?!\w)")
CAN_OUTLET = re.compile(r"^(CBC|CTV|Global News|The Canadian Press|Toronto Star|National Post|CityNews|CP24|APTN|CPAC|"
                        r"Ottawa Citizen|Calgary Herald|Edmonton Journal|Vancouver Sun|Winnipeg Free Press|Times Colonist|"
                        r"The Tyee|Hill Times|iPolitics|BNN|Financial Post|Prime Minister|Government of Canada)", re.I)
FOREIGN_SRC = re.compile(r"/(world|international|us-news|us|europe|asia|africa|middle-east|americas|global-news-world)/|bbc\.|aljazeera|euronews|apnews\.com/article|reuters\.com/world", re.I)
FOREIGN_SHARE = 0.4  # a story is "from another country" when at least this share of its reports run on world desks or foreign newsrooms
ANGLE_MAX = 5


# U.S. stories: the Canadian angle is also the Canada-U.S. relationship itself (Hannah, Wed Oct 28: "there are many
# canada angles to the US relationship today"). A U.S. political, election or trade story gets, after any reports tying
# that exact story to Canada, the newest Canada-U.S. reports (trade talks, tariffs, Hoekstra, the border, U.S. media on Canada).
US_STORY = re.compile(r"\b(Trump|Vance|Rubio|Hegseth|Bessent|Lutnick|Greer|White House|Congress|Senate|House Republicans|GOP|Republicans?|"
                      r"Democrats?|midterms?|governor's race|governor’s race|Pentagon|U\.S\.|US|America|American|Washington)\b")
US_POLITICS = re.compile(r"\b(Trump|Vance|Rubio|Bessent|Lutnick|Greer|White House|Congress|Senate|GOP|Republicans?|Democrats?|midterms?|"
                         r"election|campaign|rally|tariffs?|trade|border|administration|Pentagon|NATO|Golden Dome)\b", re.I)
US_TIE = re.compile(r"\b(U\.S\.|U\.S|US|United States|America|American|Americans|Washington|Trump|Vance|Hoekstra|White House|Congress|"
                    r"Senate|midterms?|Republicans?|Democrats?|CUSMA|USMCA)\b")
GENERIC = set("""united states arab north south east west new farm workers debate senate house budget election elections live news
world national party government minister president latest updates update video watch dozens least percent people officials
city state county court day week year today""".split())
TOPIC = re.compile(r"\b(midterms?|elections?|tariffs?|trade (?:deal|talks|war)|border|steel|aluminum|autos?|softwood|dairy|energy|oil|"
                   r"defen[cs]e|NATO|Golden Dome|fentanyl|immigration|CUSMA|USMCA)\b", re.I)


def _angle(name, words, mine, recent, eds, papers, otr, pool, anchor_words=None):
    """The Canadian angle for one story from another country, or None. `mine` = the story's own reports."""
    import autoupdate as au
    import gap_check as gc
    from collections import Counter
    if CAN_TIE.search(name + " " + " ".join(words)):
        return None  # a Canadian story already
    is_us = bool(US_STORY.search(name) or US_ELECTION.search(name))  # the headline itself is about the U.S. (or its election)
    if not is_us:
        if len(mine) < 2 or sum(1 for x in mine if FOREIGN_SRC.search(x[3]) or au.US.search(x[1]) or au.WORLDO.search(x[1])) / len(mine) < FOREIGN_SHARE:
            return None  # a story from another country runs on world desks and foreign newsrooms; this one doesn't
    co = Counter(n.replace("’s", "").replace("'s", "") for x in mine for n in gc.names(x[2]))
    top = {n for n, c in co.most_common(6) if c >= 2 and n not in GENERIC and (n not in WEAK or (n == "trump" and "trump" in name.lower())) and not CAN_TIE.search(n[:1].upper() + n[1:])}
    aw = [x for x in (anchor_words or words) if x and x.lower() not in GENERIC]
    anchor = re.compile(r"\b(" + "|".join(re.escape(x) for x in aw) + r")\b", re.I) if aw else None
    topics = {m.group(1).lower().rstrip("s") for m in TOPIC.finditer(name + " " + " ".join(x[2] for x in mine[:6]))}

    def about(title):
        nm = {n.replace("’s", "").replace("'s", "") for n in gc.names(title)}
        if anchor and anchor.search(title):
            return True
        if len(nm & top) >= 2:
            return not is_us or bool(US_TIE.search(title))
        return is_us and bool(US_TIE.search(title)) and any(re.search(r"\b" + re.escape(t) + r"s?\b", title, re.I) for t in topics)  # same U.S. issue

    picked, seen, used = [], [], set()

    def add(dt_iso, t, outlet, title, link, tie=""):
        n = gc.names(title) | gc.keys(title)
        base = re.sub(r"^(CityNews|CTV News|Global News|CBC News)\b.*", r"\1", outlet)  # one per network
        if base in used or any(len(n & s_) >= 4 for s_ in seen) or any(re.sub(r"\W", "", p_["title"].lower()) == re.sub(r"\W", "", title.lower()) for p_ in picked):
            return
        seen.append(n)
        used.add(base)
        picked.append({"t": t, "iso": dt_iso, "outlet": outlet, "title": clean(title), "url": link, "ca": bool(CAN_OUTLET.search(outlet)), "tie": tie})

    for dt, outlet, title, link, k in recent:
        if len(picked) >= ANGLE_MAX:
            break
        if not CAN_TIE.search(title) or not about(title):
            continue
        if au.OPINION.search(title + " " + link) or SPORT.search(title + " " + link) or VIDEO.search(link + " " + title):
            continue
        add(dt.isoformat(), w.eastern(dt), au.clean_outlet(outlet), title, link)
    specific = len(picked)
    if is_us and (US_POLITICS.search(name) or US_ELECTION.search(name)):
        for x in pool:  # the Canada-U.S. relationship today, newest first
            if len(picked) >= ANGLE_MAX:
                break
            if US_TIE.search(x["title"]) or re.search(r"CUSMA|USMCA|Hoekstra|Washington", x["title"]):  # really about the U.S.
                add(x["iso"], x["t"], x["outlet"], x["title"], x["url"], "Canada and the U.S.")
    official = [{"outlet": p_["name"], "title": p_["hed"], "url": p_["href"], "t": p_["date"]} for p_ in (otr or [])
                if p_.get("cat") in ("pm", "mp") and about(p_["hed"] + " " + p_.get("summary", ""))][:2]
    views = [{"outlet": e[0], "kind": e[1], "title": e[2], "url": e[3]} for e in (eds or []) if about(e[2]) and CAN_TIE.search(e[2])][:2]
    views += [{"outlet": p_["inst"], "kind": "Think tank", "title": p_["t"], "url": p_["u"]} for p_ in (papers or []) if about(p_["t"]) and CAN_TIE.search(p_["t"])][:2]
    if not (picked or official or views):
        return None
    return {"story": name or (words[0] if words else ""), "us": is_us, "specific": specific, "stories": picked, "official": official, "views": views}


def _recent(items, now):
    import autoupdate as au
    return [x for x in items if (now - x[0]).total_seconds() < 72 * 3600 and au.ok_item(x[1], x[3]) and not au.FRENCH.search(x[1])]


def _pool(canus_):
    c = canus_ or {}
    return sorted((c.get("talks") or []) + (c.get("usmedia") or []), key=lambda x: x.get("iso", ""), reverse=True)


def canadian_angle(items, stories, now, eds, papers, otr, canus_=None):
    """{story key: {...}} for the top stories (hand-written, Breaking events and auto top stories) from another country."""
    out, recent, pool = {}, _recent(items, now), _pool(canus_)
    for st_ in stories:
        key, words, own = st_[:3]
        name = st_[3] if len(st_) > 3 else ""
        if not words:
            continue
        rx = re.compile(r"\b(" + "|".join(re.escape(x) for x in words) + r")\b", re.I)
        mine = [x for x in recent if x[3] in own] if own else [x for x in recent if rx.search(x[2]) and (now - x[0]).total_seconds() < 24 * 3600]
        if not mine:
            continue
        nm = name or (mine[0][2] if own else "")
        got = _angle(nm, words, mine, recent, eds, papers, otr, pool, words[:4] if own else words)
        if got:
            out[key] = got
    return out


def canadian_angle_live(items, now, res):
    """The same sidebar for the other headline spots: live coverage (live blogs and live video, now and coming up) and
    What America's newsrooms are leading with. Keyed by the item's own link."""
    import autoupdate as au
    import gap_check as gc
    recent, pool = _recent(items, now), _pool(res.get("canus"))
    targets = [(x.get("title", ""), x.get("url", "")) for x in (res.get("blogs_auto") or [])]
    lv = res.get("live") or {}
    targets += [(x.get("title", ""), x.get("url", "")) for x in (lv.get("now") or []) + (lv.get("upcoming") or [])]
    targets += [(x.get("h", ""), x.get("u", "")) for x in (res.get("ledes") or [])]
    out = {}
    for title, url in targets:
        if not title or not url or url in out or SPORT.search(title + " " + url):
            continue
        t = re.sub(r"^\s*(LIVE|WATCH LIVE|LIVE NOW|LIVE UPDATES)\s*[:|-]\s*", "", title, flags=re.I)
        words = sorted({n.replace("’s", "").replace("'s", "") for n in gc.names(t)
                        if len(n) > 3 and n not in PARTY and n not in GENERIC and (n not in WEAK or n == "trump")}, key=len, reverse=True)[:5]
        if not words:
            continue
        rx = re.compile(r"\b(" + "|".join(re.escape(x) for x in words) + r")\b", re.I)
        mine = [x for x in recent if (now - x[0]).total_seconds() < 24 * 3600 and len({m.lower() for m in rx.findall(x[2])}) >= min(2, len(words))]
        got = _angle(t, words, mine, recent, res.get("eds"), res.get("papers"), res.get("otr"), pool)
        if got:
            out[url] = got
    return out


def canada_tie(s, items, now, eds, papers, otr, canus_):
    """'canadian' (a Canadian story), 'tie' (from another country, with a Canadian angle in the news) or 'none'."""
    import autoupdate as au
    title = s.get("title", "")
    if CAN_TIE.search(title + " " + s.get("summary", "")):
        return "canadian"
    recent = _recent(items, now)
    own = {r["url"] for r in s.get("reports", [])}
    mine = [x for x in recent if x[3] in own]
    if mine and sum(1 for x in mine if CAN_TIE.search(x[2])) * 2 >= len(mine):
        return "canadian"
    if _angle(title, s.get("words") or [], mine, recent, eds, papers, otr, _pool(canus_), (s.get("words") or [])[:4]):
        return "tie"
    foreign = US_STORY.search(title) or (mine and sum(1 for x in mine if FOREIGN_SRC.search(x[3]) or au.US.search(x[1]) or au.WORLDO.search(x[1])) / len(mine) >= FOREIGN_SHARE)
    return "none" if foreign else "canadian"


# ===== A Canadian event happening live is the top news (Hannah, Thu Oct 29, 2026: "the breaking news is still not
# focussing on canada. The european commission president was speaking in montreal and there was news that could have
# been built around that"). After the live streams are found: an event on air now, or due within LIVE_SOON_HOURS, that
# is Canadian (names Canada, a Canadian place or leader) or belongs to a Canadian running theme (Canada and the EU) and
# matches a top-story candidate lifts that story: on air now -> Breaking and LIVE_NOW_BOOST; coming up -> LIVE_SOON_BOOST
# (an announced statement on the top story is the top news until it happens). The story then carries the live link:
# what is on, who is carrying it, the picture, and every other place carrying it.
LIVE_NOW_BOOST, LIVE_SOON_BOOST, LIVE_SOON_HOURS = 20, 8, 3
ROUTINE_LIVE = re.compile(r"Question Period|Top Headlines|News Live|24/7|Daily Briefing|Morning Brief|spacewalk|weather|traffic", re.I)


def _live_theme(title):
    """The running theme a live stream belongs to: its other side named (EU, von der Leyen...) plus Canada, a Canadian
    leader OR a Canadian place ("Von der Leyen, Costa arrive in Montreal" is the Canada-EU summit)."""
    try:
        import lead_check as lc
        for tname, _, ra, rb in lc.THEMES:
            if rb.search(title) and (ra.search(title) or CAN_TIE.search(title)):
                return tname
    except Exception:
        pass
    return ""


def promote_live(res, now):
    if not LAST_PICK:
        return
    auto, cands, tier = LAST_PICK
    lv = res.get("live") or {}
    events = [(e, "now") for e in lv.get("now") or []]
    for e in lv.get("upcoming") or []:
        try:
            t = datetime.fromisoformat(e["when"])
        except Exception:
            continue
        if 0 < (t - now).total_seconds() < LIVE_SOON_HOURS * 3600:
            events.append((e, "soon"))
    hits = []
    for e, state in events:
        title = e.get("title", "")
        theme = _live_theme(title)
        if ROUTINE_LIVE.search(title) or not (CAN_TIE.search(title) or theme):
            continue
        ew = event_words(title) - EVENT_KIND_STOP
        ev_urls = {r["url"] for r in e.get("reports") or []}
        best, best_n = None, 0
        for s in cands:
            if s["canada"] == "none":
                continue
            if theme and s.get("theme") == theme:
                n = 10
            else:
                text = s["title"] + " " + " ".join(r["title"] for r in s.get("reports", []))
                n = len(ew & (event_words(text) - EVENT_KIND_STOP)) + 3 * len(ev_urls & {r["url"] for r in s.get("reports", [])})
            if n > best_n:
                best, best_n = s, n
        if best is None or best_n < 2:
            continue
        hits.append((best, e, state))
    # every stream on the story (Hannah, Thu Oct 29, 2026: "there are live videos that should be attached to the canada
    # eu summit"): on air now first, then coming up; the first is the big live bar, the rest are listed under it
    for s in cands:
        s.pop("live", None); s.pop("live_more", None)
    for s, e, state in sorted(hits, key=lambda h: (h[2] != "now", h[1].get("when") or "")):
        item = {"state": state, "net": e.get("net", ""), "url": e.get("url", ""),
                "title": re.sub(r"^\s*(?:🔴\s*)?(?:WATCH LIVE|LIVE NOW|LIVE)\s*[:|\-–—]\s*", "", e.get("title", ""), flags=re.I).replace(" | LIVE", ""),
                "img": e.get("img", ""), "when": e.get("when", ""), "also": e.get("also", [])[:6]}
        if not s.get("live"):
            s["live"] = item
        elif item["url"] != s["live"]["url"]:
            s.setdefault("live_more", []).append(item)
    clips_ = res.get("clips") or []
    for s in cands:
        if s["canada"] == "none":
            continue
        th = s.get("theme") if s.get("theme") and s["theme"] not in SPLIT_THEMES else ""
        text = s["title"] + " " + " ".join(r["title"] for r in s.get("reports", []))
        sw = event_words(text) - EVENT_KIND_STOP
        vids = []
        for c in clips_:
            t = c.get("t", "")
            if (th and _live_theme(t) == th) or (not th and len(sw & (event_words(t) - EVENT_KIND_STOP)) >= 3):
                vids.append({"net": c["o"], "url": c["u"], "title": t, "img": c.get("img", ""), "rec": bool(c.get("rec")), "up": c.get("up", "")})
        if vids:
            s["videos"] = vids[:4]
    for s in cands:
        if s.get("live"):
            s["weight"] = (s.get("weight") or 0) + (LIVE_NOW_BOOST if s["live"]["state"] == "now" else LIVE_SOON_BOOST)
            if s["live"]["state"] == "now":
                s["tag"] = "Breaking"
    if not hits:
        return
    ranked = sorted(cands, key=lambda s: (tier(s), -(s.get("weight") or 0)))
    _select(auto, cands, ranked, tier)
    print("live lifts:", [(s["title"][:50], s["live"]["state"], s["live"]["title"][:50]) for s, e, st in hits], "-> top:", [s["title"][:50] for s in auto["stories"][:2]])


EVENT_KIND_STOP = set("speaks speak speech remarks holds hold news conference press announcement announces live watch statement update".split())


def _select(auto, cands, ranked, tier):
    """The top two (one per running theme), the spares, the lead slot (more) and the record of why (considered)."""
    global LAST_PICK
    LAST_PICK = (auto, cands, tier)
    seen_t, top2, rest = set(), [], []
    for s in ranked:
        t = s.get("theme")
        if len(top2) < 2 and not (t and t in seen_t):
            top2.append(s)
            if t:
                seen_t.add(t)
        else:
            rest.append(s)
    ranked = top2 + rest
    # keep spares so the page can step past a story whose own Breaking event is showing
    auto["stories"] = ranked[:2] + [s for s in ranked[2:4] if tier(s) < 2 and any(x.get("events") for x in ranked[:2])]
    # the next biggest stories (with a Canadian tie), for the lead slot under the top two when its hand-written story
    # goes stale (Hannah, Wed Oct 28, 2026: "go through the whole page to ensure we have the top news at the top ...
    # update regularly")
    top_themes = {s.get("theme") for s in auto["stories"][:2] if s.get("theme")}
    auto["more"] = [s for s in ranked[2:] if tier(s) < 2 and s not in auto["stories"] and not (s.get("theme") and s["theme"] in top_themes)][:3]
    auto["passed_over"] = [{"title": s["title"], "url": s["url"]} for s in cands if tier(s) == 2 and s not in ranked[:2]]
    # why each story is or isn't at the top (Hannah: "why is that not at the top of the news?")
    auto["considered"] = [{"title": s["title"], "url": s["url"], "rank": n + 1, "live": (s.get("live") or {}).get("title", ""), "weight": s.get("weight"), "score": s.get("score"), "independent": s.get("independent"), "most_read": s["popular"],
                           "canada": s["canada"], "theme": s.get("theme") or "", "top": s in ranked[:2]} for n, s in enumerate(ranked)] + [c for c in (auto.get("considered") or []) if "rank" not in c]


LAST_PICK = None


def pick_by_canada(auto, items, now, eds, papers, otr, canus_, mostread=None):
    """Hannah, Wed Oct 28, 2026: "If there are Canadian ties to a top story, that should be there instead ... the
    Bolsonaro story does not have any Canadian ties, but the JD Vance has multiple. I would switch those out"
    ("especially with so much coming out about the Canada-US relationship"). Of the ranked candidates, the two top
    stories are the highest-ranked ones that are Canadian or tied to Canada (U.S. political stories count when the
    Canada-U.S. relationship is in the news); a story from another country with no Canadian tie only fills a slot
    when nothing else qualifies."""
    cands = (auto or {}).get("stories") or []
    for s in cands:
        try:
            s["canada"] = canada_tie(s, items, now, eds, papers, otr, canus_)
        except Exception as e:
            print("canada tie failed:", e)
            s["canada"] = "canadian"
    # first: the Canada-U.S. relationship and stories from abroad with a Canadian tie; then other Canadian stories;
    # last: stories from abroad with no Canadian tie. Within each, the ranking order (newsrooms, Newswatch, CBC).
    def canus_story(s):
        text = s["title"] + " " + " ".join(r["title"] for r in s.get("reports", [])[:6])
        return bool(CANUS.search(text) or (CAN_TIE.search(text) and US_TIE.search(text)))
    for s in cands:
        s["canus"] = canus_story(s)
    # every candidate gets its running theme from its own headline too, so one event never takes two top spots
    # (the Canada-EU summit came through as two stories, Wed Oct 28, 2026)
    try:
        import lead_check as lc
        for s in cands:
            if not s.get("theme"):
                for tname, _, ra, rb in lc.THEMES:
                    if tname in SPLIT_THEMES:
                        continue
                    if ra.search(s["title"]) and rb.search(s["title"]):
                        s["theme"] = tname
                        break
    except Exception as e:
        print("theme match failed:", e)
    # What Canadians are reading (Hannah, Wed Oct 28, 2026: "look at ... top 5 popular stories on other Canadian websites
    # to judge what our top stories should be"): each candidate scores from the most-read lists it is on, higher for a
    # higher rank and for more sites. Within each tier, the most-read stories go first; then the newsroom ranking.
    for s in cands:
        s["popular"] = popularity(s, mostread)
    # Hannah, Wed Oct 28, 2026: "Any American story that is breaking for the election could go to the top two and attach
    # the Canadian angle to it." A Breaking U.S. election story (Breaking already means 4+ independent newsrooms and a
    # report in the last hour) competes for the top two like a Canadian story; its Canadian angle box is built by
    # canadian_angle() (the Canadian reports on it, then the Canada-U.S. relationship today).
    for s in cands:
        s["us_election"] = us_election_breaking(s)
        if s["us_election"] and s["canada"] == "none":
            s["canada"] = "tie"
    tier = lambda s: 2 if s["canada"] == "none" else 0
    # Within the tier: how big the story is right now. Newsroom coverage and National Newswatch / CBC placement (the
    # group's score), what Canadians are reading (most-read lists, weighted), and a Canadian story ahead of a story from
    # abroad of the same size (Hannah, Wed Oct 28, 2026: Winnipeg's new mayor and the Canada-EU summit were sitting below
    # a smaller foreign story). A big story from abroad with a real Canadian angle (6 Canadians hurt in Spain) can still lead.
    def weight(s):
        w = (s.get("score") or 0) + 2 * s["popular"] + min(s.get("independent") or 0, 10)
        if s["canada"] == "canadian":
            w += CANADIAN_WEIGHT
        if s.get("us_election"):
            w += 4
        return w
    for s in cands:
        s["weight"] = weight(s)
    ranked = sorted(cands, key=lambda s: (tier(s), -s["weight"]))  # stable: ties keep the ranking order
    # one story per running theme in the top pair, so Canada-U.S. leads without crowding out everything else
    # (the rest of the day's Canada-U.S. stories are in the Canada and the U.S. section and the Canadian angle sidebars)
    _select(auto, cands, ranked, tier)
    print("top stories:", " | ".join(f"{s['title'][:50]} [{s['canada']}{' canus' if s['canus'] else ''}{' us-election' if s.get('us_election') else ''} read:{s['popular']}]" for s in cands), "->", [s["key"] for s in auto["stories"]])
    return auto


US_ELECTION = re.compile(r"\b(midterms?|elections?|Election (?:Day|Night)|ballots?|polls? (?:close|closed|open|opened)|exit polls?|"
                         r"vote counts?|projected (?:winner|to win)|wins? (?:re-?election|the race|the seat|control)|concedes?|"
                         r"(?:Senate|House|governor['’]?s?) (?:race|seat|control|majority)|recount|electoral|early voting|voters?)\b", re.I)


def us_election_breaking(s):
    """A Breaking story about the U.S. election (not a Canadian one)."""
    if s.get("tag") != "Breaking":
        return False
    text = s.get("title", "") + " " + " ".join(r["title"] for r in s.get("reports", [])[:6])
    return bool(US_ELECTION.search(text) and (US_STORY.search(text) or US_TIE.search(text)) and not CAN_TIE.search(s.get("title", "")))


# the kind of event a headline is about: the same Canadian place plus the same kind of event is the same story
# ("Gillingham wins another term as Winnipeg mayor" = "Winnipeg election results: Mayor and councillors")
EVENT_KIND = set("""mayor mayoral election elections vote votes voters ballot council councillors premier budget strike strikes
lockout fire fires wildfire wildfires crash collision shooting stabbing storm flood flooding evacuation evacuated
referendum tariff tariffs trade layoffs layoff water outage closure""".split())


def popularity(s, mostread):
    """How high and how widely a story sits on Canadian newsrooms' most-read lists (0 when it is on none)."""
    import gap_check as gc
    if not mostread or not mostread.get("list"):
        return 0
    def words(t):  # names and key words, possessives folded in ("Winnipeg's" is Winnipeg)
        t = re.sub(r"(\w)['’]s\b", r"\1", t)
        return {x for x in gc.names(t) | gc.keys(t) if x.lower() not in WEAK}
    mine = set()
    for t in [s["title"]] + [r["title"] for r in s.get("reports", [])[:8]]:
        mine |= words(t)
    score = 0
    for m in mostread["list"]:
        n = words(m["h"])
        shared = n & mine
        place_or_name = {x for x in shared if x[:1].isalpha() and (CAN_TIE.search(x.title()) or x in {y.lower() for y in gc.names(s["title"])})}
        raw = lambda t: set(re.findall(r"[a-z]+", t.lower()))
        same_kind = EVENT_KIND & raw(m["h"]) & raw(" ".join([s["title"]] + [r["title"] for r in s.get("reports", [])[:8]]))
        if len(shared) >= 3 or (n and len(shared) >= max(2, len(n) // 2)) or (place_or_name and (len(shared) >= 2 or same_kind)):
            score += sum(6 - min(5, o[1]) for o in m.get("o", []))
    return score


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
LIVE_BLOG_HOURS = 3  # a live blog with no new post for this long is not live (the page uses the same number)
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
    out = [o for o in out if not au.BLOG_CLOSED.search(o["title"])]  # "– as it happened": the blog is over
    named_first = [o for o in out if any(nm[1].search(o["title"]) for nm in named)]
    out = (named_first + [o for o in out if o not in named_first])[:16]

    def state(o):  # the blog's own newest post and whether it has ended
        x = curl(o["url"])
        return au.blog_state(x, now) if x else {"updated": None, "ended": False}
    with ThreadPoolExecutor(6) as ex:
        for o, st in zip(out, ex.map(state, out)):
            o["ended"] = st["ended"]
            if st["updated"]:
                o["updated"] = st["updated"]
    out = [o for o in out if not o["ended"] and (now - datetime.fromisoformat(o["updated"])).total_seconds() < LIVE_BLOG_HOURS * 3600][:12]
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
    try:  # the two top stories: Canadian ties first
        res["auto"] = pick_by_canada(res.get("auto") or {}, items, now, res.get("eds"), res.get("papers"), res.get("otr"), res.get("canus"), res.get("mostread"))
    except Exception as e:
        print("autopilot pick failed:", e)
        if res.get("auto"):
            res["auto"]["stories"] = (res["auto"].get("stories") or [])[:2]
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
    try:  # a Canadian event live now (or due soon) lifts its story to the top as Breaking, with the live link
        promote_live(res, now)
        a = res.get("auto") or {}
    except Exception as e:
        print("autopilot live promotion failed:", e)
    print(f"autopilot live blogs: {len(res.get('blogs_auto') or [])}")
    try:
        keyed = [("top" if st["where"].startswith("Top") else st["where"].split("UPNEXT ")[-1].rstrip(")"), words, set(), st["name"]) for st, words in breaking]
        keyed += [(s_["key"], s_.get("words") or [], {r["url"] for r in s_["reports"]}) + ((s_["theme"],) if s_.get("theme") and s_["theme"] not in SPLIT_THEMES else ())
                  for s_ in a.get("stories", []) + a.get("more", [])]
        res["related"] = related(items, keyed, now, res.get("eds"), res.get("papers"), groups)
    except Exception as e:
        print("autopilot related failed:", e)
        res["related"] = prev.get("related") or {}
    try:  # the Canadian angle on top stories from another country (sidebar on the page)
        res["canangle"] = canadian_angle(items, keyed, now, res.get("eds"), res.get("papers"), res.get("otr"), res.get("canus"))
        res["canangle_live"] = canadian_angle_live(items, now, res)
    except Exception as e:
        print("autopilot canangle failed:", e)
        res["canangle"] = prev.get("canangle") or {}
        res["canangle_live"] = prev.get("canangle_live") or {}
    print(f"autopilot Canadian angle: {len(res['canangle'])} top stories ({', '.join(res['canangle'])}), {len(res.get('canangle_live') or {})} live/U.S. headlines")
    try:
        skip = {r["url"] for st in a.get("stories", []) for r in st.get("reports", [])}
        res["bds"] = auto_breakdowns(groups, page, now, imgdir, skip, (prev.get("auto") or {}).get("stories", []))
    except Exception as e:
        print("autopilot bds failed:", e)
        res["bds"] = prev.get("bds") or []
    # Every YouTube video named anywhere on the page (hand-written live boxes, Watch entries, timelines): the ones whose
    # uploader does not allow them in Canada go in geo_blocked, and the page removes them (geoHide in index.html).
    try:
        prevgeo = prev.get("geo") or {}
        ids = sorted(set(re.findall(r"(?:youtube(?:-nocookie)?\.com/(?:watch\?v=|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})", page)))
        for v in ids:
            if prevgeo.get(v, {}).get("v") in ("ok", "blocked") and (now - datetime.fromisoformat(prevgeo[v]["at"])).total_seconds() < 6 * 3600:
                GEO_CACHE.setdefault(v, prevgeo[v]["v"])
        with ThreadPoolExecutor(8) as ex:
            verdicts = dict(zip(ids, ex.map(yt_in_canada, ids)))
        res["geo"] = {v: {"v": r, "at": prevgeo.get(v, {}).get("at") if v in prevgeo and prevgeo[v].get("v") == r else now.isoformat()} for v, r in verdicts.items()}
        res["geo_blocked"] = sorted(v for v, r in GEO_CACHE.items() if r in ("blocked", "unplayable"))
        res["noembed"] = sorted(v for v, inf in YT_INFO.items() if inf and not inf.get("embed", True))
        print(f"autopilot video check: {len(ids)} videos on the page; won't play in Canada: {res['geo_blocked']}; no embedding: {res['noembed']}")
    except Exception as e:
        print("autopilot geo failed:", e)
        res["geo"], res["geo_blocked"] = prev.get("geo") or {}, prev.get("geo_blocked") or []
    print(f"autopilot: {len(a.get('stories', []))} auto stories (takeover {a.get('takeover')}), {len(res['clips'])} clips, {len(res['ledes'])} U.S. ledes, "
          f"{len(res['papers'])} papers, {len(res['eds'])} editorials, canus {len((res['canus'] or {}).get('talks', []))}/{len((res['canus'] or {}).get('usmedia', []))}, brief {bool(res['brief'])}, {len(res['bds'])} breakdowns, {len(res['otr'])} on the record, live {len((res['live'] or {}).get('now', []))} now / {len((res['live'] or {}).get('upcoming', []))} upcoming, PM events {len(res['pm'])}, related for {len(res['related'])} stories, most read {len((res['mostread'] or {}).get('list', []))} from {len((res['mostread'] or {}).get('sites', []))} sites, smaller {len(res['smaller'])}")
    return res
