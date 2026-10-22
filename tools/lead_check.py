#!/usr/bin/env python3
"""Lead check: what should the top two stories be right now?

Hannah, Wed Oct 21, 2026: "get hints from National Newswatch, Political Playbook and other locations. Look at all
sources and decide what should be the top two stories of the day."

    python3 tools/lead_check.py --page index.html          # ranking + advice
(tools/autoupdate.py also calls it every 10 minutes and puts the ranking in live/auto.json as "leads".)

It scores every story the newsrooms are running (grouped the way gap_check.py groups headlines):
  +4  in National Newswatch's top 8 (the editors' pick of Canada's political news, in their order)
  +3  in the top 6 of CBC News's own front page (CTV's list is by time, so it is not used for rank)
  +1  for every newsroom carrying it in the last 6 hours (up to +15)
  +2  if its newest report is under 2 hours old
Opinion, sports and lifestyle never count. Politico's Ottawa Playbook refuses automated reading (403); read it
through search when a run has time. The two Breaking/Developing stories on the page are compared with the ranking:
if a story the page does not lead with outscores one of them by 4 or more, it prints SWAP, and a run should move
the weaker one down to its desk (archive/ keeps the full block) and put the stronger one up.

Hannah, Wed Oct 21, 2026 (the Canada–U.S. day the check missed): a big story is often a THEME told through several
headlines (Carney–Trump call, the U.S. Embassy's interference claims, Clinton on Canada, ex-diplomats' response).
So: headlines that match both sides of a THEME (below) are scored as one story, each National Newswatch entry in it
counts (higher spots count more), an event kept on the page by keepUntil still counts as a slot, and when a story
outranks a slot it prints PROMOTE with the words to use, so the run makes it the top Developing story.
"""
import argparse
import html
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wire_scan as w  # noqa: E402
import gap_check as gc  # noqa: E402
from autoupdate import SOFT  # noqa: E402

UA = w.UA
OPINION = re.compile(r"/opinion|/columnists?/|/editorials?/|\| ?Opinion|^Opinion", re.I)


# Running themes: a headline belongs to a theme when it matches BOTH patterns. Add a theme whenever a story keeps
# coming back under different headlines.
THEMES = [
    ("Canada and the U.S.", "Canada and the U.S.",
     re.compile(r"\b(Canad\w*|Carney|Ottawa|Joly|LeBlanc|Champagne|Anand|Ford|Poilievre|premiers?)\b", re.I),
     re.compile(r"\b(Trump|U\.?S\.?|American|Americans|Washington|White House|Hoekstra|Lutnick|Greer|embassy|midterms?|tariffs?|CUSMA|USMCA|trade war|51st state|Clinton|Rubio|Vance)\b")),
]


def nn_bonus(i):
    """National Newswatch spot i (0-based): #1 +6, #2 +5, #3 +4, then +3 to #8, +2 below."""
    return 6 - i if i < 3 else (3 if i < 8 else 2)


def curl(u):
    r = subprocess.run(["curl", "-sL", "-m", "25", "-A", UA, "--", u], capture_output=True)
    return r.stdout.decode("utf-8", "ignore") if r.returncode == 0 else ""


def newswatch(n=20):
    s = curl("https://www.nationalnewswatch.com/")
    out = []
    for u, t in re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', s, re.S):
        t = " ".join(html.unescape(re.sub(r"<[^>]+>", "", t)).split())
        if len(t) > 35 and "nationalnewswatch" not in u and not OPINION.search(u + " " + t) and "Your browser" not in t:
            out.append((t, u))
        if len(out) >= n:
            break
    return out


