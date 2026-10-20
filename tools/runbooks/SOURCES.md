# Sources: where we get the news, and how to reach it from here

Hannah: "always be checking for breaking news in all outlets. Also continue to use primary sources as much as possible." This file is the directory. It lists every outlet and official source, how this workspace can reach it, and how to check facts before they go on the page. Read it with BREAKING_SOURCES.md on every run.

Reachability was tested Mon Oct 19, 2026, late evening. If a method stops working, note it in your summary and update this file.

## Step 0 of every run: the wire scan (about 20 seconds)
```
python3 tools/wire_scan.py --fresh 30            # everything, newest first, NEW = last 30 min
python3 tools/wire_scan.py --grep "Wainwright|referendum"   # one story
```
- It reads CBC News and CTV News front pages (their own story lists, with real update times) and fresh RSS feeds: Global News (top, Canada, world, politics), Al Jazeera, The Globe and Mail (Canada, world, politics, business; subscribers only, so never the first click) and The Tyee.
- Every NEW line is a lead to check. Open the article, read its real time and facts, and decide whether it is breaking news, a new development on a story we carry, or wire material.
- It is the fast first pass, not the whole job. Then run the wide WebSearch (BREAKING_SOURCES.md) for everything it cannot reach.

## How each source can be reached

### A. Direct (curl, front page and articles): the fastest and freshest
| Outlet | How |
|---|---|
| CBC News | cbc.ca/news: `window.__INITIAL_STATE__` (replace `:undefined` with `:null`). Articles and live blogs by curl. CBC RSS is stale: don't use it. Photos on i.cbc.ca are blocked, so take screen grabs (BREAKING_TEMPLATE step 6). |
| CTV News | ctvnews.ca: `Fusion.contentCache`. Articles by curl. CTV RSS returns 404. |
| Global News | RSS (`/feed/`, `/canada/feed/`, `/world/feed/`, `/politics/feed/`), articles by curl. |
| The Globe and Mail | RSS by category (`/arc/outboundfeeds/rss/category/<canada|world|politics|business>/`). Subscribers only, so cite in "sub", never as the first click. |
| Al Jazeera | RSS `/xml/rss/all.xml`, articles by curl. |
| The Hill Times | Articles by curl. |
| The Tyee | RSS `/rss2.xml`. |

### B. WebFetch on ARTICLE pages (found with WebSearch)
These work for many more outlets: CityNews, CP24, The Canadian Press (Yahoo copies only), Postmedia papers (National Post, Calgary Herald, Edmonton Journal and others), Toronto Star, APTN, Radio-Canada, AP, Reuters, BBC, NBC, CBS, ABC, PBS, NPR, The Guardian and local outlets.
- **Front pages fetched with WebFetch are often stale cached copies.** Never take "what's new" from one. Use WebSearch for the newest reports, then open each article and read its own published or updated time (meta tags `article:published_time` / `article:modified_time`, `datePublished` / `dateModified` in its JSON-LD, or the time printed on the page).
- Never take a time from a search snippet.

### C. Primary sources (official, first-hand): use them first
Reachable:
- **Alberta:** alberta.ca/news (government releases); elections.ab.ca (results, turnout, official statements).
- **Parliament:** ourcommons.ca (Hansard, votes, committees; ParlVU for video).
- **Data:** Statistics Canada The Daily (statcan.gc.ca); Bank of Canada (bankofcanada.ca: rate decisions, speeches).
- **Police:** RCMP (rcmp.ca news releases).
- **United States:** whitehouse.gov (statements, briefings, schedule); state.gov; supremecourt.gov (opinions, orders); fbi.gov.
- **International:** who.int.

Partly reachable (try, then fall back to the newsroom that quoted it):
- canada.ca (department releases; National Defence statements) and pm.gc.ca (PM's statements and itinerary).

How to use them:
- Cite the primary source directly, with the newsrooms that reported it.
- When a number or name comes from an official source, the official source wins (see the facts protocol below).
- Full video of news conferences: CPAC (unedited), ParlVU, the government's own channel.

### D. Not reachable from this workspace
- **No direct access:** AP, Reuters, BBC, CNN, NYT, Washington Post, CityNews and CP24 front pages, X, Instagram and LinkedIn.
- **Never scrape:** X, Instagram and LinkedIn. Never use mirrors, caches or archive copies to get around a block.
- **Use instead:** article pages through WebSearch + WebFetch where they work. Use the networks' official YouTube channels for their video (tools/network_youtube.py).

## Domains Hannah could allow (claude.ai Settings > Capabilities, network access)
Allowing these would let every run read them directly, faster and fresher than WebFetch:
- **Canadian newsrooms:** citynews.ca, cp24.com, thecanadianpress.com, nationalpost.com, calgaryherald.com, edmontonjournal.com, thestar.com, aptnnews.ca, ici.radio-canada.ca, cpac.ca
- **Wires and international:** apnews.com, reuters.com, bbc.com, bbc.co.uk, theguardian.com
- **U.S. networks:** nbcnews.com, cbsnews.com, abcnews.go.com, npr.org, pbs.org
- **Photos:** i.cbc.ca, so CBC's own photos can be used instead of screen grabs
- **Official sources:** canada.ca, pm.gc.ca, news.gc.ca (the federal news release feed)
- **Official alerts:** alertready.ca and Environment Canada weather alerts (weather.gc.ca)

## Facts protocol: getting the best facts, every time
1. **Primary first.**
   - For any number, name, title, time or quote, look for the official source: release, results page, filing, Hansard or the full video.
   - If there is one, use its wording and cite it. Then cite the newsrooms.
2. **Two sources for a new fact without a primary source.**
   - A fact from one newsroom alone goes up attributed to it ("CTV News reports …").
   - When a second outlet confirms it independently, drop the attribution if you like.
   - Never present one outlet's exclusive as settled.
3. **When outlets disagree** (e.g. 106 vs 107 vs "more than 100"):
   - Use the primary source's figure.
   - With no primary, use the most recent report from the outlet closest to the source, and say "at least" or give both ("39, according to National Defence; CBC reports 40").
   - Never average or pick the bigger number.
4. **Real times only.**
   - Every time on the page comes from the article's own metadata or printed time, in Eastern.
   - Never a search snippet, never "about an hour ago" guesses.
   - If no time is given, use the day only.
5. **Names and titles.** Check spelling and title against the official source or two outlets before publishing, above all for victims.
6. **Quotes.** Use exact quotes only as an outlet or the official transcript prints them. Never stitch or paraphrase inside quote marks.
7. **Corrections.**
   - When a fact on the page turns out wrong or is revised (a death toll, a name, a time), fix it everywhere on the page in the same run: headline, dek, key facts, timeline, wire.
   - Add a timeline line "Correction: …" or "Revised: … (was …)" with its time and source.
   - Note it in the log.
8. **Labels.**
   - Unconfirmed, contested or official-only claims say so plainly ("police say", "unconfirmed", "the campaign claims").
   - "Not yet known" lists what is still open.
