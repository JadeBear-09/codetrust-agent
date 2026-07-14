FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system codetrust && useradd --system --gid codetrust codetrust

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install .

COPY demo ./demo
RUN chown -R codetrust:codetrust /app

USER codetrust
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=2)"

CMD ["codetrust", "serve", "--host", "0.0.0.0", "--port", "8787"]

