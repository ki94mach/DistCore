# DistCore Web MVP — FastAPI service
#
# Matches on-prem Orchid Nexus usage (same pip-proxy as other Python services).
# Extra vs those services: SQL Server ODBC — install from vendor/*.deb on air‑gapped hosts
# (see vendor/README.txt). Optional DEBIAN_MIRROR if you later add an apt proxy.
#
# Runtime: SQL auth in db.yml; DMS NTLM via env or dms.yml.

ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

ARG DEBIAN_MIRROR=
ARG DEBIAN_SECURITY_MIRROR=
ARG MSODBCSQL_DEB_URL=

# Orchid Pharmed Nexus PyPI proxy (on-prem). Override via build arg / .env if needed.
ARG PIP_INDEX_URL=https://nexus.orchidpharmed.com/repository/pip-proxy/simple
ARG PIP_TRUSTED_HOST=nexus.orchidpharmed.com

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    DISTCORE_HOST=0.0.0.0 \
    DISTCORE_PORT=8000 \
    DISTCORE_JOBS_DIR=/app/data/jobs \
    DISTCORE_DB_CONFIG=/config/db.yml

WORKDIR /app

# unixodbc + msodbcsql17 (not required by your other slim Python apps)
COPY vendor/ /tmp/vendor/

RUN set -eux; \
    if ls /tmp/vendor/*.deb >/dev/null 2>&1; then \
      echo "Installing ODBC packages from vendor/*.deb"; \
      # Install unixODBC stack first, then Microsoft driver (avoids dependency order issues). \
      deps=$(ls /tmp/vendor/*.deb | grep -v msodbcsql || true); \
      if [ -n "${deps}" ]; then \
        dpkg -i ${deps}; \
      fi; \
      ACCEPT_EULA=Y dpkg -i /tmp/vendor/msodbcsql*.deb; \
    elif [ -n "${DEBIAN_MIRROR}" ]; then \
      if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i \
          -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
          -e "s|https://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
          /etc/apt/sources.list.d/debian.sources; \
        if [ -n "${DEBIAN_SECURITY_MIRROR}" ]; then \
          sed -i \
            -e "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
            -e "s|https://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
            -e "s|http://security.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
            -e "s|https://security.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
            /etc/apt/sources.list.d/debian.sources; \
        fi; \
      fi; \
      apt-get update; \
      apt-get install -y --no-install-recommends curl ca-certificates unixodbc unixodbc-dev; \
      if [ -n "${MSODBCSQL_DEB_URL}" ]; then \
        curl -fsSL "${MSODBCSQL_DEB_URL}" -o /tmp/msodbcsql17.deb; \
        ACCEPT_EULA=Y dpkg -i /tmp/msodbcsql17.deb; \
        rm -f /tmp/msodbcsql17.deb; \
      else \
        echo "ERROR: set MSODBCSQL_DEB_URL or place msodbcsql17 .deb in vendor/" >&2; \
        exit 1; \
      fi; \
      rm -rf /var/lib/apt/lists/*; \
    else \
      echo "ERROR: DistCore needs ODBC Driver 17 + unixodbc." >&2; \
      echo "Your Nexus covers pip (like other apps) but not Debian apt." >&2; \
      echo "On a machine with internet, fill vendor/ (see vendor/README.txt), copy to this host, rebuild." >&2; \
      exit 1; \
    fi; \
    rm -rf /tmp/vendor

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY src ./src

RUN mkdir -p /app/data/jobs /config \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /config

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/live', timeout=3)"

CMD ["python", "-m", "src.web"]
