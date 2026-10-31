# Palindrome News

News from every direction. One clear perspective.

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

## A lighter front page (Hannah, Sat Oct 31, 2026)

Hannah: "there's too much on it." `tools/trim_layer.html` (copied into the end of `index.html`) keeps the front page short by itself, on every load and every update. The settings are `PAL_TRIM` at the top of its script:

- **Their own pages.** Corrections & updates, Story board and How each story developed are off the front page. Each opens on its own at `index.html?view=corrections`, `?view=board` and `?view=developed`, linked from the footer. The Story board is out of the top menu.
- **Capped.** The day so far shows its 5 stories nearest to six sources, with "See all" (`?view=day`). Think tanks & white papers shows its 3 newest papers, with "See all" (`?view=thinktanks`).
- **One "Coming up".** The big week ahead, Coming up live (taken out of the Live coverage band) and the What to watch dates are one section above the Canada desk. Dates already in the big week ahead are not repeated. The 60-second brief stays where it was, under the heading "Listen".

## News judgment: is this the top story? (Hannah, Sat Oct 31, 2026)

Before ranking, the code asks the question an editor asks at the morning meeting: who is this story for? It answers it from what the newsrooms themselves published (`news_judgment()` in `tools/autopilot.py`, explained in full in the NEWS JUDGMENT note above it).

1. **How many people does it affect?** Many: Ottawa or a province, the economy, prices, trade, Canada in the world, elections, strikes, health care, housing, the military, disasters, or a tragedy with many victims. Few: a single crime, arrest, court date, crash or fire.
2. **How many people will want to read it?** It counts the national desks carrying it and how many cities' newsrooms chose to run it. A story only on one city's local desks is a story for that city.

A story that touches few people and is read in one city is **Local**. It stays in the Canada desk and the other sections, but it is never a top story. A story that scores high on both is **National** and gets a lift. Each candidate's verdict and the reason are in `live/auto.json` under "considered".

Example: "Toronto man identified as suspect in Bridle Path home invasion" (one crime, Toronto desks only) is Local. "Canada-EU associate membership talks" (Canada's trade and place in the world, in newsrooms in seven cities) is National, and the top story.

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
