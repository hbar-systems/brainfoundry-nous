# hbar.brain.demo

Stamped: 2026-02-28T13:15:19Z

## Run

From repo root:

    cp instances/hbar.brain.demo/.env.example instances/hbar.brain.demo/.env
    docker compose -f docker-compose.dev.yml -f instances/hbar.brain.demo/docker-compose.overlay.yml --env-file instances/hbar.brain.demo/.env up -d --build

UI:
    http://127.0.0.1:${UI_PORT}

Kernel Console:
    http://127.0.0.1:${UI_PORT}/kernel
