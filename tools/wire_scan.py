#!/usr/bin/env python3
"""Newsroom wire scan: what every reachable newsroom has published most recently, newest first, in one list.

Hannah's rules: "always be checking for breaking news in all outlets" and "continue to use primary sources as much as
possible". Run this at the START of every update and live check, before searching. It reads, directly (curl through the
workspace proxy), the sources that this workspace can reach without a browser:

  front pages with machine-readable story lists:  CBC News (window.__INITIAL_STATE__), CTV News (Fusion.contentCache)
  RSS feeds that are fresh:                       Global News (top, Canada, world, politics), Al Jazeera,
                                                  The Globe and Mail (Canada, world, politics, business; subscribers),
                                                  The Tyee, CityNews, CP24, Toronto Star, National Post, Calgary Herald,
                                                  Edmonton Journal, APTN, Radio-Canada, BBC, The Guardian, CBS, ABC, PBS

Each item gets its real publish/update time in Eastern time, the outlet, the headline and the link. Items newer than
--fresh minutes (default 60) are flagged NEW. Use --grep to filter (e.g. --grep "Wainwright|referendum").

This is the fast first pass, not the whole job. Sources it cannot reach (AP and Reuters block automated reading on their side; CNN, NYT;
primary sources) are still covered by WebSearch + WebFetch on ARTICLE pages, as
tools/runbooks/SOURCES.md says (homepages fetched through WebFetch are often stale caches).

Usage:  python3 tools/wire_scan.py [--fresh 60] [--limit 60] [--grep REGEX] [--json out.json]
"""
import argparse
import email.utils
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

