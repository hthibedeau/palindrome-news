#!/usr/bin/env python3
"""Source discovery: keep finding newsrooms whose stories the page can read, and add them.

Hannah, Tue Oct 20, 2026: "always constantly be looking for news sources to be adding to the code so we can update
the news". Run it in EVERY full update (about a minute):

    python3 tools/source_discovery.py            # test candidates not yet in tools/wire_scan.py
    python3 tools/source_discovery.py --add      # also append the working ones to wire_scan.FEEDS

For each candidate newsroom it opens the home page, finds its RSS/Atom feeds (<link rel="alternate">), tries the
common feed paths, and keeps a feed only if it is FRESH (newest item under 24 hours, with real dates that are not in
the future). With --add, working feeds go into wire_scan.py's FEEDS so every run reads them from then on; the
outcome of every test is logged in tools/runbooks/SOURCES_LOG.md. Add new candidates to CANDIDATES whenever you meet a
newsroom (from search results, citations, bylines "with files from", or regional lists).
"""
import argparse
import datetime as dt
import html
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wire_scan as w  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
UA = w.UA

# name, home page. Canadian national, regional, local, Indigenous, francophone, wires, U.S. and international.
CANDIDATES = [
    ("CBC News (Canada)", "https://www.cbc.ca/news/canada"), ("CBC News (World)", "https://www.cbc.ca/news/world"),
    ("CBC News (Business)", "https://www.cbc.ca/news/business"), ("CBC News (Indigenous)", "https://www.cbc.ca/news/indigenous"),
    ("Global News (Canada)", "https://globalnews.ca/canada/"), ("CTV News", "https://www.ctvnews.ca"),
    ("The Canadian Press", "https://www.thecanadianpress.com"), ("Toronto Sun", "https://torontosun.com"),
    ("Ottawa Citizen", "https://ottawacitizen.com"), ("Montreal Gazette", "https://montrealgazette.com"),
    ("Calgary Herald", "https://calgaryherald.com"), ("Edmonton Journal", "https://edmontonjournal.com"),
    ("Vancouver Sun", "https://vancouversun.com"), ("The Province", "https://theprovince.com"),
    ("Regina Leader-Post", "https://leaderpost.com"), ("Saskatoon StarPhoenix", "https://thestarphoenix.com"),
    ("Windsor Star", "https://windsorstar.com"), ("London Free Press", "https://lfpress.com"),
    ("Hamilton Spectator", "https://www.thespec.com"), ("Waterloo Region Record", "https://www.therecord.com"),
    ("Winnipeg Free Press", "https://www.winnipegfreepress.com"), ("Halifax Examiner", "https://www.halifaxexaminer.ca"),
    ("SaltWire", "https://www.saltwire.com"), ("Telegraph-Journal", "https://tj.news"), ("CTV Atlantic", "https://www.ctvnews.ca/atlantic/"),
    ("Cabin Radio", "https://cabinradio.ca"), ("Nunatsiaq News", "https://nunatsiaq.com"), ("Yukon News", "https://www.yukon-news.com"),
    ("APTN News", "https://www.aptnnews.ca"), ("Windspeaker", "https://windspeaker.com"), ("IndigiNews", "https://indiginews.com"),
    ("The Narwhal", "https://thenarwhal.ca"), ("The Tyee", "https://thetyee.ca"), ("Canada's National Observer", "https://www.nationalobserver.com"),
    ("The Hill Times", "https://www.hilltimes.com"), ("iPolitics", "https://ipolitics.ca"), ("Policy Options", "https://policyoptions.irpp.org"),
    ("Maclean's", "https://macleans.ca"), ("The Walrus", "https://thewalrus.ca"), ("The Logic", "https://thelogic.co"),
    ("Financial Post", "https://financialpost.com"), ("BNN Bloomberg", "https://www.bnnbloomberg.ca"),
    ("Radio-Canada", "https://ici.radio-canada.ca/info"), ("La Presse", "https://www.lapresse.ca"), ("Le Devoir", "https://www.ledevoir.com"),
    ("Le Journal de Montréal", "https://www.journaldemontreal.com"), ("TVA Nouvelles", "https://www.tvanouvelles.ca"), ("Le Soleil", "https://www.lesoleil.com"),
    ("Times Colonist", "https://www.timescolonist.com"), ("Castanet", "https://www.castanet.net"), ("Daily Hive", "https://dailyhive.com"),
    ("Narcity", "https://www.narcity.com"), ("CityNews Vancouver", "https://vancouver.citynews.ca"), ("CityNews Calgary", "https://calgary.citynews.ca"),
    ("CityNews Edmonton", "https://edmonton.citynews.ca"), ("CityNews Winnipeg", "https://winnipeg.citynews.ca"), ("CityNews Ottawa", "https://ottawa.citynews.ca"),
    ("CityNews Montreal", "https://montreal.citynews.ca"), ("CityNews Halifax", "https://halifax.citynews.ca"), ("CKOM / PAnow", "https://www.ckom.com"),
    ("Lethbridge Herald", "https://lethbridgeherald.com"), ("Medicine Hat News", "https://medicinehatnews.com"), ("The Western Producer", "https://www.producer.com"),
    ("Associated Press", "https://apnews.com"), ("Reuters", "https://www.reuters.com"), ("AFP", "https://www.afp.com/en"),
    ("BBC News", "https://www.bbc.com/news"), ("The Guardian", "https://www.theguardian.com/world"), ("NPR", "https://www.npr.org"),
    ("NBC News", "https://www.nbcnews.com"), ("CBS News", "https://www.cbsnews.com"), ("ABC News", "https://abcnews.go.com"),
    ("PBS NewsHour", "https://www.pbs.org/newshour"), ("Politico", "https://www.politico.com"), ("Axios", "https://www.axios.com"),
    ("The Hill", "https://thehill.com"), ("Fox News", "https://www.foxnews.com"), ("CNN", "https://www.cnn.com"),
    ("Al Jazeera", "https://www.aljazeera.com"), ("France 24", "https://www.france24.com/en/"), ("DW", "https://www.dw.com/en"),
    ("Euronews", "https://www.euronews.com"), ("Sky News", "https://news.sky.com"), ("The Independent", "https://www.independent.co.uk"),
    ("ABC News (Australia)", "https://www.abc.net.au/news"), ("CNA", "https://www.channelnewsasia.com"), ("The Japan Times", "https://www.japantimes.co.jp"),
    ("Kyiv Independent", "https://kyivindependent.com"), ("Times of Israel", "https://www.timesofisrael.com"), ("Middle East Eye", "https://www.middleeasteye.net"),
    ("Government of Canada news", "https://www.canada.ca/en/news.html"), ("Prime Minister of Canada", "https://www.pm.gc.ca/en/news"),
    ("Statistics Canada The Daily", "https://www150.statcan.gc.ca/n1/dai-quo/index-eng.htm"), ("Bank of Canada", "https://www.bankofcanada.ca"),
    ("RCMP news", "https://rcmp.ca/en/news"), ("Elections Canada", "https://www.elections.ca"), ("White House", "https://www.whitehouse.gov"),
]
PATHS = ["/feed/", "/feed", "/rss", "/rss.xml", "/rss/", "/feeds/all.rss", "/arc/outboundfeeds/rss/?outputType=xml", "/index.rss", "/atom.xml"]


