# Multi-stage is load-bearing, not ceremony: huggingface-hub is a *dev*
# dependency, so the stage that downloads the embedding model must have the dev
# group installed. The runtime stage installs --no-dev and takes only the model.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy

# Dependencies before source: editing a module must not re-download 87 MB.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY scripts/download_model.py ./scripts/
RUN .venv/bin/python scripts/download_model.py


FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /usr/local/bin/uv
WORKDIR /app
# PYTHONPATH is what makes --no-install-project work below. `python -m` puts the
# cwd on sys.path, but streamlit puts the *script's* directory there instead, so
# `streamlit run app/main.py` would otherwise search /app/app and never find
# `agent`. Setting it explicitly makes every entry point resolve the same way.
ENV UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# MODEL_PATH is the relative "models/Xenova/all-MiniLM-L6-v2"
# (ingestion/prose/__init__.py), resolved from this WORKDIR.
COPY --from=builder /app/models ./models

# --no-install-project above is deliberate: the packages are imported from /app
# via PYTHONPATH, so editing a module does not invalidate the dependency layer.
COPY ingestion/ ./ingestion/
COPY agent/ ./agent/
COPY monitoring/ ./monitoring/
COPY app/ ./app/
COPY evaluation/ ./evaluation/
COPY scripts/ ./scripts/

EXPOSE 8501
CMD ["streamlit", "run", "app/main.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