FEEDS = [
    ("Global News", "https://globalnews.ca/feed/"),
    ("Global News", "https://globalnews.ca/canada/feed/"),
    ("Global News", "https://globalnews.ca/world/feed/"),
    ("Global News", "https://globalnews.ca/politics/feed/"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Globe and Mail (subscribers)", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/canada/"),
    ("The Globe and Mail (subscribers)", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/world/"),
    ("The Globe and Mail (subscribers)", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/politics/"),
    ("The Globe and Mail (subscribers)", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/"),
    ("The Tyee", "https://thetyee.ca/rss2.xml"),
    # Reachable since Hannah allowed all domains (Tue Oct 20, 2026)
    ("CityNews", "https://toronto.citynews.ca/feed/"),
    ("CP24", "https://www.cp24.com/arc/outboundfeeds/rss/?outputType=xml"),  # pubDate is UTC wrongly marked -0400 (checked against article:published_time); fixed in UTC_MISLABELLED
    ("Toronto Star", "https://www.thestar.com/search/?f=rss&t=article&c=news*&l=50&s=start_time&sd=desc"),
    ("National Post", "https://nationalpost.com/feed"),
    ("Calgary Herald", "https://calgaryherald.com/feed"),
    ("Edmonton Journal", "https://edmontonjournal.com/feed"),
    ("APTN News", "https://www.aptnnews.ca/feed/"),
    ("Radio-Canada", "https://ici.radio-canada.ca/rss/4159"),
    ("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC News", "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("CBS News", "https://www.cbsnews.com/latest/rss/main"),
    ("ABC News", "https://abcnews.go.com/abcnews/topstories"),
    ("PBS NewsHour", "https://www.pbs.org/newshour/feeds/rss/headlines"),
    # Added Tue Oct 20, 2026 after Hannah: "you need to scan more sources" (missed: budget date, Hoekstra)
    ("CBC News (politics)", "https://www.cbc.ca/webfeed/rss/rss-politics"),
    ("Global News", "https://globalnews.ca/national/feed/"),
    ("Toronto Star (politics)", "https://www.thestar.com/search/?f=rss&t=article&c=politics*&l=50&s=start_time&sd=desc"),
    ("The Canadian Press (via Winnipeg Free Press)", "https://www.winnipegfreepress.com/rss/?path=%2Fcanada"),
    ("The Canadian Press (via Winnipeg Free Press)", "https://www.winnipegfreepress.com/rss/?path=%2Fbusiness"),
    ("Canada's National Observer", "https://www.nationalobserver.com/front/rss"),
    ("Financial Post", "https://financialpost.com/feed"),
    ("BNN Bloomberg", "https://www.bnnbloomberg.ca/arc/outboundfeeds/rss/?outputType=xml"),
    ("Radio-Canada (politique)", "https://ici.radio-canada.ca/rss/4175"),
    ("La Presse", "https://www.lapresse.ca/actualites/rss"),
    ("Le Devoir", "https://www.ledevoir.com/rss/manchettes.xml"),
    ("Le Journal de Montréal", "https://www.journaldemontreal.com/rss.xml"),
    ("Times Colonist", "https://www.timescolonist.com/rss"),
    ("Global News (Canada)", "https://globalnews.ca/category/canada/feed/"),  # added by source_discovery.py 2026-10-20
    ("CTV News", "https://www.ctvnews.ca/arc/outboundfeeds/rss/?outputType=xml"),  # added by source_discovery.py 2026-10-20
    ("Toronto Sun", "https://torontosun.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("Ottawa Citizen", "https://ottawacitizen.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("Vancouver Sun", "https://vancouversun.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("The Province", "https://theprovince.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("Halifax Examiner", "https://www.halifaxexaminer.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("SaltWire", "https://www.saltwire.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("Telegraph-Journal", "https://tj.news/feed/"),  # added by source_discovery.py 2026-10-20
    ("Nunatsiaq News", "https://nunatsiaq.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("Yukon News", "https://www.yukon-news.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("The Narwhal", "https://thenarwhal.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("The Logic", "https://thelogic.co/feed/"),  # added by source_discovery.py 2026-10-20
    ("TVA Nouvelles", "https://www.tvanouvelles.ca/rss"),  # added by source_discovery.py 2026-10-20
    ("Le Soleil", "https://www.lesoleil.com/arc/outboundfeeds/rss/?outputType=xml"),  # added by source_discovery.py 2026-10-20
    ("Daily Hive", "https://dailyhive.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("Narcity", "https://www.narcity.com/feeds/feed.rss"),  # added by source_discovery.py 2026-10-20
    ("CityNews Vancouver", "https://vancouver.citynews.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("CityNews Calgary", "https://calgary.citynews.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("CityNews Edmonton", "https://edmonton.citynews.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("CityNews Winnipeg", "https://winnipeg.citynews.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("CityNews Ottawa", "https://ottawa.citynews.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("CityNews Montreal", "https://montreal.citynews.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("CityNews Halifax", "https://halifax.citynews.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("CKOM / PAnow", "https://www.ckom.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("Lethbridge Herald", "https://lethbridgeherald.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("Medicine Hat News", "https://medicinehatnews.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("NBC News", "https://www.nbcnews.com/feed/"),  # added by source_discovery.py 2026-10-20
    ("The Hill", "https://thehill.com/feed/"),  # added by source_discovery.py 2026-10-20
    # Politico (Hannah, Fri Oct 30, 2026: "do we use politico as a source?"): its U.S. politics and Congress feeds.
    # Politico Europe and the Ottawa Playbook newsletter refuse automated reading (403), so they are not listed.
    ("Politico", "https://rss.politico.com/politics-news.xml"),
    ("Politico", "https://rss.politico.com/congress.xml"),
    # Politico's Canada coverage (Hannah, Fri Oct 30, 2026: "also add in Politico's canada playbook"). The Ottawa
    # Playbook newsletter page and its feed refuse automated reading (403); this is Politico's Canada news feed, the
    # stories its Ottawa bureau files (e.g. its Carney interview, Oct 30).
    ("Politico", "https://rss.politico.com/canada.xml"),
    # CBC's regional desks, so every clock at the top has its region's news (Hannah, Sat Oct 31, 2026: "my clocks aren't
    # working again"): Winnipeg and St. John's had little or nothing in the feeds
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-canada-newfoundland"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-canada-manitoba"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-canada-saskatchewan"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-canada-novascotia"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-canada-newbrunswick"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-canada-pei"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-canada-north"),
    ("VOCM", "https://vocm.com/feed/"),
    ("Fox News", "https://moxie.foxnews.com/google-publisher/latest.xml"),  # added by source_discovery.py 2026-10-20
    ("Euronews", "https://www.euronews.com/rss"),  # added by source_discovery.py 2026-10-20
    ("The Japan Times", "https://www.japantimes.co.jp/feed/"),  # added by source_discovery.py 2026-10-20
    ("Kyiv Independent", "https://kyivindependent.com/news-archive/rss/"),  # added by source_discovery.py 2026-10-20
    ("Middle East Eye", "https://www.middleeasteye.net/rss"),  # added by source_discovery.py 2026-10-20
    ("Prime Minister of Canada", "https://www.pm.gc.ca/rss.xml"),  # added by source_discovery.py 2026-10-20
    ("Bank of Canada", "https://www.bankofcanada.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("Cabin Radio", "https://cabinradio.ca/feed/"),  # added by source_discovery.py 2026-10-20
    ("IndigiNews", "https://indiginews.com/feed/"),  # added by source_discovery.py 2026-10-20
]
# Feeds whose pubDate carries a wrong offset: the clock time is really UTC
UTC_MISLABELLED = {"https://www.cp24.com/arc/outboundfeeds/rss/?outputType=xml", "https://www.bnnbloomberg.ca/arc/outboundfeeds/rss/?outputType=xml"}
FRONTS = [
    ("CBC News", "https://www.cbc.ca/news", "window.__INITIAL_STATE__", "https://www.cbc.ca"),
    ("CTV News", "https://www.ctvnews.ca", "Fusion.contentCache", "https://www.ctvnews.ca"),
    ("CTV News", "https://www.ctvnews.ca/politics/", "Fusion.contentCache", "https://www.ctvnews.ca"),
    ("CBC News", "https://www.cbc.ca/news/politics", "window.__INITIAL_STATE__", "https://www.cbc.ca"),
]


def curl(url):
    r = subprocess.run(["curl", "-sL", "-m", "25", "-A", UA, "--", url], capture_output=True)
    return r.stdout.decode("utf-8", "ignore") if r.returncode == 0 else ""


def to_utc(v):
    if v is None:
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        n = int(v)
        return datetime.fromtimestamp(n / 1000 if n > 10**11 else n, tz=timezone.utc)
    s = str(v).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def eastern(dt):
    # Eastern daylight time until the first Sunday of November, then standard time
    y = dt.year
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    first_sun_nov = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    second_sun_mar = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)
    dst = second_sun_mar + timedelta(hours=7) <= dt < first_sun_nov + timedelta(hours=6)
    local = dt + timedelta(hours=-4 if dst else -5)
    h = local.hour % 12 or 12
    return local.strftime("%a ") + f"{h}:{local.minute:02d} " + ("a.m." if local.hour < 12 else "p.m.")


def rss(outlet, url):
    out = []
    x = curl(url)
    for it in re.findall(r"<item\b.*?</item>", x, re.S):
        t = re.search(r"<title>(.*?)</title>", it, re.S)
        l = re.search(r"<link>(.*?)</link>", it, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
        if not (t and l):
            continue
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1))).strip()
        link = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", l.group(1))).strip()
        dt = to_utc(d.group(1).strip()) if d else None
        if dt and (url in UTC_MISLABELLED or '/arc/outboundfeeds/' in url):  # Arc feeds (CTV, CP24, BNN, Le Soleil) mark UTC as -0400
            dt = to_utc(re.sub(r"\s[+-]\d{4}$", " +0000", d.group(1).strip()))
        out.append((dt, outlet, title, link))
    return out


def walk(o, acc):
    if isinstance(o, dict):
        h = o.get("headlines")
        t = (h.get("basic") if isinstance(h, dict) else None) or o.get("title") or o.get("headline")
        u = o.get("canonical_url") or o.get("url") or o.get("website_url")
        tm = o.get("last_updated_date") or o.get("display_date") or o.get("updateTime") or o.get("publishTime") or o.get("first_publish_date")
        if isinstance(t, str) and isinstance(u, str) and tm and len(t) > 20:
            acc.append((tm, t, u))
        for v in o.values():
            walk(v, acc)
    elif isinstance(o, list):
        for v in o:
            walk(v, acc)


def front(outlet, url, marker, base):
    s = curl(url)
    i = s.find(marker)
    if i < 0:
        return []
    j = s.find("{", i)
    blob = re.sub(r":undefined([,}\]])", r":null\1", s[j:])
    try:
        obj = json.JSONDecoder().raw_decode(blob)[0]
    except ValueError:
        return []
    acc = []
    walk(obj, acc)
    out = []
    for tm, t, u in acc:
        if u.startswith("/"):
            u = base + u
        if not u.startswith("http"):
            continue
        out.append((to_utc(tm), outlet, html.unescape(t).strip(), u))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", type=int, default=60, help="flag items newer than this many minutes")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--grep", default="", help="regex filter on headline or link (case-insensitive)")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    items, failed = [], []
    for outlet, url in FEEDS:
        got = rss(outlet, url)
        (items.extend(got) if got else failed.append(url))
    for outlet, url, marker, base in FRONTS:
        got = front(outlet, url, marker, base)
        (items.extend(got) if got else failed.append(url))
    seen, rows = set(), []
    for dt, outlet, title, link in items:
        key = link.split("?")[0].rstrip("/")
        if key in seen or dt is None:
            continue
        seen.add(key)
        rows.append((dt, outlet, title, link))
    if a.grep:
        rx = re.compile(a.grep, re.I)
        rows = [r for r in rows if rx.search(r[2]) or rx.search(r[3])]
    rows.sort(key=lambda r: r[0], reverse=True)
    now = datetime.now(timezone.utc)
    future = [r for r in rows if (r[0] - now).total_seconds() > 600]
    rows = [r for r in rows if r not in future]
    for dt, outlet, title, link in rows[: a.limit]:
        mins = int((now - dt).total_seconds() // 60)
        flag = "NEW " if mins <= a.fresh else "    "
        print(f"{flag}{eastern(dt):>15} | {outlet} | {title} | {link}")
    if future:
        print("BAD TIMES (in the future; check the feed's offset, never use these times): " + ", ".join(sorted({r[1] for r in future})), file=sys.stderr)
    if failed:
        print("UNREACHABLE: " + " ".join(failed), file=sys.stderr)
    if a.json:
        json.dump([{"utc": r[0].isoformat(), "et": eastern(r[0]), "outlet": r[1], "title": r[2], "url": r[3]} for r in rows], open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
