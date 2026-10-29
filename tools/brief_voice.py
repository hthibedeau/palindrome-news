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


def reference_wav(tmp):
    files = sorted(f for f in glob.glob(os.path.join(SAMPLES, "*")) if re.search(r"\.(m4a|mp3|wav|aac|ogg|flac|caf|mp4|mov)$", f, re.I))
    if not files:
        return None
    out = os.path.join(tmp, "ref.wav")
    # mono 24 kHz, trimmed to 40 seconds, quiet edges removed
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", files[0], "-ac", "1", "-ar", "24000", "-t", "40",
                        "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                        out], capture_output=True, text=True)
    return out if r.returncode == 0 and os.path.exists(out) else None


def speakable(line):
    s = line.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s*/\s*PAnow|\s*\(via [^)]*\)", "", s)        # "CKOM / PAnow" -> "CKOM"
    s = re.sub(r"(\w)-U\.S\.", r"\1 U.S.", s)                # "Canada-U.S." reads as two words
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
    for i, line in enumerate(brief["lines"]):
        wav = model.generate(speakable(line), audio_prompt_path=ref, exaggeration=0.45, cfg_weight=0.5)
        p = os.path.join(tmp, f"{i:02d}.wav")
        torchaudio.save(p, wav, model.sr)
        parts.append(p)
        print(f"line {i + 1}/{len(brief['lines'])} done", flush=True)
    # join with a short pause between lines, then mp3
    lst = os.path.join(tmp, "list.txt")
    gap = os.path.join(tmp, "gap.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={model.sr}:cl=mono", "-t", "0.35", gap], check=True)
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\nfile '{gap}'\n")
    os.makedirs(os.path.join(root, "live", "audio"), exist_ok=True)
    rel = f"live/audio/brief-{slug(brief['edition'])}.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-ac", "1", "-b:a", "64k",
                    os.path.join(root, rel)], check=True)
    from datetime import datetime as _dt, timezone as _tz
    json.dump({"edition": brief["edition"], "lines": brief["lines"], "audio": rel, "at": _dt.now(_tz.utc).isoformat()}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for f in sorted(glob.glob(os.path.join(root, "live", "audio", "*.mp3")), key=os.path.getmtime)[:-3]:
        os.remove(f)
    print("VOICE_OK", rel)


if __name__ == "__main__":
    sys.exit(main())
