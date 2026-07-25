FROM python:3.12-bookworm

LABEL org.opencontainers.image.source="https://github.com/cbizon/granular_benchmark"

ARG CODEX_VERSION=0.144.1
ARG CLAUDE_VERSION=2.1.110

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm git build-essential \
    && npm install -g \
       "@openai/codex@${CODEX_VERSION}" \
       "@anthropic-ai/claude-code@${CLAUDE_VERSION}" \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir "uv==0.8.15" \
    && /opt/venv/bin/uv pip install --python /opt/venv/bin/python \
       "numpy==2.2.6" \
       "scipy==1.18.0" \
       "numba==0.66.0" \
       "matplotlib==3.11.0" \
       "pillow==12.3.0" \
       "psutil==7.2.2" \
       "pytest==9.1.1" \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 benchmark

COPY --chown=benchmark:benchmark challenge/prompt.md \
    /opt/balls-challenge/PROMPT.md
COPY --chown=benchmark:benchmark challenge/environment.json \
    /opt/balls-challenge/
COPY --chown=benchmark:benchmark \
    challenge/schema/submission.schema.json \
    challenge/schema/final-response.schema.json \
    /opt/balls-challenge/schema/
COPY --chown=benchmark:benchmark challenge/sources/ \
    /opt/balls-challenge/sources/
COPY --chown=benchmark:benchmark challenge/starter/pyproject.toml \
    /opt/balls-challenge/pyproject.toml
COPY --chown=benchmark:benchmark \
    harness/container/agent_package/balls_bench/__init__.py \
    /opt/balls-bench/balls_bench/__init__.py
COPY --chown=benchmark:benchmark harness/balls_bench/providers.py \
    harness/balls_bench/usage.py \
    /opt/balls-bench/balls_bench/
COPY --chown=benchmark:benchmark harness/container/kubernetes_runner.py \
    /opt/balls-bench/kubernetes_runner.py

USER benchmark
WORKDIR /workspace

ENV PATH=/opt/venv/bin:$PATH \
    BALLS_BENCH_ISOLATED=1 \
    PYTHONPATH=/opt/balls-bench \
    PYTHONUNBUFFERED=1 \
    PIP_NO_INDEX=1 \
    UV_NO_SYNC=1

CMD ["python", "--version"]
