from __future__ import annotations

import logging
from pathlib import Path

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient

from app.core.retry import retry_external_call

logger = logging.getLogger("rfp_function.storage")


def blob_service(account_url: str, credential) -> BlobServiceClient:
    return BlobServiceClient(account_url=account_url, credential=credential)


@retry_external_call
def download_blob(
    blob_service_client: BlobServiceClient,
    container_name: str,
    blob_name: str,
    destination: Path,
) -> None:
    blob_client = blob_service_client.get_blob_client(
        container=container_name,
        blob=blob_name,
    )
    with destination.open("wb") as handle:
        download = blob_client.download_blob()
        handle.write(download.readall())


def ensure_container(container_client) -> None:
    try:
        container_client.create_container()
    except ResourceExistsError:
        logger.debug("Container already exists: %s", container_client.container_name)


@retry_external_call
def upload_file(container_client, source: Path, blob_path: str) -> None:
    with source.open("rb") as handle:
        container_client.upload_blob(blob_path, handle, overwrite=True)


def upload_directory(container_client, source_dir: Path, blob_prefix: str) -> None:
    if not source_dir.exists():
        return
    for file_path in source_dir.rglob("*"):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(source_dir).as_posix()
        blob_path = f"{blob_prefix}/{relative}" if blob_prefix else relative
        upload_file(container_client, file_path, blob_path)
