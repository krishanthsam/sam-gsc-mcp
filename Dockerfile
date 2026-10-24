# Sam GSC MCP — container image for remote/HTTP use.
# Local desktop users don't need this; see README "Remote deployment & Docker".
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=3001 \
    GSC_CONFIG_DIR=/data \
    GSC_EXPORT_DIR=/data/exports

WORKDIR /app
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY sam_gsc_mcp ./sam_gsc_mcp
COPY skills ./skills
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 mcp && mkdir -p /data && chown mcp /data

USER mcp
VOLUME ["/data"]
EXPOSE 3001
CMD ["sam-gsc-mcp"]