def rank(items=None, now=None):
    now = now or datetime.now(timezone.utc)
    if items is None:
        items = []
        for o, u in w.FEEDS:
            items += w.rss(o, u)
    fronts = {}
    for o, u, m, b in w.FRONTS[:1]:  # CBC News home page, in its editors' order (CTV's list is by time, not rank)
        got = [x for x in w.front(o, u, m, b) if not OPINION.search(x[3]) and "LIVE" not in x[2]]
        fronts[o] = got[:6]
        items += got
    rows = [x for x in items if x[0] and 0 <= (now - x[0]).total_seconds() < 6 * 3600 and not re.search(gc.SKIP, x[2], re.I)
            and not OPINION.search(x[3] + " " + x[2]) and not SOFT.search(x[2] + " " + x[3])
            and not re.search(r"jackpot|Lotto|died of natural causes", x[2], re.I)]
    groups = []

    def place(title, link, outlet, dt, bonus, why):
        n, k = gc.names(title), gc.keys(title)
        for g in groups:
            if len(n & g["n"]) >= 2 or (len(n & g["n"]) >= 1 and len(k & g["k"]) >= 2) or len(k & g["k"]) >= 4:
                break
        else:
            g = {"n": set(), "k": set(), "outlets": set(), "bonus": 0, "why": [], "lead": (title, link, outlet), "newest": None}
            groups.append(g)
        g["n"] |= n; g["k"] |= k
        if outlet:
            g["outlets"].add(outlet.replace(" (subscribers)", ""))
        if bonus and why not in g["why"]:
            g["bonus"] += bonus; g["why"].append(why)
        if dt and (g["newest"] is None or dt > g["newest"]):
            g["newest"] = dt
    for i, (t, u) in enumerate(newswatch()):
        place(t, u, "", None, nn_bonus(i), f"National Newswatch #{i + 1}")
    for o, got in fronts.items():
        for i, (dt, _, t, u) in enumerate(got):
            place(t, u, o, dt, 3, f"{o} front #{i + 1}")
    for dt, o, t, u in sorted(rows, reverse=True):
        place(t, u, o, dt, 0, "")
    # second pass: groups sharing a distinctive name (one that turns up in only a few groups, e.g. Witkoff, Hubbard)
    # are one story told from different angles; merge them. Common names (Carney, Trump) never merge on their own.
    from collections import Counter
    freq = Counter(x for g in groups for x in g["n"])
    merged = []
    for g in groups:
        for m in merged:
            shared = {x for x in g["n"] & m["n"] if 2 <= freq[x] <= 4 and len(x) > 4 and x not in {"canada", "europe", "ottawa", "ontario", "alberta"}}
            if shared:
                m["n"] |= g["n"]; m["k"] |= g["k"]; m["outlets"] |= g["outlets"]; m["bonus"] += g["bonus"]; m["why"] += g["why"]
                if g["newest"] and (m["newest"] is None or g["newest"] > m["newest"]):
                    m["newest"] = g["newest"]
                break
        else:
            merged.append(g)
    groups[:] = merged
    # third pass: themes. Every group whose headline matches both sides of a theme folds into one story.
    for tname, _, ra, rb in THEMES:
        members = [g for g in groups if ra.search(g["lead"][0]) and rb.search(g["lead"][0])]
        if len(members) < 2:
            continue
        top = max(members, key=lambda g: (g["bonus"], len(g["outlets"])))
        for g in members:
            if g is top:
                continue
            top["n"] |= g["n"]; top["k"] |= g["k"]; top["outlets"] |= g["outlets"]; top["bonus"] += g["bonus"]; top["why"] += g["why"]
            if g["newest"] and (top["newest"] is None or g["newest"] > top["newest"]):
                top["newest"] = g["newest"]
            groups.remove(g)
        top["theme"] = tname
        top["parts"] = len(members)
    for g in groups:
        g["bonus"] = min(g["bonus"], 16)  # many Newswatch spots help, but one theme can't run away with the page
        g["score"] = g["bonus"] + min(len(g["outlets"]), 15) + (2 if g["newest"] and (now - g["newest"]).total_seconds() < 7200 else 0)
    return sorted(groups, key=lambda g: -g["score"])


def page_leads(page):
    s = open(page, encoding="utf-8").read()
    out = []
    m = re.search(r'id="breaking"[^>]*data-match="([^"]*)"|data-match="([^"]*)"[^>]*id="breaking"', s)
    st = re.search(r'id="breaking"[^>]*data-story="([^"]*)"', s)
    if st:
        out.append((st.group(1), [x.strip() for x in ((m.group(1) or m.group(2)) if m else "").split(",") if x.strip()]))
    now = datetime.now(timezone.utc)
    for line in re.findall(r"\{ id: '[^']*',[^\n]*", s):
        ev = re.search(r"story: '([^']*)'", line); words = re.search(r"match: \[([^\]]*)\]", line)
        ku = re.search(r"keepUntil: '([^']*)'", line); un = re.search(r"[^p]until: '([^']*)'", line)
        if not (ev and words):
            continue
        if ku:  # keepUntil decides when it is set, whatever the event's own window says
            if datetime.fromisoformat(ku.group(1)) < now:
                continue
        elif un and (now - datetime.fromisoformat(un.group(1))).total_seconds() > 12 * 3600:
            continue
        out.append((ev.group(1), re.findall(r"'([^']+)'", words.group(1))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="index.html")
    a = ap.parse_args()
    groups = rank()
    print("TOP STORIES RIGHT NOW (score: why)")
    for g in groups[:12]:
        t, u, o = g["lead"]
        th = f" [theme: {g['theme']}, {g['parts']} headlines]" if g.get("theme") else ""
        print(f"  {g['score']:>2}  {t[:100]}{th}\n       {len(g['outlets'])} outlets; {', '.join(g['why']) or 'coverage only'} | {u}")
    leads = page_leads(a.page)
    def score_of(words):
        rx = re.compile("|".join(re.escape(x) for x in words), re.I) if words else None
        best = 0
        for g in groups:
            if rx and rx.search(g["lead"][0] + " " + " ".join(g["n"])):
                best = max(best, g["score"])
        return best
    print("\nTHE PAGE LEADS WITH")
    sc = [(name, score_of(words)) for name, words in leads]
    for name, s_ in sc:
        print(f"  {s_:>2}  {name}")
    weakest = min(sc, key=lambda x: x[1]) if sc else None
    if len(sc) < 2:  # an empty Breaking/Developing slot: the best story not already up there fills it
        for g in groups[:3]:
            t = g["lead"][0]
            if not any(words and re.search("|".join(map(re.escape, words)), t + " " + " ".join(g["n"]), re.I) for _, words in leads):
                print(f"\nPROMOTE: '{g.get('theme') or t[:90]}' (score {g['score']}) goes in the empty slot as the top Developing story. Lead report: {g['lead'][1]}")
                return
    for g in groups[:3]:
        t = g["lead"][0]
        if weakest and g["score"] >= weakest[1] + 4 and not any(score_of(words) == g["score"] and re.search("|".join(map(re.escape, words)), t, re.I) for _, words in leads if words):
            print(f"\nSWAP: '{t[:90]}' (score {g['score']}) outranks '{weakest[0]}' (score {weakest[1]}). Move the weaker story to its desk and lead with this.")
            print(f"PROMOTE: '{g.get('theme') or t[:90]}' becomes the top Developing story this run (BREAKING_TEMPLATE.md). Lead report: {g['lead'][1]}")
            break


if __name__ == "__main__":
    main()
