#!/usr/bin/env python3
"""Gap check: which stories are newsrooms running right now that the page does NOT have?

Written Tue Oct 20, 2026, after Hannah found the page had missed the federal budget date (Nov. 5) and U.S.
Ambassador Pete Hoekstra's "we're not in a trade war" remarks: "you need to scan more sources", "why are you not
updating". Run it in EVERY full update and live check, after the wire scan:

    python3 tools/gap_check.py --page index.html [--hours 4] [--min 1]

It reads every feed and front page in tools/wire_scan.py, groups headlines about the same story (shared names and
distinctive words), and checks each group against the page: its links, and its names and key words in the page text.
It prints the groups the page is MISSING, the most widely covered first, with every outlet and link, then the groups
that are on the page only weakly (named but not linked). A story carried by 2 or more newsrooms, or by a national
politics desk, that is missing is a gap: put it on the page this run (wire at least; a desk, What to watch, or
Breaking if it is big), with the newest, fullest free report as the link and the Globe as "sub" only.
Sports results, horoscopes, recipes and the like are skipped.
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wire_scan as w  # noqa: E402

SKIP = r"\b(NHL|NFL|MLB|NBA|CFL|MLS|Leafs|Oilers|Flames|Canucks|Jets|Senators|Canadiens|Raptors|Blue Jays|Argonauts|Steelers|horoscope|recipe|Wordle|crossword|podcast|deals?|shopping|best .* to buy)\b"
STOP = set("""the a an and or of in on at to for from with after before over under into as by is are was were be been
says say said will would could can may new news live update updates video watch what why how who when where this that
these those its their his her they them it not no more than about after amid over up down out off one two three four
five six seven eight nine ten first last year years day days week today tonight tuesday monday wednesday thursday
friday saturday sunday october november canada canadian canadians u.s. us ontario alberta quebec government""".split())


def toks(t):
    return [x for x in re.findall(r"[A-Za-zÀ-ÿ'’.-]+", t)]


ALIAS = [(re.compile(r"\bEuropean (?:Union|Commission|Council)\b|\bEuropean Union's\b"), "eu"),
         (re.compile(r"\bParti Qu[ée]b[ée]cois\b"), "pq")]
ACRONYM = re.compile(r"^[A-Z][A-Z0-9]{1,5}$")


def names(t):
    """Capitalized words that are not the first word (people, places, organizations), lowercased. Also: abbreviations
    anywhere (EU, PQ, NATO), the parts of joined names ("Canada-EU" -> canada-eu, eu) and the short form of a long
    name (European Union -> eu), so headlines about one story in different words still group (Hannah, Wed Oct 28, 2026:
    the Canada-EU summit was split into pieces because "EU" was never read as a name)."""
    ws = toks(t)
    out = {x.strip(".’'").lower() for i, x in enumerate(ws) if i > 0 and x[:1].isupper() and len(x) > 2 and x.lower().strip(".") not in STOP}
    for x in ws:
        x = x.strip(".’'")
        parts = [x] + (x.split("-") if "-" in x else [])
        for p_ in parts:
            if ACRONYM.match(p_) and p_.lower() not in STOP:
                out.add(p_.lower())
            elif p_ is not x and p_[:1].isupper() and len(p_) > 2 and p_.lower() not in STOP:
                out.add(p_.lower())
    for rx, short in ALIAS:
        if rx.search(t):
            out.add(short)
    return out


def keys(t):
    return {x.strip(".’'").lower() for x in toks(t) if len(x) > 4 and x.lower().strip(".’'") not in STOP}


def page_text(path):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"(?s)<style.*?</style>", " ", s)
    links = set(u.split("?")[0].rstrip("/") for u in re.findall(r"https?://[^\s\"'<>]+", s))
    text = re.sub(r"<[^>]+>", " ", s)
    return links, text.lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--hours", type=float, default=4)
    ap.add_argument("--min", type=int, default=1, help="minimum number of outlets for a group to be listed")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    items = []
    for outlet, url in w.FEEDS:
        items += w.rss(outlet, url)
    for outlet, url, marker, base in w.FRONTS:
        items += w.front(outlet, url, marker, base)
    seen, rows = set(), []
    for dt, outlet, title, link in items:
        k = link.split("?")[0].rstrip("/")
        if not dt or k in seen or (now - dt).total_seconds() > a.hours * 3600 or (dt - now).total_seconds() > 600:
            continue
        if re.search(SKIP, title, re.I) or re.search(r"/(sports?|entertainment|lifestyle|shopping|horoscope)/", link):
            continue
        seen.add(k)
        rows.append({"dt": dt, "outlet": outlet.replace(" (subscribers)", ""), "title": title, "url": link, "n": names(title), "k": keys(title)})
    # group: same story if they share 2+ names, or 1 name and 2+ key words, or 4+ key words
    groups = []
    for r in sorted(rows, key=lambda r: r["dt"], reverse=True):
        for g in groups:
            if len(r["n"] & g["n"]) >= 2 or (len(r["n"] & g["n"]) >= 1 and len(r["k"] & g["k"]) >= 2) or len(r["k"] & g["k"]) >= 4:
                g["rows"].append(r)
                g["n"] |= r["n"]
                g["k"] |= r["k"]
                break
        else:
            groups.append({"rows": [r], "n": set(r["n"]), "k": set(r["k"])})
    links, text = page_text(a.page)
    missing, weak = [], []
    for g in groups:
        outlets = sorted({r["outlet"] for r in g["rows"]})
        if len(outlets) < a.min:
            continue
        linked = any(r["url"].split("?")[0].rstrip("/") in links for r in g["rows"])
        if linked:
            continue
        lead = g["rows"][0]
        top_names = [x for x in lead["n"] if len(x) > 3][:4]
        named = sum(1 for x in top_names if x in text)
        keyhits = sum(1 for x in list(lead["k"])[:6] if x in text)
        if top_names and named >= max(1, len(top_names) - 1) and keyhits >= 2:
            weak.append((len(outlets), g, outlets))
        elif not top_names and keyhits >= 3:
            weak.append((len(outlets), g, outlets))
        else:
            missing.append((len(outlets), g, outlets))
    missing.sort(key=lambda x: (-x[0], -max(r["dt"] for r in x[1]["rows"]).timestamp()))
    print(f"MISSING from the page ({len(missing)} stories in the last {a.hours:g} h, most widely covered first):")
    for n, g, outlets in missing[:40]:
        lead = g["rows"][0]
        print(f"\n  [{n} outlet{'s' if n > 1 else ''}] {w.eastern(lead['dt'])} | {lead['title']}")
        for r in g["rows"][:6]:
            print(f"      {w.eastern(r['dt']):>15} | {r['outlet']} | {r['url']}")
    print(f"\nNAMED BUT NOT LINKED ({len(weak)}): check these are current and link the newest report")
    for n, g, outlets in sorted(weak, key=lambda x: -x[0])[:15]:
        lead = g["rows"][0]
        print(f"  [{n}] {w.eastern(lead['dt'])} | {lead['title'][:110]} | {lead['url']}")


if __name__ == "__main__":
    main()
