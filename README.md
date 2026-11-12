# Palindrome News

News from every direction.

Your personal newsroom. See it all and go straight to the source.

Palindrome News is an online newsroom for people who get their news online instead of on TV. It summarizes the day's stories from trusted outlets, always links to the original reporting, and never publishes its own editorials.

Founded and edited by Hannah Thibedeau.

## What's here

| File | What it is |
| --- | --- |
| `index.html` | The homepage preview: newspaper-style nameplate, a compact bar that follows you down the page, breaking news with what we know and a confirmation tracker, a live wire, a Late edition stamp after 10 p.m., a wall of clocks for the cities in the news, a story board of everything in progress, a 60-second read-aloud brief, a corrections and updates log, The day in pictures (a rotating, shuffled photo gallery), photos on the wire and Most read, editor screenshot uploads on post and video cards, The breakdown (a full reporter's synopsis for every story verified by six or more independent outlets), breaking news with two accounts and a timeline, a From every direction comparison, a Watch strip of the day's video, What to watch (dated decisions ahead) with a 60-second read-aloud brief, "Why it matters" lines, desk-by-desk section fronts with a six-source meter on every story, a United States section with a midterms countdown and what America's newsrooms are leading with, Most read across Canada, Today's reading, On the record, Editorials, Think tanks, Go deeper, and sponsor sections. |
| `editors-desk.html` | The Editor's Desk preview, where the editor reviews, publishes, hides and ranks stories and manages sources. It runs on sample data; nothing is saved. |

Both pages open directly in a web browser. They are previews: the live site will need a server that gathers the news, checks sources and serves the Editor's Desk.

## House rules

- Every summary is built from at least six independent, trusted sources, with links attached.
- Tapping a story takes the reader straight to the original article.
- Breaking news can run with credit to the outlet that reported it, and takes over the top of the homepage.
- Sponsors pay for the site but never choose or rank the news. Paid editorials are always labelled.
- Breaking news means checking every source out there, not rechecking the same pages: national, local and hometown newsrooms, official sources and wires, every run. Names, photos and tributes of victims go on the page as soon as an outlet publishes them. See `tools/runbooks/BREAKING_SOURCES.md`.

## Design preview (Hannah, Sun Nov 1, 2026)

`preview-design.html` is the homepage with Chris T's design review applied on top (`tools/design_layer.html`): photo tiles when a picture fails, old stories and clips tucked under "Show older", unsold sponsor slots without placeholder text, a lighter lead panel with red kept for Breaking, navigation that fits with a More menu, a slimmer clock strip with every clock, long sections folded with "Show all" (nothing removed), a compact phone header with tabs and a menu, the source meter on the lead stories with a one-line legend, Back to top and a "Beta" badge. `index.html` is untouched.

- Keep it: `python3 tools/build_design_preview.py --adopt` (puts the layer into index.html).
- Drop it: `python3 tools/build_design_preview.py --drop`, then delete `tools/design_layer.html`.

## Combined sections (Hannah, Wed Nov 4, 2026) — on the homepage since Nov 4, 2026

"There is also a lot of duplication on the page ... do that and then I want to look at it. Be prepared to go back to this if I dont." Hannah: "Can you put it into the github and we will revert if I dont like it." The layer (`tools/combine_layer.html`) is now in `index.html`, between `<!-- cmb:start -->` and `<!-- cmb:end -->`. To go back, revert the commit "Homepage: combined sections" (or delete that block from index.html).

- **One package for the big story.** Anything the top story already shows (same article, same wire headline, same live video) is left out of The big week ahead, Canada and the U.S., United States, Live coverage, Watch and the live-event strip. An event that is over and is the top story drops out of The big week ahead.
- **One list of reports in the top story** (Hannah, Wed Nov 4, 2026: "These two segments seem repetitive"): What each newsroom reports and Connected to this story are one list, "The latest from every newsroom": the primary source first, then newest first, each headline once (a wire headline run by two newsrooms is one line with both names).
- **How this developed** is the top story's own timeline, folded under it.
- **Coming up**: The big week ahead, What to watch (Dates & decisions) and Story board as tabs. The 60-second brief player stays just above it.
- **Opinion & analysis**: Editorials and Think tanks as tabs. **Read & listen**: Most read, Today's reading and Podcasts (Go deeper) as tabs; podcasts older than a week age out, and an empty tab goes.
- **Corrections & updates** folds to one line, "See all … updates", which opens the full log.
- Menu links to a merged section open its tab. Nothing is removed from the page.


## Canada leads, and no empty panel (Hannah, Fri Nov 6, 2026)

- **Canada leads.** At the top of the page, a story from abroad with no Canadian tie and fewer than six independent newsrooms never sits above a Canadian story, and it shows "Developing", not "Breaking", when that Canadian story has more coverage (`canada_leads()` in `tools/autopilot.py`). Why: Tesla ending the Cybertruck (5 newsrooms) led as Breaking over the federal budget (12 newsrooms, live on CPAC).
- **A national headline for a national story.** A story with six or more independent newsrooms takes its headline from a national desk, not a city or regional angle ("what does it mean for B.C.?"); the local angles stay in its reports.
- **No empty panel.** On a wide screen the two top columns stack on their own, so a short lead story no longer leaves an empty block beside the stories on the right (`place()` in `tools/crisp_layer.html`).
- Checks: `python3 tools/test_story_match.py`.

## Nothing outdated (Hannah, Sun Nov 8, 2026)

"There seems to be a lot of outdated stories on the website. Can you make that better and fix it in the code." Sections that were written by hand weeks ago now age out by themselves and fill from each update:

- **Watch** shows clips from the last two days, newest first. Every clip's day comes from the clip itself (upload date, time added, or the date in its web address), so an Oct. 18 clip can never say "Today". Older clips wait behind "Show older clips". Each update now adds up to 30 new clips, three per network.
- **United States** is a desk filled by each update: today's American stories, most newsrooms first (`desks()` in `tools/autopilot.py`, desk `us`). The hand-written list shows only for two days after it was written (`US_WRITTEN` in index.html). The same story told twice on a desk counts once.
- **Today's reading**: the editor's picks show for three days; after that, today's long reads from Canadian newsrooms (analysis, explainers, investigations, features, never opinion: `reads()` in `tools/autopilot.py`).
- **Canada and the U.S.**: the band says when the newest reports were checked and when the trade figures were last reviewed. "How U.S. media see Canada" folds cards older than five days into "Earlier U.S. coverage"; more U.S. newsrooms are read for it.
- **Most read** leaves out articles more than a week old, even when they sit on a newsroom's most-read list.
- **Weekday labels are not dates** (Mon Nov 9, 2026: "look how old this story is ... It has been on the site for a long time"). The Oct. 26 Carney lead said only "Updated Mon 6:47 p.m.", so it came back as new every Monday. A hand-written story now counts as current only when it carries a real recent date (`data-updated`, or the date in one of its links: `PAL_handFresh` in index.html). The lead slot, the hand-written desk stories and the wire all use it.
- **Go deeper** fills from the newest episodes of Canada's news podcasts (Front Burner, The House, Power & Politics, As It Happens, What on Earth?) every update, with each show's own picture: `podcasts()` in tools/autopilot.py. The hand-written episodes show only for a week. (Mon Nov 9, 2026: "I want all news updated")
- **Story board** is built every update from the stories the page is carrying: the top stories, then the biggest stories on each desk.
- **Obituaries, memorial notices and classifieds** are never news (`NOT_NEWS_PAGE` in tools/autoupdate.py); a SooToday "In memoriam" notice had shown in Smaller newsrooms.
- **Editorials** and **Most read** no longer show one day's hand-written intro or fine print.

## Watch this story (Hannah, Mon Nov 9, 2026)

"Under the top news story, can you put a watch section like we have below, but just include the watch of that story." Under each top story and its photo (before the reports), "Watch this story" shows the same Watch cards, only for that story, in a row that scrolls sideways like Watch below: clips from the last two days whose titles share two of the story's words, or one of its names (Hegseth, Massie) that isn't an everyday political word. The second top story gets its own row too, with smaller cards, shown even while the story is folded (Hannah, Mon Nov 9, 2026: "add video. Watch this story under the NVIDIA one as well in a scroll bar. Could be smaller than the main one"). A clip appears under only one story. `PAL_storyWatch` in index.html; it redraws whenever the top stories or the clips update. Each tap goes straight to the clip on the network's site.

## The report count goes to the reports (Hannah, Mon Nov 9, 2026)

"At the top where it says 8 independent reports, when you touch that, could it take you down to the screen where it says what each newsroom reports?" On every top story, the lead story and a hand-written Breaking story, the report count ("8 independent reports ↓") is a link: one tap opens that story's "What each newsroom reports" list, shows all of it, and scrolls down to it (`goReps` in index.html).

## Independent reports, not newsrooms (Hannah, Mon Nov 9, 2026)

"Some you count as a independent report are not, because a lot of them use Associated Press story." The Politics, Business, World, U.S. and Canada desks now read the byline of each newsroom's report (`grouped_outlets()` in tools/autopilot.py, and the Canada desk in tools/autoupdate.py), the same way the top stories do: one wire story run by several newsrooms counts once. The outlets line shows it: a comma between independent reports, "+" between newsrooms that ran the same one, with the wire named ("Toronto Star + ABC News + CTV News + CP24 (AP)"). The six-source meter and the ranking count independent reports. A wire's own address on a newsroom's site (/wireStory/, apnews.com) counts as the wire's report too.

## Subscription pages go later (Hannah, Mon Nov 9, 2026)

"If you have to subscribe to the page, put it later", then "Change to hard paywalls." Hard paywalls only, sites with no free articles (`PAYWALL` in tools/autopilot.py: The Globe and Mail, The Logic, The Hill Times, The Wall Street Journal, the Financial Times, The Economist, Bloomberg.com, Barron's, The Athletic, The Times). Metered sites that give some free articles (the Toronto Star, the Postmedia papers, The New York Times, The Washington Post) count as free. A subscription page is never the headline's link when a free report exists; in every list of reports it comes after the free ones, marked "subscribers", still one tap away. Of newsrooms running the same wire story, a free one leads. The page applies the same order to its lists (`PAL_subsLater` in index.html). A story with only a subscription report still links to it.

## Breaking holds the top (Hannah, Mon Nov 9, 2026)

The Nvidia story, leading 9 front pages but with no new report in two hours, had pushed the Breaking Massie-Hegseth story (8 independent reports, a report 20 minutes old) off the top, because "leading other newsrooms' front pages" outranked everything. Hannah agreed to this rule: a story that is still Breaking (a report in the last hour, or live now) stays above a story ranked up for its front pages, unless that story leads at least twice as many front pages (`breaking_holds()` and `BREAKING_FRONTS_FACTOR` in tools/autopilot.py). An event day still leads. The reason shows in live/auto.json "considered".

## A rolling news stream is not one event (Hannah, Mon Nov 9, 2026)

"In live coverage now, it says Trump gives White House briefing, but it's really Hakeem Jeffries now up." LiveNOW from FOX kept the rundown it started with as the title of its all-evening stream. A live stream whose title is a rundown of several stories, or that has been on air more than three hours (a hearing, debate, trial or sitting excepted), is rolling coverage: it stays among the live videos with its picture ("I like having that live video in there though"), labelled "Rolling live news coverage, as it happens", never named as the event on air now or tied to a story (`ROLLING_TITLE`, `ROLLING_HOURS` in tools/autopilot.py).

## How the page updates itself: the code runs it

Since Tue Oct 27, 2026, the site runs on code, not on Claude (Hannah: "I dont want to rely on claude to run my site. I want the code to do it"). Nothing needs a person or an AI to keep it current:

- **Every 10 minutes**, GitHub Actions runs `tools/autoupdate.py` (with `tools/autopilot.py`) and writes `live/auto.json`. The page reads it every 2 minutes. It covers:
  - **Top stories.** When the hand-written top story has had nothing new for 3 hours, the two biggest stories take its place. They're ranked by National Newswatch, CBC's front page and how many newsrooms carry each one. Each gets the newest report's own headline and summary, credited, plus "First reported by", the outlet's own photo and caption, and every newsroom carrying it. "Breaking" lasts an hour after the newest report.
  - **The wire**, newest headlines from about 85 newsrooms.
  - **Newest reports and photos** on every Breaking story, and live-blog times.
  - **The Canada desk**, today's stories from every province and territory.
  - **Watch**, new uploads from the networks' official YouTube channels, Canadian and U.S. first.
  - **What America's newsrooms are leading with.**
  - **Think tanks & white papers** and **Editorials**.
  - **Canada and the U.S.**: the newest on trade and the border, and U.S. newsrooms on Canada.
  - **The Canadian angle.** When a top story is from another country, a sidebar on it lists the newest reports tying it to Canada (Canadians caught up in it, Ottawa's and the Prime Minister's response, effects on Canadian trade, travel or communities), plus official Canadian statements, each the outlet's own headline, credited and linked. U.S. political, election and trade stories also carry the newest Canada–U.S. relationship reports (trade talks, tariffs, Hoekstra, U.S. media on Canada). The same panel goes on Live coverage tiles (live blogs and live video, now and coming up) and on What America's newsrooms are leading with. No Canadian angle in the news: no sidebar. `canadian_angle()` and `canadian_angle_live()` in `tools/autopilot.py`.
  - **The 60-second brief**, each story credited to its newsroom and read aloud by the reader's device.
- **What each newsroom reports**: every auto top story shows each outlet's own lead sentence side by side, credited and linked.
- **The breakdown**: any story carried by 6 or more independent newsrooms (same owner and wire copies counted once) gets a breakdown by itself, each line in a newsroom's own words.
- **On the record**: statements from official sources the code can read: the Prime Minister, the federal and provincial governments, the White House and the UN.
- **Hannah's voice**: `tools/brief_voice.py` (`.github/workflows/brief.yml`, three times a day) reads each brief in Hannah's own voice. It copies the voice from her recording in `tools/voice-samples/` with Chatterbox, an open-source model that runs on GitHub. No sign-ups, and nothing is sent anywhere else.
- **Every hour**, `tools/linkcheck.py` checks every link on the page. The page hides anything whose link is dead (404/410 on two checks in a row).
- **The page itself** ages out old material: breakdowns move to Earlier after 24 hours and drop after 72, and think-tank papers drop after six weeks.

Everything shown is the outlets' own: headlines, summaries, captions, times and pictures, always credited and linked. The code never writes or guesses.

**House rule (Hannah, Oct 27, 2026): everything she asks for is built into the code.** Any new feature or rule goes into `tools/` and the page script so it runs by itself, never as a task someone has to repeat. The runbooks in `tools/runbooks/` describe the older hand-run process. Claude's scheduled tasks for the site are paused; Claude now works only when Hannah asks for something.

## News judgment: is this the top story? (Hannah, Sat Oct 31, 2026)

Before ranking, the code asks the question an editor asks at the morning meeting: who is this story for? It answers it from what the newsrooms themselves published (`news_judgment()` in `tools/autopilot.py`, explained in full in the NEWS JUDGMENT note above it).

1. **How many people does it affect?** Many: Ottawa or a province, the economy, prices, trade, Canada in the world, elections, strikes, health care, housing, the military, disasters, or a tragedy with many victims. Few: a single crime, arrest, court date, crash or fire.
2. **How many people will want to read it?** It counts the national desks carrying it and how many cities' newsrooms chose to run it. A story only on one city's local desks is a story for that city.

A story that touches few people and is read in one city is **Local**. It stays in the Canada desk and the other sections, but it is never a top story. A story that scores high on both is **National** and gets a lift. Each candidate's verdict and the reason are in `live/auto.json` under "considered".

Example: "Toronto man identified as suspect in Bridle Path home invasion" (one crime, Toronto desks only) is Local. "Canada-EU associate membership talks" (Canada's trade and place in the world, in newsrooms in seven cities) is National, and the top story.

## The biggest story leads like one (Hannah, Wed Nov 4, 2026)

"It doesn't look like a site with all the latest news on the biggest story in the globe." The day after a big event, the code now:

- **Keeps it alone at the top, full width,** while the front pages here and abroad still lead with it (six or more, two of them Canadian). When they move on, the day's other stories come back beside it. `big_news_day()` in `tools/autopilot.py`.
- **Leads with the result itself** ("Midterm fallout begins after Democrats win control of Congress", CBS News), never a reaction ("minister says", "despite", "vindicates"), the markets or one race. The big newsrooms' own front-page leads are candidates, linked to their article and timed by the newsroom. Reactions stay in the Canadian angle. `morning_headline()`.
- **Credits the first report of the result** as "First", not an overnight markets story.
- **Never leads with an old file photo**: a caption dated days before today ("June 16, 2026", "in 2023", "file photo") goes behind any photo from today and never joins the reel. `file_photo()`.
- **Files one state's seat under its race**, never under "Control of the House" in Results: who called what. `proj_race()`.

## Page order (Hannah, Wed Oct 28, 2026)

The page script (`PAL_orderTop` in `index.html`) keeps this order by itself, whatever is showing:

1. The two Breaking/Developing top stories (the automatic pair, or the hand-written top story and any hand-written Breaking event).
   The automatic pair is picked by `pick_by_canada()` in `tools/autopilot.py` (Hannah, Oct 28: "If there are Canadian ties to a top story, that should be there instead"). Up to 8 ranked candidates are built. A story from another country with no Canadian tie in the news gives way to the next-ranked story that is Canadian or has a tie. U.S. political stories count as tied when the Canada–U.S. relationship is in the news. Running themes like Canada and the U.S. are split into their separate stories, so a Canada–U.S. story can lead, one per theme in the top pair.
2. The Canada desk, "Across Canada": today's stories province by province.
3. A scheduled live broadcast the code has promoted to the event slot, then Live coverage, then everything else.

The Canada desk heading is styled like the Palindrome News nameplate (a "The Canada desk" kicker, "Across *Canada*" in the nameplate's purple italic, under a double rule). It has no maple leaf, so it never looks like a government logo.

## Photos on the preview link

The claude.ai preview blocks images hosted on other websites, so outlet photos are copied into the page's own storage. `tools/localize_images.py index.html <folder>` downloads every photo it can reach and lists the exact host names still to approve under claude.ai Settings > Capabilities > Allow network egress. The page tries the stored copy first, then the outlet's original, then a drawn illustration.

`tools/grab_picture.py <link> <out.jpg>` gets a picture for any story, post or video: the page's own share image if it has one, otherwise a screen grab of the top of the page. X (Twitter) pages are not grabbed; their posts use X's official embed on the live site.

On the record cards carry `data-embed` (the original post link) and `data-platform`. On the live site these are swapped for each platform's official embed (X, Instagram, LinkedIn, Truth Social), so posts show exactly as published without scraping.

## A newspaper front when one story stands alone (Hannah, Mon Nov 9, 2026)

"Half the page is blank" ... "still isnt the most appealing." On a wide screen (iPad, laptop) the lone big story is now laid out like a front page: the headline across the full width with its subheadline and byline; the live strip; then the photo beside the Canadian angle and Connected to this story, the photo cut to the height of that column so both end together; then "The latest from every newsroom" across the width, three reports side by side. With no Canadian angle in an edition, the newsroom list goes beside the photo instead. Phones are unchanged. Code: `tools/solo_front_layer.html`, in index.html between `<!-- solo-front:start -->` and `<!-- solo-front:end -->` (pure layout; nothing moved or removed). The no-repeats check between the two lists now also runs beside a lone big story.


## Canadian exclusives get the credit (Hannah, Wed Nov 11, 2026)

"If there is exclusive reporting like the CTV story ... it should get an exclusive. and write the rules that if it is Canadian, big exclusive, cite the source, put it close to the top, if not the top story, unless there's other big stories." CTV's scoop that the Carney government was actively involved in the Stellantis Brampton plant sale had been folded into the Stellantis story as its fourth report, and the story led with a weaker headline.

- **Canadian, big exclusive:** a Canadian (or Canada-U.S.) story with a report that is a major newsroom's own scoop or interview ("exclusive", ": sources", "sources say", "has learned", "documents obtained"...). It doesn't matter whether other newsrooms are already covering the story.
- **Cite the source:** the exclusive becomes the headline and link, its report goes first, and the story is labelled "Exclusive · CTV News". Credit goes to the newsroom that broke it (the first one, within a day); newsrooms that confirm it later are listed as confirming it. A CTV report run on CP24 is credited to CTV News.
- **Close to the top, if not the top:** rule 4 of `TOP_RULES`. It leads unless there are bigger stories (event day, the story every front page leads with, Canadian breaking news, a big international story, breaking news from abroad).
- `exclusive_inside()` in `tools/autopilot.py`; checks: `python3 tools/test_story_match.py`.

## Clear clock labels (Hannah, Wed Nov 11, 2026)

"Looking at the times across, like St. John's, Halifax, Ottawa, Winnipeg ... the bottom descriptors, I like having them there, but they're not clear enough." Each clock used to show one word picked from the headlines, which was often unclear ("Kilam") or wrong ("Police" on a Remembrance Day story, "Fire" on the Nvidia story). Each clock now shows its story's own headline, shortened at a word break (`clock_label()` in tools/autopilot.py), with the newsroom's name under it, at most three lines. The whole clock is still one tap to the story. Sports stories with a Canadian team's full name ("Edmonton Elks") or coaching news no longer reach the clocks or the top.

## Section pages (Hannah, Thu Nov 12, 2026)

"When you click on a specific section, it would probably be better to go to a new page rather than scroll down." A tap on a section in the menu (the main menu or the bar that follows you down the page) now opens that section as its own page, at the top of the screen, with its own address that can be shared or bookmarked (for example `#/canada`, `#/politics`, `#/most-read`, `#/watch`). The page shows a "← Front page" link and the section's name; Back, "Front page" or the bottom link return to the front page where the reader left it, and "Top stories" or the logo go to the top of it. The section keeps updating as usual, and the "New update" button keeps the reader on the same section page. Nothing is removed: the front page is exactly as before, and other links on the page (a story's report count, How this developed, a Breakdown entry) still move within the page. The code is in `index.html` between `<!-- secpage:start -->` and `<!-- secpage:end -->` (a copy in `tools/section_pages_layer.html`).
