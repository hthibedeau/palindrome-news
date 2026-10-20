#!/usr/bin/env python3
"""Put clips from news networks' official YouTube channels in Watch, with real pictures.

Started for CNN and CNBC (their own sites block automated reading), now used for any
network in OFFICIAL, including ones whose sites are blocked to us (BBC, Sky News, DW,
AP, Reuters, CityNews) and ones whose pictures don't load (CBC).

cnn.com and cnbc.com block automated reading, so their own video pages give us no
picture. Their official YouTube channels post the same reports, and YouTube's
thumbnails can be downloaded. This tool turns a checked YouTube upload into a Watch
clip with its picture.

The run (a person or a scheduled task) finds the clip and CHECKS it first:
  - WebSearch for this week's uploads, e.g. "CNN <today's top story> youtube" or
    "CNBC <market story> youtube" (allowed_domains youtube.com);
  - WebFetch the watch page and read the channel name and upload date it reports.
Then:

  1. Prepare (checks channel, date, duplicates; downloads the picture):
     python3 tools/network_youtube.py prepare <youtube url> --network CNN \
         --channel "CNN" --date 2026-10-18 --title "Plain headline" \
         [--region us|world|ca] [--midterms] [--life] [--when "Today"] [--dur 3:12]
     It prints PREPARED <json> with the picture's file path, or REFUSED <reason>.

  2. Upload the picture to the preview (Artifact tool, url
     https://claude.ai/artifact/3QyruwrVH2QoqZtUQYivag, asset: true, file_path = the
     printed file) and note the "/_blob/<id>" it returns.

  3. Apply (writes the clip into Watch and the picture into LOCAL):
     python3 tools/network_youtube.py apply index.html <the PREPARED json file> --blob /_blob/<id>

  5. Checked (EVERY run, full update and live check, after looking for new clips, even if
     none were added): python3 tools/network_youtube.py checked index.html
     It sets the "Clips checked <time> ET" line under the Watch heading. apply also sets it,
     and stamps each new clip with "added", so the page shows it first with a "New" badge for
     3 hours. Day labels ("Today", "Yesterday", "Oct 18") come from "up" on the page itself.

  4. Tidy (run once per update; removes network YouTube clips older than 7 days and
     keeps the newest 4 per network):
     python3 tools/network_youtube.py tidy index.html

Only official channels are accepted (see OFFICIAL). Never pass a channel name you
have not read on the watch page yourself.
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import tempfile

# Network name as shown on Palindrome -> the official YouTube channel names it posts under
OFFICIAL = {
    # U.S.
    "CNN": ["CNN"],
    "CNBC": ["CNBC Television", "CNBC", "CNBC International Live", "CNBC International TV", "CNBC Make It"],
    "NBC News": ["NBC News", "TODAY", "Meet the Press"],
    "ABC News": ["ABC News"],
    "CBS News": ["CBS News", "CBS Evening News", "CBS Mornings", "Face the Nation"],
    "PBS NewsHour": ["PBS NewsHour"],
    "Fox News": ["Fox News"],
    "C-SPAN": ["C-SPAN"],
    "Bloomberg": ["Bloomberg Television", "Bloomberg Originals"],
    "Associated Press": ["Associated Press"],
    "Reuters": ["Reuters"],
    # Canada
    "CBC News": ["CBC News", "CBC News: The National", "CBC Alberta", "CBC British Columbia", "CBC Manitoba", "CBC Toronto", "CBC Ottawa", "CBC Montreal", "CBC North", "CBC Saskatchewan", "CBC Nova Scotia", "CBC New Brunswick", "CBC Newfoundland and Labrador", "CBC PEI"],
    "CTV News": ["CTV News"],
    "Global News": ["Global News"],
    "CityNews": ["CityNews", "CityNews Toronto", "CityNews Calgary", "CityNews Edmonton", "CityNews Vancouver"],
    "CPAC": ["CPAC"],
    "CP24": ["CP24"],
    "APTN News": ["APTN News"],
    "TVO Today": ["TVO Today"],
    # World
    "BBC News": ["BBC News"],
    "Sky News": ["Sky News"],
    "DW News": ["DW News"],
    "Al Jazeera": ["Al Jazeera English"],
    "France 24": ["FRANCE 24 English"],
    "Euronews": ["euronews"],
    "ABC News (Australia)": ["ABC News (Australia)", "ABC News In-depth"],
    "CNA": ["CNA"],
    "NHK World": ["NHK WORLD-JAPAN"],
}
MAX_AGE_DAYS = 7
KEEP_PER_NETWORK = 4
INSERT_AT = 3  # clips go in after the first few, so they are seen without scrolling far
STAGE = os.path.join(tempfile.gettempdir(), "pn-youtube")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def video_id(url):
    m = ID_RE.search(url)
    return m.group(1) if m else None


def js_str(s):
    """A single-quoted JS string; straight apostrophes become curly ones (house style)."""
    s = s.replace("\\", "").replace("'", "’").replace("\n", " ").strip()
    return "'" + s + "'"


def eastern_today():
    out = subprocess.run(["bash", "-c", "TZ=America/Toronto date +%F"], capture_output=True, text=True).stdout.strip()
    return dt.date.fromisoformat(out)


def fetch(url):
    r = subprocess.run(["curl", "-sS", "-L", "--max-time", "30", "-A", UA, "-w", "\n%{http_code}", url], capture_output=True)
    if r.returncode != 0:
        return None, 0
    body, _, code = r.stdout.rpartition(b"\n")
    return body, int(code or 0)


def thumbnail(vid, out):
    """Best available YouTube still, saved as a 1280px-max JPEG. Skips YouTube's 120x90 'no picture' placeholder."""
    from PIL import Image
    for name in ("maxresdefault", "hq720", "sddefault", "hqdefault"):
        url = f"https://i.ytimg.com/vi/{vid}/{name}.jpg"
        data, code = fetch(url)
        if code != 200 or not data:
            continue
        try:
            im = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            continue
        if im.width <= 120:
            continue
        if name in ("sddefault", "hqdefault"):  # 4:3 with black bars: crop to 16:9
            h = round(im.width * 9 / 16)
            top = (im.height - h) // 2
            im = im.crop((0, top, im.width, top + h))
        im.thumbnail((1280, 720))
        im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
        return url
    return None


