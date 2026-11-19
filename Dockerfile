# The chat page, the agent and the MCP server in one image.
# The language model runs in a second container (see docker-compose.yml).
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY ontology ./ontology
COPY data ./data
COPY eval ./eval
COPY tests ./tests

# Editable install: the code finds the ontology and the data relative to /app.
RUN pip install --no-cache-dir -e ".[dev]"

ENV LHO_HOST=0.0.0.0 \
    LHO_PORT=8000 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["lho-chat"]
