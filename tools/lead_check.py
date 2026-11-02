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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
    # Hannah, Mon Nov 2, 2026: "there is new budget news that is not showing at the top". Budget week brings many
    # headlines from different angles (Poilievre's asks, child care, the North, what to expect); they are ONE story, so
    # they rank together and can reach the top. It comes before Canada and the U.S. so "budget ... amid U.S. trade war"
    # is counted as budget news. One event: never split (autopilot.SPLIT_THEMES).
    ("Federal budget", "Federal budget",
     re.compile(r"\b(federal|Ottawa|Champagne|Carney|Poilievre|Liberals?|Canad\w*|Budget 2026)\b", re.I),
     re.compile(r"\b(budget)\b(?!\s+(?:airline|travel|hotel|friendly))", re.I)),
    # Hannah, Mon Nov 2, 2026: the Carney-Trump call never reached the top while a train crash in Spain ("4 Americans
    # and 1 Canadian") and a Zelensky-Turkey story were being counted as Canada-U.S. news. The U.S. side must now be the
    # U.S. government or the trade fight itself, never just the word "American(s)", and the finished Turkey trip is out.
    ("Canada and the U.S.", "Canada and the U.S.",
     re.compile(r"\b(Canad\w*|Carney|Ottawa|Joly|LeBlanc|Champagne|Anand|Ford|Poilievre|premiers?)\b", re.I),
     re.compile(r"\b(Trump|U\.S\.|US|Washington|White House|Hoekstra|Lutnick|Greer|midterms?|tariffs?|CUSMA|USMCA|trade war|trade deal|trade talks|Keystone|51st state|Rubio|Vance)\b")),
    # Hannah, Wed Oct 28, 2026: the Canada-EU summit had "a lot of different reporting" but never reached the top,
    # because each angle (the associate-membership title, Quebec's empty chair, the summit itself) was its own group.
    # One event, so it stays ONE story (it is not split back up like the Canada-U.S. theme; see autopilot.SPLIT_THEMES).
    ("Canada and the EU", "Canada and the EU",
     re.compile(r"\b(Canad\w*|Carney|Ottawa|Anand|LeBlanc|Champagne|Quebec|Québec|premiers?|Plamondon|PQ)\b", re.I),
     re.compile(r"\b(EU|European Union|European Commission|European Council|von der Leyen|António Costa|Antonio Costa|Brussels|Canada-EU|Canada–EU)\b")),
]


# Hannah, Mon Nov 2, 2026 (and Sun Nov 1: a shared party name is never a Canadian angle): a party or a nationality is not
# a story. "Canadians favour Democrats" (a Canadian poll) and "Democrats condemn Haley Stevens" (Michigan) were fused into
# one 40-headline story that then led the page. These words never join two headlines on their own.
GENERIC_NAMES = {"democrats", "democrat", "democratic", "republicans", "republican", "gop", "liberals", "liberal",
                 "conservatives", "conservative", "ndp", "canadians", "canadian", "americans", "american", "u.s", "us",
                 "senate", "house", "congress", "federal", "mps", "tories"}


def _names(t):
    return gc.names(t) - GENERIC_NAMES


