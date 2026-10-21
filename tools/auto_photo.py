#!/usr/bin/env python3
"""Auto photo: put the newest captioned news photo on every Breaking story, automatically.

Hannah, Tue Oct 20, 2026: "I need you to constantly look for new photos … the one for Alberta votes has been the same
all day" and "This has to always happen in the code. The latest photos, captions and source."

Run in EVERY full update and live check:

    python3 tools/auto_photo.py --page index.html            # show what it would change
    python3 tools/auto_photo.py --page index.html --apply    # change the page

For each story in the Breaking segment (found by tools/photo_scan.py: the top slot and every live UPNEXT event) it:
  1. gathers the story's newest reports and live blogs (photo_scan.story_urls) and reads every photo with its own
     caption, credit and post time (JSON-LD live-blog posts, article images, and <figcaption> on the page);
  2. keeps only photos that have a caption AND a credit, are at least MIN_WIDTH pixels wide, and were posted AFTER the
     photo now on the page was put up (data-photo-set on section#breaking, photoSet on the UPNEXT entry);
  3. picks the newest; with --apply it saves it to img/live/, writes the photo, the caption exactly as published
     "(credit) — via <outlet>", the alt text, and the new set time into the page, and keeps the previous photo as the
     first fallback (topSlotImage's imageChain for the top slot; `photos` on the UPNEXT entry).
It prints FILES TO UPLOAD: upload each to the preview as an asset and map it in LOCAL (or pass --blob file=/_blob/id).

Look at every applied photo with Read before publishing. Never use a photo that does not show the story, and for a
contested vote prefer a neutral scene or the people now speaking over one side's rally; if the newest photo fails
that test, run again with --skip <image url> to take the next one.
"""
import argparse
import html
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photo_scan as ps  # noqa: E402

MIN_WIDTH = 900
HERE = os.path.dirname(os.path.abspath(__file__))


def figcaptions(url):
    """Photos captioned on the page itself (<figure><img …><figcaption>), with the page's publish time."""
    page = ps.curl(url) or ""
    when = ps.to_utc(ps.meta(page, "article:published_time") or (re.search(r'"datePublished":"([^"]+)"', page) or [None, None])[1])
    outlet = ps.meta(page, "og:site_name") or url.split("/")[2]
    out = []
    for fig in re.findall(r"<figure\b.*?</figure>", page, re.S)[:6]:
        img = re.search(r'<img[^>]+(?:data-src|src)="(https?://[^"]+)"', fig)
        cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", fig, re.S)
        if not (img and cap):
            continue
        text = " ".join(html.unescape(re.sub(r"<script.*?</script>|<[^>]+>", " ", cap.group(1), flags=re.S)).split())
        credit = ""
        m = re.search(r"\(([^()]*(?:Press|Photo|CBC|CTV|Global|Getty|Reuters|AP|Postmedia|Submitted|Handout|file)[^()]*)\)\s*$", text)
        if m:
            credit, text = m.group(1).strip(), text[: m.start()].strip()
        else:
            m = re.search(r"((?:[A-Z][\w.'-]+ ){1,3}[A-Z][\w.'-]+/ ?[^.]*?(?:Press|Postmedia|Reuters|Getty|AP|CBC|CTV|Global News)[^.]*)$", text)
            if m:
                credit, text = m.group(1).strip(), text[: m.start()].strip()
            m = re.search(r"THE CANADIAN PRESS/([^.]+)", text)
            if m and not credit:
                credit, text = "The Canadian Press/" + m.group(1).strip(), text[: m.start()].strip()
        out.append({"when": when, "outlet": outlet, "caption": text, "credit": credit, "src": html.unescape(img.group(1)), "url": url})
    return out


def candidates(st):
    rows = []
    for u in ps.story_urls(st, cap=12):
        for r in ps.scan(u):
            rows.append({"when": r["when"], "outlet": r["outlet"], "caption": r["caption"], "credit": r["credit"], "src": r["src"], "url": r["url"]})
        rows += figcaptions(u)
    seen, good = set(), []
    for r in sorted(rows, key=lambda r: r["when"] or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True):
        k = re.sub(r"\?.*", "", r["src"])
        if k in seen or not r["when"] or not r["caption"] or not r["credit"]:
            continue
        seen.add(k)
        good.append(r)
    return good


