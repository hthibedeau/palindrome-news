#!/usr/bin/env python3
"""Get the front page of a think-tank paper or white paper.

1. Open the paper's page in a headless browser and look for the paper's PDF
   (links ending in .pdf, preferring the main report over news releases,
   presentations, summaries or French versions).
2. Download the PDF and render page 1 (the cover) as a JPEG, 900px tall.
3. If there is no PDF (web-only memos and briefs), fall back to a screen grab of
   the top of the paper's own page.

Usage: python3 tools/paper_cover.py <paper page url> <out.jpg> [--pdf <direct pdf url>]
Prints one of:
  COVER_OK <pdf url>      front page of the PDF saved to out.jpg
  GRAB_OK <page url>      no PDF found; screen grab of the page saved to out.jpg
  BLOCKED <host>          the site can't be reached from this workspace; allow the
                          host in claude.ai Settings > Capabilities
  FAILED <reason>
Always exits 0.
"""
import asyncio
import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
SKIP = re.compile(r"news.?release|presentation|summary|highlights|infographic|appendix|backgrounder|-fr[._-]|french|francais|sommaire|errata", re.I)
HERE = os.path.dirname(os.path.abspath(__file__))


def blocked(err):
    return any(k in str(err) for k in ("ERR_TUNNEL_CONNECTION_FAILED", "ERR_PROXY", "403", "ERR_CONNECTION", "ERR_NAME_NOT_RESOLVED"))


async def find_and_get_pdf(url, pdf_hint):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(user_agent=UA)
        pdfs = [pdf_hint] if pdf_hint else []
        if not pdf_hint:
            pg = await ctx.new_page()
            try:
                await pg.goto(url, timeout=60000)
                await pg.wait_for_timeout(2500)
            except Exception as e:
                await b.close()
                return ("BLOCKED", urlparse(url).hostname) if blocked(e) else ("FAILED", str(e)[:200])
            links = await pg.evaluate("[...document.querySelectorAll('a')].map(a => [a.href, (a.textContent || '').trim()])")
            cands = [h for h, t in links if re.search(r"\.pdf(\?|#|$)", h, re.I)]
            cands += [h for h, t in links if re.search(r"download|read the (full )?(report|paper|study)|full (report|paper|study)", t, re.I) and h not in cands]
            seen = []
            for h in cands:
                if h not in seen:
                    seen.append(h)
            pdfs = [h for h in seen if not SKIP.search(h)] + [h for h in seen if SKIP.search(h)]
        for h in pdfs[:4]:
            try:
                r = await ctx.request.get(h, timeout=120000)
            except Exception as e:
                if blocked(e):
                    await b.close()
                    return ("BLOCKED", urlparse(h).hostname)
                continue
            body = await r.body()
            if not (r.ok and body[:5] == b"%PDF-"):
                # some sites answer a browsing session with a check page; a clean request often gets the file
                try:
                    fresh = await b.new_context(user_agent=UA)
                    r = await fresh.request.get(h, timeout=120000)
                    body = await r.body()
                    await fresh.close()
                except Exception:
                    pass
            if r.ok and body[:5] == b"%PDF-":
                await b.close()
                return ("PDF", (h, body))
        await b.close()
        return ("NOPDF", None)


def main():
    if len(sys.argv) < 3:
        return print(__doc__)
    url, out = sys.argv[1], sys.argv[2]
    hint = sys.argv[sys.argv.index("--pdf") + 1] if "--pdf" in sys.argv else None
    kind, val = asyncio.run(find_and_get_pdf(url, hint))
    if kind in ("BLOCKED", "FAILED"):
        return print(kind, val)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if kind == "PDF":
        pdf_url, body = val
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "p.pdf")
            open(f, "wb").write(body)
            r = subprocess.run(["pdftoppm", "-f", "1", "-l", "1", "-scale-to-y", "900", "-scale-to-x", "-1", "-jpeg", "-jpegopt", "quality=82", f, os.path.join(d, "c")], capture_output=True)
            imgs = [x for x in os.listdir(d) if x.startswith("c") and x.endswith(".jpg")]
            if r.returncode == 0 and imgs:
                os.replace(os.path.join(d, imgs[0]), out)
                return print("COVER_OK", pdf_url)
    # No PDF: screen grab of the paper's own page
    r = subprocess.run([sys.executable, os.path.join(HERE, "grab_picture.py"), url, out, "--grab"], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or ["FAILED no output"])[-1]
    if last.startswith("SCREEN_GRAB"):
        return print("GRAB_OK", url)
    print(last)


if __name__ == "__main__":
    main()
