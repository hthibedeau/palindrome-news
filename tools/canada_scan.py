#!/usr/bin/env python3
"""Canada desk scan: the newest stories from every province and territory, for the Canada section.

Hannah: "beef up the Canada section" (Tue Oct 20, 2026). The Canada desk is a full-width band with 8–12 stories
from at least 5 provinces or territories. Run this in every full update (it takes about a minute):

    python3 tools/canada_scan.py [--hours 18] [--per 6]

It reads, directly:
  - CBC News's front page for each region (each one's own story list, with real update times);
  - Global News's regional feeds;
  - regional and local newsrooms with feeds: Vancouver Sun, Ottawa Citizen, Winnipeg Free Press, Halifax Examiner,
    Yukon News, Nunatsiaq News, The Narwhal, The Tyee, APTN News, CityNews, CP24, Radio-Canada.
It prints the newest stories grouped by region, flagging how many outlets carry similar headlines, so you can pick the
biggest story from each region and find every outlet reporting it (then open each article for its real time and facts).

Then edit `const stories = [` in index.html: each Canada story is
  [pic, "Canada", badge, headline, summary, "Outlet, Outlet, …", link (newest, fullest free report), photo, "Day h:mm a.m.", "Region"]
Region is the province or territory as readers know it ("Quebec", "B.C.", "N.W.T."). Lead with the biggest story.
Leave out stories now in the Breaking segment (the page hides them anyway) and sports scores.
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wire_scan as w  # noqa: E402

CBC = {
    "B.C.": ["british-columbia"], "Alberta": ["calgary", "edmonton"], "Saskatchewan": ["saskatchewan", "saskatoon"],
    "Manitoba": ["manitoba"], "Ontario": ["toronto", "ottawa", "hamilton", "kitchener-waterloo", "london", "windsor", "sudbury", "thunder-bay"],
    "Quebec": ["montreal"], "New Brunswick": ["new-brunswick"], "Nova Scotia": ["nova-scotia"], "P.E.I.": ["pei"],
    "N.L.": ["newfoundland-labrador"], "North": ["north"],
}
GLOBAL = {
    "B.C.": ["bc", "okanagan"], "Alberta": ["calgary", "edmonton", "lethbridge"], "Saskatchewan": ["saskatoon", "regina"],
    "Manitoba": ["winnipeg"], "Ontario": ["toronto", "ottawa", "kingston", "hamilton", "london", "guelph", "peterborough"],
    "Quebec": ["montreal"], "New Brunswick": ["new-brunswick"], "Nova Scotia": ["halifax"],
}
FEEDS = [
    ("B.C.", "Vancouver Sun", "https://vancouversun.com/feed"), ("B.C.", "The Tyee", "https://thetyee.ca/rss2.xml"),
    ("Ontario", "Ottawa Citizen", "https://ottawacitizen.com/feed"), ("Ontario", "CityNews", "https://toronto.citynews.ca/feed/"),
    ("Ontario", "CP24", "https://www.cp24.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("Manitoba", "Winnipeg Free Press", "https://www.winnipegfreepress.com/rss/?path=%2Flocal"),
    ("Nova Scotia", "Halifax Examiner", "https://www.halifaxexaminer.ca/feed/"),
    ("North", "Yukon News", "https://www.yukon-news.com/feed/"), ("North", "Nunatsiaq News", "https://nunatsiaq.com/feed/"),
    ("Canada", "The Narwhal", "https://thenarwhal.ca/feed/"), ("Canada", "APTN News", "https://www.aptnnews.ca/feed/"),
    ("Quebec", "Radio-Canada", "https://ici.radio-canada.ca/rss/4159"),
]
SKIP = r"\b(NHL|NFL|MLB|NBA|CFL|Leafs|Oilers|Flames|Canucks|Jets|Senators|Canadiens|Raptors|Blue Jays|Argonauts|Redblacks|Roughriders|Stampeders|Elks|Lions|score|horoscope|recipe|contest|podcast)\b"
NOTLOCAL = r"/(world|business|money|entertainment|sports|lifestyle|health|science|tech|uncategorized)/|cp-newsalert"  # wire copy in local feeds
STOP = set("the a an and of in on at to for from with after before over says say said is are was were be as by new".split())


def words(t):
    return {x for x in re.findall(r"[a-z0-9']+", t.lower()) if len(x) > 3 and x not in STOP}


def collect(hours=18, now=None):
    """Every regional story in the last `hours`: (dt, region, outlet, title, url, other outlets with the same story)."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for region, paths in CBC.items():
        for pth in paths:
            for dt, o, t, u in w.front("CBC News", "https://www.cbc.ca/news/canada/" + pth, "window.__INITIAL_STATE__", "https://www.cbc.ca"):
                if "/news/canada/" in u:
                    rows.append((dt, region, "CBC News", t, u))
    for region, paths in GLOBAL.items():
        for pth in paths:
            for dt, o, t, u in w.rss("Global News", "https://globalnews.ca/" + pth + "/feed/"):
                rows.append((dt, region, "Global News", t, u))
    for region, outlet, url in FEEDS:
        for dt, o, t, u in w.rss(outlet, url):
            rows.append((dt, region, outlet, t, u))
    seen, keep = set(), []
    for dt, region, outlet, t, u in rows:
        k = u.split("?")[0].rstrip("/")
        if not dt or k in seen or (now - dt).total_seconds() > hours * 3600 or re.search(SKIP, t) or re.search(NOTLOCAL, u):
            continue
        seen.add(k)
        keep.append((dt, region, outlet, t, u))
    # how many outlets carry a similar headline (shared distinctive words)
    base = list(keep)
    for i, (dt, region, outlet, t, u) in enumerate(base):
        wi = words(t)
        others = {o for d, r, o, tt, uu in base if o != outlet and len(wi & words(tt)) >= 3}
        keep[i] = (dt, region, outlet, t, u, others)
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=18)
    ap.add_argument("--per", type=int, default=6, help="stories to show per region")
    a = ap.parse_args()
    keep = collect(a.hours)
    by = {}
    for x in sorted(keep, key=lambda x: x[0], reverse=True):
        by.setdefault(x[1], []).append(x)
    for region in list(CBC) + ["Canada"]:
        items = by.get(region, [])
        if not items:
            continue
        print(f"\n=== {region} ({len(items)} in the last {a.hours} h) ===")
        for dt, _, outlet, t, u, others in items[: a.per]:
            more = f"  [+{len(others)}: {', '.join(sorted(others))}]" if others else ""
            print(f"  {w.eastern(dt):>15} | {outlet} | {t[:110]}{more}")
            print(f"                  {u}")


if __name__ == "__main__":
    main()
