#!/usr/bin/env python3
"""Immediate back-end transcript of a broadcast that is LIVE NOW (Hannah's rule).

Usage: python3 tools/live_transcribe.py <out.txt> <stream url> [<more stream urls> ...] [--seconds 900]

Give every place the broadcast is streaming, best first: the event's YouTube watch
page on the network's own channel, CPAC, the CBC player page, ParlVU (House of
Commons), the network's own video page. The first one that works is used.

- From the start of the stream when the site allows it (YouTube --live-from-start),
  otherwise the last --seconds of audio from the live edge.
- Captions are used when the stream has them; otherwise speech-to-text
  (faster-whisper, installed on first use).

Prints TRANSCRIPT_OK <out.txt> (<n> words) or TRANSCRIPT_UNAVAILABLE <reason>,
plus BLOCKED <host> for each video host this workspace cannot reach (Hannah can
allow it in claude.ai Settings > Capabilities). Always exits 0.

The transcript is a working note for the editor only. NEVER commit it, publish it,
or put it (or long quotes from it) on the page. Write <out.txt> outside the repo.
The running summary on the page cites outlets' reports, or the network's own
video page for a point that comes only from the broadcast.
"""
import glob, os, re, subprocess, sys, tempfile
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from transcribe import vtt_to_text, ensure  # shared helpers
except Exception:  # pragma: no cover
    vtt_to_text = None
    def ensure(pkg, mod):
        try:
            __import__(mod); return True
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", pkg, "--break-system-packages"], capture_output=True)
            try:
                __import__(mod); return True
            except ImportError:
                return False


def sh(cmd, timeout):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        class R: pass
        r = R(); r.returncode = 124; r.stdout = e.stdout or ""; r.stderr = e.stderr or ""
        if isinstance(r.stdout, bytes): r.stdout = r.stdout.decode("utf8", "ignore")
        if isinstance(r.stderr, bytes): r.stderr = r.stderr.decode("utf8", "ignore")
        return r


def blocked(err):
    return "403" in err and ("proxy" in err.lower() or "Tunnel" in err)


def whisper(audio, out):
    if not ensure("faster-whisper", "faster_whisper"):
        return None
    from faster_whisper import WhisperModel
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "base.en"), device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, vad_filter=True)
    lines = []
    for sg in segs:
        m, s = divmod(int(sg.start), 60)
        lines.append(f"[{m:02d}:{s:02d}] {sg.text.strip()}")
    open(out, "w").write("\n".join(lines) + "\n")
    return len(" ".join(lines).split())


def try_one(url, out, seconds, work):
    host = urlparse(url).hostname or url
    # 1. captions (YouTube and others)
    r = sh(["yt-dlp", "--no-warnings", "--skip-download", "--write-subs", "--write-auto-subs",
            "--sub-langs", "en.*,en", "--sub-format", "vtt", "-o", os.path.join(work, "cap.%(ext)s"), url], 120)
    if blocked(r.stderr):
        return None, "BLOCKED " + host
    vtts = glob.glob(os.path.join(work, "cap*.vtt"))
    if vtts and vtt_to_text:
        text = vtt_to_text(vtts[0])
        if len(text.split()) > 50:
            open(out, "w").write(text)
            return len(text.split()), None
    # 2. audio: from the start if possible, else the live edge, for at most `seconds`
    audio = os.path.join(work, "audio.m4a")
    r = sh(["yt-dlp", "--no-warnings", "-f", "bestaudio/best", "--live-from-start", "-x", "--audio-format", "m4a",
            "-o", os.path.join(work, "audio.%(ext)s"), url], seconds + 60)
    parts = [p for p in glob.glob(os.path.join(work, "audio*")) if os.path.getsize(p) > 50000]
    if not parts:
        g = sh(["yt-dlp", "--no-warnings", "-g", "-f", "bestaudio/best", url], 90)
        if blocked(g.stderr):
            return None, "BLOCKED " + host
        stream = (g.stdout or "").strip().splitlines()
        if not stream:
            return None, "no stream at " + host + ": " + (g.stderr or r.stderr).strip().splitlines()[-1:][0] if (g.stderr or r.stderr).strip() else "no stream at " + host
        f = sh(["ffmpeg", "-y", "-loglevel", "error", "-i", stream[0], "-t", str(seconds), "-vn", "-ac", "1", "-ar", "16000", audio], seconds + 60)
        if blocked(f.stderr):
            return None, "BLOCKED " + urlparse(stream[0]).hostname
        parts = [audio] if os.path.exists(audio) and os.path.getsize(audio) > 50000 else []
    if not parts:
        return None, "could not record audio from " + host
    n = whisper(max(parts, key=os.path.getsize), out)
    if not n:
        return None, "speech-to-text unavailable (faster-whisper did not load)"
    return n, None


def main():
    args = sys.argv[1:]
    seconds = 900
    if "--seconds" in args:
        i = args.index("--seconds"); seconds = int(args[i + 1]); del args[i:i + 2]
    if len(args) < 2:
        print(__doc__); print("TRANSCRIPT_UNAVAILABLE usage"); return
    out, urls = args[0], args[1:]
    if os.path.abspath(out).startswith(os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))):
        print("TRANSCRIPT_UNAVAILABLE write the transcript outside the repo (e.g. /tmp/live.txt)"); return
    reasons = []
    for url in urls:
        with tempfile.TemporaryDirectory() as work:
            n, why = try_one(url, out, seconds, work)
        if n:
            print(f"TRANSCRIPT_OK {out} ({n} words) from {url}")
            for x in reasons:
                if x.startswith("BLOCKED"): print(x)
            return
        reasons.append(why)
    for x in reasons:
        if x and x.startswith("BLOCKED"): print(x)
    print("TRANSCRIPT_UNAVAILABLE " + "; ".join(x for x in reasons if x))


if __name__ == "__main__":
    main()
