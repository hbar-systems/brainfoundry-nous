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

# The Update endpoint runs as root in this container; the brain repo is
# bind-mounted and owned by uid 1000. Without this, git 2.47's dubious-ownership
# guard refuses every git command (the Update tab + version status boxes).
RUN git config --system --add safe.directory /home/hbar/brain

WORKDIR /app

# requirements live under api/ when build context is repo root
COPY api/requirements.txt /app/requirements.txt

# CPU-only torch FIRST. The fleet boxes have no GPU (Hetzner CAX ARM, CPU
# embeddings + CPU Ollama), but the default `torch` wheel pulled by
# sentence-transformers drags in multi-GB nvidia/cudnn CUDA libraries that are
# pure dead weight here — and they filled brain disks during `--build` rebuilds
# ("no space left on device" writing libcudnn_*.so). Installing CPU-only torch
# from PyTorch's cpu index up front means sentence-transformers sees torch
# already satisfied and never installs the CUDA build. Arch-agnostic: the cpu
# index serves both x86_64 and aarch64 CPU wheels.
RUN pip install --no-cache-dir torch \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy ONLY the api package from repo root into /app/api
COPY api /app/api

# VERSION file is the single source of truth for BRAIN_VERSION (read at
# api startup). Lives at /app/VERSION so api.main can resolve it via
# Path(__file__).parent.parent / "VERSION".
COPY VERSION /app/VERSION

RUN ls -la /app/api && echo "----" && (ls -la /app/api/identity || true)

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
