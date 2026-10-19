# The 60-second brief: Hannah Thibedeau's voice

The brief is Hannah speaking to the listener, as the editor of Palindrome News. Write it to be heard, not read.

## How it sounds (working guide — refine from Hannah's own scripts and recordings in `tools/voice-samples/`)
- First person, warm and direct. Opens: "Good morning." / "Good evening." then "I'm Hannah Thibedeau, and this is your Palindrome News brief."
- Lead with the biggest story, then move briskly: "We begin in…", "Tomorrow…", "In Washington…", "And in Vancouver…".
- Short spoken sentences, one fact each. About 140–160 words, 8–10 lines, under 65 seconds.
- Numbers as she would say them: "thirty-nine", "one point three million", "nearly twenty-four hundred".
- Names and titles in full the first time ("Sergeant Morgan Wong"); no abbreviations (Sgt., Pte., U.S. is fine).
- Plain and neutral. Attribute claims ("the prime minister calls it…", "Iran's Revolutionary Guard says…"). Say plainly when something is unconfirmed. No opinion.
- Human touches where the story calls for it (a tragedy is said simply, without hype). No exclamation marks.
- Sign-off: "That’s your brief. We’ll keep watching, so you don’t have to."
- Use curly apostrophes (’) inside the page's single-quoted strings.

## Where it lives
- `const brief = [...]` in index.html: one spoken line per item. `const BRIEF_FOR` names the edition (e.g. 'Monday morning, October 19').
- `const BRIEF_AUDIO`: path to a recording in Hannah's own voice (e.g. 'audio/brief-2026-10-19-am.mp3'). Empty = the device reads the script aloud.
- `tools/brief_audio.py` makes that recording with Hannah's cloned voice once an ElevenLabs voice and key exist.
