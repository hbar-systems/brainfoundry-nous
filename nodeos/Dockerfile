FROM python:3.11-slim

WORKDIR /app
# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose port
EXPOSE 8001

# Wire GITHUB_TOKEN to git credentials at startup, then run the application.
# SECURITY NOTE: GITHUB_TOKEN is stored in /root/.git-credentials inside the container.
# This is visible via `docker inspect` and container forensics.
# For higher security deployments, use SSH deploy keys instead:
# mount your SSH private key as a Docker secret and configure git to use it.
CMD if [ -n "$GITHUB_TOKEN" ]; then \
      echo "https://x-access-token:$GITHUB_TOKEN@github.com" > /root/.git-credentials && \
      chmod 600 /root/.git-credentials && \
      git config --global credential.helper store; \
    fi && \
    exec uvicorn main:app --host 0.0.0.0 --port 8001
