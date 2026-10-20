#!/usr/bin/env python3
"""Schedule check: keep "Coming up" current for EVERY Breaking story, now and in the future.

Hannah: the "Coming up" section must never be old, for all Breaking news. Run this in EVERY full update and live
check:   python3 tools/schedule_check.py --page index.html

For each story now in the Breaking segment (found from the page itself, like tools/photo_scan.py: the top slot and
every UPNEXT Breaking event, plus events whose next scheduled item is within 2 hours), it prints:
  1. The schedule on the page, each item marked DONE / NOW / NEXT, and a warning when nothing is ahead or the times
     were last checked more than 30 minutes ago.
  2. Scheduling lines found in the newest reports and live blogs on the story: sentences with a time or day AND a
     scheduling word ("to speak", "will address", "news conference", "results", "expected", "vote", "hearing",
     "update", "tonight", "tomorrow", a weekday...). Each comes with its outlet, its post time and link.

Then YOU decide and edit the page (the tool never writes to it):
  - Add each newly announced item to the event's schedule:
      { at: ISO Eastern, to?: ISO, local?: 'local time as announced', text, outlet, url }
    or, when the source gives only a rough time ("Wednesday morning"), { at: a sort time, approx: 'Wed morning', ... }:
    the page shows approx exactly as written, never as a countdown.
  - Fix any changed time (cite the newest source), and remove items that are cancelled (say so in the timeline).
  - Read each time on the source itself; never take it from a search snippet. Convert local times to Eastern.
  - Set scheduleChecked on the UPNEXT entry (and data-schedule-checked on section#breaking) to the real time of
    the check, even if nothing changed.
  - Add the matching COMING entries (one per network) for anything that will be carried live.
The page itself shows upcoming items first, folds finished ones into "Earlier", says "Nothing else is scheduled
yet" when the list is empty, and brings an event back into Breaking 2 hours before any later scheduled item.
"""
import argparse
import html
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photo_scan  # noqa: E402  (shares the story finder, link gatherer, curl and time helpers)

TIME = r"(\b\d{1,2}(:\d{2})?\s?(a\.m\.|p\.m\.|am|pm)\b|\bnoon\b|\bmidnight\b|\btonight\b|\btomorrow\b|\bthis (morning|afternoon|evening)\b|\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b|\b(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.? \d{1,2}\b)"
SCHED = r"(\b(speak|address|announce|hold|testify|appear|meet|vote|rule|release|update|brief|travel|visit)\b|\bnews conference\b|\bpress conference\b|\bbriefing\b|\bresults?\b|\bhearing\b|\bfuneral\b|\bvigil\b|\bmemorial service\b|\bceremony\b|\bsitting\b|\bdebate\b|\bvote\b|\bdeadline\b|\binquest\b|\binquiry\b|\bcourt\b)"
# A line must also look AHEAD: something will happen, is expected, is set or scheduled
AHEAD = r"(\bwill\b|\bto be\b|\bexpected\b|\bscheduled\b|\bplans? to\b|\bset to\b|\bis to\b|\bare to\b|\bupcoming\b|\blater (today|tonight|this)\b|\btonight\b|\btomorrow\b|\bnext (week|month|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b)"


def text_of(page):
    page = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", page)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def posts_of(page):
    """Live-blog posts with their own times (JSON-LD BlogPosting), else the article text with its page time."""
    out = []
    for m in re.finditer(r'"headline":"((?:[^"\\]|\\.)*)","articleBody":"((?:[^"\\]|\\.)*)"(.{0,400}?)"datePublished":"([^"]+)"', page):
        out.append((photo_scan.to_utc(m.group(4)), m.group(1), m.group(2)))
    # CBC live blogs: "articleBody":"…","dateModified":"…","datePublished":"…","url":"…","headline":"…"
    for m in re.finditer(r'"articleBody":"((?:[^"\\]|\\.)*)","dateModified":"[^"]*","datePublished":"([^"]+)","url":"[^"]*","headline":"((?:[^"\\]|\\.)*)"', page):
        out.append((photo_scan.to_utc(m.group(2)), m.group(3), m.group(1)))
    if not out:
        t = photo_scan.meta(page, "article:modified_time") or photo_scan.meta(page, "article:published_time")
        out.append((photo_scan.to_utc(t), photo_scan.meta(page, "og:title"), text_of(page)))
    return out


