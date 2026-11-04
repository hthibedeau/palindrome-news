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

print("\nall passed" if not fails else f"\n{fails} failed")
sys.exit(1 if fails else 0)