def fetch_ok(src):
    try:
        from PIL import Image
    except ImportError:
        return None
    data = subprocess.run(["curl", "-sL", "-m", "25", "-A", ps.UA, "--", src], capture_output=True).stdout
    try:
        im = Image.open(io.BytesIO(data))
        return im if im.size[0] >= MIN_WIDTH else None
    except Exception:
        return None


OUTLETS = {"winnipegfreepress.com": "Winnipeg Free Press", "ici.radio-canada.ca": "Radio-Canada", "timescolonist.com": "Times Colonist",
           "cbc.ca": "CBC News", "ctvnews.ca": "CTV News", "globalnews.ca": "Global News", "thestar.com": "Toronto Star",
           "nationalpost.com": "National Post", "calgaryherald.com": "Calgary Herald", "edmontonjournal.com": "Edmonton Journal",
           "citynews.ca": "CityNews", "cp24.com": "CP24", "aptnnews.ca": "APTN News", "lapresse.ca": "La Presse",
           "ledevoir.com": "Le Devoir", "theglobeandmail.com": "The Globe and Mail", "bnnbloomberg.ca": "BNN Bloomberg"}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre"
MNUM = {m.lower(): i % 12 + 1 for i, m in enumerate(MONTHS.split("|"))}


def outlet_name(o, url):
    host = re.sub(r"^www\.", "", (o if "." in (o or "") and " " not in o else url.split("/")[2]).lower())
    for k, v in OUTLETS.items():
        if host == k or host.endswith("." + k):
            return v
    return o if o and "." not in o else host


def old_photo(c, now):
    """True for file/archive photos and photos whose caption dates them more than 2 days back (Hannah wants the latest)."""
    t = c["caption"] + " " + c["credit"]
    if re.search(r"\bfile\b|archives?\b|d[’']archives|earlier this (year|month)|in a (?:\d{4} )?photo", t, re.I):
        return True
    if re.search(r"chroniqueu|columnist|\bprofil", t + " " + c["src"], re.I):
        return True  # a writer's headshot is not news
    for m in re.finditer(r"\b(%s)\.? (\d{1,2})(?:er)?\b(?:,? (20\d\d))?|\b(\d{1,2})(?:er)? (%s)\b(?: (20\d\d))?" % (MONTHS, MONTHS), t, re.I):
        try:
            mon, day, yr = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(4), m.group(6))
            d = datetime(int(yr or now.year), MNUM[mon.lower()], int(day), tzinfo=timezone.utc)
            if not yr and d > now + timedelta(days=1):
                d = d.replace(year=now.year - 1)
        except (ValueError, KeyError):
            continue
        if (now - d).days > 2:
            return True
    return False


