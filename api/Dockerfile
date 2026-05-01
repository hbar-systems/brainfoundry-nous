FROM python:3.11-slim

ARG BRAIN_GIT_COMMIT=unknown
ARG BRAIN_BUILD_TIME=unknown
ENV BRAIN_GIT_COMMIT=${BRAIN_GIT_COMMIT}
ENV BRAIN_BUILD_TIME=${BRAIN_BUILD_TIME}

# git + docker CLI are needed by /admin/update so the console "Update" tab can
# run scripts/update_brain.sh end-to-end (git pull + docker compose up --build).
# We install via Docker's official apt repo to get docker compose v2 plugin.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tesseract-ocr git ca-certificates gnupg bash \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements live under api/ when build context is repo root
COPY api/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy ONLY the api package from repo root into /app/api
COPY api /app/api

RUN ls -la /app/api && echo "----" && (ls -la /app/api/identity || true)

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
