# hbar.brain.gamma

Stamped: 2026-02-28T16:45:22Z

## Run

From repo root:

    cp instances/hbar.brain.gamma/.env.example instances/hbar.brain.gamma/.env
    docker compose -f docker-compose.dev.yml -f instances/hbar.brain.gamma/docker-compose.overlay.yml --env-file instances/hbar.brain.gamma/.env up -d --build

UI:
    http://127.0.0.1:${UI_PORT}

Kernel Console:
    http://127.0.0.1:${UI_PORT}/kernel
