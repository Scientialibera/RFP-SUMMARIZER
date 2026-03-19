from __future__ import annotations

import base64
import json
import logging
import os
import re
from collections import defaultdict
from pathlib import PurePosixPath

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("rfp_api")

STORAGE_ACCOUNT_URL = os.environ.get(
    "STORAGE_ACCOUNT_URL", ""
)
OUTPUT_CONTAINER = os.environ.get("OUTPUT_CONTAINER", "outputs")
PROMPTS_CONTAINER = os.environ.get("PROMPTS_CONTAINER", "prompts")
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
READER_ROLE = os.environ.get("READER_ROLE", "RFP.Reader")
ADMIN_ROLE = os.environ.get("ADMIN_ROLE", "RFP.Admin")

_AUTH_EXEMPT_PATHS = {"/api/health"}
_ADMIN_PREFIXES = ("/api/prompts",)

API_PREFIX = "/api"
app = FastAPI(title="RFP Summarizer Viewer")

_credential = DefaultAzureCredential()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _parse_client_principal(request: Request) -> dict:
    """Decode the X-MS-CLIENT-PRINCIPAL header injected by Easy Auth.

    Returns a dict with keys like 'auth_typ', 'name_typ', 'role_typ',
    'claims' (list of {typ, val}), etc.  Returns empty dict on failure.
    """
    header = request.headers.get("X-MS-CLIENT-PRINCIPAL")
    if not header:
        return {}
    try:
        decoded = base64.b64decode(header)
        return json.loads(decoded)
    except Exception:
        return {}


def _get_roles(request: Request) -> set[str]:
    """Extract the set of App Role values from the Easy Auth principal."""
    principal = _parse_client_principal(request)
    if not principal:
        return set()
    claims = principal.get("claims") or []
    roles: set[str] = set()
    for claim in claims:
        if claim.get("typ") == "roles":
            roles.add(claim.get("val", ""))
    return roles


def _has_role(request: Request, role: str) -> bool:
    return role in _get_roles(request)


class EasyAuthMiddleware(BaseHTTPMiddleware):
    """Enforces Easy Auth authentication and role-based authorization.

    - Health probe and CORS preflight are always allowed.
    - All other endpoints require authentication (X-MS-CLIENT-PRINCIPAL-ID).
    - Read endpoints require READER_ROLE or ADMIN_ROLE.
    - Write endpoints (/api/prompts PUT) require ADMIN_ROLE.
    """

    async def dispatch(self, request: Request, call_next):
        if not AUTH_ENABLED:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in _AUTH_EXEMPT_PATHS:
            return await call_next(request)

        principal_id = request.headers.get("X-MS-CLIENT-PRINCIPAL-ID")
        if not principal_id:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)

        roles = _get_roles(request)
        path = request.url.path

        is_write = any(path.startswith(p) for p in _ADMIN_PREFIXES) and request.method in ("PUT", "POST", "DELETE")

        if is_write:
            if ADMIN_ROLE not in roles:
                return JSONResponse({"detail": "Admin role required"}, status_code=403)
        else:
            if READER_ROLE not in roles and ADMIN_ROLE not in roles:
                return JSONResponse({"detail": "Insufficient permissions"}, status_code=403)

        return await call_next(request)


