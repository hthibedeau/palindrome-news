#!/usr/bin/env python3
"""Back-end transcript of a finished live broadcast, for writing the recap.

Usage: python3 tools/transcribe.py <video page url> <out.txt>

The transcript is a working note for the editor only. NEVER commit it, publish
it, or quote it on the page: write <out.txt> outside the repo (e.g. /tmp).
The recap on the page still cites the outlets' own reports, or the network's
own video page when a point comes only from the broadcast.

Tries, in order:
  1. Captions from the video page (YouTube or any site yt-dlp supports):
     the network's own captions first, then automatic captions.
  2. Speech-to-text on the audio with faster-whisper, if a model can load.
Prints TRANSCRIPT_OK <out.txt> (<n> words) or TRANSCRIPT_UNAVAILABLE <reason>.
Always exits 0 so a run can fall back to the outlets' coverage.
"""
import glob, os, re, subprocess, sys, tempfile


def sh(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ensure(pkg, mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        r = sh([sys.executable, "-m", "pip", "install", "-q", pkg, "--break-system-packages"])
        try:
            __import__(mod)
            return True
        except ImportError:
            return False


def vtt_to_text(path):
    lines, last = [], None
    for ln in open(path, encoding="utf-8", errors="ignore"):
        ln = ln.strip()
        if not ln or ln.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or "-->" in ln or ln.isdigit():
            continue
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if ln and ln != last:
            lines.append(ln)
            last = ln
    return " ".join(lines)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return
    url, out = sys.argv[1], os.path.abspath(sys.argv[2])
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if out.startswith(repo + os.sep):
        print("TRANSCRIPT_UNAVAILABLE refusing to write a transcript inside the repo; use /tmp")
        return
    if not ensure("yt-dlp", "yt_dlp"):
        print("TRANSCRIPT_UNAVAILABLE could not install yt-dlp")
        return
    work = tempfile.mkdtemp(prefix="pn-tx-")
    reasons = []
    for flag in ("--write-subs", "--write-auto-subs"):
        r = sh([sys.executable, "-m", "yt_dlp", "--skip-download", flag, "--sub-langs", "en.*,en",
                "--sub-format", "vtt", "-o", os.path.join(work, "cap"), url], timeout=180)
        subs = glob.glob(os.path.join(work, "cap*.vtt"))
        if subs:
            text = vtt_to_text(subs[0])
            if len(text.split()) > 50:
                open(out, "w").write(text)
                print(f"TRANSCRIPT_OK {out} ({len(text.split())} words, from {'captions' if flag == '--write-subs' else 'automatic captions'})")
                return
        reasons.append((r.stderr or r.stdout).strip().splitlines()[-1:] or ["no captions"])
    # Speech-to-text fallback
    r = sh([sys.executable, "-m", "yt_dlp", "-f", "bestaudio/best", "-x", "--audio-format", "mp3",
            "-o", os.path.join(work, "audio.%(ext)s"), url], timeout=600)
    audio = glob.glob(os.path.join(work, "audio.*"))
    if not audio:
        print("TRANSCRIPT_UNAVAILABLE could not get the video or its captions:", reasons[-1][0][:200] if reasons else "")
        return
    if not ensure("faster-whisper", "faster_whisper"):
        print("TRANSCRIPT_UNAVAILABLE speech-to-text not installable")
        return
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(audio[0], vad_filter=True)
        text = " ".join(s.text.strip() for s in segs)
    except Exception as e:
        print("TRANSCRIPT_UNAVAILABLE speech-to-text model could not load:", str(e)[:200])
        return
    open(out, "w").write(text)
    print(f"TRANSCRIPT_OK {out} ({len(text.split())} words, speech-to-text)")


if __name__ == "__main__":
    main()
