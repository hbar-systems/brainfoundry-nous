# hbar.brain.alpha

Stamped: 2026-02-28T16:07:07Z

## Run

From repo root:

    cp instances/hbar.brain.alpha/.env.example instances/hbar.brain.alpha/.env
    docker compose -f docker-compose.dev.yml -f instances/hbar.brain.alpha/docker-compose.overlay.yml --env-file instances/hbar.brain.alpha/.env up -d --build

UI:
    http://127.0.0.1:${UI_PORT}

Kernel Console:
    http://127.0.0.1:${UI_PORT}/kernel