app.add_middleware(EasyAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_TIMESTAMP_RE = re.compile(r"^\d{8}_\d{6}$")


# ---------------------------------------------------------------------------
# Blob helpers
# ---------------------------------------------------------------------------

def _container_client() -> ContainerClient:
    return ContainerClient(
        account_url=STORAGE_ACCOUNT_URL,
        container_name=OUTPUT_CONTAINER,
        credential=_credential,
    )


def _prompts_client() -> ContainerClient:
    return ContainerClient(
        account_url=STORAGE_ACCOUNT_URL,
        container_name=PROMPTS_CONTAINER,
        credential=_credential,
    )


def _read_blob_text(client: ContainerClient, blob_name: str) -> str | None:
    try:
        return client.get_blob_client(blob_name).download_blob().readall().decode("utf-8")
    except ResourceNotFoundError:
        return None


def _read_blob_json(client: ContainerClient, blob_name: str) -> dict | list | None:
    text = _read_blob_text(client, blob_name)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_blob_bytes(client: ContainerClient, blob_name: str) -> bytes | None:
    try:
        return client.get_blob_client(blob_name).download_blob().readall()
    except ResourceNotFoundError:
        return None


def _blob_exists(client: ContainerClient, blob_name: str) -> bool:
    try:
        client.get_blob_client(blob_name).get_blob_properties()
        return True
    except ResourceNotFoundError:
        return False


def _list_run_ids(client: ContainerClient) -> list[str]:
    seen: set[str] = set()
    for blob in client.list_blobs():
        parts = blob.name.split("/", 1)
        if parts and _TIMESTAMP_RE.match(parts[0]):
            seen.add(parts[0])
    return sorted(seen, reverse=True)


def _list_chunk_files(client: ContainerClient, run_id: str) -> list[str]:
    blobs = client.list_blobs(name_starts_with=f"{run_id}/intermediate/")
    return sorted(
        b.name.rsplit("/", 1)[-1]
        for b in blobs
        if b.name.endswith(".json")
    )


def _validate_run_id(run_id: str) -> None:
    if not _TIMESTAMP_RE.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run id format")


# ---------------------------------------------------------------------------
# User info endpoint
# ---------------------------------------------------------------------------

@app.get(f"{API_PREFIX}/me")
def get_me(request: Request) -> JSONResponse:
    """Returns the current user's identity and roles (for frontend UI gating)."""
    if not AUTH_ENABLED:
        return JSONResponse({"roles": [READER_ROLE, ADMIN_ROLE], "name": "local-dev"})
    principal = _parse_client_principal(request)
    claims = principal.get("claims") or []
    name = ""
    roles = []
    for c in claims:
        if c.get("typ") == "name":
            name = c.get("val", "")
        if c.get("typ") == "roles":
            roles.append(c.get("val", ""))
    return JSONResponse({"roles": roles, "name": name})


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@app.get(f"{API_PREFIX}/health")
def health() -> dict:
    return {"status": "ok"}


@app.get(f"{API_PREFIX}/rfps")
def list_rfps() -> JSONResponse:
    client = _container_client()
    run_ids = _list_run_ids(client)

    runs: list[dict] = []
    for run_id in run_ids:
        meta = _read_blob_json(client, f"{run_id}/metadata.json") or {}
        runs.append({
            "id": run_id,
            "rfp_blob_name": meta.get("rfp_blob_name", run_id),
            "created_at": meta.get("created_at"),
            "chunking_enabled": meta.get("chunking_enabled", False),
            "has_result": _blob_exists(client, f"{run_id}/final/result.json"),
            "has_pdf": _blob_exists(client, f"{run_id}/source/source.pdf"),
            "chunk_files": _list_chunk_files(client, run_id),
        })

    grouped: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        grouped[run["rfp_blob_name"]].append(run)

    payload = []
    for rfp_name, rfp_runs in grouped.items():
        display_name = PurePosixPath(rfp_name).stem.replace("_", " ")
        latest = rfp_runs[0]["created_at"] if rfp_runs else None
        payload.append({
            "id": rfp_name,
            "name": display_name,
            "filename": rfp_name,
            "latest_run": latest,
            "run_count": len(rfp_runs),
            "runs": [
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    "chunking_enabled": r["chunking_enabled"],
                    "has_result": r["has_result"],
                    "has_pdf": r["has_pdf"],
                    "chunk_count": len(r["chunk_files"]),
                }
                for r in rfp_runs
            ],
        })
    payload.sort(key=lambda x: x.get("latest_run") or "", reverse=True)
    return JSONResponse(payload)


