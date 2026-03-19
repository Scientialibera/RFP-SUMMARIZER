from __future__ import annotations

from functools import lru_cache

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

_credential = DefaultAzureCredential()


@lru_cache(maxsize=16)
def _download_template(account_url: str, container: str, blob_path: str) -> str:
    client = BlobServiceClient(account_url=account_url, credential=_credential)
    blob = client.get_blob_client(container, blob_path)
    return blob.download_blob().readall().decode("utf-8")


def _build_capabilities_prompt(
    capabilities_text: str,
    *,
    account_url: str,
    container: str,
    blob_path: str,
) -> str:
    template = _download_template(account_url, container, blob_path)
    return template.replace("{capabilities_text}", capabilities_text.strip())


build_system_prompt = _build_capabilities_prompt
build_chunk_system_prompt = _build_capabilities_prompt
build_reconcile_system_prompt = _build_capabilities_prompt


def build_user_prompt(
    rfp_text: str,
    image_names: list[str] | None = None,
    *,
    account_url: str,
    container: str,
    blob_path: str,
) -> str:
    template = _download_template(account_url, container, blob_path)
    image_block = ""
    if image_names:
        joined = "\n".join(f"- {name}" for name in image_names)
        image_block = f"\n\nAttached images (RFP pages only):\n{joined}\n"
    return template.replace("{rfp_text}", rfp_text.strip()).replace("{image_block}", image_block)


def build_chunk_user_prompt(
    chunk_text: str,
    previous_summary: str,
    previous_extractions: str,
    image_names: list[str] | None = None,
    part_label: str = "RFP Part",
    *,
    account_url: str,
    container: str,
    blob_path: str,
) -> str:
    template = _download_template(account_url, container, blob_path)
    image_block = ""
    if image_names:
        joined = "\n".join(f"- {name}" for name in image_names)
        image_block = f"\n\nAttached images (RFP pages only):\n{joined}\n"

    parts = []
    summary = previous_summary.strip()
    if summary:
        parts.append(
            f"Previous summary (do not repeat, use as context only):\n{summary}\n"
        )
    extractions = previous_extractions.strip()
    if extractions and extractions != "None":
        parts.append(
            f"Previously extracted fields (do not re-add; only add new items from this chunk):\n{extractions}\n"
        )
    previous_context = "\n".join(parts)

    return (
        template
        .replace("{previous_context}", previous_context)
        .replace("{part_label}", part_label)
        .replace("{chunk_text}", chunk_text.strip())
        .replace("{image_block}", image_block)
    )


def build_reconcile_user_prompt(
    extraction_candidates: str,
    chunk_summaries: str,
    reconciliation_failures: str,
    *,
    account_url: str,
    container: str,
    blob_path: str,
) -> str:
    template = _download_template(account_url, container, blob_path)
    return (
        template
        .replace("{reconciliation_failures}", reconciliation_failures.strip() or "None")
        .replace("{chunk_summaries}", chunk_summaries.strip())
        .replace("{extraction_candidates}", extraction_candidates.strip())
    )
