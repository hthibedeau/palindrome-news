# The Breaking story template (Hannah: "I want all breaking news to be done like this in the future")

Every Breaking story uses this layout, now and in the future. That covers the top slot (section#breaking) and every Breaking event panel (#bkEvent, built from UPNEXT). It was settled with Hannah on Mon Oct 19, 2026, on the CFB Wainwright fire and the Alberta referendum. When a new story takes the top slot or a new Breaking event starts, build it this way in the same run. Never fall back to the old long layout.

The other runbooks give the detail behind each part: house rules 12–22 in full-update.md, BREAKING_SOURCES.md and BREAKING_EVENTS.md. This file is the checklist.

## The layout, top to bottom
0. **Order, top to bottom (Hannah, Tue Oct 20, 2026):** the photo, its caption, then the latest summary of the story (.bk-dek / UPNEXT dek, newest first, at most 3 short sentences), then the Breaking tag and the LIVE box, then the headline and tabs. The page places the summary under the photo by itself; the Latest tab holds the newest timeline lines.
1. **Photo first, then its caption.** It is replaced automatically every run by `python3 tools/auto_photo.py --page index.html --apply`, which uses the newest captioned, credited photo and keeps the old one as a fallback. tools/freshness_check.py flags a photo unchanged for 3 hours.
   - Find it with `python3 tools/photo_scan.py --page index.html`, which checks every Breaking story on the page, whatever it is, and gives the newest photos with their own captions and credits (method in full-update.md, under house rule 18b).
   - Use the best, newest real news photo of the story, never a drawing. Check for a better one every 15 minutes, from all sources.
   - Save it to img/live/, upload it as an asset and map it in LOCAL.
   - Under the photo goes the caption exactly as the photo's publisher wrote it, ending "— via <outlet>": data-caption on .bart, or caption in the UPNEXT entry.
   - Keep earlier photos as fallbacks in imageChain.
   - On wide screens, the event photo sits on the left beside the headline.
2. **The "Breaking" tag**, and under it, whenever there is live coverage on the story, the **LIVE NOW bar** (Hannah: "live coverage under way needs to stand out more, and where it will take the viewer").
   - The page builds it by itself, for any Breaking story: a bright red bar with a pulsing dot, what is on air, and one button per live video or live blog.
   - Each button says exactly where it goes, for example "▶ Watch live on CBC News · Live video · on now · opens cbc.ca" or "Live updates on CTV News · Live blog · updated 1:14 p.m. ET · opens ctvnews.ca".
   - It reads LIVENOW (`story` must match the Breaking story's name), COMING items on air now, and live blogs updated in the last 6 hours (LIVE_BLOG_HOURS).
   - Your part: keep LIVENOW current, with `updated` (the blog's real last-update time) and `until` for video, so the bar shows only coverage that is really live.
   - **Every source, with a picture** (Hannah: "add in the photo or screen grab, and are there other sources … if there are primary sources offer them too"):
     - List every newsroom running live coverage on the story in LIVENOW: CBC, CTV, Global, CityNews/CP24, the Toronto Star, Radio-Canada, the local papers, and AP or Reuters when they run one.
     - Each entry gets a picture: `file` + `blob`, from the coverage's own share photo or a screen grab (img/grabs/). The bar shows it on the button, with a play icon for video.
     - Add the primary source as `kind: 'official'`: an official live results page, a government or police live stream, a court or legislature feed, or CPAC for the full proceedings. Give it `what` (what it shows, with its own last-updated time), `updated` (when you checked it), `until`, a screen grab, and an optional `note`.
     - **Coming up live, inside the box** (Hannah: "if there is a press conference coming up live on a topic it should be available in the live updates box … not down below in Coming up live"):
       - Any COMING item on the story in the next 24 hours shows in the story's live box under "Coming up live", with its Eastern time, local time, a countdown and where to watch. It moves to Live broadcasts at its start time.
       - The Live coverage band no longer repeats upcoming items for stories that are in the Breaking segment.
       - Your part: add every announced news conference, address or briefing on a Breaking story to COMING the moment it is announced, one entry per network, each with its watch page.
     - The bar groups the buttons under their own headings, broadcasts kept apart from blogs (Hannah: "separate blogs from broadcast"): **Live broadcasts** (live video), **Live blogs** (newest first), **Official sources** (pale yellow, "Official: … · Primary source"). A group shows only when it has something live.
3. **The tag itself.**
   - The page switches it to "Developing" one hour after the latest development (data-lastdev).
   - An event shows a countdown or "Live coverage under way".
3. **Headline.**
   - One line, about 15 words, leading with the NEWEST development.
   - Rewrite it every time the story develops.
4. **Credit lines.**
   - "LATEST <outlet> · <time>" points to the newest, fullest free report.
   - "First reported by <outlet> · <time>".
   - "For subscribers: The Globe and Mail", when it applies.
5. **Tabs**, only one open at a time:
   - **Top story:** Latest · Key facts · <the victims' box, under its own heading, e.g. "The four who died">, only if there are victims · Not yet known · Timeline.
   - **Breaking event:** Latest · Coming up · Key facts · Not yet known · Timeline.
   - **Latest** holds the two newest timeline lines ("Latest updates"). The summary itself sits under the photo (step 0).
   - **Key facts** holds 3–6 one-line facts, each led by its number in bold and ending with its source link.
     - Top story: section#breaking .bk-keyfacts ul.kf. Event: UPNEXT keyfacts.
     - Below the facts: the source-count tracker, and the full "What we know" paragraphs folded as "Everything we know, in full".
   - **Not yet known** holds 2–4 one-line open questions, each with a source.
     - Top story: .bk-keyfacts ul.ky. Event: UPNEXT unknowns.
     - The full paragraphs are folded below.
   - **Coming up** (events only) holds every scheduled update still ahead, with its Eastern time, local time and "in N min / Now" (or "Expected" for a rough time), each cited, then the watch buttons. Finished items fold into "Earlier". Keep it current every run with `python3 tools/schedule_check.py --page index.html` and set scheduleChecked.
   - **Timeline** holds "How this story developed", newest first, one or two short sentences per line, each with its real time and source.
     - Top story: .tl. Event: UPNEXT developed.
     - Long-running stories also get a folded "Further back: how we got here" (TOP_BACKGROUND, or UPNEXT background). Truly breaking stories (a sudden fire, crash, attack or disaster) get NO "further back".
6. **"Latest reports".**
   - Screen grabs of the three newest reports on the story, each linked to the outlet with its real time.
   - Replace the oldest when a newer report comes in.
   - If CBC News has a report on the story, one of the three is always CBC's newest (Hannah's rule). CBC pages block the usual screen-grab tool here, so load the page in Playwright with each cbc.ca request fetched by curl (images skipped) and screenshot it at 1200x675. Save it as img/grabs/cbc-<slug>.jpg, check it with Read, upload it and map it in LOCAL.
7. **Never on a Breaking story:**
   - a "Read the latest" button or a "Today's Daily Brief" link (Hannah removed them; the "LATEST" credit line and "Latest reports" do that job)
   - a "How this developed" button (the Timeline tab replaced it)
   - "Tap to open" wording on fold-out buttons
   - long walls of text
   - material older than 12 hours in the Breaking segment (the page drops it by itself; the full record lives in the "How this developed" section further down and in the log)
   - old broadcasts at the top: a summary more than two hours old folds into one "Earlier today" line

## Around it
- **One story, one place.** While a story is Breaking or Developing, the page hides its repeats from the other news sections and brings them back when it leaves. Opinion, analysis and video stay.
- **Nothing is lost.** Whatever a hidden repeat says that the story lacks is carried into the story's Timeline tab under "Also on this story"; runs then move it into the real timeline. A Breaking event stays as "Developing" for 12 hours after its live window or its last scheduled item (keepUntil to change that).
- **The Canada desk comes right after the Breaking and Developing stories, all the time** (Hannah, Tue Oct 20, 2026). The page moves it there by itself (canadaAfterBreaking).
- **"Live coverage now" is its own band**, after the Breaking stories and the Canada desk, separate from them. It holds live video, live blogs and "Coming up live" tiles, named by story, each with a picture.
- **Always watching for new breaking news, and primary sources first** (BREAKING_SOURCES.md): every run scans all outlets and official alert channels for anything new, and cites official releases, results pages, court filings, Hansard and full video directly, with the newsrooms that reported them.
- **Every source, every run.**
  - Search the whole range of newsrooms: national, local, hometown, official, wire, U.S. and international.
  - Link every outlet reporting the story in its STORY match, the tribute lists and the key facts.
  - Names, photos and family tributes of victims go up as soon as any outlet publishes them.
- **Scheduled live coverage** on a story makes it a Breaking event two hours before it starts (UPNEXT, BREAKING_EVENTS.md).
- **Check every link** before publishing. Replace any dead one with a working source.

## When a NEW story becomes Breaking (top slot)
In the same run:
0. Set data-match on section#breaking (or match on the UPNEXT entry) to the story's distinctive words, so its repeats leave the rest of the page (one story, one place).
1. Set section#breaking's data-since, data-lastdev, data-latest, data-first, data-story and data-photo-checked.
2. Write the photo with its caption, the headline, the credit lines and the summary.
3. Write .bk-keyfacts (ul.kf, ul.ky).
4. Add the victims' box (.who), if there are victims.
5. Start a fresh .tl timeline.
6. Add the full .know paragraphs.
7. Add the "Latest reports" screen grabs.
8. Set TOP_BACKGROUND to [] for a sudden event, or fill it with dated milestones for a long-running story.
9. Add the STORY entry.
10. Move the old top story to the lead or the wire.

The page builds the tabs, "Latest updates", the timeline toggle and the "How this developed" section by itself from these parts.

Before publishing, check it like a reader on a phone (390 wide) and a wide screen (1280):
- every tab opens
- the photo and its caption show
- no headline is older than the newest timeline line
- every link opens the right outlet in a new tab
- there are no page errors
