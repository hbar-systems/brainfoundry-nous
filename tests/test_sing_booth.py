"""The booth page (SING-FREE-1, 2026-11-24): ui/lib/booth.js in node, and the page's promises in its source.

hbar 2026-11-24: "I don't want a loop. I just wanted to sing." The page opens on one record control, keeps every
take as a WAV through /cc/booth/take, and only offers a track or a loop under the voice. The WAV the page writes
must read back sample for sample (24-bit PCM) with Python's wave module; the marker must be found where it was
put, in a take that also holds a voice-like signal; the meter's numbers must be right at the edges.
The page in a real browser with a synthetic microphone: tests/browser/test_sing_booth.py."""
import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ui" / "lib" / "booth.js"
PAGE = (ROOT / "ui" / "pages" / "sing.js").read_text()
V1 = ROOT / "ui" / "pages" / "sing" / "v1.js"


def _node(tmp_path, body):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    shutil.copy(LIB, tmp_path / "booth.mjs")
    r = subprocess.run([node, "--input-type=module", "-e", f"import('./booth.mjs').then(m=>{{{body}}})"],
                       capture_output=True, text=True, timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_wav_reads_back_sample_for_sample(tmp_path):
    out = tmp_path / "t.wav"
    _node(tmp_path, f"""
      const n = 4800, a = new Float32Array(n), b = new Float32Array(n)
      for (let i = 0; i < n; i++) {{ a[i] = Math.sin(i / 7) * 0.8; b[i] = i % 2 ? 1.5 : -1.5 }}
      const bytes = m.encodeWav([a, b], 48000, 24)
      import('node:fs').then(fs => fs.writeFileSync({json.dumps(str(out))}, bytes))
    """)
    with wave.open(str(out)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (2, 3, 48000, 4800)
        frames = w.readframes(4800)
    import math
    def s24(o):
        v = int.from_bytes(frames[o:o + 3], "little", signed=True)
        return v
    for i in (0, 1, 100, 4799):
        assert abs(s24(i * 6) - round(math.sin(i / 7) * 0.8 * 8388607)) <= 1
        assert s24(i * 6 + 3) == (8388607 if i % 2 else -8388607)      # clipped to full scale, never wrapped


def test_sixteen_bit_and_mono(tmp_path):
    out = tmp_path / "m.wav"
    _node(tmp_path, f"""
      const a = new Float32Array(441).fill(0.5)
      import('node:fs').then(fs => fs.writeFileSync({json.dumps(str(out))}, m.encodeWav([a], 44100, 16)))
    """)
    with wave.open(str(out)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 44100, 441)
        assert int.from_bytes(w.readframes(1), "little", signed=True) == round(0.5 * 32767)


def test_marker_found_where_it_was_put(tmp_path):
    got = json.loads(_node(tmp_path, """
      const rate = 48000, x = new Float32Array(rate * 3)
      for (let i = 0; i < x.length; i++) x[i] = 0.3 * Math.sin(2 * Math.PI * 220 * i / rate) + 0.05 * (Math.random() - 0.5)
      const c = m.chirpSamples(rate, m.CHIRP.amp), at = Math.round(0.35 * rate) + 17
      for (let i = 0; i < c.length; i++) x[at + i] += c[i]
      const f = m.findChirp(x, rate, 0, 3)
      const none = m.findChirp(new Float32Array(rate).map(() => 0.1 * (Math.random() - 0.5)), rate, 0, 1)
      console.log(JSON.stringify({ t: f.t, want: at / rate, clear: f.clarity, none: none.t }))
    """))
    assert abs(got["t"] - got["want"]) < 1 / 48000 + 1e-9
    assert got["clear"] >= 3 and got["none"] is None


def test_meter_and_clock(tmp_path):
    got = json.loads(_node(tmp_path, """
      const full = new Float32Array(512).fill(1), zero = new Float32Array(512), half = new Float32Array(512).fill(0.5)
      console.log(JSON.stringify({
        full: m.levels(full), zero: m.levels(zero), half: m.levels(half).peakDb,
        pos: [m.meterPos(-60), m.meterPos(-30), m.meterPos(0), m.meterPos(3), m.meterPos(-90)],
        words: [m.levelWord(-50, -50), m.levelWord(-12, -12), m.levelWord(-2, -2), m.levelWord(-12, 0)],
        clock: [m.clock(0), m.clock(59.9), m.clock(61), m.clock(3725), m.clock(-4)],
        joined: Array.from(m.joinChunks([[new Float32Array([1, 2])], [new Float32Array([3])]], 1)[0]),
      }))
    """))
    assert got["full"]["peakDb"] == 0 and got["full"]["rmsDb"] == 0 and got["zero"]["peakDb"] == -120
    assert abs(got["half"] - (-6.0206)) < 1e-3
    assert got["pos"] == [0, 0.5, 1, 1, 0]
    assert got["words"] == ["quiet", "good", "hot", "clip"]
    assert got["clock"] == ["0:00", "0:59", "1:01", "1:02:05", "0:00"]
    assert got["joined"] == [1, 2, 3]


def test_page_opens_on_one_record_control_no_loop_needed():
    # the ring is enabled with no loop chosen: only arming and saving disable it
    assert "disabled={phase === 'arming' || phase === 'saving'}" in PAGE
    assert "if (!loop) return" not in PAGE
    # the voice as it is: no browser processing, kept as WAV through the booth door, never MediaRecorder
    assert "echoCancellation: false, noiseSuppression: false, autoGainControl: false" in PAGE
    assert "fetch('/cc/booth/take'" in PAGE and "encodeWav(chans, tk.rate, 24)" in PAGE
    assert "MediaRecorder" not in PAGE
    # the marker goes into the recording only (recIn), never to the speakers
    assert "play(ctx, mb, M, a.recIn)" in PAGE
    # a take the box did not take stays in the tab with try again / download
    assert "download the take" in PAGE
    # the track and the loop are optional, the loop list folded away until asked
    assert "const [loopsOpen, setLoopsOpen] = useState(false)" in PAGE
    assert "sing over a track" in PAGE and "over a loop" in PAGE
    # send to the phone through the bridge's existing door
    assert "fetch('/cc/send-file'" in PAGE


def test_old_look_is_kept_as_v1():
    v1 = V1.read_text()
    assert "SING-1 \"Booth\", 2026-11-14" in v1 and "Pick a loop" in v1 and "export default function Sing()" in v1
    assert 'href="/sing/v1"' in PAGE
