---
created: 2026-11-13
---

# Speaking Russian without a key (Piper on the box)

A brain speaks an answer aloud through one of three engines (scripts/cc/cc-bridge.py, `_voice_backend`):

1. a voice spoke, `CC_TTS_URL` (an OpenAI-shaped server such as Kokoro on the tailnet);
2. ElevenLabs, `ELEVENLABS_API_KEY` (paid per character);
3. Piper on the box (2026-11-13): free, local, CPU. Taken when the console speaks Russian (`lang` "ru" in GET /layout) and there is no ElevenLabs key, or always with `CC_VOICE_BACKEND=piper`.

A Kokoro spoke is skipped for a Russian console when Piper is installed (Kokoro has no Russian voice).

## Install, once per box

    bash scripts/cc/install-piper.sh            # dmitri denis irina ruslan
    sudo systemctl restart cc-bridge-<member>   # each member's bridge

It writes only /opt/piper (venv + voices, sha256-checked) and installs ffmpeg from apt when missing (mp3; without it the bridge sends wav). Undo: `sudo rm -rf /opt/piper`.

## Voices (measured on hbar, 8 ARM cores under load, 2026-11-13)

| voice | sex | model | real-time factor | whisper round trip (WER, floor ~0.08) | licence |
|---|---|---|---|---|---|
| dmitri (default) | male | 63 MB | 0.47-0.56 | 0.097 | dataset CC0 |
| denis | male | 63 MB | 0.24-0.50 | 0.184 | dataset CC0 |
| irina | female | 63 MB | 0.21-0.24 | 0.079 | dataset RHVoice, "unknown" on the model card: non-commercial use only |
| ruslan | male | 63 MB | 0.26-0.49 | 0.231 | CC BY-NC-SA 4.0: non-commercial use only |

The engine, piper-tts 1.8.0, is GPL-3.0-or-later; the bridge runs it as a separate program and never imports it.
Choose a voice in the console's voice menu (POST /cc/voice), kept as `CC_PIPER_VOICE` in the bridge env file.
Env: `CC_PIPER_DIR` (default /opt/piper), `CC_PIPER_BIN` (default $CC_PIPER_DIR/venv/bin/piper), `CC_PIPER_VOICE` (default dmitri).
