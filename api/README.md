# RFP Summarizer API

FastAPI backend that serves RFP processing results from Azure Blob Storage with role-based access control.

## Endpoints

### Read endpoints (Reader or Admin role)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (no auth required) |
| GET | `/api/me` | Current user info and roles |
| GET | `/api/rfps` | List all RFPs with runs |
| GET | `/api/runs/{run_id}` | Get run details, metadata, and result |
| GET | `/api/runs/{run_id}/result` | Get extraction result JSON |
| GET | `/api/runs/{run_id}/pdf` | Download source PDF |
| GET | `/api/runs/{run_id}/context` | Get fed context text |
| GET | `/api/runs/{run_id}/intermediate/{filename}` | Get chunk JSON |
| GET | `/api/prompts` | List all prompt templates and schemas |
| GET | `/api/prompts/{blob_path}` | Read a prompt template or schema |

### Write endpoints (Admin role only)

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/api/prompts/{blob_path}` | Update a prompt template or schema |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_ACCOUNT_URL` | _(set by deploy-apps.ps1)_ | Blob storage URL |
| `OUTPUT_CONTAINER` | `outputs` | Container with processing results |
| `PROMPTS_CONTAINER` | `prompts` | Container with prompt templates and schemas |
| `AUTH_ENABLED` | `false` | Enable Easy Auth + RBAC enforcement |
| `READER_ROLE` | `RFP.Reader` | App Role value for read access |
| `ADMIN_ROLE` | `RFP.Admin` | App Role value for write access |

## Authentication & Authorization

Two layers work together in production:

1. **Easy Auth (platform)** -- configured as `AllowAnonymous` so CORS preflight `OPTIONS` requests pass through. When a valid Bearer token is present, Easy Auth validates it and injects `X-MS-CLIENT-PRINCIPAL` (base64-encoded claims including roles).
2. **App-level middleware** -- when `AUTH_ENABLED=true`, the FastAPI `EasyAuthMiddleware`:
   - Rejects unauthenticated requests with 401
   - Checks App Roles: read endpoints require `RFP.Reader` or `RFP.Admin`, write endpoints require `RFP.Admin`
   - Returns 403 for insufficient permissions

Locally, `AUTH_ENABLED` defaults to `false` so all roles are granted for development.

## Local run

```bash
pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

## Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ ./api/
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "api.main:app", "--bind", "0.0.0.0:8000"]
```

Deployed via `deploy/deploy-apps.ps1` which builds the image in ACR and updates the Container App.