def prepare(a):
    vid = video_id(a.url)
    if not vid:
        return print("REFUSED not a YouTube video url:", a.url)
    if a.network not in OFFICIAL:
        return print("REFUSED network must be one of:", ", ".join(OFFICIAL))
    if a.channel not in OFFICIAL[a.network]:
        return print(f"REFUSED channel {a.channel!r} is not an official {a.network} channel ({', '.join(OFFICIAL[a.network])})")
    try:
        up = dt.date.fromisoformat(a.date)
    except ValueError:
        return print("REFUSED --date must be YYYY-MM-DD (the upload date shown on the watch page)")
    today = eastern_today()
    age = (today - up).days
    if age < 0 or age > MAX_AGE_DAYS:
        return print(f"REFUSED uploaded {a.date}, {age} days ago; Watch only takes clips from the last {MAX_AGE_DAYS} days")
    if a.index and os.path.exists(a.index) and f"u: 'https://www.youtube.com/watch?v={vid}'" in open(a.index, encoding="utf-8").read():
        return print("REFUSED already on the page:", vid)
    os.makedirs(STAGE, exist_ok=True)
    jpg = os.path.join(STAGE, f"{re.sub(r'[^a-z0-9]+', '-', a.network.lower()).strip('-')}-{vid}.jpg")
    img = thumbnail(vid, jpg)
    if not img:
        return print("REFUSED no picture could be downloaded from i.ytimg.com for", vid)
    when = a.when or ("Today" if age == 0 else up.strftime("%b ") + str(up.day))
    entry = {
        "r": a.region, "m": 1 if a.midterms else 0, "k": "life" if a.life else "",
        "o": a.network, "d": a.dur or "", "t": a.title.strip(), "w": when,
        "u": f"https://www.youtube.com/watch?v={vid}", "img": img, "pic": a.pic,
        "id": vid, "date": a.date, "channel": a.channel, "file": jpg,
    }
    spec = os.path.join(STAGE, f"{re.sub(r'[^a-z0-9]+', '-', a.network.lower()).strip('-')}-{vid}.json")
    json.dump(entry, open(spec, "w"), indent=1, ensure_ascii=False)
    print("PREPARED", spec)
    print(json.dumps(entry, ensure_ascii=False))
    print(f"Next: upload {jpg} to the artifact as an asset, then: python3 tools/network_youtube.py apply index.html {spec} --blob /_blob/<id>")


def vid_line(e):
    parts = [f"r: {js_str(e['r'])}"]
    if e.get("m"):
        parts.append("m: 1")
    if e.get("k"):
        parts.append(f"k: {js_str(e['k'])}")
    parts.append(f"o: {js_str(e['o'])}")
    if e.get("d"):
        parts.append(f"d: {js_str(e['d'])}")
    parts += [f"t: {js_str(e['t'])}", f"w: {js_str(e['w'])}", f"u: {js_str(e['u'])}", f"img: {js_str(e['img'])}",
              f"pic: {js_str(e.get('pic') or 'globe')}", f"up: {js_str(e['date'])}"]
    if e.get("added"):
        parts.append(f"added: {js_str(e['added'])}")
    return "    { " + ", ".join(parts) + " },\n"


