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
