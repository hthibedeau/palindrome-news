#!/usr/bin/env python3
"""The 60-second brief in Hannah Thibedeau's own voice, made by the code, with no sign-ups (Hannah, Oct 2026: "the
60-second brief in her own voice ... does not want to sign up on other websites"; "made automatically, without having
to record herself each edition").

GitHub Actions (.github/workflows/brief.yml) runs this three times a day:

    python3 tools/brief_voice.py --auto live/auto.json --out live/brief.json

1. Takes the newest brief the code wrote (live/auto.json "brief": each story credited to the newsroom it comes from).
2. Copies Hannah's voice from her own recording in tools/voice-samples/ (any .m4a, .mp3, .wav; 20–60 seconds of her
   speaking) with Chatterbox, an open-source voice model (MIT licence) that runs on GitHub itself. Nothing is sent to
   any outside service. The model marks its audio with an inaudible watermark as AI-made.
3. Saves live/audio/brief-<edition>.mp3 and live/brief.json {edition, lines, audio}. The page plays it with the
   script on screen. Keeps the 3 newest recordings.

Prints VOICE_OK <file>, or VOICE_SKIPPED <reason> (no recording yet, nothing new) and exits 0, so the page simply
falls back to the device voice.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "voice-samples")


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def best_window(src, want=10.0):
    """The best ~10 seconds of Hannah speaking: the model takes its sense of a voice from about 10 seconds, so give it
    her steadiest stretch of continuous speech (fewest and shortest pauses), starting and ending at a natural pause."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", "silencedetect=noise=-38dB:d=0.25", "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    dur = float((re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr) or [0, 0, 0, 0])[3] or 0) + 60 * float((re.search(r"Duration: (\d+):(\d+)", r.stderr) or [0, 0, 0])[2] or 0)
    pauses = list(zip(starts, ends))
    cuts = [0.0] + [e for _, e in pauses]  # speech resumes here
    best = None
    for c in cuts:
        # end at the last pause that starts between want-2 and want+2 seconds later
        ok = [st for st, _ in pauses if want - 2 <= st - c <= want + 2]
        if not ok:
            continue
        end = ok[-1]
        inside = [(st, e) for st, e in pauses if c < st < end]
        cost = sum(e - st for st, e in inside) + 0.5 * len(inside)
        if best is None or cost < best[0]:
            best = (cost, c, end)
    if not best and dur:
        return 0.0, min(want, dur)
    return (best[1], best[2] - best[1]) if best else (0.0, want)


GREETS = {"Good morning.": "good-morning", "Good afternoon.": "good-afternoon", "Good evening.": "good-evening"}
SIGNOFF = "signoff"  # "That's your brief. We'll keep watching, so you don't have to."
STYLE = "brief-read"  # Hannah reading a whole brief on air, 30-60 seconds: the best reference for her delivery


def clip(name):
    """Hannah's own recording called <name>.m4a/.mp3/.wav in tools/voice-samples, or None."""
    for f in glob.glob(os.path.join(SAMPLES, name + ".*")):
        if re.search(r"\.(m4a|mp3|wav|aac|ogg|flac|caf|mp4|mov)$", f, re.I):
            return f
    return None


INTRO = os.path.join(SAMPLES, "intro.m4a")  # Hannah saying "I'm Hannah Thibedeau, and this is your Palindrome News brief."
INTRO_LINE = re.compile(r"I[’']m Hannah Thibedeau, and this is your Palindrome News brief\.?\s*$")


