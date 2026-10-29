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


def reference_wav(tmp):
    files = sorted(f for f in glob.glob(os.path.join(SAMPLES, "*")) if re.search(r"\.(m4a|mp3|wav|aac|ogg|flac|caf|mp4|mov)$", f, re.I))
    if not files:
        return None
    out = os.path.join(tmp, "ref.wav")
    st, dur = best_window(files[0])
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
    parts = []
    chunks = passages([speakable(x) for x in brief["lines"]])
    for i, text in enumerate(chunks):
        # settings that scored closest to Hannah in tests on her own recording (Thu Oct 29, 2026)
        wav = model.generate(text, audio_prompt_path=ref, exaggeration=0.5, cfg_weight=0.3)
        p = os.path.join(tmp, f"{i:02d}.wav")
        torchaudio.save(p, wav, model.sr)
        parts.append(p)
        print(f"passage {i + 1}/{len(chunks)} done", flush=True)
    # join with a short pause between lines, then mp3
    lst = os.path.join(tmp, "list.txt")
    gap = os.path.join(tmp, "gap.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={model.sr}:cl=mono", "-t", "0.5", gap], check=True)
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\nfile '{gap}'\n")
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
