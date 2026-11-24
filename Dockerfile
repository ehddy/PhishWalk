FROM python:3.11.17-slim@sha256:45037981b62b34b44602584fccbc4d884d5f7dc92c7ee86bb38a698a79fe1e51

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /opt/ms-playwright

# Non-root user (UID/GID 1000) so that files in ./artifacts are owned by the host user.
RUN groupadd --gid 1000 phishwalk \
    && useradd --uid 1000 --gid phishwalk --create-home --shell /usr/sbin/nologin phishwalk
COPY --chown=phishwalk:phishwalk agent ./agent
RUN chown phishwalk:phishwalk /app

USER phishwalk

ENTRYPOINT ["python", "-m", "agent.experiment.cli"]
CMD ["targets.txt", "--artifact-root", "artifacts"]
