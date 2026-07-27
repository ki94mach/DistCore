# DistCore Web MVP — FastAPI service
#
# Build:  docker build -t distcore-web .
# Run:    see docker-compose.yml, or:
#   docker run --rm -p 8000:8000 \
#     -e DISTCORE_DB_CONFIG=/config/db.yml \
#     -v /path/to/db.yml:/config/db.yml:ro \
#     -v distcore-jobs:/app/data/jobs \
#     distcore-web
#
# Linux containers cannot use Windows Auth / SSPI for SQL — set
# use_windows_auth: false and SQL credentials in db.yml.
# DMS SharePoint: use NTLM via DISTCORE_DMS_USERNAME / DISTCORE_DMS_PASSWORD
# (or username/password in dms.yml) and mount DISTCORE_DMS_CONFIG.

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DISTCORE_HOST=0.0.0.0 \
    DISTCORE_PORT=8000 \
    DISTCORE_JOBS_DIR=/app/data/jobs \
    DISTCORE_DB_CONFIG=/config/db.yml

WORKDIR /app

# System deps: ODBC Driver 17 for SQL Server + build tools for pyodbc/scipy wheels fallback
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        apt-transport-https \
        ca-certificates \
        unixodbc \
        unixodbc-dev \
        g++ \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 \
    && apt-get purge -y --auto-remove gnupg apt-transport-https \
    && rm -rf /var/lib/apt/lists/*

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
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["python", "-m", "src.web"]
