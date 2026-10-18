#!/usr/bin/env python3
"""Get a picture for any story, post or video link.

1. Open the page and use its own share image (og:image / twitter:image) if it has one.
2. If it has none, or the image will not download, take a screen grab of the top of
   the page in a headless browser (cookie banners closed where possible).

Either way the result is a 1200px-wide JPEG ready to store with the Palindrome page.
Only works for sites approved in claude.ai Settings > Capabilities > Allow network egress;
for any other site it prints the exact host name to approve.

Usage: python3 tools/grab_picture.py <page url> <out.jpg> [--grab]   (--grab forces a screen grab)
"""
import io
import re
import subprocess
import sys
from urllib.parse import urljoin, urlparse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def curl(url: str) -> bytes | None:
    r = subprocess.run(["curl", "-sS", "-L", "--max-time", "30", "-A", UA, url], capture_output=True)
    return r.stdout if r.returncode == 0 and r.stdout else None


def share_image(page_url: str, html: str) -> str | None:
    for prop in ("og:image", "twitter:image", "og:image:url"):
        m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']+)' % re.escape(prop), html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']%s["\']' % re.escape(prop), html, re.I)
        if m:
            return urljoin(page_url, m.group(1).replace("&amp;", "&"))
    return None


def to_jpeg(data: bytes, out: str) -> bool:
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return False
    if im.width < 200 or im.height < 120:
        return False
    im.thumbnail((1200, 1200))
    im.save(out, "JPEG", quality=84)
    return True


def screen_grab(url: str, out: str) -> bool:
    import asyncio
    from playwright.async_api import async_playwright

    async def run() -> bool:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page(viewport={"width": 1280, "height": 720}, user_agent=UA, device_scale_factor=1)
            try:
                resp = await pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                if not resp or resp.status >= 400:
                    return False
                await pg.wait_for_timeout(2500)
                for label in ("Accept", "Accept all", "I agree", "Agree", "OK", "Got it", "Close", "Continue"):
                    try:
                        btn = pg.get_by_role("button", name=re.compile("^" + label + "$", re.I))
                        if await btn.count():
                            await btn.first.click(timeout=1500)
                            await pg.wait_for_timeout(500)
                    except Exception:
                        pass
                png = await pg.screenshot(type="png")
            except Exception:
                return False
            finally:
                await b.close()
        return to_jpeg(png, out)

    return asyncio.run(run())


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        return
    url, out, force = sys.argv[1], sys.argv[2], "--grab" in sys.argv
    page = curl(url)
    if page is None:
        print("BLOCKED", urlparse(url).hostname)
        sys.exit(2)
    if not force:
        img = share_image(url, page.decode("utf-8", "ignore"))
        if img:
            data = curl(img)
            if data and to_jpeg(data, out):
                print("SHARE_IMAGE", img)
                return
            if data is None:
                print("NOTE image host blocked:", urlparse(img).hostname)
    if screen_grab(url, out):
        print("SCREEN_GRAB", url)
        return
    print("FAILED", url)
    sys.exit(1)


if __name__ == "__main__":
    main()