def eastern_now_iso():
    return subprocess.run(["bash", "-c", "TZ=America/Toronto date +%Y-%m-%dT%H:%M:00%:z"], capture_output=True, text=True).stdout.strip()


def stamp(s):
    """Set VIDS_CHECKED (the "Clips checked" time shown in Watch) to now, Eastern."""
    return re.sub(r"const VIDS_CHECKED = '[^']*';", "const VIDS_CHECKED = '" + eastern_now_iso() + "';", s, count=1)


def checked(a):
    s = open(a.index, encoding="utf-8").read()
    if "const VIDS_CHECKED = '" not in s:
        return print("REFUSED could not find `const VIDS_CHECKED` in", a.index)
    open(a.index, "w", encoding="utf-8").write(stamp(s))
    print("CHECKED", eastern_now_iso())


def apply(a):
    e = json.load(open(a.spec, encoding="utf-8"))
    e["added"] = eastern_now_iso()
    s = open(a.index, encoding="utf-8").read()
    if f"u: '{e['u']}'" in s:
        return print("SKIPPED already on the page:", e["id"])
    if not re.fullmatch(r"/_blob/[0-9a-f]{32}", a.blob or ""):
        return print("REFUSED --blob must be the /_blob/<32 hex> path the asset upload returned")
    head = "  const vids = [\n"
    if s.count(head) != 1:
        return print("REFUSED could not find `const vids = [` in", a.index)
    pos = s.index(head) + len(head)
    for _ in range(a.at if a.at is not None else INSERT_AT):
        nxt = s.find("\n", pos)
        if nxt == -1 or not s[pos:nxt].lstrip().startswith("{"):
            break
        pos = nxt + 1
    s = s[:pos] + vid_line(e) + s[pos:]
    loc = "  const LOCAL = {"
    if s.count(loc) != 1:
        return print("REFUSED could not find `const LOCAL = {` in", a.index)
    if json.dumps(e["img"]) + ":" not in s:
        s = s.replace(loc, loc + json.dumps(e["img"]) + ": " + json.dumps(a.blob) + ", ", 1)
    s = stamp(s)
    open(a.index, "w", encoding="utf-8").write(s)
    print("APPLIED", e["o"], e["id"], "-", e["t"])


def tidy(a):
    s = open(a.index, encoding="utf-8").read()
    today = eastern_today()
    lines = s.split("\n")
    kept, removed, count = [], [], {}
    for ln in lines:
        m = re.match(r"\s*\{ r: .*o: '(%s)'.*u: 'https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})'.*up: '(\d{4}-\d\d-\d\d)'" % "|".join(map(re.escape, OFFICIAL)), ln)
        if m:
            net, vid, d = m.groups()
            age = (today - dt.date.fromisoformat(d)).days
            count[net] = count.get(net, 0) + 1
            if age > MAX_AGE_DAYS or count[net] > KEEP_PER_NETWORK:
                removed.append(f"{net} {vid} ({d})")
                continue
            # keep the "Today" label honest
            if age > 0 and "w: 'Today'" in ln:
                dd = dt.date.fromisoformat(d)
                ln = ln.replace("w: 'Today'", "w: '" + dd.strftime("%b ") + str(dd.day) + "'")
        kept.append(ln)
    open(a.index, "w", encoding="utf-8").write("\n".join(kept))
    print("TIDY removed:", ", ".join(removed) if removed else "nothing")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("prepare")
    q.add_argument("url"); q.add_argument("--network", required=True); q.add_argument("--channel", required=True)
    q.add_argument("--date", required=True); q.add_argument("--title", required=True)
    q.add_argument("--region", default="us", choices=["us", "world", "ca"])
    q.add_argument("--midterms", action="store_true"); q.add_argument("--life", action="store_true")
    q.add_argument("--when"); q.add_argument("--dur"); q.add_argument("--pic", default="globe")
    q.add_argument("--index", default="index.html")
    q = sub.add_parser("apply")
    q.add_argument("index"); q.add_argument("spec"); q.add_argument("--blob", required=True)
    q.add_argument("--at", type=int, help="position in Watch (0 = first); default %d" % INSERT_AT)
    q = sub.add_parser("tidy")
    q.add_argument("index")
    q = sub.add_parser("checked")
    q.add_argument("index")
    a = p.parse_args()
    {"prepare": prepare, "apply": apply, "tidy": tidy, "checked": checked}[a.cmd](a)


if __name__ == "__main__":
    main()
