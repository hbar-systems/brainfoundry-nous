FROM python:3.11-slim

ARG BRAIN_GIT_COMMIT=unknown
ARG BRAIN_BUILD_TIME=unknown
ENV BRAIN_GIT_COMMIT=${BRAIN_GIT_COMMIT}
ENV BRAIN_BUILD_TIME=${BRAIN_BUILD_TIME}

RUN apt-get update && apt-get install -y curl tesseract-ocr && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements live under api/ when build context is repo root
COPY api/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy ONLY the api package from repo root into /app/api
COPY api /app/api

RUN ls -la /app/api && echo "----" && (ls -la /app/api/identity || true)

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
