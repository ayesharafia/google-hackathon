# PYTHON_BASE must include an approved SHA-256 digest, supplied by build-images.sh.
ARG PYTHON_BASE
FROM ${PYTHON_BASE} AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib XDG_CACHE_HOME=/tmp/cache
WORKDIR /app
COPY requirements-runtime.lock /app/requirements-runtime.lock
COPY dist/wheelhouse /wheels
RUN python -m pip install --no-compile --no-cache-dir --no-index --find-links=/wheels --require-hashes -r requirements-runtime.lock && rm -rf /wheels
COPY dist/*.whl /app/
RUN python -m pip install --no-compile --no-deps /app/*.whl && rm /app/*.whl
RUN groupadd --gid 10001 physimesh && useradd --uid 10001 --gid 10001 --no-create-home physimesh
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "uvicorn", "physimesh.api.app:app_from_environment", "--factory", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "100", "--backlog", "64"]
FROM application AS worker
HEALTHCHECK NONE
CMD ["python", "-m", "physimesh.platform.worker"]