def trimmed(src, dst, tmp_rate=24000):
    """A clip with its silent edges removed, mono 24 kHz, steady level."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(tmp_rate), "-af",
                    "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.08,areverse,"
                    "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.12,areverse,loudnorm=I=-20:TP=-2", dst], check=True)
    return dst


def clip_len(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def reference_wav(tmp):
    """About 10 seconds of Hannah for the model to copy: her brief opening (intro.m4a, her on-air delivery) first,
    then her steadiest stretch of the longer recording to make up the rest (Hannah, Thu Oct 29, 2026)."""
    own = {INTRO} | {clip(n) for n in list(GREETS.values()) + [SIGNOFF]} | set(glob.glob(os.path.join(SAMPLES, "open-*"))) | set(glob.glob(os.path.join(SAMPLES, "credit-*")))
    files = sorted(f for f in glob.glob(os.path.join(SAMPLES, "*")) if re.search(r"\.(m4a|mp3|wav|aac|ogg|flac|caf|mp4|mov)$", f, re.I) and f not in own)
    if clip(STYLE):  # her own brief read: the delivery to copy
        files = [clip(STYLE)] + [f for f in files if f != clip(STYLE)]
    if not files and not os.path.exists(INTRO):
        return None
    out = os.path.join(tmp, "ref.wav")
    if clip(STYLE):  # her brief read (Fri Oct 30, 2026): her best ~10 seconds of story delivery, nothing else
        st, dur = best_window(clip(STYLE), want=10.5)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, st - 0.05):.2f}", "-i", clip(STYLE), "-t", f"{dur + 0.15:.2f}",
                        "-ac", "1", "-ar", "24000", "-af", "loudnorm=I=-20:TP=-2", out], check=True)
        print(f"reference: brief-read.m4a {st:.1f}s for {dur:.1f}s", flush=True)
        return out
    intro = trimmed(INTRO, os.path.join(tmp, "intro_ref.wav")) if os.path.exists(INTRO) else None
    have = clip_len(intro) if intro else 0
    if not files:
        return intro
    st, dur = best_window(files[0], want=max(4.0, 10.5 - have))
    if intro:
        body = os.path.join(tmp, "body_ref.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, st - 0.05):.2f}", "-i", files[0], "-t", f"{dur + 0.15:.2f}",
                        "-ac", "1", "-ar", "24000", "-af", "loudnorm=I=-20:TP=-2", body], check=True)
        gap = os.path.join(tmp, "ref_gap.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.3", gap], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", intro, "-i", gap, "-i", body, "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1", out], check=True)
        print(f"reference: intro.m4a ({have:.1f}s) + {os.path.basename(files[0])} {st:.1f}s for {dur:.1f}s", flush=True)
        return out
    print(f"reference: {os.path.basename(files[0])} {st:.1f}s for {dur:.1f}s", flush=True)
    print(f"reference: {os.path.basename(files[0])} {st:.1f}s for {dur:.1f}s", flush=True)
    # mono 24 kHz, her best ~10 seconds, at a steady level
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, st - 0.05):.2f}", "-i", files[0], "-t", f"{dur + 0.15:.2f}",
                        "-ac", "1", "-ar", "24000", "-af", "loudnorm=I=-20:TP=-2", out], capture_output=True, text=True)
    return out if r.returncode == 0 and os.path.exists(out) else None


def passages(lines, limit=300):
    """Lines joined into passages of up to ~300 characters, so the voice keeps its phrasing across sentences instead of
    restarting cold on every line (the sign-off always stays with the line before it)."""
    out, cur = [], ""
    for ln in lines:
        if cur and len(cur) + 1 + len(ln) > limit:
            out.append(cur)
            cur = ln
        else:
            cur = (cur + " " + ln).strip()
    if cur:
        out.append(cur)
    return out


def speakable(line):
    s = line.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s*/\s*PAnow|\s*\(via [^)]*\)", "", s)        # "CKOM / PAnow" -> "CKOM"
    s = re.sub(r"(\w)-U\.S\.", r"\1 U.S.", s)                # "Canada-U.S." reads as two words
    s = re.sub(r"\$(\d[\d,.]*)\s?B\b", r"\1 billion dollars", s)
    s = re.sub(r"\$(\d[\d,.]*)\s?M\b", r"\1 million dollars", s)
    s = re.sub(r"\bDOJ\b", "the Justice Department", s)
    s = re.sub(r"\bInc\.", "", s)
    s = re.sub(r"\$(\d[\d,.]*)\s?(billion|million)", r"\1 \2 dollars", s)
    s = re.sub(r"\$(\d[\d,.]*)", r"\1 dollars", s)
    s = re.sub(r"(\d+)%", r"\1 percent", s)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", default="live/auto.json")
    ap.add_argument("--out", default="live/brief.json")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(a.out)))
    try:
        brief = json.load(open(a.auto, encoding="utf-8")).get("brief")
    except (OSError, ValueError):
        brief = None
    if not brief or not brief.get("lines"):
        return print("VOICE_SKIPPED no brief in", a.auto)
    try:
        prev = json.load(open(a.out, encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    if not a.force and prev.get("edition") == brief["edition"] and prev.get("audio") and os.path.exists(os.path.join(root, prev["audio"])):
        return print("VOICE_SKIPPED this edition is already recorded:", brief["edition"])
    import tempfile
    tmp = tempfile.mkdtemp()
    ref = reference_wav(tmp)
    if not ref:
        return print("VOICE_SKIPPED no recording of Hannah's voice in tools/voice-samples/ yet")
    try:
        import torch
        import torchaudio
        from chatterbox.tts import ChatterboxTTS
    except ImportError as e:
        return print("VOICE_SKIPPED voice model not installed:", e)
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    model = ChatterboxTTS.from_pretrained(device="cpu")
    parts, gaps = [], []   # gaps[k]: the pause after parts[k], in seconds

    def add(p, pause=0.5):
        parts.append(p); gaps.append(pause)

    def real(name, tag):
        p = os.path.join(tmp, f"{len(parts):02d}_{tag}.wav")
        trimmed(clip(name), p, model.sr)
        return p

    def say(text, tag):
        wav = model.generate(text, audio_prompt_path=ref, exaggeration=0.5, cfg_weight=0.3)
        p = os.path.join(tmp, f"{len(parts):02d}_{tag}.wav")
        torchaudio.save(p, wav, model.sr)
        return p
    lines = list(brief["lines"])
    # The opening in Hannah's own voice (Fri Oct 30, 2026 recording): the whole "Good afternoon. I'm Hannah Thibedeau,
    # and this is your Palindrome News brief." as she said it, else her greeting + her intro
    if lines and INTRO_LINE.search(lines[0]):
        greet = INTRO_LINE.sub("", lines[0]).strip()
        part = {"Good morning.": "morning", "Good afternoon.": "afternoon"}.get(greet, "evening")
        if clip("open-" + part):
            add(real("open-" + part, "open"), 0.6)
            print("opening: Hannah's own recording (open-%s)" % part, flush=True)
        else:
            if greet and clip(GREETS.get(greet, "")):
                add(real(GREETS[greet], "greet"), 0.2)
            elif greet:
                add(say(speakable(greet), "greet"), 0.2)
            if os.path.exists(INTRO):
                p = os.path.join(tmp, "intro_real.wav"); trimmed(INTRO, p, model.sr); add(p, 0.6)
        lines = lines[1:]
    tail = None
    if lines and clip(SIGNOFF) and re.match(r"That[’']s your brief", lines[-1]):
        tail = SIGNOFF
        lines = lines[:-1]
    # Each story: the sentence in her copied voice, then the credit in her real voice when she has recorded it
    # ("…, The Canadian Press reports." -> generated sentence + credit-the-canadian-press.m4a)
    for i, line in enumerate(lines):
        m = re.match(r"^(.*?),?\s*([”\"]?)\s*((?:The )?[A-Z][\w.&’' -]{1,40}?) reports\.\s*$", line)
        cname = "credit-" + slug(m.group(3)) if m else ""
        if m and clip(cname):
            body = m.group(1).rstrip(" ,") + (m.group(2) or "") + "."
            add(say(speakable(body), f"s{i}"), 0.3)
            add(real(cname, f"c{i}"), 0.65)
            print(f"story {i + 1}/{len(lines)}: her own credit ({cname})", flush=True)
        else:
            add(say(speakable(line), f"s{i}"), 0.65)
            print(f"story {i + 1}/{len(lines)} done", flush=True)
    if tail:
        add(real(SIGNOFF, "signoff"), 0.0)
        print("sign-off: Hannah's own recording", flush=True)
    # join with a short pause between lines, then mp3
    lst = os.path.join(tmp, "list.txt")
    gap = os.path.join(tmp, "gap.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={model.sr}:cl=mono", "-t", "0.5", "-c:a", "pcm_s16le", gap], check=True)
    with open(lst, "w") as f:
        pauses = {}
        for k, p in enumerate(parts):
            # every piece in one format (16-bit, 24 kHz, mono) and one loudness, so her real clips and the copied voice match
            q = os.path.join(tmp, f"norm{k:02d}.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", p, "-ac", "1", "-ar", str(model.sr), "-af", "loudnorm=I=-20:TP=-2", "-ar", str(model.sr), "-c:a", "pcm_s16le", q], check=True)
            f.write(f"file '{q}'\n")
            g_ = gaps[k]
            if g_ > 0:
                if g_ not in pauses:
                    pauses[g_] = os.path.join(tmp, f"pause{int(g_ * 100)}.wav")
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={model.sr}:cl=mono", "-t", str(g_), "-c:a", "pcm_s16le", pauses[g_]], check=True)
                f.write(f"file '{pauses[g_]}'\n")
    os.makedirs(os.path.join(root, "live", "audio"), exist_ok=True)
    rel = f"live/audio/brief-{slug(brief['edition'])}.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-ac", "1", "-af", "loudnorm=I=-16:TP=-1.5",
                    "-ar", "24000", "-b:a", "96k", os.path.join(root, rel)], check=True)
    from datetime import datetime as _dt, timezone as _tz
    json.dump({"edition": brief["edition"], "lines": brief["lines"], "audio": rel, "at": _dt.now(_tz.utc).isoformat()}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for f in sorted(glob.glob(os.path.join(root, "live", "audio", "*.mp3")), key=os.path.getmtime)[:-3]:
        os.remove(f)
    print("VOICE_OK", rel)


if __name__ == "__main__":
    sys.exit(main())
