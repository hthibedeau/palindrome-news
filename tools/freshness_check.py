#!/usr/bin/env python3
"""Freshness check: what on the page has gone stale, so every run changes something real.

Hannah, Tue Oct 20, 2026: "updates to photos, stories, copy, lives should be regular" and "why are you not updating".
Runs were stamping check times without changing the page. Run this at the END of the research step of EVERY full
update and live check (after wire_scan, gap_check, photo_scan, schedule_check):

    python3 tools/freshness_check.py --page index.html

It prints, for each part of the page, how old its newest item is, and a TO DO line for anything past its limit:
  - each Breaking story's photo (its own post time from the photo map, if recorded) vs. the newest photo found;
  - each Breaking story's headline vs. its newest timeline line;
  - the wire (newest item), and each desk: Canada, Politics, Business & Economy, World (newest story time);
  - LIVENOW entries: live blogs whose `updated` is old, and videos past `until`;
  - What to watch items whose date has passed.
A TO DO is work for this run: update it from the newest reports, or say in the summary why nothing newer exists.
"""
import argparse
import re
from datetime import datetime, timedelta, timezone

LIMITS_H = {"wire": 0.75, "Canada": 6, "Politics": 6, "Business & Economy": 8, "World": 6}


def et_now():
    return datetime.now(timezone.utc) - timedelta(hours=4)  # EDT; good enough for ages within the day