def curl(u):
    r = subprocess.run(["curl", "-sL", "-m", "15", "-A", UA, "--", u], capture_output=True)
    return r.stdout.decode("utf-8", "ignore") if r.returncode == 0 else ""


def feed_age(u):
    x = curl(u)
    if "<item" not in x and "<entry" not in x:
        return None, 0
    dates = re.findall(r"<(?:pubDate|updated|published|dc:date)>([^<]+)<", x)
    now = dt.datetime.now(dt.timezone.utc)
    ds = [d for d in (w.to_utc(v.strip()) for v in dates) if d and (d - now).total_seconds() < 600]
    n = len(re.findall(r"<item\b|<entry\b", x))
    return ((now - max(ds)).total_seconds() / 3600 if ds else None), n


def discover(home):
    page = curl(home)
    found = [html.unescape(m) for m in re.findall(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]+href="([^"]+)"', page)]
    found += [html.unescape(m) for m in re.findall(r'<link[^>]+href="([^"]+)"[^>]+type="application/(?:rss|atom)\+xml"', page)]
    base = re.match(r"(https?://[^/]+)", home).group(1)
    found = [f if f.startswith("http") else base + ("" if f.startswith("/") else "/") + f for f in found]
    return found + [base + p for p in PATHS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--max", type=int, default=200)
    a = ap.parse_args()
    have = {u for _, u in w.FEEDS}
    have_hosts = {re.sub(r"^www\.", "", u.split("/")[2]) for u in have}
    added, log = [], []
    for name, home in CANDIDATES[: a.max]:
        host = re.sub(r"^www\.", "", home.split("/")[2])
        if host in have_hosts and home.rstrip("/").count("/") <= 2:
            continue
        best = None
        for f in dict.fromkeys(discover(home)):
            if f in have:
                best = ("have", f, 0, 0)
                break
            age, n = feed_age(f)
            if age is not None and age < 24 and n >= 5:
                best = ("ok", f, age, n)
                break
        if not best:
            log.append(f"- {name}: no fresh feed found ({home}); read it through search and article pages")
            print(f"  --  {name}: no fresh feed")
        elif best[0] == "have":
            continue
        else:
            _, f, age, n = best
            print(f"  OK  {name}: {f} ({n} items, newest {age:.1f} h ago)")
            log.append(f"- {name}: {f} works ({n} items, newest {age:.1f} h)" + (" — added to wire_scan.FEEDS" if a.add else ""))
            added.append((name, f))
    if a.add and added:
        p = os.path.join(HERE, "wire_scan.py")
        s = open(p, encoding="utf-8").read()
        k = s.index("\n]\nUTC_MISLABELLED") if "\n]\nUTC_MISLABELLED" in s else s.index("\n]\n", s.index("FEEDS = ["))
        s = s[:k] + "".join(f'\n    ("{n}", "{f}"),  # added by source_discovery.py {dt.date.today()}' for n, f in added) + s[k:]
        open(p, "w", encoding="utf-8").write(s)
        print(f"Added {len(added)} feeds to wire_scan.FEEDS")
    lp = os.path.join(HERE, "runbooks", "SOURCES_LOG.md")
    with open(lp, "a", encoding="utf-8") as fh:
        if os.path.getsize(lp) == 0 if os.path.exists(lp) else True:
            fh.write("# Source discovery log\n\nEach run of tools/source_discovery.py appends what it tested.\n")
        fh.write(f"\n## {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC\n" + "\n".join(log) + "\n")


if __name__ == "__main__":
    main()
