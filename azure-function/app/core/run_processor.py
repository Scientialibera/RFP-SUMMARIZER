from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from app.config.config import RfpConfig
from app.core.analysis import run_extraction
from app.core.blob_storage import blob_service, download_blob
from app.core.run_outputs import upload_run_outputs
from app.core.sql_output import write_result_to_sql

logger = logging.getLogger("rfp_function.processor")


def process_rfp(
    config: RfpConfig,
    credential,
    rfp_path: Path,
    rfp_blob_name: str,
    tmp_path: Path,
    base_dir: Path,
) -> None:
    blob_service_client = blob_service(config.storage_account_url, credential)

    capabilities_filename = Path(config.storage_capabilities_blob).name
    capabilities_path = (
        tmp_path / config.storage_reference_container / capabilities_filename
    )
    capabilities_path.parent.mkdir(parents=True, exist_ok=True)
    download_blob(
        blob_service_client,
        config.storage_reference_container,
        config.storage_capabilities_blob,
        capabilities_path,
    )

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    temp_config = replace(
        config,
        capabilities_pdf=str(capabilities_path),
        output_dir=str(tmp_path / config.storage_output_container),
        uploads_dir=str(tmp_path / config.storage_input_container),
        fed_context_dir=str(tmp_path / config.storage_output_container / "fed_context"),
    )

    artifacts = run_extraction(
        config=temp_config,
        base_dir=base_dir,
        rfp_pdf_override=rfp_path,
        timestamp=run_timestamp,
        persist_source_pdf=True,
    )

    upload_run_outputs(
        blob_service_client,
        config.storage_output_container,
        artifacts,
        rfp_blob_name,
        config.chunking_enabled,
        config.upload_assets,
    )

    output_mode = (config.output_mode or "storage").strip().lower()
    if output_mode == "sql":
        write_result_to_sql(
            credential=credential,
            sql_server=config.sql_server,
            sql_database=config.sql_database,
            sql_schema=config.sql_schema,
            sql_table=config.sql_table,
            sql_driver=config.sql_driver,
            sql_encrypt=config.sql_encrypt,
            sql_trust_server_certificate=config.sql_trust_server_certificate,
            run_id=artifacts.timestamp,
            rfp_blob_name=rfp_blob_name,
            result=artifacts.result,
        )
