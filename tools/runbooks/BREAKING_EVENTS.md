# Breaking events (layout: tools/runbooks/BREAKING_TEMPLATE.md): live coverage coming becomes the Breaking story 2 hours ahead (Hannah's rule)

Hannah: "When there is a story that will have live updates, put that as the breaking story 2 hours before the event, then add in any updates that are coming with times." She wants this to happen all the time, on every run of every update task (full updates at :09 and :39, live checks at :24 and :54). This file says exactly how it was first done (the Alberta referendum, Mon Oct 19, 2026) so every run does it the same way.

## What the page does by itself
In the page script (index.html), right after the `breakingPace` code:
- `const EVENT_LEAD_HOURS = 2;`
- `const UPNEXT = [ ... ];` — one entry per upcoming live event (fields below).
- `breakingEvent()` — every minute it picks the earliest event whose start is within 2 hours (or under way) and whose `until` hasn't passed, and shows it in `<section id="bkEvent">` above the top slot: a red "Breaking" tag, a countdown ("Live coverage begins in 28 min" / "Live coverage under way"), the headline (linked), a "Latest" credit, a 2–3 sentence dek, "Coming up" (each update with its Eastern time, local time, "in N min" / "Now" / "Done", and its source link), and "Where to watch" buttons taken from `COMING` items whose story starts with the event's `story`.
- Safety net: if a `COMING` item (not `top: true`) has no `UPNEXT` entry, the page builds a plain event from the `COMING` items for that story by itself (headline "<story>: live coverage begins at <time>", schedule from each network's start). This is only a fallback: always write a proper `UPNEXT` entry.
- When nothing is due, the panel is hidden. You never need to switch it on or off by hand: the times do it.

## UPNEXT fields
```
{ id: 'short-slug-date',
  story: 'Alberta referendum',          // must be the START of the matching COMING story names ('Alberta referendum results')
  start: '2026-10-19T21:00:00-04:00',   // ISO Eastern: when the FIRST live coverage begins
  until: '2026-10-20T07:00:00-04:00',   // when it stops being the Breaking event (final results / end of the event)
  h: 'Alberta referendum: live results coverage begins at 9 p.m. ET; the last polls close at midnight ET',
  url: '<newest, fullest free report>', outlet: 'CTV News', urlWhen: 'Mon 7:55 p.m.',
  dek: '2–3 short sentences, each fact linked: <a href="..." target="_blank" rel="noopener">CTV News</a>',
  photo: 'img/live/<file>.jpg', credit: 'as the outlet credits it', alt: 'what the picture shows',
  schedule: [ { at: ISO, to: ISO (optional, for a window), local: '7 p.m. MT', text: 'what happens', outlet: 'CBC News', url: '<page that reports this time>' }, ... ] }
```

## "How this developed" (required)
Every Breaking event also needs `devName` (e.g. 'the Alberta referendum') and `developed: [[time label, text, outlet, url], ...]`, newest first: the story's dated developments so far, each from a real report with its real time ("Mon 7:55 p.m."). They feed the event's Latest and Timeline tabs (there is no "How this developed" button any more). Add a line every time the story develops (full-update.md house rule 21). If the story has been building for a while (never for a sudden breaking event), also give the entry `background: [[date, text, outlet, url], ...]` (newest first) so readers are taken back to how it began (house rule 22).

## How to do it, every run
1. **Find every live event coming in the next 24 hours** on any story on the page or any major Canadian, U.S. or world story: news conferences, statements and addresses, House of Commons statements, votes and results nights, court rulings, inquiries and hearings, launches, funerals and memorials, sporting finals that lead the news. Search widely (BREAKING_SOURCES.md): WebSearch "<story> live coverage", "<story> what time", "<story> results when", "where to watch <story>", "<person> to speak", "news conference at", "media advisory"; the Prime Minister's itinerary (https://www.pm.gc.ca/en/news/media-advisories); premiers' and ministers' advisories; the White House schedule for U.S. stories; the networks' "where to watch" pages (CBC, CTV, Global, CPAC, CityNews; CBS, NBC, ABC, PBS, C-SPAN, CNN, Fox).
2. **Confirm every time on the page that reports it.** Open it (curl with a browser user agent for cbc.ca and ctvnews.ca; WebFetch otherwise) and read the exact time and time zone. For the referendum: CBC's coverage page said "streaming live starting at 7:00 p.m. MT"; CTV's where-to-watch page said "begins at 10 p.m. MT"; CTV's live blog said most polls close at 8 p.m. MT, the last at 10 p.m. MT, results not before 10 p.m. MT, and Question 10 results "between 1 a.m. and 4 a.m. MT Tuesday". Never guess a time; never use a time only a search snippet shows.
3. **Convert to Eastern** (MT +2, CT +1, PT +3, AT −1, NT −1.5; watch for daylight time) and write ISO with the offset (-04:00 in daylight time, -05:00 in standard time). Keep the local time as announced in `local`.
4. **Add a COMING item per network carrying it live** (live rule 4 in full-update.md), with its own watch page and a picture (grab_picture.py, uploaded as an asset). The event's "Where to watch" buttons come from these.
5. **Write the UPNEXT entry**: `start` = the earliest live coverage; `until` = when the news is expected to be complete (final results, end of the event, plus about an hour); `h` = one line saying what is coming and when, in ET; `dek` = 2–3 sentences of the newest confirmed facts, cited; `url` = the newest free report (never The Globe and Mail); `schedule` = EVERY timed update that is coming, each cited to the page that reported its time (coverage start times per network, polls closing, results expected, speakers in order, votes, rulings). A real picture is REQUIRED (full-update.md house rule 18): use one already in img/live/ (mapped in `const LOCAL` to its `/_blob/` id) or save a new one there; the page also falls back to the COMING and LIVENOW pictures for the story.
6. **Every later run**: add any newly announced times to `schedule`; update `h`, `dek`, `url`, `urlWhen` from the newest report; when coverage is live, also set `LIVE` (live rules 1–3c: live picture, running summary). Rows mark themselves "Now" and "Done"; you don't edit them.
7. **When the event has its own developments** (results coming in, the speaker has spoken): move the story into `section#breaking` itself (headline, dek, "How this story developed", `data-lastdev`, STORY entry, screen grabs of the latest reports), move the previous top story to the lead or the wire, and delete its UPNEXT entry. Delete entries whose `until` has passed.
8. **Check it like a reader** (Playwright, iPhone size): at a time inside the 2-hour window the panel shows with the right countdown, every schedule link and watch button opens the right page in a new tab, and the picture loads. Run `node --check` on the last script block.
9. **Log it**: one line in the Corrections & updates log naming the event and the times, cited.

## Never
Invent a time, a network, a speaker or a link. Show an event whose time no reliable source has reported. Leave an event up after its `until`.

## Tabs (required)
Every Breaking event shows the same tabs as the top story: Latest · Coming up · Key facts · Not yet known · Timeline. Give each UPNEXT entry `keyfacts: [['number', 'one-line fact', 'Outlet', 'url'], ...]` (3–6, number first) and `unknowns: [['one-line open question', 'Outlet', 'url'], ...]` (2–4), from real reports, and update them every run (full-update.md house rule 12c).

## Keeping "Coming up" current (every run)
Run `python3 tools/schedule_check.py --page index.html` and follow the "COMING UP IS NEVER OLD" step in full-update.md / live-check.md.
- Schedule items can carry `approx` (a rough time, shown as written).
- Each UPNEXT entry carries `scheduleChecked`.
- An event shows again 2 hours before any later scheduled item, even after its `until`.

## After the live window
An event stays on the page as "Developing" for EVENT_KEEP_HOURS (12) after `until` or after its last scheduled item, whichever is later. Its tabs and its How this developed block go with it. Set `keepUntil: ISO` to change that.
