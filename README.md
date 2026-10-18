# Palindrome Newsroom

News from every direction. One clear perspective.

Palindrome Newsroom is an online newsroom for people who get their news online instead of on TV. It summarizes the day's stories from trusted outlets, always links to the original reporting, and never publishes its own editorials.

Founded and edited by Hannah Thibedeau.

## What's here

| File | What it is |
| --- | --- |
| `index.html` | The homepage preview: newspaper-style nameplate, a compact bar that follows you down the page, breaking news with what we know and a confirmation tracker, a live wire, a Late edition stamp after 10 p.m., a wall of clocks for the cities in the news, a story board of everything in progress, a 60-second read-aloud brief, a corrections and updates log, editor screenshot uploads on post and video cards, The breakdown (a full reporter's synopsis for every story verified by six or more independent outlets), breaking news with two accounts and a timeline, a From every direction comparison, a Watch strip of the day's video, The Editor's Read (a signed analysis with What to watch), "Why it matters" lines, desk-by-desk section fronts with a six-source meter on every story, a United States section with a midterms countdown and what America's newsrooms are leading with, Most read across Canada, Today's reading, On the record, Editorials, Think tanks, Go deeper, and sponsor sections. |
| `editors-desk.html` | The Editor's Desk preview, where the editor reviews, publishes, hides and ranks stories and manages sources. It runs on sample data; nothing is saved. |

Both pages open directly in a web browser. They are previews: the live site will need a server that gathers the news, checks sources and serves the Editor's Desk.

## House rules

- Every summary is built from at least six independent, trusted sources, with links attached.
- Tapping a story takes the reader straight to the original article.
- Breaking news can run with credit to the outlet that reported it, and takes over the top of the homepage.
- Sponsors pay for the site but never choose or rank the news. Paid editorials are always labelled.

## Photos on the preview link

The claude.ai preview blocks images hosted on other websites, so outlet photos are copied into the page's own storage. `tools/localize_images.py index.html <folder>` downloads every photo it can reach and lists the exact host names still to approve under claude.ai Settings > Capabilities > Allow network egress. The page tries the stored copy first, then the outlet's original, then a drawn illustration.
