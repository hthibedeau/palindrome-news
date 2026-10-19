#!/usr/bin/env python3
"""Record the 60-second brief in Hannah Thibedeau's own (cloned) voice.

Reads `const brief = [...]` from index.html, sends it to ElevenLabs text-to-speech with
Hannah's voice, saves audio/brief-<edition>.mp3 in the repo, and points BRIEF_AUDIO at it.

Needs (one-time setup):
  - an ElevenLabs voice made from Hannah's own recording (Instant or Professional Voice Clone),
  - ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in the environment,
  - api.elevenlabs.io allowed in claude.ai Settings > Capabilities > network egress.

Usage: python3 tools/brief_audio.py index.html [--edition 2026-10-19-am]
Prints AUDIO_OK <path> or AUDIO_UNAVAILABLE <reason>; always exits 0 so a run can fall back
to the device voice (BRIEF_AUDIO is then left as it was, or cleared if its file is missing).
Removes recordings older than the 4 newest.
"""
import glob
import json
import os
import re
import subprocess
import sys


def brief_lines(s):
    m = re.search(r"const brief = \[(.*?)\n  \];", s, re.S)
    if not m:
        return None
    return [x.replace("’", "'") for x in re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))]


def set_audio(s, path):
    return re.sub(r"const BRIEF_AUDIO = '[^']*';", "const BRIEF_AUDIO = '%s';" % path, s, count=1)


def main():
    if len(sys.argv) < 2:
        return print(__doc__)
    index = sys.argv[1]
    edition = sys.argv[sys.argv.index("--edition") + 1] if "--edition" in sys.argv else \
        subprocess.run(["bash", "-c", "TZ=America/Toronto date +%F-%H%M"], capture_output=True, text=True).stdout.strip()
    repo = os.path.dirname(os.path.abspath(index))
    s = open(index, encoding="utf-8").read()
    cur = re.search(r"const BRIEF_AUDIO = '([^']*)';", s)
    if cur and cur.group(1) and not os.path.exists(os.path.join(repo, cur.group(1))):
        s = set_audio(s, "")
        open(index, "w", encoding="utf-8").write(s)
    key, voice = os.environ.get("ELEVENLABS_API_KEY"), os.environ.get("ELEVENLABS_VOICE_ID")
    if not key or not voice:
        return print("AUDIO_UNAVAILABLE no ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID set (Hannah's cloned voice is not set up yet)")
    lines = brief_lines(s)
    if not lines:
        return print("AUDIO_UNAVAILABLE could not find const brief in", index)
    text = " ".join(lines)
    out_rel = f"audio/brief-{edition}.mp3"
    out = os.path.join(repo, out_rel)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    body = json.dumps({"text": text, "model_id": "eleven_multilingual_v2",
                       "voice_settings": {"stability": 0.5, "similarity_boost": 0.85, "style": 0.2, "use_speaker_boost": True}})
    r = subprocess.run(["curl", "-sS", "--max-time", "120", "-X", "POST",
                        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
                        "-H", f"xi-api-key: {key}", "-H", "Content-Type: application/json", "-H", "Accept: audio/mpeg",
                        "--data", body, "-o", out, "-w", "%{http_code}"], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() != "200" or not os.path.exists(out) or os.path.getsize(out) < 10000:
        msg = (r.stderr or "").strip()[:200] or f"HTTP {r.stdout.strip()}"
        if os.path.exists(out) and os.path.getsize(out) < 10000:
            msg += " " + open(out, errors="ignore").read()[:200]
            os.remove(out)
        return print("AUDIO_UNAVAILABLE", msg)
    open(index, "w", encoding="utf-8").write(set_audio(s, out_rel))
    for old in sorted(glob.glob(os.path.join(repo, "audio", "brief-*.mp3")))[:-4]:
        os.remove(old)
    print("AUDIO_OK", out_rel, f"({os.path.getsize(out)//1024} KB)")


if __name__ == "__main__":
    main()
