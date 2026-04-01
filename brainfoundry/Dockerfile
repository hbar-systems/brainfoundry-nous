FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
COPY brainfoundry /app/brainfoundry
CMD ["uvicorn", "brainfoundry.main:app", "--host", "0.0.0.0", "--port", "8090"]
