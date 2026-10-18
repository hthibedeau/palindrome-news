#!/usr/bin/env python3
"""Copy outlet photos into the Palindrome preview's own storage.

The claude.ai preview link blocks images hosted on other websites, so each
outlet photo is downloaded, resized and stored with the page. This script:

  1. finds every image URL in index.html (story photos, video stills, post media);
  2. skips the ones already mapped in the page's LOCAL table;
  3. downloads the rest it can reach and saves them as small JPEGs in a staging folder;
  4. writes staging/manifest.json (original URL -> staged file);
  5. prints the exact host names it could NOT reach, so they can be added to
     claude.ai Settings > Capabilities > Allow network egress.

After it runs, the staged files are uploaded to the artifact as assets and their
/_blob/ paths are added to LOCAL in index.html (see update_local()).

Usage:
  python3 tools/localize_images.py index.html staging/
  python3 tools/localize_images.py index.html staging/ --apply ids.json   # write LOCAL from upload ids
"""
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

IMG_RE = re.compile(r"https://[A-Za-z0-9.-]+/[^'\"\s<>]+?\.(?:jpe?g|png|webp)(?:\?[^'\"\s<>]*)?", re.I)
LOCAL_RE = re.compile(r"const LOCAL = (\{.*?\});")


def image_urls(html: str) -> list[str]:
    seen, out = set(), []
    for m in IMG_RE.finditer(html):
        u = m.group(0).replace("&amp;", "&")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def current_local(html: str) -> dict:
    m = LOCAL_RE.search(html)
    return json.loads(m.group(1)) if m else {}


def fetch(url: str) -> bytes | None:
    r = subprocess.run(["curl", "-sS", "-L", "--max-time", "30", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    if r.returncode != 0 or len(r.stdout) < 500:
        return None
    return r.stdout


def to_jpeg(data: bytes) -> bytes | None:
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None
    im.thumbnail((1200, 1200))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=84)
    return buf.getvalue()


def stage(html_path: Path, out_dir: Path) -> None:
    html = html_path.read_text(encoding="utf-8")
    done = current_local(html)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest, blocked = {}, {}
    for u in image_urls(html):
        if u in done:
            continue
        host = urlparse(u).hostname
        data = fetch(u)
        jpg = to_jpeg(data) if data else None
        if not jpg:
            blocked.setdefault(host, 0)
            blocked[host] += 1
            continue
        name = hashlib.md5(u.encode()).hexdigest()[:12] + ".jpg"
        (out_dir / name).write_bytes(jpg)
        manifest[u] = name
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"Staged {len(manifest)} new photos in {out_dir}/ ({len(done)} already stored).")
    if blocked:
        print("Not reachable yet. Add these exact host names in claude.ai Settings > Capabilities:")
        for h, n in sorted(blocked.items()):
            print(f"  {h}   ({n} photo{'s' if n > 1 else ''})")


def update_local(html_path: Path, out_dir: Path, ids_path: Path) -> None:
    """ids.json maps staged file name -> asset id returned by the upload."""
    html = html_path.read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text())
    ids = json.loads(ids_path.read_text())
    local = current_local(html)
    for url, name in manifest.items():
        if name in ids:
            local[url] = "/_blob/" + ids[name]
    new = "const LOCAL = " + json.dumps(local, separators=(",", ":")) + ";"
    html = LOCAL_RE.sub(lambda _: new, html, count=1)
    html_path.write_text(html, encoding="utf-8")
    print(f"LOCAL now maps {len(local)} photos.")


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[3] == "--apply":
        update_local(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[4]))
    elif len(sys.argv) >= 3:
        stage(Path(sys.argv[1]), Path(sys.argv[2]))
    else:
        print(__doc__)
