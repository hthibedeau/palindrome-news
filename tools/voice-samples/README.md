Hannah's voice recording, encrypted (hannah.m4a.enc). The repo is public, so the recording itself is never stored
here in the open: GitHub decrypts it during the Voice brief run with the VOICE_KEY secret (Settings > Secrets and
variables > Actions), and tools/brief_voice.py copies the voice from it with an open-source model on GitHub's machine.
To replace it, encrypt the new recording the same way (see .github/workflows/brief.yml) with the same key.
