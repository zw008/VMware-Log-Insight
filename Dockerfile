FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
COPY README.md .
COPY vmware_log_insight/ vmware_log_insight/
COPY mcp_server/ mcp_server/

RUN uv pip install --system .

CMD ["vmware-log-insight", "mcp"]
