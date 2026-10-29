#!/usr/bin/env python3
"""Tap check: every outlet button and label must open that outlet's own page (Hannah, Wed Oct 28, 2026:
"make sure this doesn't happen again. I need the links to always go to the right page").

    python3 tools/tap_check.py --install                # copy tools/tap_guard.js into index.html (between the markers)
    python3 tools/tap_check.py --page index.html        # tap everything at phone and desktop width, write live/taps.json

The check opens the page in a real browser (Chromium, through Playwright), at 390 and 1280 wide. For every element on the
page whose label names an outlet ("CBC News", "The Canadian Press via CP24", "Watch live on CTV News", an outlet chip, a
source line), it finds what a tap on that spot would really open (the element under the finger, so a card's stretched
headline link counts) and checks that it is that outlet's site. It uses the page's own tap guard (window.PAL_tap), so
the browser and this check judge by the same rules.

It writes live/taps.json: {checked, problems: [...], guard: {fixed, disabled, lifted}}. Problems are printed as GitHub
error annotations. Exit code 1 when a tap still goes to the wrong outlet (with --strict); otherwise 0, so a news update
is never held back. The guard in the page already stops a wrong tap for readers; this check proves it.
"""
import argparse
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
START, END = "<!-- PAL-TAP-GUARD:START -->", "<!-- PAL-TAP-GUARD:END -->"

PROBE = r"""async () => {
  const T = window.PAL_tap; if (!T) return { error: 'tap guard missing from the page' };
  T.run();
  const out = [], seen = new Set();
  const els = [...document.querySelectorAll('a, span, b, strong, small, em, i, cite, p, div, li, button')].filter((el) => {
    if (el.closest('[hidden]') || el.closest('a[aria-hidden="true"]') || el.closest('#srcList') || el.closest('.credit, figcaption, .ph, [data-credit]')) return false; // a photo credit names who took the picture, not where a tap goes
    const kids = [...el.children].filter((k) => k.textContent.trim());
    if (el.tagName !== 'A' && kids.length) return false;
    return T.outletsOf(el.tagName === 'A' && !el.textContent.trim() ? el.getAttribute('aria-label') : el.textContent);
  });
  for (const el of els) {
    const rs = el.getClientRects(); if (!rs.length) continue;
    el.scrollIntoView({ block: 'center', behavior: 'instant' });
    const r = el.getClientRects()[0]; if (!r || r.width < 2 || r.height < 2) continue;
    const x = r.left + Math.min(r.width / 2, 12), y = r.top + r.height / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
    const hit = document.elementFromPoint(x, y); if (!hit) continue;
    // What a tap there opens: the link under the finger, which may be a card's headline link stretched over the label.
    const a = hit.closest('a[href]');
    if (!a) continue;                                                     // nothing opens: fine
    if (!(el === hit || el.contains(hit) || hit.contains(el)) && !a.contains(el)) {
      const s = getComputedStyle(a, '::after');                           // a stretched card link covering the label
      if (!(s.position === 'absolute' && s.content !== 'none' && s.content !== 'normal')) continue; // another layer (e.g. the header)
    }
    const label = (el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    // the label is the link itself: judge the link; a label under someone else's link: that link must fit the label
    const ok = (a === el || a.contains(el)) ? T.labelOk(label, a.getAttribute('href')) : T.fits(T.outletsOf(label), a);
    const key = label + '|' + a.href; if (seen.has(key)) continue; seen.add(key);
    if (ok === false) out.push({ label, opens: a.href, section: (el.closest('section[id]') || {}).id || '', link: a === el || el.contains(a) });
  }
  return { problems: out, checked: els.length, guard: T.report };
}"""


def install(page):
    js = open(os.path.join(HERE, "tap_guard.js"), encoding="utf-8").read()
    html = open(page, encoding="utf-8").read()
    block = f"{START}\n<script>\n{js}</script>\n{END}"
    if START in html:
        html = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: block, html, flags=re.S)
    else:
        html = html.replace("</body>", block + "\n</body>", 1)
    open(page, "w", encoding="utf-8").write(html)
    print("tap guard installed in", page)


def check(page, widths, wait):
    from playwright.sync_api import sync_playwright
    root = os.path.dirname(os.path.abspath(page))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(type("Q", (SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory=root))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/{os.path.basename(page)}"
    results = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in widths:
            pg = b.new_page(viewport={"width": w, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
            pg.goto(url, wait_until="load", timeout=120000)
            pg.wait_for_timeout(wait)
            r = pg.evaluate(PROBE)
            r["page_errors"] = errors[:5]
            results[w] = r
            pg.close()
        b.close()
    srv.shutdown()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--out", default="live/taps.json")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--wait", type=int, default=6000)
    a = ap.parse_args()
    if a.install:
        install(a.page)
        return
    res = check(a.page, (390, 1280), a.wait)
    problems, guard, checked = [], {}, 0
    for w, r in res.items():
        if r.get("error"):
            print(f"::error::{r['error']}")
            problems.append({"width": w, "label": "(page)", "opens": r["error"]})
            continue
        checked = max(checked, r["checked"])
        guard = r["guard"]
        for x in r["problems"]:
            x["width"] = w
            problems.append(x)
    out = {"checked": datetime.now(timezone.utc).isoformat(), "labels": checked, "problems": problems,
           "guard": {k: guard.get(k, []) for k in ("fixed", "disabled", "lifted")}}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"tap check: {checked} outlet labels, {len(problems)} wrong taps; guard fixed {len(out['guard']['fixed'])}, "
          f"unlinked {len(out['guard']['disabled'])}, lifted {len(out['guard']['lifted'])}")
    for x in problems:
        print(f"::error::Wrong tap ({x['width']} wide, {x.get('section','')}): “{x['label']}” opens {x['opens']}")
    for x in out["guard"]["fixed"] + out["guard"]["disabled"]:
        print("  guard:", json.dumps(x, ensure_ascii=False)[:220])
    if a.strict and problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
