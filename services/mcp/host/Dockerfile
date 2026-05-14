# mcp-host: Starlette gateway that mounts every services/mcp/servers/<name>
# package over Streamable HTTP (/<name>/mcp) and SSE (/<name>/sse). Lets any
# remote agent connect to a bench-anything (or future) MCP without spawning a
# local subprocess.
#
# Build context is ./services so we can COPY both mcp/ and bench/common/.
# (bench-anything-mcp is a thin client over bench-api's HTTP surface, so it
# does not need bench_common installed; only the MCP packages here are wheels.)

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY mcp/host/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Install every MCP server package as an editable wheel. Adding a new server
# under services/mcp/servers/<name>/ + rebuilding picks it up automatically;
# the registry walks this directory at startup.
COPY mcp/servers/ /app/servers/
RUN find /app/servers -maxdepth 2 -name pyproject.toml -print0 \
    | xargs -0 -n1 dirname \
    | xargs -I {} pip install --no-cache-dir {}

COPY mcp/host/app/ /app/app/

EXPOSE 8009

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
