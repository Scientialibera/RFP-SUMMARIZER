from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.core.blob_storage import ensure_container, upload_directory, upload_file

logger = logging.getLogger("rfp_function.outputs")


def upload_run_outputs(
    blob_service_client,
    output_container: str,
    artifacts,
    rfp_blob_name: str,
    chunking_enabled: bool,
    upload_assets: bool,
) -> None:
    container_client = blob_service_client.get_container_client(output_container)
    ensure_container(container_client)

    run_prefix = artifacts.timestamp
    _upload_outputs(
        container_client,
        run_prefix,
        artifacts,
        rfp_blob_name,
        chunking_enabled,
        upload_assets,
    )
    logger.info("Run artifacts uploaded for run_id=%s", artifacts.timestamp)


def _upload_outputs(
    container_client,
    run_prefix: str,
    artifacts,
    rfp_blob_name: str,
    chunking_enabled: bool,
    upload_assets: bool,
) -> None:
    upload_file(container_client, artifacts.output_path, f"{run_prefix}/final/result.json")
    upload_file(container_client, artifacts.fed_context_path, f"{run_prefix}/context/fed_context.txt")

    if upload_assets:
        upload_directory(container_client, artifacts.assets_dir, f"{run_prefix}/assets")

    run_dir = artifacts.fed_context_path.parent
    intermediate_dir = run_dir / "intermediate"
    upload_directory(container_client, intermediate_dir, f"{run_prefix}/intermediate")

    if artifacts.stored_pdf_path and artifacts.stored_pdf_path.exists():
        upload_file(container_client, artifacts.stored_pdf_path, f"{run_prefix}/source/source.pdf")

    metadata = {
        "run_id": artifacts.timestamp,
        "rfp_blob_name": rfp_blob_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chunking_enabled": chunking_enabled,
    }
    metadata_path = run_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    upload_file(container_client, metadata_path, f"{run_prefix}/metadata.json")
