---
created: 2026-10-25
---

# Deck: slides from speech or last year's PPTX

Created 2026-10-25. First case: a teaching professor who builds lectures in PowerPoint. The skill does not replace PowerPoint. It does the part before it: she speaks the lecture's shape (or drops last year's deck), the brain writes the deck, and she opens the result in PowerPoint as always.

## The flow

1. **In.** The words of the lecture, in one of three forms: a `.txt` (typed notes, or a transcript of the chat's voice input), an audio file (`.ogg .oga .opus .mp3 .m4a .wav .webm`, transcribed by the same backend as the chat's voice: `CC_STT_URL`, else ElevenLabs with `ELEVENLABS_API_KEY`), or an old `.pptx` (titles, bullets and speaker notes read per slide).
2. **Draft.** `scripts/deck/make-deck.py <input> --out <dir> --draft-only` writes `deck.md` in Marp markdown with a fixed rule set (paragraph = slide, first sentence = heading, at most six bullets, long sentences cut with the full text kept in the speaker notes). No model call. The draft is crude on purpose.
3. **Rewrite.** The reasoner rewrites `deck.md`: one idea per slide, short bullets, the person's own words kept in the `<!-- -->` speaker notes, nothing invented, a doubtful fact flagged in the notes. The bridge prompt carries this rule ("Decks:").
4. **Render.** The same command on the rewritten `deck.md`, without `--draft-only`, writes into `<dir>/<slug>/`:
   - `deck.pptx`: **editable** (python-pptx): real title and bullet placeholders, bullet levels, speaker notes. Bold and italics are dropped in v1; images are named in the notes, not placed.
   - `deck.pdf`: Marp, with notes as PDF annotations; for sharing or projecting.
   - `preview/deck.NNN.png`: one picture per slide, for the chat.
   - `notes.md`, `manifest.json` (input hash, timings, embedded fonts, warnings), `transcript.txt` for audio.

Language: `--lang auto` (default) chooses Russian when at least a third of the letters are Cyrillic, else English; a quoted Russian proverb does not make an English deck Russian.

## What the box needs

- python3, and a deck venv with python-pptx: `python3 -m venv ~/.local/deck-venv && ~/.local/deck-venv/bin/pip install python-pptx` (as the hands user). Without it the PPTX falls back to Marp's image PPTX (one picture per slide, not editable) and the manifest says so.
- node 18+ (Marp CLI runs through `npx @marp-team/marp-cli`, fetched on first use; `MARP_CMD` overrides).
- a headless chromium: `CHROME_PATH`, else the newest Playwright headless shell under `~/.cache/ms-playwright`. `CHROME_LIBS` adds library dirs on a box without chromium's system libraries.
- fonts with Cyrillic (DejaVu is enough; the manifest lists what the PDF embedded).

Measured on the hbar box (CAX, arm64) 2026-10-25: a 9-slide lecture renders in about 20 s (PDF 9 s, PPTX 0.5 s, previews 10 s).

## Not yet

- The Telegram door takes text only (`/integrations/telegram/webhook`), so a member whose door is Telegram cannot yet send a voice note or a PPTX and get the files back. The console works today: attach the PPTX or speak into the chat.
- Speaker-notes-first decks (the lecture script as the main product) and a per-person template (her college's slide master) are the next two steps once a real lecture has been through.

## Mistakes it guards against (from the first runs)

- Marp CLI reads a piped stdin and waits forever when run from a job or a background shell; the script runs it with stdin closed.
- Front matter must not be followed by a slide separator, or the deck opens with an empty slide.
