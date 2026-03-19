import json
import os
import logging
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import azure.functions as func
from azure.identity import DefaultAzureCredential

BASE_DIR = Path(__file__).resolve().parent

from app.config.config import RfpConfig
from app.core.blob_storage import blob_service, download_blob
from app.core.run_processor import process_rfp

logger = logging.getLogger("rfp_function")
for noisy_logger in (
    "azure",
    "azure.core",
    "azure.storage",
    "azure.identity",
    "azure.core.pipeline.policies.http_logging_policy",
):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

app = func.FunctionApp()
credential = DefaultAzureCredential()
SUPPORTED_INPUT_EXTENSIONS = {".pdf"}


@lru_cache(maxsize=1)
def _load_config() -> RfpConfig:
    try:
        return RfpConfig.from_env()
    except KeyError:
        return RfpConfig.from_toml(BASE_DIR / "config.toml")


def _http_auth_level() -> func.AuthLevel:
    raw_value = os.environ.get("FUNCTION_HTTP_AUTH_LEVEL", "admin").strip().lower()
    levels = {
        "anonymous": func.AuthLevel.ANONYMOUS,
        "function": func.AuthLevel.FUNCTION,
        "admin": func.AuthLevel.ADMIN,
    }
    auth_level = levels.get(raw_value)
    if auth_level is None:
        logger.warning(
            "Invalid FUNCTION_HTTP_AUTH_LEVEL=%s. Falling back to admin auth.",
            raw_value,
        )
        return func.AuthLevel.ADMIN
    return auth_level


HTTP_AUTH_LEVEL = _http_auth_level()
ENABLE_HTTP_TRIGGERS = os.environ.get("ENABLE_HTTP_TRIGGERS", "false").strip().lower() == "true"