def parse_label(lbl, now):
    """'Tue 3:19 p.m.' -> datetime (Eastern, naive) within the last 7 days."""
    m = re.match(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\.? (\d{1,2}):(\d{2}) (a|p)\.m\.", lbl or "")
    if not m:
        return None
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    back = (now.weekday() - days.index(m.group(1))) % 7
    h = int(m.group(2)) % 12 + (12 if m.group(4) == "p" else 0)
    d = (now - timedelta(days=back)).replace(hour=h, minute=int(m.group(3)), second=0, microsecond=0, tzinfo=None)
    return d


def age(d, now):
    return (now.replace(tzinfo=None) - d).total_seconds() / 3600 if d else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="index.html")
    a = ap.parse_args()
    s = open(a.page, encoding="utf-8").read()
    now = et_now()
    todo = []
    print(f"Freshness at {now:%a %H:%M} ET")
    # wire
    i = s.find("const latest = [")
    first = re.search(r"\['([A-Z][a-z]{2} \d{1,2}:\d{2} [ap]\.m\.)'", s[i:i + 3000]) if i >= 0 else None
    h = age(parse_label(first.group(1), now), now) if first else None
    print(f"  wire: newest item {first.group(1) if first else '?'} ({h:.1f} h)" if h is not None else "  wire: ?")
    if h is None or h > LIMITS_H["wire"]:
        todo.append("WIRE: nothing new in 45 min. Run wire_scan/gap_check and add every new story.")
    # desks
    j = s.find("  const stories = [")
    block = s[j: s.find("\n  ];", j)] if j >= 0 else ""
    for desk in ["Canada", "Politics", "Business & Economy", "World"]:
        times = [parse_label(t, now) for t in re.findall(r'^\s*\["[^"]*", "%s", .*"([A-Z][a-z]{2} \d{1,2}:\d{2} [ap]\.m\.)"' % re.escape(desk), block, re.M)]
        times = [t for t in times if t]
        n = len(re.findall(r'^\s*\["[^"]*", "%s"' % re.escape(desk), block, re.M))
        newest = max(times) if times else None
        h = age(newest, now)
        print(f"  {desk}: {n} stories, newest {newest:%a %H:%M} ({h:.1f} h)" if newest else f"  {desk}: {n} stories, no times")
        if h is None or h > LIMITS_H[desk]:
            todo.append(f"{desk.upper()} DESK: newest story is {('%.1f h' % h) if h is not None else 'undated'} old. Add today's newest stories, replace stale ones.")
        if desk == "Canada" and n < 8:
            todo.append(f"CANADA DESK: only {n} stories; keep 8-12 from 5+ provinces (tools/canada_scan.py).")
    # breaking photos
    chk = re.search(r'data-photo-checked="([^"]*)"', s)
    print(f"  top-slot photo last checked: {chk.group(1) if chk else '?'}")
    # Hannah: "constantly look for new photos" — a Breaking photo unchanged for PHOTO_MAX_H hours is a TO DO
    PHOTO_MAX_H = 3
    ps = re.search(r'data-photo-set="([^"]*)"', s)
    sets = [("top slot", ps.group(1))] if ps else []
    sets += [("event " + n, t) for n, t in re.findall(r"\{ id: '([^']*)'[^\n]*?photoSet: '([^']*)'", s)]
    sets += [("event " + n, t) for n, t in re.findall(r"\{ id: '([^']*)', story[^\n]*\n(?:[^\n]*\n){0,200}?\s*photo: '[^']*'[^\n]*?photoSet: '([^']*)'", s)]
    seen_sets = set()
    for who, t in sets:
        if who in seen_sets:
            continue
        seen_sets.add(who)
        try:
            h = (datetime.now(timezone.utc) - datetime.fromisoformat(t).astimezone(timezone.utc)).total_seconds() / 3600
        except ValueError:
            continue
        print(f"  {who} photo set {h:.1f} h ago")
        if h > PHOTO_MAX_H:
            todo.append(f"PHOTO ({who}): unchanged for {h:.1f} h. Run photo_scan.py, switch to a newer captioned photo (keep the old one as a fallback) and update data-photo-set / photoSet, or say why there is none.")
    if not ps:
        todo.append("PHOTO (top slot): no data-photo-set. Add it (the time the photo was put up) whenever the photo changes.")
    # headline vs newest timeline line (top slot)
    k = s.find('id="breaking"')
    seg = s[k: s.find("</section>", k)] if k >= 0 else ""
    tl = re.findall(r"<li><time>([A-Z][a-z]{2} \d{1,2}:\d{2} [ap]\.m\.)</time>", seg)
    lastdev = re.search(r'data-lastdev="([^"]*)"', seg)
    if tl:
        newest_tl = max(filter(None, (parse_label(t, now) for t in tl)))
        print(f"  top-slot newest timeline line: {newest_tl:%a %H:%M}; data-lastdev {lastdev.group(1) if lastdev else '?'}")
    # LIVENOW
    m = s.find("  const LIVENOW = [")
    lv = s[m: s.find("\n  ];", m)] if m >= 0 else ""
    for kind, story, net, upd, until in re.findall(r"kind: '(\w+)', story: '([^']*)', net: '([^']*)'.*?updated: '([^']*)'(?:, until: '([^']*)')?", lv):
        try:
            u = datetime.fromisoformat(upd).astimezone(timezone.utc) - timedelta(hours=4)
        except ValueError:
            continue
        h = age(u.replace(tzinfo=None), now)
        if kind == "updates" and h is not None and 1.5 < h < 24:
            todo.append(f"LIVE BLOG {net} ({story}): `updated` is {h:.1f} h old. Read the blog's newest post time and update it, or drop it if the blog has stopped.")
    # what to watch
    for until, name in re.findall(r'<li data-until="([^"]*)"><span class="when">[^<]*</span><span class="what"><b><a[^>]*>([^<]*)</a>', s):
        try:
            if datetime.fromisoformat(until).astimezone(timezone.utc) < datetime.now(timezone.utc):
                todo.append(f"WHAT TO WATCH: '{name}' has passed. Remove it and add what is next.")
        except ValueError:
            pass
    if "<li><span class=\"when\">" in s[s.find('aside class="watch"'): s.find('</aside>', s.find('aside class="watch"'))]:
        todo.append("WHAT TO WATCH: an item has no data-until date; give every item one so it drops off by itself.")
    # Hannah: "I need the program to continually scan for the latest news. The Wainwright story is not the most up to
    # date." Every Breaking story: any report on it newer than the story's last development that the page does not
    # link yet is a TO DO (read it; add the new facts to the timeline, summary, headline; or say why not).
    try:
        import os, sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import photo_scan as _ps, wire_scan as _ws
        items = []
        for outlet, url in _ws.FEEDS:
            items += _ws.rss(outlet, url)
        for outlet, url, marker, base in _ws.FRONTS:
            items += _ws.front(outlet, url, marker, base)
        links = set(u.split("?")[0].rstrip("/") for u in re.findall(r"https?://[^\s\"'<>]+", s))
        nowu = datetime.now(timezone.utc)
        for st in _ps.breaking_stories(a.page):
            words = []
            if st["where"].startswith("Top"):
                mm = re.search(r'data-match="([^"]*)"', s)
                words = [w.strip() for w in (mm.group(1).split(",") if mm else []) if w.strip()]
                ld = re.search(r'data-lastdev="([^"]*)"', s)
                since = _ps.to_utc(ld.group(1)) if ld else None
            else:
                ev = st["where"].split("UPNEXT ")[-1].rstrip(")")
                blk = s[s.find("{ id: '%s'" % ev):]
                blk = blk[: blk.find("schedule: [")]
                mm = re.search(r"match: \[([^\]]*)\]", blk)
                words = re.findall(r"'([^']+)'", mm.group(1)) if mm else []
                tl = re.findall(r"\['((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2}:\d{2} [ap]\.m\.)'", blk)
                newest = max([t for t in (parse_label(x, now) for x in tl) if t], default=None)
                since = (newest + timedelta(hours=4)).replace(tzinfo=timezone.utc) if newest else None
            words = words or _ps.keywords(st["name"])
            rx = re.compile("|".join(re.escape(w) for w in words), re.I)
            newer, seen = [], set()
            for dt_, outlet, title, link in items:
                k = link.split("?")[0].rstrip("/")
                if not dt_ or k in seen or k in links or not rx.search(title):
                    continue
                if since and dt_ <= since:
                    continue
                if (dt_ - nowu).total_seconds() > 600 or (nowu - dt_).total_seconds() > 12 * 3600:
                    continue
                seen.add(k)
                newer.append((dt_, outlet, title, link))
            newer.sort(reverse=True)
            print(f"  {st['name']}: {len(newer)} report(s) newer than its last development, not yet on the page")
            for dt_, outlet, title, link in newer[:8]:
                print(f"      {_ws.eastern(dt_)} | {outlet} | {title[:100]} | {link}")
            if newer:
                todo.append(f"STORY {st['name']}: {len(newer)} newer report(s) not on the page (listed above). Read them; add each new fact to the timeline with its real time, rewrite the summary and headline newest-first, set data-lastdev; or say why each adds nothing.")
    except Exception as e:  # never block the run
        print("  (story check unavailable:", e, ")")
    print("\nTO DO this run:" if todo else "\nNothing stale.")
    for t in todo:
        print("  - " + t)


if __name__ == "__main__":
    main()
