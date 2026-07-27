# DistCore Web MVP — Server Runbook

One-user FastAPI app: refresh SQL snapshots → run optimization → download Excel.

## CLI vs app: VPN split

| Surface | VPN | Config used |
| --- | --- | --- |
| Laptop CLIs (`scripts/pipeline_cli.py`, `scripts/optimization_cli.py`, …) | Yes — `ensure_vpn_connected` in scripts only | `db.yml`, optional `vpn.yml`, optional `dms.yml` |
| Deployed web app (`python -m src.web`) | **Never** — no VPN imports under `src/web/` | `db.yml` (and `dms.yml` only if deliveries refresh is enabled) |

Health and API errors mean **network / credentials / ODBC / DMS reachability**, not “VPN down.”

## Server prerequisites

1. **ODBC Driver 17 for SQL Server** (or the driver named in `db.yml`).
2. Python 3.x with a venv recommended.
3. From the repo root: `pip install -r requirements.txt`.
4. Writable jobs directory (default `{repo}/data/jobs`).
5. Copy and fill config on the host (gitignored YAML — do not commit secrets):

| File | Role |
| --- | --- |
| `src/orchestrator/config/db.yml` | SQL `source` / `prod` (start from `db.yml.example`) |
| `src/orchestrator/config/dms.yml` | SharePoint folder URLs + optional NTLM credentials (start from `dms.yml.example`) |
| `src/orchestrator/config/vpn.yml` | **CLI only** — not used by the app |

Windows auth or SQL auth are both supported by `DBConnectionFactory`.

## Environment overrides (optional)

| Variable | Purpose | Default |
| --- | --- | --- |
| `DISTCORE_DB_CONFIG` | Path to `db.yml` | Factory default under `src/orchestrator/config/db.yml` |
| `DISTCORE_DMS_CONFIG` | Path to `dms.yml` | `src/orchestrator/config/dms.yml` |
| `DISTCORE_DMS_USERNAME` | DMS NTLM/Basic username | From `dms.yml` if unset |
| `DISTCORE_DMS_PASSWORD` | DMS NTLM/Basic password | From `dms.yml` if unset |
| `DISTCORE_DMS_AUTH` | `auto` / `ntlm` / `sspi` / `basic` | `auto` |
| `DISTCORE_JOBS_DIR` | Jobs root | `{repo}/data/jobs` |
| `DISTCORE_HOST` | Bind address | `0.0.0.0` |
| `DISTCORE_PORT` | Bind port | `8000` |

## Start the app

```bash
cd /path/to/DistCore
pip install -r requirements.txt
# ensure db.yml exists on the host
python -m src.web
# or:
# uvicorn src.web.app:app --host 0.0.0.0 --port 8000
```

- UI: `/` — one page with **Data freshness** (status + refresh) and **Optimize** (settings/solver → Excel download)
- OpenAPI: `/docs`
- Health: `GET /health` (prod DB ping only)

Process stdout carries uvicorn access logs plus app INFO/WARNING (startup, stale jobs, failures). Point your service manager at stdout; there is no separate log database.

## Jobs folder and cleanup

Each job lives under `{jobs_root}/{job_id}/`:

- `meta.json` — status / timestamps / error
- `result.json` — internal payload
- `result.xlsx` — downloadable Excel (Shipments / Summary / Parameters)

`data/jobs/` is gitignored. On startup, leftover `running` jobs are marked failed.

**MVP cleanup (manual):** periodically delete job directories older than ~14 days (Task Scheduler / cron). Example (PowerShell, adjust path and days):

```powershell
$root = "C:\path\to\DistCore\data\jobs"
$cutoff = (Get-Date).AddDays(-14)
Get-ChildItem $root -Directory | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Recurse -Force
```

No automatic in-app garbage collection in MVP.

## Distributor deliveries / DMS

Web refresh **always** includes distributor deliveries (no UI toggle).

- Valid `dms.yml` folder URLs are required (see `dms.yml.example`).
- **Windows (domain-joined):** SSPI by default when no DMS credentials are set.
- **Linux / Docker:** set `DISTCORE_DMS_USERNAME` + `DISTCORE_DMS_PASSWORD` (NTLM; `DISTCORE_DMS_AUTH=ntlm`) or put `username` / `password` under the `dms:` key in `dms.yml`.
- Freshness still marks deliveries `optional_for_optimize`; optimize can proceed when the four required SQL snapshots are `ready` even if deliveries are missing/partial.

Errors: DB → **503**, DMS → **502**, busy lock → **409**.

## Smoke-test checklist (no VPN)

Against the deployed host:

1. `GET /health` → `status=ok` and prod DB healthy.
2. `GET /data/status?snapshot_date=YYYY-MM-DD` → overall state + per-pipeline last updated / row counts.
3. `POST /data/refresh` with `{ "snapshot_date": "YYYY-MM-DD" }` → `job_id`; poll `GET /jobs/{id}` until `succeeded` (includes deliveries).
4. While refresh is `running`, `POST /optimizations` → **409** lock message.
5. After data is ready, `POST /optimizations` with solver/preset → poll until `succeeded`.
6. `GET /optimizations/{id}/download` → `.xlsx` with `Content-Disposition`; open Shipments / Summary / Parameters.

UI path `/` exercises the same flow.

## Explicitly out of scope (MVP)

Docker/K8s packaging, secret managers, reverse-proxy TLS, automated job GC, multi-instance locks, and any VPN integration inside `src/web`.
