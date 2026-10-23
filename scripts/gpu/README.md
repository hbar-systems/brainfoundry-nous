# gpu-run: rent a GPU for one job

Created 2026-10-12.

A brain box has no GPU and should not have one waiting. When a job needs one (stem separation, rendering, a model), `gpu-run.sh` rents a pod for that job only: it starts the pod, copies the inputs in, runs one command, copies the outputs back, and terminates the pod, also when the command fails. Nothing is kept on the pod. Storage stays with the person whose job it is; the GPU is minutes, not a server.

```
RUNPOD_API_RELAY=you@your-laptop scripts/gpu/gpu-run.sh \
  --in song.wav --out ./stems \
  --setup 'pip install -q demucs' \
  -- 'python -m demucs -n htdemucs --two-stems vocals -o out in/song.wav'
```

Measured on the first run (2026-10-12): a 181 s track separated in 6 s on an RTX 4090, against 20 to 40 minutes on an 8-core ARM brain box.

The provider key never appears in a command or a log. Put it in `RUNPOD_API_KEY` for the run, or keep it on another machine you own and set `RUNPOD_API_RELAY` to it; that machine needs `~/bin/runpod-rest.sh` (a curl wrapper that reads the key from its own file). Defaults: the first available of L4, A4000, A5000, RTX 4000 Ada, 4090 on secure cloud; a 60-minute hard stop (`GPU_MAX_MIN`).

# gpu.sh: an open model for one sitting

Added 2026-10-23.

`gpu-run.sh` is for one job with files in and out. `gpu.sh` keeps a model answering for a sitting, so the brain or a bench can talk to it:

```
scripts/gpu/gpu.sh up private      # rent a GPU, pull the profile's model, open the tunnel
scripts/gpu/gpu.sh status          # what is up, minutes used and left, whether it answers
scripts/gpu/gpu.sh down            # give everything back
```

Two profiles, split by trust rather than by topic (`profiles/*.env`):

| Profile | Port | Brain's spoke | For |
|---|---|---|---|
| `private` | 11500 | yes | the brain's own open model; it may read local-only memory |
| `lab` | 11501 | never | security benches and trials of new models; the brain never sends it memory |

How it stays private:
- The pod's only public port is SSH. Ollama listens on the pod's localhost.
- The box reaches it through an SSH tunnel that listens on `GPU_BIND`. Set this to an address of yours, such as the box's Tailscale address, in `~/.config/gpu/config`.
- Add `http://<GPU_BIND>:11500` to the brain's `OLLAMA_SPOKE_URL` once. It is a comma list, so it sits next to any spoke you already have, such as a laptop. While the pod is up, local inference goes there. When it is down, the brain falls back to its own Ollama. No restart is needed in either direction.

What it does not claim: a rented GPU is someone else's hardware. Nothing is logged by a model company, nothing is kept after `down`, and the traffic is encrypted end to end. But the host could in principle see the running pod. A machine of your own uses the same spoke setting without a pod.

How it ends:
- Every pod ends at `down`, at a failed `up`, or at the profile's time cap through a watchdog (120 min by default).
- A cap over 240 min needs `GPU_ALLOW_LONG=1`.
- `down` prints the minutes and the approximate cost.
- `--dry-run` shows what `up` would do without renting anything.