def _is_supported_input(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_INPUT_EXTENSIONS


def _sharepoint_enabled() -> bool:
    try:
        return _load_config().sharepoint_enabled
    except (KeyError, FileNotFoundError):
        logger.warning("SharePoint handlers are disabled due to missing configuration.")
        return False


def _blob_name_from_event(subject: str, data_url: str) -> str:
    """Extract blob name from Event Grid event subject or data URL."""
    marker = "/blobs/"
    if marker in subject:
        return subject.split(marker, 1)[1]
    if data_url:
        parsed = urlparse(data_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            return "/".join(parts[1:])
    raise ValueError("Could not determine blob name from Event Grid payload.")


@app.function_name(name="RfpBlobTrigger")
@app.event_grid_trigger(arg_name="event")
def rfp_analysis(event: func.EventGridEvent):
    config = _load_config()
    event_data = event.get_json() or {}
    blob_name = _blob_name_from_event(
        subject=event.subject or "",
        data_url=event_data.get("url", ""),
    )
    logger.info("EventGrid trigger received: %s", blob_name)

    if not _is_supported_input(blob_name):
        logger.warning("Skipping unsupported input format for blob: %s", blob_name)
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        rfp_filename = Path(blob_name).name or "rfp.pdf"
        rfp_path = tmp_path / config.storage_input_container / rfp_filename
        rfp_path.parent.mkdir(parents=True, exist_ok=True)

        blob_service_client = blob_service(config.storage_account_url, credential)
        download_blob(blob_service_client, config.storage_input_container, blob_name, rfp_path)
        process_rfp(config, credential, rfp_path, blob_name, tmp_path, BASE_DIR)


if ENABLE_HTTP_TRIGGERS:
    @app.route(route="manual_run", methods=["POST"], auth_level=HTTP_AUTH_LEVEL)
    def manual_run(req: func.HttpRequest) -> func.HttpResponse:
        config = _load_config()
        try:
            payload = req.get_json()
        except ValueError:
            payload = {}

        blob_name = payload.get("blob_name") or req.params.get("blob_name")
        if not blob_name:
            return func.HttpResponse(
                "Missing blob_name in JSON body or query string.",
                status_code=400,
            )
        if not _is_supported_input(blob_name):
            return func.HttpResponse(
                json.dumps(
                    {
                        "status": "unsupported_format",
                        "supported_extensions": sorted(SUPPORTED_INPUT_EXTENSIONS),
                    }
                ),
                status_code=400,
                mimetype="application/json",
            )

        logger.info("Manual trigger requested for blob: %s", blob_name)

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                rfp_filename = Path(blob_name).name
                rfp_path = tmp_path / config.storage_input_container / rfp_filename
                rfp_path.parent.mkdir(parents=True, exist_ok=True)

                blob_service_client = blob_service(config.storage_account_url, credential)
                download_blob(
                    blob_service_client,
                    config.storage_input_container,
                    blob_name,
                    rfp_path,
                )

                process_rfp(config, credential, rfp_path, blob_name, tmp_path, BASE_DIR)
        except Exception:
            logger.exception("Manual trigger failed for blob: %s", blob_name)
            return func.HttpResponse(
                json.dumps({"status": "error", "blob_name": blob_name}),
                status_code=500,
                mimetype="application/json",
            )

        return func.HttpResponse(
            json.dumps({"status": "ok", "blob_name": blob_name}),
            status_code=200,
            mimetype="application/json",
        )


if _sharepoint_enabled():
    @app.route(
        route="sharepoint_webhook",
        methods=["POST", "GET"],
        auth_level=HTTP_AUTH_LEVEL,
    )
    def sharepoint_webhook(req: func.HttpRequest) -> func.HttpResponse:
        config = _load_config()
        from app.core.sharepoint import enqueue_notification, parse_notification

        validation_token = req.params.get("validationtoken") or req.params.get("validationToken")
        if validation_token:
            return func.HttpResponse(validation_token, status_code=200)

        try:
            payload = req.get_json()
        except ValueError:
            payload = {}

        notifications = payload.get("value") or []
        if not isinstance(notifications, list) or not notifications:
            return func.HttpResponse(
                json.dumps({"status": "no_notifications"}),
                status_code=200,
                mimetype="application/json",
            )

        connection_string = os.environ.get("AzureWebJobsStorage", "")
        if not connection_string:
            return func.HttpResponse(
                "AzureWebJobsStorage is not configured.",
                status_code=500,
            )

        queued_count = 0
        for notification in notifications:
            if not isinstance(notification, dict):
                logger.warning("Skipping invalid SharePoint notification payload.")
                continue
            parsed = parse_notification(notification)
            if config.sharepoint_client_state and (
                parsed.clientState != config.sharepoint_client_state
            ):
                continue
            enqueue_notification(
                connection_string,
                config.sharepoint_queue_name,
                notification,
            )
            queued_count += 1

        return func.HttpResponse(
            json.dumps({"status": "queued", "count": queued_count}),
            status_code=202,
            mimetype="application/json",
        )


    @app.queue_trigger(
        arg_name="msg",
        queue_name="%SHAREPOINT_QUEUE%",
        connection="AzureWebJobsStorage",
    )
    def sharepoint_queue(msg: func.QueueMessage):
        config = _load_config()
        from app.core.sharepoint import (
            download_sharepoint_file,
            parse_notification,
            parse_resource,
        )
        try:
            payload = json.loads(msg.get_body().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("SharePoint queue message is not valid JSON.")
            return
        if not isinstance(payload, dict):
            logger.warning("SharePoint queue message is not an object.")
            return

        notification = parse_notification(payload)
        if config.sharepoint_client_state and (
            notification.clientState != config.sharepoint_client_state
        ):
            logger.info("SharePoint notification clientState mismatch.")
            return

        list_id, item_id = parse_resource(notification.resource or "")
        if config.sharepoint_list_id:
            list_id = config.sharepoint_list_id
        if not config.sharepoint_site_id:
            logger.warning("SharePoint site_id is not configured.")
            return
        if not list_id or not item_id:
            logger.warning("SharePoint notification missing list or item id.")
            return

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            temp_download_path = (
                tmp_path / config.storage_input_container / f"sharepoint_{item_id}.bin"
            )
            temp_download_path.parent.mkdir(parents=True, exist_ok=True)
            filename = download_sharepoint_file(
                credential,
                config.sharepoint_site_id,
                list_id,
                item_id,
                temp_download_path,
            )
            if not _is_supported_input(filename):
                logger.warning(
                    "Skipping unsupported SharePoint file format for item=%s filename=%s",
                    item_id,
                    filename,
                )
                return
            suffix = Path(filename).suffix.lower() or ".pdf"
            rfp_path = tmp_path / config.storage_input_container / f"sharepoint_{item_id}{suffix}"
            temp_download_path.replace(rfp_path)
            blob_name = f"sharepoint/{list_id}/{item_id}/{Path(filename).name}"
            process_rfp(config, credential, rfp_path, blob_name, tmp_path, BASE_DIR)
