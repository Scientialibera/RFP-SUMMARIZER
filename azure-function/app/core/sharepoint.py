from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from azure.identity import DefaultAzureCredential
from azure.storage.queue import QueueClient

from app.core.retry import retry_external_call

logger = logging.getLogger("rfp_function.sharepoint")


@dataclass(frozen=True)
class SharePointNotification:
    subscriptionId: str | None = None
    clientState: str | None = None
    expirationDateTime: str | None = None
    resource: str | None = None
    tenantId: str | None = None
    siteUrl: str | None = None
    webId: str | None = None


RESOURCE_ITEM_PATTERN = re.compile(
    r"lists(?:\\(|/)(?P<list_id>[^)'/]+)(?:\\)|/)/items(?:\\(|/)(?P<item_id>[^)'/]+)",
    re.IGNORECASE,
)


def enqueue_notification(
    connection_string: str,
    queue_name: str,
    notification: dict,
) -> None:
    queue = QueueClient.from_connection_string(connection_string, queue_name)
    queue.create_queue()
    queue.send_message(json.dumps(notification))


def parse_notification(payload: dict) -> SharePointNotification:
    return SharePointNotification(
        subscriptionId=payload.get("subscriptionId"),
        clientState=payload.get("clientState"),
        expirationDateTime=payload.get("expirationDateTime"),
        resource=payload.get("resource"),
        tenantId=payload.get("tenantId"),
        siteUrl=payload.get("siteUrl"),
        webId=payload.get("webId"),
    )


def parse_resource(resource: str) -> tuple[str | None, str | None]:
    if not resource:
        return None, None
    match = RESOURCE_ITEM_PATTERN.search(resource)
    if not match:
        return None, None
    return match.group("list_id"), match.group("item_id")


def _get_graph_token(credential: DefaultAzureCredential) -> str:
    return credential.get_token("https://graph.microsoft.com/.default").token


@retry_external_call
def _graph_get_json(url: str, token: str) -> dict:
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    return response.json()


@retry_external_call
def _graph_download(url: str, token: str) -> bytes:
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    response.raise_for_status()
    return response.content


def download_sharepoint_file(
    credential: DefaultAzureCredential,
    site_id: str,
    list_id: str,
    item_id: str,
    destination: Path,
) -> str:
    if not site_id or not list_id or not item_id:
        raise ValueError("sharepoint site_id, list_id, and item_id are required.")
    token = _get_graph_token(credential)
    item_url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items/"
        f"{item_id}?expand=driveItem"
    )
    data = _graph_get_json(item_url, token)
    drive_item = data.get("driveItem") or {}
    drive_item_id = drive_item.get("id")
    filename = drive_item.get("name") or f"sharepoint_item_{item_id}"
    if not drive_item_id:
        raise ValueError("No driveItem id found for the SharePoint list item.")
    content_url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{drive_item_id}/content"
    )
    content = _graph_download(content_url, token)
    destination.write_bytes(content)
    return filename
