# Autoupdate: the page keeps itself current between runs

Hannah, Wed Oct 21, 2026: "I need the program to continually scan for the latest news" and "you have not kept the page up to date. I want you to create a code that does this."

## What runs, and when
- **GitHub Actions, every 10 minutes:** `.github/workflows/autoupdate.yml` runs `tools/autoupdate.py`. It writes `live/auto.json` (and photos in `live/img/`), then commits and pushes. GitHub's scheduler can run a few minutes late; it can also be run by hand from the Actions tab ("Auto update" > Run workflow).
- **The page, every 2 minutes:** a script at the end of `index.html` fetches `live/auto.json`. It tries our own site first, then raw.githubusercontent.com, and uses whichever is newer. It ignores the file if it is over 3 hours old.

## What it changes on the page by itself
1. **Newest reports, under each Breaking/Developing story's summary.** It lists every report on the story that is newer than the story's last development and not linked on the page yet: real time, headline and outlet, up to 6. The box reads "Newest reports · checked automatically h:mm ET".
2. **Photo.** It uses the newest photo on the story with the outlet's own caption and credit, using the same rules as `auto_photo.py`:
   - at least 900 px wide;
   - not a file or archive photo;
   - dated within 2 days;
   - caption about this story;
   - no handout campaign video.
3. **The latest (wire).** Newer headlines go to the top, exactly as each outlet wrote them. A story qualifies when 2 or more newsrooms carry it, or a national desk does. Opinion, sports, lifestyle and local-only stories are left out, and so is anything already on the page.
4. **Live blogs.** It reads each LIVENOW blog's real newest-post time (dateModified), so an active blog keeps showing.
5. **A Developing story stays up while news keeps coming.** An event past its keep window stays on the page while autoupdate finds 2 or more new reports on it in the last 6 hours.

Never listed: The Globe and Mail (subscribers), Yahoo links other than The Canadian Press, X/Instagram/LinkedIn, French-language outlets (English page).

## What the agent runs still do (full update, live check)
- **Read the "Newest reports" on each story** (`python3 tools/autoupdate.py --no-photos` locally, or the box on the page). Write the new facts into the timeline, summary and headline, and set `data-lastdev`. Once the page links a report, the box drops it.
- **When the auto photo is good, make it permanent.** Copy it from `live/img/` to `img/live/`, set the photo fields and `data-photo-set`/`photoSet`, and keep the old photo as a fallback (`auto_photo.py --apply` does this). Then upload it to the preview.
- **Check the workflow is running.** On GitHub, the Actions tab > "Auto update" should show runs every ~10 minutes. If `checked` in `live/auto.json` is over 30 minutes old, say so in the summary and fix it.
6. **What should lead.** The `leads` list ranks the top 10 stories, using `tools/lead_check.py`: National Newswatch order, CBC front-page order and how many newsrooms carry each story. The agent runs use it to keep the two Breaking slots on the two biggest stories.
7. **Canada desk: today only.** The page shows only Canada stories whose own time is today (Eastern). Every 10 minutes `todays_canada()` adds up to 18 of today's regional stories, at most 2 per province or territory, each with the outlet's own summary and picture. Wire copy is placed by its dateline, and stories from outside Canada are left out. The lead is the story the most newsrooms carry. Agent runs still write the desk's own stories, and anything from an earlier day drops off by itself.
8. **The Canadian angle (Hannah, Wed Oct 28, 2026).** For each top story from another country (at least 40% of its reports run on world desks or foreign newsrooms, and its name isn't Canadian), `canadian_angle()` finds the newest reports that name the story and a Canadian tie (Canada, Canadians, Ottawa, Carney, Anand, Global Affairs, provinces and cities), one per network, up to 5, plus matching statements from the Prime Minister or the Government of Canada and Canada-focused editorials or think-tank papers. They go in `canangle` in `live/auto.json`; the page shows them in a red-leaf "The Canadian angle" sidebar on that story.