@app.get(f"{API_PREFIX}/runs/{{run_id}}")
def get_run(run_id: str) -> JSONResponse:
    _validate_run_id(run_id)
    client = _container_client()

    meta = _read_blob_json(client, f"{run_id}/metadata.json") or {}
    result = _read_blob_json(client, f"{run_id}/final/result.json")

    return JSONResponse({
        "id": run_id,
        "metadata": meta,
        "has_pdf": _blob_exists(client, f"{run_id}/source/source.pdf"),
        "has_context": _blob_exists(client, f"{run_id}/context/fed_context.txt"),
        "chunk_files": _list_chunk_files(client, run_id),
        "result": result,
    })


@app.get(f"{API_PREFIX}/runs/{{run_id}}/result")
def get_result(run_id: str) -> JSONResponse:
    _validate_run_id(run_id)
    client = _container_client()
    result = _read_blob_json(client, f"{run_id}/final/result.json")
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return JSONResponse(result)


@app.get(f"{API_PREFIX}/runs/{{run_id}}/pdf")
def get_pdf(run_id: str) -> Response:
    _validate_run_id(run_id)
    client = _container_client()
    data = _read_blob_bytes(client, f"{run_id}/source/source.pdf")
    if data is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=source.pdf"},
    )


@app.get(f"{API_PREFIX}/runs/{{run_id}}/context")
def get_context(run_id: str) -> PlainTextResponse:
    _validate_run_id(run_id)
    client = _container_client()
    text = _read_blob_text(client, f"{run_id}/context/fed_context.txt")
    if text is None:
        raise HTTPException(status_code=404, detail="Context not found")
    return PlainTextResponse(text)


@app.get(f"{API_PREFIX}/runs/{{run_id}}/intermediate/{{filename}}")
def get_intermediate(run_id: str, filename: str) -> JSONResponse:
    _validate_run_id(run_id)
    if not filename.endswith(".json") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    client = _container_client()
    data = _read_blob_json(client, f"{run_id}/intermediate/{filename}")
    if data is None:
        raise HTTPException(status_code=404, detail="File not found")
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# Prompts management endpoints (Admin role required for PUT)
# ---------------------------------------------------------------------------

_ALLOWED_PROMPT_PREFIXES = ("prompts/", "schemas/")


def _validate_prompt_path(blob_path: str) -> None:
    if not any(blob_path.startswith(p) for p in _ALLOWED_PROMPT_PREFIXES):
        raise HTTPException(status_code=400, detail="Invalid prompt path")
    if ".." in blob_path or "\\" in blob_path:
        raise HTTPException(status_code=400, detail="Invalid prompt path")


@app.get(f"{API_PREFIX}/prompts")
def list_prompts() -> JSONResponse:
    """List all prompt templates and schemas in the prompts container."""
    client = _prompts_client()
    items = []
    for blob in client.list_blobs():
        if not any(blob.name.startswith(p) for p in _ALLOWED_PROMPT_PREFIXES):
            continue
        items.append({
            "blob_path": blob.name,
            "size": blob.size,
            "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
        })
    items.sort(key=lambda x: x["blob_path"])
    return JSONResponse(items)


@app.get(f"{API_PREFIX}/prompts/{{blob_path:path}}")
def get_prompt(blob_path: str) -> PlainTextResponse:
    """Read the content of a prompt template or schema."""
    _validate_prompt_path(blob_path)
    client = _prompts_client()
    text = _read_blob_text(client, blob_path)
    if text is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return PlainTextResponse(text)


@app.put(f"{API_PREFIX}/prompts/{{blob_path:path}}")
async def update_prompt(blob_path: str, request: Request) -> JSONResponse:
    """Update a prompt template or schema (Admin role required)."""
    _validate_prompt_path(blob_path)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")
    client = _prompts_client()
    blob_client = client.get_blob_client(blob_path)
    blob_client.upload_blob(body, overwrite=True)
    logger.info("Prompt updated: %s by %s", blob_path, request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "unknown"))
    return JSONResponse({"status": "updated", "blob_path": blob_path})
