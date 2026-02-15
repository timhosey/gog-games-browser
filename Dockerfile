FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends unrar-free \
    && rm -rf /var/lib/apt/lists/*

# rarfile prefers unrar (non-free); unrar-free is in debian. If you need full RAR support,
# use a base image that can install unrar or copy unrar binary.
# Alternatively: install unrar from backports or use rarfile's optional unrar detection.

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

EXPOSE 8000

ENV GOG_INSTALLER_PATH=/data/installers
ENV GOG_METADATA_PATH=/data/metadata

CMD ["uvicorn", "gog_browser.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
