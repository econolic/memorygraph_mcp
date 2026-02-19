FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY kb_mcp /app/kb_mcp

RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["python", "-m", "kb_mcp.server.transport_http"]