def lines(url, since_h=18):
    page = photo_scan.curl(url) or ""
    outlet = photo_scan.meta(page, "og:site_name") or url.split("/")[2]
    now = datetime.now(timezone.utc)
    found = []
    for when, head, body in posts_of(page):
        if when and (now - when).total_seconds() > since_h * 3600:
            continue
        body = photo_scan.clean(body.encode().decode("unicode_escape", "ignore") if "\\u" in body else body)
        for sent in re.split(r"(?<=[.!?])\s+", body):
            if 25 < len(sent) < 400 and re.search(TIME, sent, re.I) and re.search(SCHED, sent, re.I) and re.search(AHEAD, sent, re.I):
                sent = sent.strip()
                if len(sent) > 220:  # show the part around the forward-looking words
                    m = re.search(AHEAD, sent, re.I)
                    sent = "…" + sent[max(0, m.start() - 120): m.end() + 120] + "…"
                found.append((when, outlet, photo_scan.clean(head)[:80], sent, url))
    return found


def page_schedule(index, st_name):
    s = open(index, encoding="utf-8").read()
    j = s.find("const UPNEXT = [")
    if j < 0:
        return None, []
    block = s[j: s.find("\n  ];", j)]
    for part in re.split(r"\n    \{ id: ", block)[1:]:
        story = re.search(r"story: '([^']*)'", part)
        if not story or story.group(1) != st_name:
            continue
        chk = re.search(r"scheduleChecked: '([^']*)'", part)
        items = re.findall(r"\{ at: '([^']*)'(?:, to: '([^']*)')?(?:, approx: '([^']*)')?.*?text: '([^']*)'", part)
        return (chk.group(1) if chk else None), items
    return None, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True)
    ap.add_argument("--hours", type=int, default=18, help="only scan posts from the last N hours")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    for st in photo_scan.breaking_stories(a.page):
        print(f"\n=== {st['where']}: {st['name']} ===")
        chk, items = page_schedule(a.page, st["name"])
        if items:
            ahead = 0
            for at, to, approx, text in items:
                t0, t1 = photo_scan.to_utc(at), photo_scan.to_utc(to) if to else None
                end = t1 or t0
                state = "DONE" if end and now > end else ("NOW " if t0 and now >= t0 else "NEXT")
                ahead += state != "DONE"
                print(f"  {state} {approx or (photo_scan.eastern(t0) if t0 else at)} | {text[:110]}")
            if not ahead:
                print("  !! NOTHING AHEAD: find the next scheduled item (news conference, address, results, sitting, vote, hearing, funeral, vigil) or confirm there is none.")
        else:
            print("  (no schedule on the page for this story; the top slot uses COMING entries with top: true)")
        if chk:
            age = (now - photo_scan.to_utc(chk)).total_seconds() / 60
            print(f"  times last checked {photo_scan.eastern(photo_scan.to_utc(chk))} ({int(age)} min ago)" + ("  !! over 30 min" if age > 30 else ""))
        else:
            print("  !! no scheduleChecked time on the page")
        found, seen = [], set()
        for u in photo_scan.story_urls(st, cap=12):
            for f in lines(u, a.hours):
                k = f[3][:120]
                if k not in seen:
                    seen.add(k)
                    found.append(f)
        found.sort(key=lambda f: f[0] or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
        print(f"  scheduling lines in the newest reports ({len(found)}):")
        for when, outlet, head, sent, url in found[:15]:
            print(f"   - {photo_scan.eastern(when) if when else 'time ?'} | {outlet} | {sent[:300]}")
            print(f"     {url}")


if __name__ == "__main__":
    main()
