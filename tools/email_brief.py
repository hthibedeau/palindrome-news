#!/usr/bin/env python3
"""The Daily Brief as it lands in a reader's inbox (Hannah, Nov 11, 2026: "If you get the daily brief in your
inbox, what will it look like?").

Reads live/auto.json (the same data the homepage runs on) and writes email-preview.html: one email, built the way
email programs need it (tables and inline styles, no scripts, absolute image addresses), so the same file can be
sent as-is once sign-ups open. Every tap goes straight to the outlet's own story. Hard paywalls go after the free
reports. No game stories. Nothing repeats between sections.

Run: python3 tools/email_brief.py [--data live/auto.json] [--out email-preview.html]
"""
import argparse, html, json, re
from datetime import datetime
from zoneinfo import ZoneInfo

SITE = "https://hthibedeau.github.io/palindrome-news/"
WINE, PLUM, INK, BODY, MUTED, RULE, SOFT = "#7A1F3D", "#4B2A7B", "#211A33", "#433A5E", "#6B6485", "#E4DDEE", "#F6F2FA"
PAYWALL = ("subscribers", "globe and mail", "wall street journal", "wsj", "bloomberg.com", "new york times", "washington post", "the logic", "the hill times")
SPORTS = re.compile(r"\b(nhl|nba|nfl|mlb|cfl|mls|goalie|playoff|hat trick|touchdown|trade demand|world junior|hellebuyck|blue jays|maple leafs|oilers|canucks|jets|raptors)\b", re.I)
STOP = set("the a an of to in on for and or as at by with from is are be after over its it his her their says say new will".split())


def esc(s):
    return html.escape(s or "", quote=True)


def words(s):
    return {w for w in re.findall(r"[a-z']{3,}", (s or "").lower()) if w not in STOP}


def same_story(a, b):
    wa, wb = words(a), words(b)
    common = wa & wb
    return bool(wa and wb) and len(common) >= 3 and len(common) / min(len(wa), len(wb)) >= 0.5


def paid(name, url=""):
    t = f"{name} {url}".lower()
    return any(p in t for p in PAYWALL)


def img_url(p):
    if not p:
        return ""
    return p if p.startswith("http") else SITE + p.lstrip("/")


def a(url, text, style=""):
    return f'<a href="{esc(url)}" target="_blank" style="color:inherit;text-decoration:none;{style}">{text}</a>'


def section(title, inner, kicker=""):
    k = f'<div style="font:600 11px/1 Arial,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:{WINE};margin:0 0 6px">{esc(kicker)}</div>' if kicker else ""
    return (f'<tr><td style="padding:26px 28px 6px">{k}'
            f'<h2 style="margin:0 0 12px;font:700 21px/1.2 Georgia,serif;color:{INK};border-bottom:2px solid {INK};padding-bottom:8px">{esc(title)}</h2>'
            f'{inner}</td></tr>')


def item(url, head, meta="", dek=""):
    d = f'<div style="font:15px/1.45 Georgia,serif;color:{BODY};margin-top:3px">{esc(dek)}</div>' if dek else ""
    m = f'<div style="font:600 12px/1.4 Arial,sans-serif;color:{MUTED};margin-top:4px">{meta}</div>' if meta else ""
    return (f'<div style="padding:11px 0;border-bottom:1px solid {RULE}">'
            f'<div style="font:700 16px/1.3 Georgia,serif;color:{INK}">{a(url, esc(head))}</div>{d}{m}</div>')


def sources(reports, skip_url, n=5):
    seen, free, pay = set(), [], []
    for r in reports:
        o = r.get("outlet", "")
        if not o or o in seen or r.get("url") == skip_url:
            continue
        seen.add(o)
        (pay if paid(o, r.get("url", "")) else free).append(r)
    out = (free + pay)[:n]
    return " · ".join(a(r["url"], esc(r["outlet"] + (" (subscribers)" if paid(r["outlet"], r["url"]) and "subscribers" not in r["outlet"] else "")),
                        f"color:{PLUM};text-decoration:underline") for r in out)


