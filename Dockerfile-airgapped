##############################
# Stage 1: builder (ONLINE)
##############################
FROM python:3.11-slim-bookworm AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# minimal system deps
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# isolated venv we’ll copy into the runtime
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# install deps
COPY requirements.txt .
RUN pip install -r requirements.txt

# bring in app code
COPY . .

# Bake Prisma engines into a deterministic cache dir, and pre-generate client
# NOTE: we DO NOT set PRISMA_QUERY_ENGINE_BINARY here; we only cache binaries.
ENV PRISMA_BINARY_CACHE_DIR=/opt/prisma-engines
RUN mkdir -p "$PRISMA_BINARY_CACHE_DIR" \
 && python -m prisma py fetch \
 && python -m prisma generate --schema=prisma/schema.prisma

##############################
# Stage 2: runtime (AIR-GAPPED)
##############################
FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# copy venv with installed deps + generated client
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# copy app code
COPY . .

# copy pre-fetched Prisma engines
COPY --from=builder /opt/prisma-engines /opt/prisma-engines

# Tell Prisma Python where the baked-in cache lives (no network at runtime)
# Important: don't set PRISMA_QUERY_ENGINE_BINARY here; let Prisma pick from the cache.
ENV PRISMA_BINARY_CACHE_DIR=/opt/prisma-engines \
    PRISMA_HIDE_UPDATE_MESSAGE=true

EXPOSE 8000
ENV HOST=0.0.0.0 PORT=8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

