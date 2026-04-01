# hbar.brain.beta

Stamped: 2026-02-28T16:34:30Z

## Run

From repo root:

    cp instances/hbar.brain.beta/.env.example instances/hbar.brain.beta/.env
    docker compose -f docker-compose.dev.yml -f instances/hbar.brain.beta/docker-compose.overlay.yml --env-file instances/hbar.brain.beta/.env up -d --build

UI:
    http://127.0.0.1:${UI_PORT}

Kernel Console:
    http://127.0.0.1:${UI_PORT}/kernel