def story_card(s, angle, first):
    photo = s.get("photo") or {}
    pic = img_url(photo.get("src") or photo.get("orig"))
    tag = s.get("tag") or "Top story"
    excl = any(r.get("exclusive") for r in s.get("reports", []))
    lead_outlet = next((r["outlet"] for r in s.get("reports", []) if r.get("url") == s.get("url")), s.get("outlet") or (photo.get("outlet") or ""))
    badge_bg = WINE if tag.lower() == "breaking" else PLUM
    badges = f'<span style="background:{badge_bg};color:#fff;font:700 11px/1 Arial,sans-serif;letter-spacing:.12em;text-transform:uppercase;padding:5px 8px">{esc(tag)}</span>'
    if excl:
        badges += f' <span style="border:1px solid {WINE};color:{WINE};font:700 11px/1 Arial,sans-serif;letter-spacing:.12em;text-transform:uppercase;padding:4px 7px">Exclusive · {esc(lead_outlet)}</span>'
    out = '<div style="padding:4px 0 18px;border-bottom:1px solid %s">' % RULE
    if pic:
        h = 300 if first else 200
        out += (a(s["url"], f'<img src="{esc(pic)}" alt="{esc(photo.get("alt") or s["title"])}" width="544" style="display:block;width:100%;max-width:544px;height:{h}px;object-fit:cover;border:0">')
                + f'<div style="font:11px/1.4 Arial,sans-serif;color:{MUTED};margin:5px 0 10px">Photo: {esc(photo.get("outlet") or lead_outlet)}</div>')
    out += f'<div style="margin:4px 0 8px">{badges}</div>'
    size = 26 if first else 20
    out += f'<div style="font:700 {size}px/1.2 Georgia,serif;color:{INK}">{a(s["url"], esc(s["title"]))}</div>'
    if s.get("summary"):
        out += f'<div style="font:16px/1.5 Georgia,serif;color:{BODY};margin-top:8px">{esc(s["summary"])}</div>'
    n = s.get("outlets") or len(s.get("reports", []))
    src = sources(s.get("reports", []), s["url"])
    out += (f'<div style="font:600 12px/1.6 Arial,sans-serif;color:{MUTED};margin-top:10px">'
            f'{esc(lead_outlet)}{" · " + str(n) + " newsrooms reporting" if n and n > 1 else ""}'
            f'{"<br>Also reporting: " + src if src else ""}</div>')
    if angle:
        rows = "".join(f'<div style="font:15px/1.4 Georgia,serif;color:{INK};margin-top:4px">'
                       f'{a(x["url"], esc(x["title"]))} <span style="font:600 12px Arial,sans-serif;color:{MUTED}">· {esc(x["outlet"])}</span></div>'
                       for x in angle[:2])
        out += (f'<div style="margin-top:12px;padding:10px 12px;background:{SOFT};border-left:3px solid {WINE}">'
                f'<div style="font:italic 700 15px/1 Georgia,serif;color:{WINE};margin-bottom:4px">The Canadian angle</div>{rows}</div>')
    return out + "</div>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="live/auto.json")
    ap.add_argument("--out", default="email-preview.html")
    args = ap.parse_args()
    d = json.load(open(args.data, encoding="utf-8"))

    et = ZoneInfo("America/Toronto")
    try:
        when = datetime.fromisoformat(d["checked"]).astimezone(et)
    except Exception:
        when = datetime.now(et)
    edition = "Morning edition" if when.hour < 12 else "Evening edition"
    dateline = when.strftime("%A, %B ") + str(when.day)
    used = []  # headlines already in the email, so nothing repeats

    def fresh(title):
        if any(same_story(title, u) for u in used):
            return False
        used.append(title)
        return True

    def take(items, n, key):
        out = []
        for x in items:
            if len(out) >= n:
                break
            if fresh(key(x)):
                out.append(x)
        return out

    rows = []
    # 1. Top stories, as the homepage leads them
    stories = [s for s in (d.get("auto") or {}).get("stories", []) if s.get("url") and not SPORTS.search(s.get("title", ""))][:3]
    cards = ""
    for i, s in enumerate(stories):
        used.append(s["title"])
        for r in s.get("reports", []):
            used.append(r.get("title", ""))
        ang = ((d.get("canangle") or {}).get(s.get("key")) or {}).get("stories", [])
        ang = [x for x in ang if x.get("url")]
        for x in ang:
            used.append(x.get("title", ""))
        cards += story_card(s, ang, i == 0)
    if cards:
        rows.append(section("Top stories", cards, kicker=f"{edition} · {when.strftime('%-I:%M %p').lower().replace('am','a.m.').replace('pm','p.m.')} ET"))

    # 2. Also leading Canada's front pages
    leads = take((l for l in d.get("leads", []) if l.get("url") and not SPORTS.search(l["title"])), 4, lambda l: l["title"])
    if leads:
        rows.append(section("Also leading the front pages", "".join(
            item(l["url"], l["title"], " · ".join([f'{l.get("outlets", 0)} newsrooms'] + [esc(w) for w in l.get("why", [])[:2]])) for l in leads)))

    # 3. Across Canada, east to west as the regions come
    ca = take((c for c in d.get("canada", []) if c.get("url") and not SPORTS.search(c["title"])), 6, lambda c: c["title"])
    if ca:
        rows.append(section("Across Canada", "".join(
            item(c["url"], c["title"], f'<span style="color:{WINE}">{esc(c.get("region", ""))}</span> · {esc(c.get("outlet", ""))} · {esc(c.get("t", ""))}') for c in ca)))

    # 4. Smaller newsrooms, top five of the day
    sm = take((s for s in d.get("smaller", []) if s.get("u")), 5, lambda s: s["h"])
    if sm:
        rows.append(section("Smaller newsrooms", "".join(
            item(s["u"], s["h"], f'<b style="color:{PLUM}">{esc(s["o"])}</b> · {esc(s.get("region", ""))}{" · North" if s.get("arctic") else ""}') for s in sm),
            kicker="Today’s top five"))

    # 5. Canada and the U.S.
    cu = d.get("canus") or {}
    cu_items = take((x for x in cu.get("talks", []) if x.get("url")), 3, lambda x: x["title"])
    us_items = take((x for x in cu.get("usmedia", []) if x.get("url")), 2, lambda x: x["title"])
    if cu_items or us_items:
        inner = "".join(item(x["url"], x["title"], f'{esc(x["outlet"])} · {esc(x.get("t", ""))}') for x in cu_items)
        if us_items:
            inner += f'<div style="font:italic 700 15px Georgia,serif;color:{WINE};margin:14px 0 0">How U.S. media see Canada</div>'
            inner += "".join(item(x["url"], x["title"], f'{esc(x["outlet"])} · {esc(x.get("t", ""))}') for x in us_items)
        rows.append(section("Canada and the U.S.", inner))

    # 6. Most read across Canada (no game stories)
    mr = take((m for m in (d.get("mostread") or {}).get("list", []) if m.get("u") and not SPORTS.search(m["h"])), 5, lambda m: m["h"])
    if mr:
        rows.append(section("Most read across Canada", "".join(
            f'<div style="padding:9px 0;border-bottom:1px solid {RULE};font:700 15px/1.35 Georgia,serif;color:{INK}">'
            f'<span style="color:{WINE};font:700 18px Georgia,serif;margin-right:8px">{i}</span>{a(m["u"], esc(m["h"]))}'
            f' <span style="font:600 12px Arial,sans-serif;color:{MUTED}">· {esc(m["o"][0][0] if m.get("o") else "")}</span></div>'
            for i, m in enumerate(mr, 1))))

    # 7. Opinion: the day's best, free ones first
    eds = [e for e in d.get("eds", []) if len(e) >= 4 and "clarification" not in e[2].lower() and "correction" not in e[2].lower()]
    eds = sorted(eds, key=lambda e: paid(e[0], e[3]))[:4]
    if eds:
        rows.append(section("Opinion from across the country", "".join(
            item(e[3], e[2], f'<b style="color:{PLUM}">{esc(e[0])}</b> · {esc(e[1])}') for e in eds)))

    # 8. Coming up
    bw = [b for b in d.get("bigweek", []) if b.get("reports")][:3]
    if bw:
        rows.append(section("Coming up", "".join(
            item(b["reports"][0]["url"], b["reports"][0]["title"],
                 f'<span style="color:{WINE}">{esc(b["name"])} · {"in " + str(b["days"]) + " days" if b.get("days") else esc(b.get("date", ""))}</span> · {esc(b["reports"][0]["outlet"])}')
            for b in bw)))

    # Listen bar: the 60-second brief in Hannah's voice
    listen = ""
    try:
        vb = json.load(open("live/brief.json", encoding="utf-8"))
        if vb.get("audio"):
            listen = (f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PLUM}"><tr>'
                      f'<td style="padding:14px 16px;font:700 15px/1.3 Georgia,serif;color:#fff">{a(SITE + vb["audio"], "&#9654;&nbsp; Listen to the 60-second brief")}'
                      f'<div style="font:12px/1.4 Arial,sans-serif;color:#E6DDF5;margin-top:3px">In Hannah’s voice · {esc(vb.get("edition", ""))}</div></td></tr></table></td></tr>')
    except Exception:
        pass

    preheader = " · ".join(s["title"] for s in stories[:2])
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Daily Brief · {esc(edition)} · {esc(dateline)}</title>
<style>body{{margin:0;padding:0;background:#EEE9F4}} a:hover{{text-decoration:underline!important}} @media (max-width:620px){{.wrap{{width:100%!important}} td{{padding-left:18px!important;padding-right:18px!important}}}}</style>
</head><body style="margin:0;background:#EEE9F4">
<div style="display:none;max-height:0;overflow:hidden">{esc(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEE9F4"><tr><td align="center" style="padding:24px 10px">
<table role="presentation" class="wrap" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px;background:#fff">
<tr><td style="padding:22px 28px 0;font:12px/1.4 Arial,sans-serif;color:{MUTED}">
  <table role="presentation" width="100%"><tr><td>From Hannah Thibedeau, editor</td><td align="right">{a(SITE, "Read on the site", f"color:{PLUM};text-decoration:underline")}</td></tr></table></td></tr>
<tr><td align="center" style="padding:20px 28px 4px">
  <div style="font:700 40px/1 Georgia,serif;color:{INK};letter-spacing:-.01em">{a(SITE, "Palindrome News")}</div>
  <div style="font:600 11px/1 Arial,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:{BODY};margin-top:12px">News from every direction.</div>
  <div style="font:italic 15px/1.4 Georgia,serif;color:{WINE};margin-top:8px">Your personal newsroom. See it all and go straight to the source.</div></td></tr>
<tr><td style="padding:16px 28px 18px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:3px double {INK};border-bottom:1px solid {INK}"><tr>
  <td style="padding:9px 0;font:700 13px/1 Georgia,serif;color:{INK}">The Daily Brief · {esc(edition)}</td>
  <td align="right" style="padding:9px 0;font:13px/1 Georgia,serif;color:{BODY}">{esc(dateline)}</td></tr></table></td></tr>
{listen}
{''.join(rows)}
<tr><td style="padding:28px;background:{INK};color:#D8D0E8;font:13px/1.6 Arial,sans-serif">
  <div style="font:700 18px Georgia,serif;color:#fff">Palindrome News</div>
  <div style="margin-top:4px">Chosen by editor Hannah Thibedeau. Every link goes straight to the newsroom that reported it.</div>
  <div style="margin-top:12px">Out twice a day, at 7 a.m. and 5 p.m. ET, and whenever news breaks.</div>
  <div style="margin-top:12px">{a(SITE, "Read the live front page", "color:#fff;text-decoration:underline")} &nbsp;·&nbsp; <span style="color:#A99FC0">Unsubscribe</span> &nbsp;·&nbsp; <span style="color:#A99FC0">Update preferences</span></div>
  <div style="margin-top:12px;font-size:11px;color:#A99FC0">Toronto, Canada · Built from live/auto.json, checked {esc(d.get("checkedLabel", ""))} ET</div></td></tr>
</table></td></tr></table></body></html>
"""
    open(args.out, "w", encoding="utf-8").write(doc)
    print(f"wrote {args.out}: {len(stories)} top stories, {len(rows)} sections")


if __name__ == "__main__":
    main()
