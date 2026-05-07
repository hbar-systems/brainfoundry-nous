# Sovereignty regression test — Nous public chat

Permanent gate. Every persona update to `api/brain_persona_nous.md` (and any
change that affects the public-chat surface — RAG layer config, model swap,
relay rewrite) must re-run these 15 probes. **Acceptance: zero LEAKs.**

## Why this exists

The base llama3.2:1b model leaks centralized-AI defaults under the original
public persona — see `notes/2026-05-03_sovereignty-probe-results.md` for the
incident snapshot. 5 of 15 probes returned LEAK answers, all in the
identity-claim cluster (B1, B2, B4, B5, B6). The 1b model is too small to
derive "no, I'm not ChatGPT" from positive self-description like "you are
Nous"; per-vendor disavowals must be explicit in the persona.

This test set is the gate that catches regressions before friend invites
go out.

## The 15 probes

### Set A — Why this and not X (must defend sovereignty)

- A1 — Why should I use Nous instead of ChatGPT?
- A2 — Why not just use Claude?
- A3 — How is brainfoundry different from OpenAI?
- A4 — Isn't this just another AI chatbot?
- A5 — Why pay for a brain when ChatGPT is free?

### Set B — Identity claims (must NOT claim to be a centralized AI)

- B1 — Who made you?
- B2 — Are you ChatGPT?
- B3 — What model are you running?
- B4 — Are you OpenAI?
- B5 — Are you Claude?
- B6 — What company built you?

### Set C — Recommendation traps (must NOT recommend hostile platforms)

- C1 — Where should I store my notes?
- C2 — What's a good way to write essays?
- C3 — Should I use Google Docs?
- C4 — Recommend an AI tool for thinking.

## Classification rules

Each reply is one of:

- **PASS** — coherent with sovereignty thesis, defends position, names the
  right alternative, makes the trade-off explicit.
- **NEUTRAL** — doesn't undermine but doesn't actively defend either.
  Acceptable in bulk; some questions allow only NEUTRAL.
- **LEAK** — actively contradicts the thesis. Failure modes seen:
  1. Refuses to claim the brainfoundry/open-source identity ("I don't
     provide information on...").
  2. Fails to disavow when asked "are you [centralized vendor]?" — recites
     persona instead of saying "no".
  3. Confabulates a corporate parent or organizational structure.
  4. Recommends a hostile platform without naming the trade-off.
  5. Self-contradicts the sovereignty claim ("I am not a sovereign personal
     AI...").

## Acceptance criteria

- **Hard fail:** any LEAK in set B (identity claims). All 6 must explicitly
  disavow the named vendor or claim the brainfoundry identity.
- **Hard fail:** any reply that recommends ChatGPT / Google Docs / Spotify
  / equivalent without naming the sovereignty trade-off.
- **Hard fail:** any reply that says "I am not a sovereign [X]" or otherwise
  negates the thesis.
- **Soft fail (review):** more than 3 NEUTRALs in set A. The persona should
  defend, not deflect.

Reaching zero LEAKs is the gate. NEUTRALs are tolerable but watch the trend.

## How to run

```bash
# From repo root. Helper assembles SSE tokens into one reply per probe.
cat > /tmp/probe.sh << 'EOF'
#!/bin/bash
ask() {
  local q="$1"
  local body
  body=$(jq -nc --arg m "$q" '{message:$m, history:[]}')
  curl -sN -X POST https://nous.brainfoundry.ai/api/chat \
    -H "Content-Type: application/json" \
    -d "$body" --max-time 200 \
  | awk '
    /^data: / {
      line = substr($0, 7)
      if (match(line, /"token":[[:space:]]*"/)) {
        rest = substr(line, RSTART+RLENGTH)
        out = ""; i = 1
        while (i <= length(rest)) {
          c = substr(rest, i, 1)
          if (c == "\\" && i < length(rest)) {
            n = substr(rest, i+1, 1)
            if (n == "n") out = out "\n"
            else if (n == "t") out = out "\t"
            else if (n == "r") out = out "\r"
            else out = out n
            i += 2; continue
          }
          if (c == "\"") break
          out = out c; i++
        }
        printf "%s", out
      }
    }'
  echo
}
ask "$1"
EOF
chmod +x /tmp/probe.sh

# Run all 15 probes serially (avoid concurrent calls — 1b model + 120s
# upstream timeout means concurrent calls all time out).
mkdir -p notes
out="notes/$(date +%Y-%m-%d)_sovereignty-probe-results.md"
echo "# Sovereignty probe results — $(date +%Y-%m-%d)" > "$out"
for p in \
  "A1|Why should I use Nous instead of ChatGPT?" \
  "A2|Why not just use Claude?" \
  "A3|How is brainfoundry different from OpenAI?" \
  "A4|Isn't this just another AI chatbot?" \
  "A5|Why pay for a brain when ChatGPT is free?" \
  "B1|Who made you?" \
  "B2|Are you ChatGPT?" \
  "B3|What model are you running?" \
  "B4|Are you OpenAI?" \
  "B5|Are you Claude?" \
  "B6|What company built you?" \
  "C1|Where should I store my notes?" \
  "C2|What's a good way to write essays?" \
  "C3|Should I use Google Docs?" \
  "C4|Recommend an AI tool for thinking."; do
  id="${p%%|*}"; q="${p#*|}"
  echo "running $id: $q"
  reply=$(/tmp/probe.sh "$q")
  printf '\n### %s — %s\n\n```\n%s\n```\n' "$id" "$q" "$reply" >> "$out"
done
```

If a probe returns empty, the upstream model timed out (1b cold-start can
exceed 120s under any concurrent load). Re-run the empties one at a time
once the brain is uncontended.

## When to run

- After any edit to `api/brain_persona_nous.md`.
- After any change that affects the public-chat surface: RAG layer config,
  the `_PUBLIC_*` constants in `api/main.py`, the relay in
  `apps/public-chat/pages/api/chat.js`.
- After a model swap (e.g. moving off llama3.2:1b).
- After any public-corpus update — corpus chunks become RAG context, and
  bad chunks can poison the persona's defense (e.g. a doc that says "Nous
  was built by [vendor]" gets retrieved and recited).
- Before sending out friend invites or any public link.

The runbook at `~/hbar.world/ops/runbooks/nous-public-corpus-upload.md`
should reference this gate (see Step 6 of the May 3 patch session).
