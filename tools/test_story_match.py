"""Checks for two rules Hannah set on U.S. Election Night, Tue Nov 3, 2026. Run: python3 tools/test_story_match.py
Every headline here is a real one published that night.

1. ONE STORY, ITS OWN SUBJECT: a country's name never pulls a story into another (The Hub's opinion piece on Jewish
   Canadians leaving for the U.S. was shown under the midterms story).
2. PROJECTIONS: every network's race call is found, credited to the network that made it, and never confused with a
   forecast, a poll or a hope.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopilot as ap  # noqa: E402

fails = 0


def check(ok, what):
    global fails
    print(("ok    " if ok else "FAIL  ") + what)
    fails += 0 if ok else 1


# 1. one story, its own subject
ev = next(e for e in ap.BIG_EVENTS if e[0] == "U.S. midterm elections")
key = "event-u-s-midterm-elections-2026-11-03"
ap.STORY_MATCH[key] = (re.compile(ev[3], re.I), re.compile(ev[4], re.I))
words = ap.subject_words(["U.S.", "midterm", "elections", "midterms"])
check("U.S." not in words and "elections" not in words, f"the election's match words carry no country or everyday word: {words}")
about = ap.on_subject(key, words)
check(not about("‘There are no consequences’: Why Jewish Canadians are leaving for the U.S."), "an opinion piece that only names the U.S. is not about the election")
check(not about("Canadian Senate defeats bill on infrastructure projects"), "the Canadian Senate and 'projects' are not the U.S. election")
check(about("Democrats will win control of the House, CNN projects"), "a race call is about the election")
check(about("GOP Sen. Ashley Moody wins special Senate election for Marco Rubio’s old seat in Florida"), "a Senate result is about the election")
check(ap.subject_words(["Canada", "EU", "summit"]) == ["summit"], "Canada and EU are never match words on their own")

# 2. projections
cases = [
    ("Democrats will win control of the House, CNN projects", "CNN", True, "Control of the House"),
    ("Florida voters will send Republican Sen. Ashley Moody back to Washington, CNN’s Decision Desk projects", "CNN", True, "Florida · Senate"),
    ("Fox News projects Georgia Dem Keisha Lance Bottoms will be first Black woman governor in US history", "Fox News", True, "Georgia · Governor"),
    ("Democratic Gov. Josh Shapiro will win reelection in Pennsylvania, ABC News projects", "ABC News", True, "Pennsylvania · Governor"),
    ("Democrat Andrews projected to win South Carolina Senate seat", "The Hill", False, "South Carolina · Senate"),
]
for head, net, named, race in cases:
    p = ap.parse_projection(head, "The Hill")
    check(bool(p) and p["net"] == net and p["named"] == named and ap.proj_race(head) == race, f"{head[:60]}… -> {net}, {race}")
for head in ["Hakeem Jeffries says Democrats are on ‘brink’ of winning House majority", "Fox News predicts a Democratic House majority",
             "Rep. Katherine Clark says Democrats are on track to win control of the House tonight", "City projects $2 billion transit plan",
             "Democrats flip GOP seats as party pushes for House control"]:
    check(ap.parse_projection(head, "NBC News") is None, f"not a call: {head[:60]}")

# 3. THE MORNING AFTER (Hannah, Wed Nov 4, 2026): the results headline leads, not overnight race calls or market side stories
from datetime import datetime as _dt
from zoneinfo import ZoneInfo as _Z
_et = _Z("America/Toronto"); _since = _dt(2026, 11, 4, 5, tzinfo=_et)
ap.FRONTS = [{"o": "CBC News", "ca": True, "h": ["U.S. midterms: Democrat leaders to detail next steps after taking Congress in blue wave"]},
             {"o": "CTV News", "ca": True, "h": ["Blue wave crashes over American politics in midterm that rebukes Trump policies"]}]
_rows = [(_dt(2026, 11, 4, 10, 18, tzinfo=_et), "CBS News", "Stocks soar after Democrats take control of Congress", "https://www.cbsnews.com/a"),
         (_dt(2026, 11, 4, 10, 10, tzinfo=_et), "NBC News", "El-Sayed wins Michigan Senate seat, NBC News projects", "https://www.nbcnews.com/b"),
         (_dt(2026, 11, 4, 9, 47, tzinfo=_et), "CTV News", "Blue wave crashes over American politics in midterm that rebukes Trump policies", "https://www.ctvnews.ca/c"),
         (_dt(2026, 11, 3, 19, 0, tzinfo=_et), "CBC News", "Polls close in key states: what to watch tonight", "https://www.cbc.ca/d")]
_ev = ap.BIG_EVENTS[0]
_pick = ap.morning_headline(_rows, re.compile(_ev[3], re.I), re.compile(_ev[4], re.I), _since)
check(bool(_pick) and _pick[1] == "CTV News", "the morning after, the results headline leads (not stocks, one race or last night)")
check(not ap.big_news_day([{"event_day": _ev[0], "aftermath": True, "fronts": 3, "fronts_ca": 1}]), "the morning after, the event no longer stands alone")
check(ap.big_news_day([{"event_day": _ev[0], "aftermath": True, "fronts": 12, "fronts_ca": 6}]),
      "the day after, while the front pages here and abroad still lead with it, it stands alone (Nov 4, 2026)")
_rows2 = [(_dt(2026, 11, 4, 15, 21, tzinfo=_et), "Global News", "Canada’s focus ‘hasn’t changed’ despite U.S. midterm blue wave, minister says", "https://globalnews.ca/e"),
          (_dt(2026, 11, 4, 15, 40, tzinfo=_et), "Narcity", "Alberta Premier Smith says U.S. midterm results 'vindicate' her approach to tariffs", "https://www.narcity.com/f"),
          (_dt(2026, 11, 4, 13, 0, tzinfo=_et), "CBS News", "Midterm fallout begins after Democrats win control of Congress", "https://www.cbsnews.com/g")]
_pick2 = ap.morning_headline(_rows2, re.compile(_ev[3], re.I), re.compile(_ev[4], re.I), _since)
check(bool(_pick2) and _pick2[1] == "CBS News", "the day after, the result leads, never a reaction ('minister says', 'vindicate')")
check(ap.file_photo("Carney and Trump at the G7 summit in Evian-les-Bains, France, on Tuesday, June 16, 2026.", _dt(2026, 11, 4, tzinfo=_et)),
      "a photo dated months ago is a file photo")
check(ap.proj_race("Bonck wins House election for Hunt’s Texas seat") == "Texas · House", "one state's House seat is not control of the House")
check(ap.big_news_day([{"event_day": _ev[0]}]), "on the night, the event stands alone")
_st = {"aftermath": True, "after_since": _since.isoformat(), "title": "kept"}
_calls = [{"race": "Michigan · Senate", "call": "El-Sayed wins Michigan Senate seat, NBC News projects", "net": "NBC News", "named": True, "via": "",
           "url": "https://www.nbcnews.com/b", "seen": _dt(2026, 11, 4, 10, 10, tzinfo=_et).isoformat(), "t": "Wed 10:10 a.m.", "w": 2},
          {"race": "Control of the House", "call": "Democrats will win control of the House, CNN projects", "net": "CNN", "named": True, "via": "",
           "url": "https://www.cnn.com/x", "seen": _dt(2026, 11, 3, 23, 0, tzinfo=_et).isoformat(), "t": "Tue 11:00 p.m.", "w": 3}]
ap.lead_with_projection(_st, _calls, _dt(2026, 11, 4, 10, 30, tzinfo=_et))
check(_st["title"] == "kept" and _st.get("tag") != "Breaking", "the morning after, a single race call or last night's call never leads as Breaking")


# 3. CANADA LEADS (Hannah, Fri Nov 6, 2026): today's real top three, as the code had them
tesla = {"title": "Musk says Tesla will end Cybertruck production next year", "canada": "none", "independent": 5, "tag": "Breaking", "judgment": "national"}
arch = {"title": "Trump moves to make Oval Office a national monument to prevent future major changes", "canada": "none", "independent": 5, "tag": "Breaking", "judgment": "national"}
budget = {"title": "Federal budget funds team to manage N.W.T. major projects", "canada": "canadian", "independent": 12, "tag": "Breaking", "judgment": "national", "theme": "Federal budget"}
top = ap.canada_leads([tesla, arch, budget])
check(top[0] is budget, "a Canadian story with 12 newsrooms leads over U.S. stories with 5")
check(tesla["tag"] == "Developing" and arch["tag"] == "Developing", "a story from abroad with no Canadian tie and under six sources is not Breaking beside it")
check(budget["tag"] == "Breaking", "the Canadian story keeps its Breaking tag")
big = {"title": "Big world story", "canada": "none", "independent": 9, "tag": "Breaking", "judgment": "national"}
small_ca = {"title": "Canadian story", "canada": "canadian", "independent": 4, "tag": "Breaking", "judgment": "national"}
top = ap.canada_leads([big, small_ca])
check(top[0] is big and big["tag"] == "Breaking", "a story from abroad with six sources or more keeps its place and tag")
ams = {"title": "Protesters break into Microsoft data centre site in Amsterdam", "canada": "none", "independent": 3, "tag": "Developing", "judgment": "national"}
jobs = {"title": "Unemployment rate rose to 6.7% in October, StatCan says", "canada": "canadian", "independent": 3, "tag": "Developing", "judgment": "national"}
b2 = dict(budget, tag="Breaking")
top = ap.canada_leads([b2, ams, jobs])
check([x["title"] for x in top] == [b2["title"], jobs["title"], ams["title"]], "a small story from abroad goes below every Canadian story at the top")
alone = [dict(tesla, tag="Breaking"), dict(arch, tag="Breaking")]
check(ap.canada_leads(alone)[0]["tag"] == "Breaking", "with no Canadian story at the top, nothing changes")

# 4. A CANADIAN EXCLUSIVE INSIDE A BIGGER STORY (Hannah, Wed Nov 11, 2026): CTV's Stellantis scoop, folded into the
# Stellantis story under a weaker headline, now leads it, credited to CTV, close to the top
from datetime import datetime as _d
_now = _d.fromisoformat("2026-11-12T00:45:00+00:00")
stel = {"title": "Former Local 444 president says Stellantis abandoning commitments made to auto workers", "canada": "canadian",
        "judgment": "national", "tag": "Developing", "newest": "2026-11-12T00:34:04+00:00", "independent": 3, "weight": 39, "reports": [
    {"outlet": "CTV News", "iso": "2026-11-12T00:34:04+00:00", "title": "Former Local 444 president says Stellantis abandoning commitments made to auto workers", "url": "https://www.ctvnews.ca/windsor/article/x/"},
    {"outlet": "CBC News", "iso": "2026-11-11T23:37:27+00:00", "title": "Ottawa had been aware of a possible Stellantis plant sale for months, source says", "url": "https://www.cbc.ca/news/politics/y"},
    {"outlet": "CP24", "iso": "2026-11-11T03:40:53+00:00", "title": "Carney government actively involved in talks leading to Stellantis plant sale: sources", "url": "https://www.cp24.com/news/canada/2026/11/11/z/"}]}
world = {"title": "Mississippi's Scott Colom secures Senate seat", "canada": "tie", "independent": 11, "carriers": 22, "judgment": "national",
         "newest": "2026-11-12T00:30:00+00:00", "weight": 54}
nv = {"title": "Nvidia's board preparing to oust CEO Jensen Huang, sources say", "canada": "tie", "judgment": "regional", "newest": "2026-11-12T00:20:00+00:00", "weight": 40}
ap.exclusive_inside([stel, world, nv], _now)
check(stel.get("scoop") and stel["scoop_outlet"] == "CTV News", "the newsroom that broke it (CTV, run on CP24) gets the Exclusive credit")
check(stel["title"].startswith("Carney government actively involved"), "the exclusive becomes the story's headline")
check(stel["reports"][0]["exclusive"] and "CBC News" in stel["exclusive"]["confirmed_by"], "its report goes first; CBC is listed as confirming it")
check(ap.top_rule(stel, _now) == 4, "a Canadian exclusive ranks under rule 4: close to the top")
check(not nv.get("scoop"), "a story from abroad is not made a Canadian exclusive")
order = [x["title"][:10] for x in sorted([stel, world, nv], key=ap.rank_key)]
check(order == [world["title"][:10], stel["title"][:10], nv["title"][:10]], "a bigger story stays above it; it goes above smaller ones")


print("\nall passed" if not fails else f"\n{fails} failed")
sys.exit(1 if fails else 0)