def story_words(page, st):
    """The story's own match words (data-match on the top slot, match: [...] on an UPNEXT event)."""
    if st["where"].startswith("Top"):
        m = re.search(r'data-match="([^"]*)"', page)
        w = [x.strip() for x in (m.group(1).split(",") if m else []) if x.strip()]
    else:
        ev = st["where"].split("UPNEXT ")[-1].rstrip(")")
        blk = page[page.find("{ id: '%s'" % ev):]
        m = re.search(r"match: \[([^\]]*)\]", blk[: blk.find("schedule: [")])
        w = re.findall(r"'([^']+)'", m.group(1)) if m else []
    return w or ps.keywords(st["name"])


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--skip", action="append", default=[], help="image url to pass over")
    ap.add_argument("--blob", action="append", default=[], help="img/live/file.jpg=/_blob/<id> to map in LOCAL")
    a = ap.parse_args()
    s = open(a.page, encoding="utf-8").read()
    now = datetime.now(timezone.utc)
    stamp = datetime.now().astimezone().isoformat(timespec="minutes")
    uploads = []
    for st in ps.breaking_stories(a.page):
        top = st["where"].startswith("Top")
        if top:
            m = re.search(r'data-photo-set="([^"]*)"', s)
        else:
            ev_id = st["where"].split("UPNEXT ")[-1].rstrip(")")
            blk = s[s.find("{ id: '%s'" % ev_id):]
            m = re.search(r"photoSet: '([^']*)'", blk[: blk.find("schedule: [")])
        since = ps.to_utc(m.group(1)) if m else None
        print(f"\n=== {st['where']}: {st['name']} (photo set {since.isoformat() if since else 'unknown'})")
        pick = None
        for c in candidates(st):
            if c["src"] in a.skip or (since and c["when"] <= since):
                continue
            if old_photo(c, now):
                print(f"   skip (file/archive or dated photo): {c['caption'][:90]}")
                continue
            if not re.search("|".join(re.escape(x) for x in story_words(s, st)), c["caption"], re.I):
                print(f"   skip (caption is not about this story): {c['caption'][:90]}")
                continue
            c["outlet"] = outlet_name(c["outlet"], c["url"])
            im = fetch_ok(c["src"])
            if im is None:
                print(f"   skip (too small or unreadable): {c['src'][:90]}")
                continue
            pick = (c, im)
            break
        if not pick:
            print("   nothing newer with a caption and credit; keep the current photo and say so in the summary")
            continue
        c, im = pick
        cap = f"{c['caption'].rstrip('.')}. ({c['credit']}) — via {c['outlet']}"
        print(f"   NEWER: {ps.eastern(c['when'])} | {c['outlet']} | {cap}\n          {c['src'][:120]}")
        if not a.apply:
            continue
        fn = f"img/live/{slug(c['outlet'])}-{slug(st['name'])}-{c['when']:%m%d-%H%M}.jpg"
        im.convert("RGB").save(os.path.join(os.path.dirname(os.path.abspath(a.page)), fn), quality=84)
        uploads.append(fn)
        credit = f"{c['credit']}, via {c['outlet']}"
        alt = c["caption"] if len(c["caption"]) <= 160 else c["caption"][:160].rsplit(" ", 1)[0] + "…"
        if top:
            old = re.search(r'<div class="bart"([^>]*)>', s[s.find('id="breaking"'):])
            tag = old.group(0)
            o_src = re.search(r'data-photo="([^"]*)"', tag).group(1)
            o_cr = (re.search(r'data-credit="([^"]*)"', tag) or [None, ""])[1]
            o_cap = (re.search(r'data-caption="([^"]*)"', tag) or [None, ""])[1]
            new = re.sub(r'data-photo="[^"]*"', f'data-photo="{fn}"', tag)
            new = re.sub(r'data-credit="[^"]*"', f'data-credit="{html.escape(credit)}"', new)
            new = re.sub(r'data-caption="[^"]*"', f'data-caption="{html.escape(cap)}"', new)
            new = re.sub(r'data-alt="[^"]*"', f'data-alt="{html.escape(alt)}"', new)
            s = s.replace(tag, new, 1)
            s = re.sub(r'data-photo-set="[^"]*"', f'data-photo-set="{stamp}"', s, count=1)
            fb = "{ src: %s, credit: %s, caption: %s }, " % (json.dumps(o_src), json.dumps(html.unescape(o_cr), ensure_ascii=False), json.dumps(html.unescape(o_cap), ensure_ascii=False))
            s = s.replace("imageChain(bart, [own, ", "imageChain(bart, [own, " + fb, 1)
        else:
            i = s.find("{ id: '%s'" % ev_id)
            j = s.find("schedule: [", i)
            part = s[i:j]
            mo = re.search(r"photo: '([^']*)', credit: '([^']*)', caption: '([^']*)', alt: '([^']*)',", part)
            q = lambda x: x.replace("'", "’")
            newp = f"photo: '{fn}', credit: '{q(credit)}', caption: '{q(cap)}', alt: '{q(alt)}',"
            part2 = part.replace(mo.group(0), newp, 1)
            part2 = re.sub(r"photoSet: '[^']*'", f"photoSet: '{stamp}'", part2, count=1) if "photoSet:" in part2 else part2.replace(newp, newp + f" photoSet: '{stamp}',", 1)
            old = "{ src: '%s', credit: '%s', caption: '%s' }" % (mo.group(1), mo.group(2), mo.group(3))
            part2 = part2.replace("photos: [", "photos: [" + old + ", ", 1) if "photos: [" in part2 else part2.replace(newp, newp + " photos: [" + old + "],", 1)
            s = s[:i] + part2 + s[j:]
        print(f"   APPLIED -> {fn}")
    for b in a.blob:
        f, blob = b.split("=", 1)
        s = s.replace("  const LOCAL = {", "  const LOCAL = {" + json.dumps(f) + ": " + json.dumps(blob) + ", ", 1)
    if a.apply or a.blob:
        open(a.page, "w", encoding="utf-8").write(s)
    if uploads:
        print("\nFILES TO UPLOAD (asset upload to the preview, then rerun with --blob file=/_blob/id, or edit LOCAL):")
        for f in uploads:
            print("  " + f)


if __name__ == "__main__":
    main()
