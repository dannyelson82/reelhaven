# syntax=docker/dockerfile:1
# ReelHaven image (ARCHITECTURE.md §14, ADR-0008, ADR-0009).
# Built only by GitHub Actions; there is no Docker in the dev environment.

ARG DEBIAN_IMAGE=debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
ARG NODE_IMAGE=node:24-trixie-slim@sha256:173f125896c3b47ddf056734c7ea789d04595a6a08769a8f78e0df642781fb66
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.19

# --- 1. Frontend: static files ------------------------------------------------
FROM ${NODE_IMAGE} AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Python: virtual environment against Debian's own Python 3.13 ----------
FROM ${UV_IMAGE} AS uv
FROM ${DEBIAN_IMAGE} AS backend
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON=/usr/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /src/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --locked --no-dev --no-editable

# --- 3. Standard ffmpeg for track changes on Dolby Vision files (ADR-0034) -----
# jellyfin-ffmpeg 8.1 drops the Dolby Vision record on stream copy. A month-end
# BtbN build (kept long-term), pinned and checked by SHA-256.
FROM ${DEBIAN_IMAGE} AS copyffmpeg
ARG COPY_FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/ffmpeg-n8.1.3-9-g29e619e767-linux64-gpl-8.1.tar.xz
ARG COPY_FFMPEG_SHA256=97ce978979194b5cf7e06a5e68020dbdaa7a4f3294c5452b6a1bc347100dbb79
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o /tmp/ffmpeg.tar.xz "${COPY_FFMPEG_URL}" \
 && echo "${COPY_FFMPEG_SHA256}  /tmp/ffmpeg.tar.xz" | sha256sum -c - \
 && mkdir -p /opt/ffmpeg-copy \
 && tar -xJf /tmp/ffmpeg.tar.xz -C /opt/ffmpeg-copy --strip-components=1 \
      --wildcards '*/bin/ffmpeg' '*/LICENSE.txt' \
 && mv /opt/ffmpeg-copy/bin/ffmpeg /opt/ffmpeg-copy/ffmpeg \
 && rmdir /opt/ffmpeg-copy/bin \
 && /opt/ffmpeg-copy/ffmpeg -hide_banner -version | head -n 1

# --- 4. Runtime ---------------------------------------------------------------
FROM ${DEBIAN_IMAGE}
ARG TARGETARCH=amd64

# jellyfin-ffmpeg (ADR-0003) from Jellyfin's repository; it bundles its own
# VA-API (Intel iHD, AMD Mesa) drivers. NVIDIA libraries are injected by the
# NVIDIA container runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg python3 tini \
 && install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
 && printf 'Types: deb\nURIs: https://repo.jellyfin.org/debian\nSuites: trixie\nComponents: main\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/jellyfin.gpg\n' "${TARGETARCH}" \
    > /etc/apt/sources.list.d/jellyfin.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends jellyfin-ffmpeg8 \
 && apt-get purge -y curl gnupg \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* \
 && /usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -version | head -n 1

# Unprivileged user; the entrypoint changes its IDs to PUID/PGID at start.
RUN groupadd --gid 100 --non-unique reelhaven \
 && useradd --uid 99 --gid 100 --non-unique --no-create-home --home-dir /config \
      --shell /usr/sbin/nologin reelhaven \
 && install -d -m 0755 /config /transcode /media

COPY --from=backend /app/venv /app/venv
COPY --from=frontend /src/frontend/dist /app/web
COPY --from=copyffmpeg /opt/ffmpeg-copy /opt/ffmpeg-copy
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

ENV PATH=/app/venv/bin:/usr/lib/jellyfin-ffmpeg:${PATH} \
    REELHAVEN_CONFIG_DIR=/config \
    REELHAVEN_TRANSCODE_DIR=/transcode \
    REELHAVEN_COPY_FFMPEG=/opt/ffmpeg-copy/ffmpeg \
    REELHAVEN_WEB_DIR=/app/web \
    REELHAVEN_PORT=7171 \
    PUID=99 PGID=100 UMASK=022 TZ=Etc/UTC \
    NVIDIA_DRIVER_CAPABILITIES=compute,video,utility \
    PYTHONUNBUFFERED=1

EXPOSE 7171
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python3", "-c", "import os,urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('REELHAVEN_PORT','7171')}/healthz\", timeout=4)"]

LABEL org.opencontainers.image.title="ReelHaven" \
      org.opencontainers.image.description="Automatic, language-aware video library compression for Unraid" \
      org.opencontainers.image.source="https://github.com/dannyelson82/reelhaven" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["reelhaven"]
