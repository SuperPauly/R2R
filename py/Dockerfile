FROM python:3.12-slim AS builder


# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ musl-dev curl libffi-dev gfortran libopenblas-dev \
    poppler-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Add Rust to PATH
ENV PATH="/root/.cargo/bin:${PATH}"

RUN mkdir -p /app/user_configs


WORKDIR /app
COPY py/pyproject.toml /app
COPY py/README.md /app/README.md

# Install Python dependencies for R2R
RUN pip install --no-cache-dir .
RUN pip install gunicorn uvicorn pydantic

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl poppler-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local

WORKDIR /app

# Copy R2R source code to run the app
COPY py/r2r /app/r2r
COPY py/sdk /app/sdk
COPY py/shared /app/shared
COPY py/core /app/core
COPY docker/user_configs/config.toml /app/user_configs/config.toml

# Expose environment variables and port
ARG R2R_PORT=8000 R2R_HOST=0.0.0.0
ENV R2R_PORT=$R2R_PORT R2R_HOST=$R2R_HOST
EXPOSE $R2R_PORT

# Launch the appDatabaseConfig
CMD ["sh", "-c", "uvicorn core.main.app_entry:app --host $R2R_HOST --port $R2R_PORT"]
