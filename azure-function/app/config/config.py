import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RfpConfig:
    endpoint: str
    model: str
    api_version: str
    capabilities_pdf: str
    output_dir: str
    uploads_dir: str
    fed_context_dir: str
    toggle_table: bool
    toggle_images: bool
    max_attached_images: int
    min_table_rows: int
    min_table_cols: int
    include_table_text: bool
    chunking_enabled: bool
    chunking_max_tokens: int
    snippet_chunk_size: int
    snippet_size: int
    snippet_top_n_summary: int
    snippet_top_n_fee: int
    snippet_top_n_date: int
    snippet_top_n_best_lead_org: int
    snippet_top_n_cross_sell_opps: int
    snippet_top_n_capabilities_for_rfp: int
    snippet_top_n_diversity_allocation: int
    snippet_page_overlap: int
    output_mode: str
    upload_assets: bool
    sharepoint_enabled: bool
    sharepoint_client_state: str
    sharepoint_site_id: str
    sharepoint_list_id: str
    sharepoint_queue_name: str
    storage_account_url: str
    storage_account_name: str
    storage_input_container: str
    storage_reference_container: str
    storage_capabilities_blob: str
    storage_output_container: str
    prompts_container: str
    system_prompt_blob: str
    user_prompt_blob: str
    chunk_system_prompt_blob: str
    chunk_user_prompt_blob: str
    reconcile_system_prompt_blob: str
    reconcile_user_prompt_blob: str
    schema_blob_path: str
    chunk_schema_blob_path: str
    sql_server: str
    sql_database: str
    sql_schema: str
    sql_table: str
    sql_driver: str
    sql_encrypt: bool
    sql_trust_server_certificate: bool

    @staticmethod
    def from_env() -> "RfpConfig":
        def _get_bool(key: str, default: bool) -> bool:
            value = os.getenv(key)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "y"}

        def _get_int(key: str, default: int) -> int:
            value = os.getenv(key)
            if value is None or not value.strip():
                return default
            return int(value)

        storage_account_name = os.environ.get("STORAGE_ACCOUNT_NAME", "")
        storage_account_url = os.environ.get(
            "STORAGE_ACCOUNT_URL",
            f"https://{storage_account_name}.blob.core.windows.net" if storage_account_name else "",
        )

        return RfpConfig(
            endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            model=os.environ["AZURE_OPENAI_MODEL"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
            capabilities_pdf=os.environ.get("CAPABILITIES_BLOB", "capabilities_document.pdf"),
            output_dir=os.environ.get("OUTPUT_DIR", os.environ.get("OUTPUT_CONTAINER", "outputs")),
            uploads_dir=os.environ.get("UPLOADS_DIR", os.environ.get("INPUT_CONTAINER", "uploads")),
            fed_context_dir=os.environ.get(
                "FED_CONTEXT_DIR",
                str(Path(os.environ.get("OUTPUT_CONTAINER", "outputs")) / "fed_context"),
            ),
            toggle_table=_get_bool("TOGGLE_TABLE", True),
            toggle_images=_get_bool("TOGGLE_IMAGES", False),
            max_attached_images=_get_int("MAX_ATTACHED_IMAGES", 50),
            min_table_rows=_get_int("MIN_TABLE_ROWS", 2),
            min_table_cols=_get_int("MIN_TABLE_COLS", 2),
            include_table_text=_get_bool("INCLUDE_TABLE_TEXT", False),
            chunking_enabled=_get_bool("CHUNKING_ENABLED", True),
            chunking_max_tokens=_get_int("CHUNKING_MAX_TOKENS", 60000),
            snippet_chunk_size=_get_int("SNIPPET_CHUNK_SIZE", 100),
            snippet_size=_get_int("SNIPPET_SIZE", 20),
            snippet_top_n_summary=_get_int("SNIPPET_TOP_N_SUMMARY", 3),
            snippet_top_n_fee=_get_int("SNIPPET_TOP_N_FEE", 1),
            snippet_top_n_date=_get_int("SNIPPET_TOP_N_DATE", 1),
            snippet_top_n_best_lead_org=_get_int("SNIPPET_TOP_N_BEST_LEAD_ORG", 3),
            snippet_top_n_cross_sell_opps=_get_int("SNIPPET_TOP_N_CROSS_SELL_OPPS", 3),
            snippet_top_n_capabilities_for_rfp=_get_int(
                "SNIPPET_TOP_N_CAPABILITIES_FOR_RFP", 3
            ),
            snippet_top_n_diversity_allocation=_get_int(
                "SNIPPET_TOP_N_DIVERSITY_ALLOCATION", 3
            ),
            snippet_page_overlap=_get_int("SNIPPET_PAGE_OVERLAP", 2),
            output_mode=os.environ.get("OUTPUT_MODE", "storage"),
            upload_assets=_get_bool("UPLOAD_ASSETS", False),
            sharepoint_enabled=_get_bool("SHAREPOINT_ENABLED", False),
            sharepoint_client_state=os.environ.get("SHAREPOINT_CLIENT_STATE", ""),
            sharepoint_site_id=os.environ.get("SHAREPOINT_SITE_ID", ""),
            sharepoint_list_id=os.environ.get("SHAREPOINT_LIST_ID", ""),
            sharepoint_queue_name=os.environ.get("SHAREPOINT_QUEUE", "sharepoint-notifications"),
            storage_account_url=storage_account_url,
            storage_account_name=storage_account_name,
            storage_input_container=os.environ.get("INPUT_CONTAINER", "uploads"),
            storage_reference_container=os.environ.get("REFERENCE_CONTAINER", "reference"),
            storage_capabilities_blob=os.environ.get("CAPABILITIES_BLOB", "capabilities_document.pdf"),
            storage_output_container=os.environ.get("OUTPUT_CONTAINER", "outputs"),
            prompts_container=os.environ.get("PROMPTS_CONTAINER", "prompts"),
            system_prompt_blob=os.environ.get("SYSTEM_PROMPT_BLOB", "prompts/system_prompt.txt"),
            user_prompt_blob=os.environ.get("USER_PROMPT_BLOB", "prompts/user_prompt.txt"),
            chunk_system_prompt_blob=os.environ.get("CHUNK_SYSTEM_PROMPT_BLOB", "prompts/chunk_system_prompt.txt"),
            chunk_user_prompt_blob=os.environ.get("CHUNK_USER_PROMPT_BLOB", "prompts/chunk_user_prompt.txt"),
            reconcile_system_prompt_blob=os.environ.get("RECONCILE_SYSTEM_PROMPT_BLOB", "prompts/reconcile_system_prompt.txt"),
            reconcile_user_prompt_blob=os.environ.get("RECONCILE_USER_PROMPT_BLOB", "prompts/reconcile_user_prompt.txt"),
            schema_blob_path=os.environ.get("SCHEMA_BLOB_PATH", "schemas/rfp_fields_schema.json"),
            chunk_schema_blob_path=os.environ.get("CHUNK_SCHEMA_BLOB_PATH", "schemas/rfp_fields_chunk_schema.json"),
            sql_server=os.environ.get("SQL_SERVER", ""),
            sql_database=os.environ.get("SQL_DATABASE", ""),
            sql_schema=os.environ.get("SQL_SCHEMA", "dbo"),
            sql_table=os.environ.get("SQL_TABLE", "rfp_extractions"),
            sql_driver=os.environ.get("SQL_DRIVER", "ODBC Driver 18 for SQL Server"),
            sql_encrypt=_get_bool("SQL_ENCRYPT", True),
            sql_trust_server_certificate=_get_bool("SQL_TRUST_SERVER_CERTIFICATE", False),
        )

    @staticmethod
    def from_toml(path: Path) -> "RfpConfig":
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        storage_config = config.get("storage", {})
        output_config = config.get("output", {})
        uploads_config = config.get("uploads", {})
        fed_context_config = config.get("fed_context", {})
        output_dir = output_config.get(
            "dir", storage_config.get("output_container", "outputs")
        )
        reference_container = storage_config.get("reference_container", "reference")
        capabilities_blob = storage_config.get("capabilities_blob", "")
        account_url = config["storage"]["account_url"]
        account_name = account_url.split("//")[1].split(".")[0] if "//" in account_url else ""
        prompts_cfg = config.get("prompts", {})
        schemas_cfg = config.get("schemas", {})
        return RfpConfig(
            endpoint=config["azure"]["endpoint"],
            model=config["azure"]["model"],
            api_version=config["azure"].get("api_version", "2025-01-01-preview"),
            capabilities_pdf=str(Path(reference_container) / capabilities_blob),
            output_dir=output_dir,
            uploads_dir=uploads_config.get(
                "dir", storage_config.get("input_container", "uploads")
            ),
            fed_context_dir=fed_context_config.get(
                "dir", str(Path(output_dir) / "fed_context")
            ),
            toggle_table=config["inputs"]["toggle_table"],
            toggle_images=config["inputs"]["toggle_images"],
            max_attached_images=config["inputs"]["max_attached_images"],
            min_table_rows=config["inputs"].get("min_table_rows", 2),
            min_table_cols=config["inputs"].get("min_table_cols", 2),
            include_table_text=config["inputs"].get("include_table_text", False),
            chunking_enabled=config["chunking"]["enabled"],
            chunking_max_tokens=config["chunking"]["max_tokens"],
            snippet_chunk_size=config["snippets"]["chunk_size"],
            snippet_size=config["snippets"]["snippet_size"],
            snippet_top_n_summary=config["snippets"]["summary_top_n"],
            snippet_top_n_fee=config["snippets"]["fee_top_n"],
            snippet_top_n_date=config["snippets"]["date_top_n"],
            snippet_top_n_best_lead_org=config["snippets"]["best_lead_org_top_n"],
            snippet_top_n_cross_sell_opps=config["snippets"]["cross_sell_opps_top_n"],
            snippet_top_n_capabilities_for_rfp=config["snippets"]["capabilities_for_rfp_top_n"],
            snippet_top_n_diversity_allocation=config["snippets"]["diversity_allocation_top_n"],
            snippet_page_overlap=config["snippets"].get("page_overlap", 0),
            output_mode=config["function"]["output_mode"],
            upload_assets=config["function"].get("upload_assets", False),
            sharepoint_enabled=config.get("sharepoint", {}).get("enabled", False),
            sharepoint_client_state=config.get("sharepoint", {}).get("client_state", ""),
            sharepoint_site_id=config.get("sharepoint", {}).get("site_id", ""),
            sharepoint_list_id=config.get("sharepoint", {}).get("list_id", ""),
            sharepoint_queue_name=config.get("sharepoint", {}).get(
                "queue_name", "sharepoint-notifications"
            ),
            storage_account_url=account_url,
            storage_account_name=account_name,
            storage_input_container=config["storage"]["input_container"],
            storage_reference_container=reference_container,
            storage_capabilities_blob=capabilities_blob,
            storage_output_container=config["storage"]["output_container"],
            prompts_container=storage_config.get("prompts_container", "prompts"),
            system_prompt_blob=prompts_cfg.get("system_prompt_blob", "prompts/system_prompt.txt"),
            user_prompt_blob=prompts_cfg.get("user_prompt_blob", "prompts/user_prompt.txt"),
            chunk_system_prompt_blob=prompts_cfg.get("chunk_system_prompt_blob", "prompts/chunk_system_prompt.txt"),
            chunk_user_prompt_blob=prompts_cfg.get("chunk_user_prompt_blob", "prompts/chunk_user_prompt.txt"),
            reconcile_system_prompt_blob=prompts_cfg.get("reconcile_system_prompt_blob", "prompts/reconcile_system_prompt.txt"),
            reconcile_user_prompt_blob=prompts_cfg.get("reconcile_user_prompt_blob", "prompts/reconcile_user_prompt.txt"),
            schema_blob_path=schemas_cfg.get("full_blob_path", "schemas/rfp_fields_schema.json"),
            chunk_schema_blob_path=schemas_cfg.get("chunk_blob_path", "schemas/rfp_fields_chunk_schema.json"),
            sql_server=config["sql"]["server"],
            sql_database=config["sql"]["database"],
            sql_schema=config["sql"]["schema"],
            sql_table=config["sql"]["table"],
            sql_driver=config["sql"]["driver"],
            sql_encrypt=config["sql"]["encrypt"],
            sql_trust_server_certificate=config["sql"]["trust_server_certificate"],
        )
