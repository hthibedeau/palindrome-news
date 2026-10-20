#!/usr/bin/env python3
"""Photo scan: the newest real news photos on a story, each with its OWN caption, credit and time.

Hannah: "Always find the best and most up to date photo to go into the breaking section", "Always check for new
photos every 15 minutes from all sources", and every photo carries the originator's caption. Run this in EVERY photo
check (full updates and live checks, for the top slot and every Breaking event), on every live blog and newest
report you found for the story (tools/wire_scan.py --grep "<story words>" gives the newest links).

What it reads, per page:
  1. Live-blog posts (CBC and others publishing JSON-LD BlogPosting/LiveBlogPosting): each post's own photo with
     its caption, creditText and the post's datePublished. This is where the newest photos are on a running story.
     (Worked out Mon Oct 19, 2026, the first night CBC photos on i.cbc.ca could be downloaded.)
  2. The article's own JSON-LD image (NewsArticle image with caption/creditText) and its published/modified time.
  3. The share photo (og:image). Its caption is printed ONLY if the page states one for that same picture; a share
     photo is never paired with another post's caption. Without a caption it is marked NO CAPTION: use it only if
     the outlet's own caption can be found on the page or its photo page.

Output: newest first, one block per photo: time (ET), outlet page, caption, credit, image url.
--download DIR saves each photo (1280 wide for CBC) as DIR/<n>.jpg so you can look at it with Read before choosing.

Choosing (house rules 18, 18b and 19 in full-update.md; BREAKING_TEMPLATE.md step 1):
  - Newest photo that shows the story, real news photography, never a drawing; look at it before using it.
  - Use the caption exactly as published, then "(<credit>) — via <outlet>". Credit = creditText.
  - Contested votes and campaigns: prefer a neutral scene (polling station, counting, officials) over one side's
    rally or watch party, unless both sides are shown.
  - Victims and families: only photos the family or an outlet published; never from social media directly.
  - Keep the previous photo as the first fallback in imageChain (top slot) so the slot is never empty.

Usage:
  python3 tools/photo_scan.py --page index.html [--download /tmp/photos]
      EVERY BREAKING STORY, WHATEVER IT IS: reads the page itself to find each story now in the Breaking
      segment (the top slot, section#breaking, and every UPNEXT Breaking event that has not ended). For each
      one it gathers the story's own links (the LATEST link, live blogs, timeline and source links on the page)
      and the newest wire reports matching the story's name (tools/wire_scan.py), then lists the newest photos
      with captions. Nothing is tied to any one story: new Breaking stories are picked up automatically.
  python3 tools/photo_scan.py <url> [<url> ...] [--download /tmp/photos] [--limit 8]
      Just these pages.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def curl(url, out=None):
    cmd = ["curl", "-sL", "-m", "25", "-A", UA]
    if out:
        cmd += ["-o", out]
    r = subprocess.run(cmd + ["--", url], capture_output=True)
    return r.stdout.decode("utf-8", "ignore") if (r.returncode == 0 and not out) else (r.returncode == 0)


def to_utc(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def eastern(dt):
    y = dt.year
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    first_sun_nov = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    second_sun_mar = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)
    dst = second_sun_mar + timedelta(hours=7) <= dt < first_sun_nov + timedelta(hours=6)
    local = dt + timedelta(hours=-4 if dst else -5)
    h = local.hour % 12 or 12
    return local.strftime("%a ") + f"{h}:{local.minute:02d} " + ("a.m." if local.hour < 12 else "p.m.")


def clean(s):
    return html.unescape((s or "").replace("\\u002F", "/").replace("\\u0026", "&")).strip()


def ld_blocks(page):
    out = []
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        txt = re.sub(r":undefined([,}\]])", r":null\1", m.group(1))
        try:
            out.append(json.loads(txt))
        except ValueError:
            pass
    return out


def walk(o, acc, when=None, head=None):
    if isinstance(o, dict):
        when = o.get("datePublished") or o.get("dateModified") or when
        head = o.get("headline") or head
        img = o.get("image")
        for im in (img if isinstance(img, list) else [img]):
            if isinstance(im, dict) and (im.get("contentUrl") or im.get("url")):
                acc.append({"when": when, "post": head, "caption": im.get("caption") or im.get("description"),
                            "credit": im.get("creditText") or im.get("copyrightHolder") or im.get("author"),
                            "src": im.get("contentUrl") or im.get("url")})
        for k, v in o.items():
            if k != "image":
                walk(v, acc, when, head)
    elif isinstance(o, list):
        for v in o:
            walk(v, acc, when, head)


def cbc_states(page, acc):
    # CBC live blogs: the same BlogPosting objects also sit in the page's inline JSON
    pat = (r'"datePublished":"([^"]*)","url":"[^"]*","headline":"([^"]*)","image":\{"@type":"ImageObject",'
           r'"caption":"([^"]*)","creditText":"([^"]*)","contentUrl":"([^"]*)"')
    for m in re.finditer(pat, page):
        acc.append({"when": m.group(1), "post": m.group(2), "caption": m.group(3), "credit": m.group(4), "src": m.group(5)})


def meta(page, prop):
    m = re.search(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]*)"' % re.escape(prop), page) or \
        re.search(r'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="%s"' % re.escape(prop), page)
    return clean(m.group(1)) if m else ""


def best_src(src):
    src = clean(src)
    m = re.match(r"(https://i\.cbc\.ca/ais/[^/]+/full/max/0/default\.jpg)", src)
    return (m.group(1) + "?im=Resize%3D1280") if m else src


def key(src):
    m = re.search(r"ais/([0-9a-f-]{36})", src)
    return m.group(1) if m else src.split("?")[0]


def scan(url):
    page = curl(url) or ""
    outlet = meta(page, "og:site_name") or re.sub(r"^www\.", "", url.split("/")[2])
    acc = []
    for b in ld_blocks(page):
        walk(b, acc)
    cbc_states(page, acc)
    og = meta(page, "og:image")
    if og:
        acc.append({"when": meta(page, "article:modified_time") or meta(page, "article:published_time"),
                    "post": meta(page, "og:title"), "caption": None, "credit": None, "src": og, "share": True})
    rows, seen = [], {}
    for a in acc:
        src = best_src(a["src"])
        k = key(src)
        if k in seen:
            r = seen[k]
            r["caption"] = r["caption"] or clean(a.get("caption"))
            r["credit"] = r["credit"] or clean(a.get("credit") if isinstance(a.get("credit"), str) else "")
            continue
        r = {"url": url, "outlet": outlet, "when": to_utc(a.get("when")), "post": clean(a.get("post")),
             "caption": clean(a.get("caption")), "credit": clean(a.get("credit")) if isinstance(a.get("credit"), str) else "",
             "src": src, "share": bool(a.get("share"))}
        seen[k] = r
        rows.append(r)
    return rows


STOP = set("""the a an and of in on at to for from with after before over under into as by is are was were be
this that these those its their his her new latest live updates update story news fire deadly""".split())


def keywords(name):
    """Distinctive words of a story's name: capitalized words and long words, e.g. 'the CFB Wainwright fire' ->
    CFB, Wainwright; 'Alberta referendum' -> Alberta, referendum."""
    words = re.findall(r"[A-Za-zÀ-ſ'’-]+", name or "")
    keep = [w for w in words if w.lower() not in STOP and (w[0].isupper() or len(w) >= 7)]
    return keep or [w for w in words if w.lower() not in STOP]


def breaking_stories(index):
    s = open(index, encoding="utf-8").read()
    now = datetime.now(timezone.utc)
    out = []
    i = s.find('id="breaking"')
    if i >= 0:
        tag = s[s.rfind("<section", 0, i): s.find(">", i)]
        body = s[i: s.find("</section>", i)]
        name = (re.search(r'data-story="([^"]*)"', tag) or [None, "top story"])[1]
        links = [m for m in re.findall(r'data-latest="([^"]+)"', tag)] + re.findall(r'href="(https?://[^"]+)"', body)
        cap = re.search(r'class="bart[^"]*"[^>]*data-caption="([^"]*)"', body)
        out.append({"where": "Top slot (section#breaking)", "name": name, "links": links,
                    "current": html.unescape(cap.group(1)) if cap else ""})
    j = s.find("const UPNEXT = [")
    if j >= 0:
        block = s[j: s.find("\n  ];", j)]
        for part in re.split(r"\n    \{ id: ", block)[1:]:
            story = re.search(r"story: '([^']*)'", part)
            until = re.search(r"until: '([^']*)'", part)
            later = [to_utc(x) for x in re.findall(r"\{ at: '([^']*)'", part)]
            if until and to_utc(until.group(1)) and to_utc(until.group(1)) < now and not any(t and t > now for t in later):
                continue  # ended, with nothing scheduled later: no longer Breaking
            links = re.findall(r"url: '(https?://[^']+)'", part) + re.findall(r"'(https?://[^']+)'", part)
            cap = re.search(r"caption: '([^']*)'", part)
            out.append({"where": "Breaking event (UPNEXT " + part.split(",")[0].strip("' ") + ")",
                        "name": story.group(1) if story else "", "links": links, "current": cap.group(1) if cap else ""})
    return out


def story_urls(st, cap=10):
    seen, urls = set(), []
    def add(u):
        k = u.split("?")[0].split("#")[0].rstrip("/")
        if k in seen or "theglobeandmail.com" in u or re.search(r"\.(jpg|png|pdf)$", k):
            return
        seen.add(k)
        urls.append(u)
    live = [u for u in st["links"] if re.search(r"live|/livestory/|en-direct", u)]
    for u in live:
        add(u)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import wire_scan
        rx = re.compile("|".join(map(re.escape, keywords(st["name"]))), re.I)
        items = []
        for outlet, url in wire_scan.FEEDS:
            items += wire_scan.rss(outlet, url)
        for outlet, url, marker, base in wire_scan.FRONTS:
            items += wire_scan.front(outlet, url, marker, base)
        items = [x for x in items if x[0] and rx.search(x[2] + " " + x[3])]
        items.sort(key=lambda x: x[0], reverse=True)
        for x in items[:6]:
            add(x[3])
    except Exception as e:  # the page's own links still work without the wire
        print("wire scan unavailable:", e, file=sys.stderr)
    for u in st["links"]:
        add(u)
    return urls[:cap]


def report(rows, limit, download, tag=""):
    rows.sort(key=lambda r: r["when"] or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    if download:
        os.makedirs(download, exist_ok=True)
    for i, r in enumerate(rows[:limit], 1):
        cap = r["caption"] or "NO CAPTION (share photo; find the outlet's own caption before using it)"
        print(f"[{tag}{i}] {eastern(r['when']) if r['when'] else 'time unknown'} | {r['outlet']} | {r['post'][:90]}")
        print(f"    caption: {cap}")
        print(f"    credit:  {r['credit'] or '-'}")
        print(f"    image:   {r['src']}")
        print(f"    page:    {r['url']}")
        if download:
            f = os.path.join(download, f"{tag}{i}.jpg")
            print(f"    saved:   {f}" if curl(r["src"], f) else "    saved:   DOWNLOAD FAILED (host blocked?)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--page", default="", help="index.html: check every story now in the Breaking segment")
    ap.add_argument("--download", default="")
    ap.add_argument("--limit", type=int, default=8)
    a = ap.parse_args()
    if a.page:
        stories = breaking_stories(a.page)
        if not stories:
            print("No Breaking stories found on the page.")
        for n, st in enumerate(stories, 1):
            urls = story_urls(st)
            print(f"\n=== {st['where']}: {st['name']} ===")
            print(f"    now on the page: {st['current'] or '(no caption)'}")
            print(f"    pages checked ({len(urls)}): " + ", ".join(re.sub(r"https?://(www\.)?([^/]+).*", r"\2", u) for u in urls))
            rows = []
            for u in urls:
                rows += scan(u)
            report(rows, a.limit, a.download, tag=f"s{n}-")
        return
    if not a.urls:
        ap.error("give page urls, or --page index.html")
    rows = []
    for u in a.urls:
        got = scan(u)
        if not got:
            print("NO PHOTOS FOUND (or page blocked):", u, file=sys.stderr)
        rows += got
    report(rows, a.limit, a.download)


if __name__ == "__main__":
    main()
