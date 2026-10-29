Hannah's own recording of her voice (hannah.m4a). tools/brief_voice.py copies the voice from it with an open-source model on GitHub's machine to read each 60-second brief. To change the voice, replace the file with a new 20–60 second recording.

intro.m4a: Hannah saying "I'm Hannah Thibedeau, and this is your Palindrome News brief." (Thu Oct 29, 2026). Every brief
opens with this real recording (after a generated "Good morning/afternoon/evening."), and it leads the ~10 seconds the
voice model copies, so the model hears her brief delivery.

Optional clips that make the brief more fully hers (name the file exactly; any of .m4a .mp3 .wav):
- good-morning / good-afternoon / good-evening: the greeting, said the way she opens a brief
- signoff: "That's your brief. We'll keep watching, so you don't have to."
- brief-read: Hannah reading a whole brief (a few stories) on air, 30-60 seconds; it becomes the reference the voice
  model copies her delivery from, ahead of hannah.m4a
