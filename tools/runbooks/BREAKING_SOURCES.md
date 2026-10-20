# Breaking news: check every source, every run (Hannah's rule)

Breaking news means checking EVERY source out there, not rechecking the same pages. Hannah's words: "Don't always recheck the same sources. Check every source out there. That's what breaking news is."

This rule applies to the top-slot story (section#breaking) on every run of every update task, to every story marked Developing on the page, and (Hannah: "for every story find all the sources you can for it") to EVERY story on the page: for each one, find every newsroom that has reported it, add each report to its STORY entry's "match" (so the section fronts link each outlet), point "latest" at the newest, fullest one, and list the outlets under the story. Work through the whole page each full run, top story first, then the lead, the breakdowns, the U.S. section, the section fronts and the wire. It overrides any narrower list of outlets elsewhere in the runbooks.

## Every run

1. **Start wide, not from the links already on the page.** Never limit the search to the outlets already linked or to a fixed list. Run at least 6 fresh WebSearch queries (mode "extended") for the top-slot story, each worded differently, built from its newest facts:
   - the names of every person involved (victims, injured, officials, accused), on their own and with "family", "tribute", "photo", "vigil", "funeral", "fundraiser";
   - "<story> latest", "<story> today", "<story> update", "<story> <today's weekday>";
   - the place, the institution and the key numbers (toll, injured, dollars);
   - what is still unknown (cause, investigation, inquiry, charges, lawsuit).
2. **Cover the whole range of newsrooms.** For a Canadian story, look beyond CBC, CTV, Global and CP24 to: The Canadian Press, CityNews, the National Post, the Toronto Star and The Globe and Mail; the local papers, TV and radio near the story (for Alberta, for example, the Edmonton Journal, Calgary Herald, CTV and Global Edmonton and Calgary, 630 CHED and CBC Edmonton); the hometown outlets of every named person (e.g. paNOW and CJWW for Prince Albert, the North Shore News for North Vancouver, the Langley Advance Times and Black Press for Langley); official sources (National Defence and the Canadian Armed Forces, RCMP and police, the PMO, provincial governments, courts, coroners); wire services (CP, AP, Reuters, AFP); U.S. and international outlets; and the networks' YouTube channels. For a U.S. story, the same across American national, local and official sources.
3. **Open every candidate that may be new** (WebFetch; for sites the runbooks say work with curl, curl) and read its real publish or update time. Anything newer than the newest line in "How this story developed" is a new development. Search results are often stale: check the date every time.
4. **The human side is news.** When an outlet publishes the names, photos or family tributes of people killed or hurt, or reports a vigil, memorial, funeral or fundraiser, put it on the page right away:
   - names, ranks or roles, ages and hometowns in "The four who died"-style box, one short line per person (house rule 13: keep the top story short), (div.who) above "What we know" (create one if the story has victims and none exists);
   - link the report with the family photos and tributes from that box, in one tap, credited to the outlet;
   - if that report's share image shows the people (photos supplied by families or the military), use it as the top-slot picture, credited exactly as the outlet credits it;
   - add a timestamped line to "How this story developed".
5. **Check every outlet's photos too, every run (every 15 minutes).** While reading each candidate report, look at its lead photo, caption, credit and time; if one is newer or better than the top-slot picture, use it (full-update.md house rules 18b and 18c).
6. **Report what you searched.** In your summary, name the outlets you checked for the top-slot story (at least 12 different newsrooms, including at least 3 local or hometown ones) and the 6+ newsrooms checked for each Developing story. If a site refuses (robots, blocked host), say which; never route around a block with mirrors, caches or other services.
7. **Never write "No new developments" for the top story** unless this wide search found nothing newer than the page.

## Always watching for new breaking news (Hannah: "always be checking for breaking news in all outlets")
Every run, not just the stories already on the page: scan for anything NEW that is breaking right now, Canadian, U.S. or world. Check the front pages and breaking banners of CBC, CTV, Global, CityNews, CP24, The Canadian Press, Radio-Canada, the Globe and Mail, Toronto Star, National Post and the Postmedia papers; AP, Reuters, AFP; CBS, NBC, ABC, CNN, Fox, PBS, NPR; BBC, Al Jazeera, Sky, DW, France 24; plus official alert channels (police, RCMP, emergency alerts, Environment Canada warnings, the PMO and White House, provincial governments). Search "breaking", "just in", "developing" with today's date. Anything confirmed by a reliable outlet goes on the wire at once with its real time; anything bigger than the current top story (deaths, a major disaster or attack, a government falling, a major ruling) takes the Breaking slot in the same run, built with tools/runbooks/BREAKING_TEMPLATE.md.

## Primary sources first (Hannah: "continue to use primary sources as much as possible")
Wherever a fact comes from an official or original source, go to that source, read it and link it, alongside (or ahead of) the newsrooms reporting it: the agency's own release or statement (National Defence, RCMP and police, Elections Alberta and other election offices, coroners, courts and court filings, the PMO, premiers, ministries, the White House, regulators), official results pages, Hansard and CPAC for what was said in Parliament, full unedited video of news conferences, the original social-media post or video only through a newsroom or official page that shows it (never scrape X, Instagram or LinkedIn), reports and data releases (Statistics Canada, central banks, Elections Alberta turnout), and the people involved quoted directly by name. In key facts, the timeline and the summary, cite the primary source by name ("National Defence says…", "Elections Alberta's results page shows…") with its link, and add the newsroom that reported it. Never treat a newsroom's paraphrase as the primary text when the original is available. If an official site can't be read from here, say so and cite the newsroom that quotes it.

## Still true

Every rule in the runbooks still applies: never invent facts, names, ages, quotes, photos, times or links; one tap to the original; The Globe and Mail is never the first click (subscribers' link only); neutral wording; real Eastern times with the day.

## See also
- tools/runbooks/SOURCES.md: every outlet and primary source with how to reach it from this workspace, the domains Hannah could allow, and the facts protocol.
- tools/photo_scan.py: the newest photos on a story, each with its own caption, credit and time (run it in every photo check).
- tools/wire_scan.py: the fast first pass over every directly reachable newsroom, run first in every update and live check.
