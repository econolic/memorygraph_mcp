FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY kb_mcp /app/kb_mcp

RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["python", "-m", "kb_mcp.server.transport_http"]