def window_start(now):
    """How far back the ranking reads. Normally the last 6 hours. Overnight little is published, so from midnight to
    11 a.m. Eastern the window reaches back to noon the day before (Hannah, Mon Nov 2, 2026: the Carney-Trump call,
    reported Sunday afternoon and evening, had dropped out of the ranking by morning while the page kept a stale lead).
    A story from last night still has to beat the morning's news: fresh reports score higher in pick_by_canada()."""
    et = now.astimezone(ZoneInfo("America/Toronto"))
    if et.hour < 11:
        start = (et - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        return start.astimezone(timezone.utc)
    return now - timedelta(hours=6)


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
    since = window_start(now)
    rows = [x for x in items if x[0] and since <= x[0] <= now + timedelta(minutes=10) and not re.search(gc.SKIP, x[2], re.I)
            and not OPINION.search(x[3] + " " + x[2]) and not SOFT.search(x[2] + " " + x[3])
            and not re.search(r"jackpot|Lotto|died of natural causes", x[2], re.I)]
    groups = []

    def place(title, link, outlet, dt, bonus, why):
        n, k = _names(title), gc.keys(title)
        for g in groups:
            if len(n & g["n"]) >= 2 or (len(n & g["n"]) >= 1 and len(k & g["k"]) >= 2) or len(k & g["k"]) >= 4:
                break
        else:
            g = {"n": set(), "k": set(), "outlets": set(), "bonus": 0, "why": [], "lead": (title, link, outlet), "newest": None, "rows": []}
            groups.append(g)
        g["n"] |= n; g["k"] |= k
        if outlet and dt:
            g["rows"].append((dt, outlet, title, link))
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
                m["n"] |= g["n"]; m["k"] |= g["k"]; m["outlets"] |= g["outlets"]; m["bonus"] += g["bonus"]; m["why"] += g["why"]; m["rows"] += g["rows"]
                if g["newest"] and (m["newest"] is None or g["newest"] > m["newest"]):
                    m["newest"] = g["newest"]
                break
        else:
            merged.append(g)
    groups[:] = merged
    # third pass: themes. Every HEADLINE that matches both sides of a theme goes to that theme's story, wherever the
    # first two passes put it (Hannah, Mon Nov 2, 2026: the budget reports and the Carney-Trump call were sitting
    # inside other stories, so they never counted). Groups whose own lead matches the theme fold in whole, with their
    # National Newswatch and CBC placement. Headlines that don't match stay where they were.
    def fits(t, ra, rb):
        return bool(ra.search(t) and rb.search(t))
    for tname, _, ra, rb in THEMES:
        free = [g for g in groups if not g.get("theme")]  # a headline already in one theme's story stays there
        whole = [g for g in free if fits(g["lead"][0], ra, rb)]
        rows = [r for g in free for r in g["rows"] if fits(r[2], ra, rb)]
        if len({r[1] for r in rows}) < 2 and len(whole) < 2:
            continue
        top = {"n": set(), "k": set(), "outlets": set(), "bonus": 0, "why": [], "lead": None, "newest": None, "rows": rows}
        for g in free:
            g["rows"] = [r for r in g["rows"] if not fits(r[2], ra, rb)]  # the rest of its headlines stay where they were
            if g in whole:  # its National Newswatch / CBC placement was earned by a headline on this theme
                top["bonus"] += g["bonus"]; top["why"] += g["why"]; g["bonus"] = 0; g["why"] = []
            g["outlets"] = {r[1].replace(" (subscribers)", "") for r in g["rows"]}
            g["newest"] = max((r[0] for r in g["rows"]), default=None)
        lead_from = max(whole, key=lambda g: len(g["rows"])) if whole else None
        r0 = max(rows) if rows else None
        top["lead"] = lead_from["lead"] if lead_from else (r0[2], r0[3], r0[1])
        for r in rows:
            top["n"] |= _names(r[2]); top["k"] |= gc.keys(r[2])
        top["outlets"] = {r[1].replace(" (subscribers)", "") for r in rows}
        top["newest"] = r0[0] if r0 else None
        top["theme"] = tname
        top["parts"] = len(rows)
        groups.append(top)
    groups[:] = [g for g in groups if g["rows"] or g["bonus"]]
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
    def score_of(words, name=None):
        rx = re.compile("|".join(re.escape(x) for x in words), re.I) if words else None
        best = 0
        for g in groups:
            if (name and g.get("theme") == name) or (rx and rx.search(g["lead"][0] + " " + " ".join(g["n"]))):  # a slot named after a theme scores as that theme
                best = max(best, g["score"])
        return best
    print("\nTHE PAGE LEADS WITH")
    sc = [(name, score_of(words, name)) for name, words in leads]
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
        if weakest and g["score"] >= weakest[1] + 4 and not any(g.get("theme") == name or (words and score_of(words) == g["score"] and re.search("|".join(map(re.escape, words)), t + " " + " ".join(g["n"]), re.I)) for name, words in leads):  # the theme's other headlines count too, so a story already in a slot is not "swapped" for itself
            print(f"\nSWAP: '{t[:90]}' (score {g['score']}) outranks '{weakest[0]}' (score {weakest[1]}). Move the weaker story to its desk and lead with this.")
            print(f"PROMOTE: '{g.get('theme') or t[:90]}' becomes the top Developing story this run (BREAKING_TEMPLATE.md). Lead report: {g['lead'][1]}")
            break


if __name__ == "__main__":
    main()
