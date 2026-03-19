from __future__ import annotations

import json
import shutil
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config.config import RfpConfig
from app.core.azure_client import AzureRfpExtractor
from app.core.chunking import build_chunks, extract_page_from_filename, split_pages
from app.core.pdf_text import PdfTextExtractor
from app.core.snippets import (
    SnippetGenerator,
    add_snippets_to_result,
    build_page_chunks,
)
from app.prompts.prompt import (
    build_chunk_system_prompt,
    build_chunk_user_prompt,
    build_reconcile_system_prompt,
    build_reconcile_user_prompt,
    build_system_prompt,
    build_user_prompt,
)

logger = logging.getLogger("rfp_function.analysis")


@dataclass(frozen=True)
class ExtractionArtifacts:
    timestamp: str
    output_path: Path
    fed_context_path: Path
    assets_dir: Path
    result: dict
    rfp_pdf_path: Path
    stored_pdf_path: Path | None


def resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def _prompt_kwargs(config: RfpConfig) -> dict:
    return {
        "account_url": config.storage_account_url,
        "container": config.prompts_container,
    }


@dataclass(frozen=True)
class _ExtractionContext:
    """Shared state produced by the common setup phase of both extraction paths."""
    run_timestamp: str
    output_dir: Path
    run_dir: Path
    assets_dir: Path
    rfp_pdf_path: Path
    stored_pdf_path: Path | None
    rfp_extractor: PdfTextExtractor
    capabilities_text: str
    rfp_text: str
    snippet_text: str
    rfp_result: object
    pages: list[str]
    pdf_elapsed_ms: int


def _prepare_extraction(
    config: RfpConfig,
    base_dir: Path,
    rfp_pdf_override: Path | None,
    timestamp: str,
    persist_source_pdf: bool,
    export_table_images: bool | None,
    export_page_images: bool | None,
) -> _ExtractionContext:
    output_dir = resolve_path(base_dir, config.output_dir)
    uploads_dir = resolve_path(base_dir, config.uploads_dir)
    fed_context_dir = resolve_path(base_dir, config.fed_context_dir)
    capabilities_pdf = resolve_path(base_dir, config.capabilities_pdf)
    if rfp_pdf_override is None:
        raise ValueError("rfp_pdf_override is required for Azure Function runs.")

    output_dir.mkdir(parents=True, exist_ok=True)
    fed_context_dir.mkdir(parents=True, exist_ok=True)
    run_dir = fed_context_dir / "runs" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    stored_pdf_path = None
    if persist_source_pdf:
        uploads_dir.mkdir(parents=True, exist_ok=True)
        stored_pdf_path = uploads_dir / f"rfp_source_{timestamp}.pdf"
        shutil.copy2(rfp_pdf_override, stored_pdf_path)

    capabilities_extractor = PdfTextExtractor(include_page_markers=False)
    rfp_extractor = PdfTextExtractor(include_page_markers=True)

    t0 = time.perf_counter()
    capabilities_text = capabilities_extractor.extract_text(capabilities_pdf)

    assets_dir = run_dir / "assets"
    rfp_result = rfp_extractor.extract_with_assets(
        rfp_pdf_override,
        image_output_dir=assets_dir,
        export_table_images=export_table_images
        if export_table_images is not None
        else config.toggle_table,
        export_page_images=export_page_images
        if export_page_images is not None
        else config.toggle_images,
        min_table_rows=config.min_table_rows,
        min_table_cols=config.min_table_cols,
        include_table_text=config.include_table_text,
    )
    rfp_text = rfp_result.text
    pdf_elapsed = round((time.perf_counter() - t0) * 1000)

    snippet_text = rfp_text
    if not config.include_table_text:
        snippet_text = rfp_extractor.extract_text_with_tables(
            rfp_pdf_override,
            min_table_rows=config.min_table_rows,
            min_table_cols=config.min_table_cols,
        )
    pages = split_pages(rfp_text, rfp_extractor.page_separator)
    logger.info(json.dumps({
        "event": "pdf_extraction",
        "elapsed_ms": pdf_elapsed,
        "pages": len(pages),
        "images": len(rfp_result.image_paths),
        "text_chars": len(rfp_text),
        "source": "pdfplumber",
    }, default=str))

    return _ExtractionContext(
        run_timestamp=timestamp,
        output_dir=output_dir,
        run_dir=run_dir,
        assets_dir=assets_dir,
        rfp_pdf_path=rfp_pdf_override,
        stored_pdf_path=stored_pdf_path,
        rfp_extractor=rfp_extractor,
        capabilities_text=capabilities_text,
        rfp_text=rfp_text,
        snippet_text=snippet_text,
        rfp_result=rfp_result,
        pages=pages,
        pdf_elapsed_ms=pdf_elapsed,
    )


def _add_snippets(config: RfpConfig, result: dict, snippet_text: str, page_separator: str) -> None:
    snippet_generator = SnippetGenerator(snippet_size=config.snippet_size)
    snippet_chunks = build_page_chunks(snippet_text, page_separator, config.snippet_chunk_size)
    add_snippets_to_result(
        result,
        snippet_generator,
        snippet_chunks,
        {
            "summary": config.snippet_top_n_summary,
            "fee": config.snippet_top_n_fee,
            "date": config.snippet_top_n_date,
            "best_lead_org": config.snippet_top_n_best_lead_org,
            "cross_sell_opps": config.snippet_top_n_cross_sell_opps,
            "capabilities_for_rfp": config.snippet_top_n_capabilities_for_rfp,
            "diversity_allocation": config.snippet_top_n_diversity_allocation,
        },
        config.snippet_page_overlap,
    )


def run_extraction(
    config: RfpConfig,
    base_dir: Path,
    rfp_pdf_override: Path | None = None,
    timestamp: str | None = None,
    persist_source_pdf: bool = True,
    export_table_images: bool | None = None,
    export_page_images: bool | None = None,
) -> ExtractionArtifacts:
    run_timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if config.chunking_enabled:
        logger.info(
            "Starting extraction. chunking=enabled max_tokens=%s model=%s",
            config.chunking_max_tokens,
            config.model,
        )
        return run_extraction_chunked(
            config=config,
            base_dir=base_dir,
            rfp_pdf_override=rfp_pdf_override,
            timestamp=run_timestamp,
            persist_source_pdf=persist_source_pdf,
            export_table_images=export_table_images,
            export_page_images=export_page_images,
        )

    logger.info("Starting extraction. chunking=disabled model=%s", config.model)

    ctx = _prepare_extraction(
        config, base_dir, rfp_pdf_override, run_timestamp,
        persist_source_pdf, export_table_images, export_page_images,
    )

    image_paths = _limit_images(ctx.rfp_result.image_paths, config.max_attached_images)
    image_names = [path.name for path in image_paths]

    pk = _prompt_kwargs(config)
    user_message = build_user_prompt(
        ctx.rfp_text, image_names, blob_path=config.user_prompt_blob, **pk,
    )
    fed_context_path = ctx.run_dir / "fed_context.txt"
    fed_context_path.write_text(user_message, encoding="utf-8")

    system_prompt = build_system_prompt(
        ctx.capabilities_text, blob_path=config.system_prompt_blob, **pk,
    )
    extractor = AzureRfpExtractor.from_blob(
        endpoint=config.endpoint,
        model=config.model,
        account_url=config.storage_account_url,
        container=config.prompts_container,
        schema_blob_path=config.schema_blob_path,
        api_version=config.api_version,
    )
    result = extractor.extract_fields(
        system_prompt,
        user_message,
        image_paths,
    )

    _add_snippets(config, result, ctx.snippet_text, ctx.rfp_extractor.page_separator)

    output_path = ctx.output_dir / f"rfp_fields_{run_timestamp}.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return ExtractionArtifacts(
        timestamp=run_timestamp,
        output_path=output_path,
        fed_context_path=fed_context_path,
        assets_dir=ctx.assets_dir,
        result=result,
        rfp_pdf_path=ctx.rfp_pdf_path,
        stored_pdf_path=ctx.stored_pdf_path,
    )


def run_extraction_chunked(
    config: RfpConfig,
    base_dir: Path,
    rfp_pdf_override: Path | None = None,
    timestamp: str | None = None,
    persist_source_pdf: bool = True,
    export_table_images: bool | None = None,
    export_page_images: bool | None = None,
) -> ExtractionArtifacts:
    total_start = time.perf_counter()
    run_timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    ctx = _prepare_extraction(
        config, base_dir, rfp_pdf_override, run_timestamp,
        persist_source_pdf, export_table_images, export_page_images,
    )
    intermediate_dir = ctx.run_dir / "intermediate"
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    chunks = build_chunks(
        ctx.pages,
        ctx.rfp_extractor.page_separator,
        config.chunking_max_tokens,
        model=config.model,
    )
    if not chunks and ctx.rfp_text.strip():
        chunks = build_chunks(
            [ctx.rfp_text],
            ctx.rfp_extractor.page_separator,
            config.chunking_max_tokens,
            model=config.model,
        )
    pages_per_chunk = [len(chunk.pages) for chunk in chunks]
    logger.info(json.dumps({
        "event": "chunking",
        "chunks": len(chunks),
        "pages_per_chunk": pages_per_chunk,
    }, default=str))

    pk = _prompt_kwargs(config)
    chunk_extractor = AzureRfpExtractor.from_blob(
        endpoint=config.endpoint,
        model=config.model,
        account_url=config.storage_account_url,
        container=config.prompts_container,
        schema_blob_path=config.chunk_schema_blob_path,
        api_version=config.api_version,
    )
    chunk_system_prompt = build_chunk_system_prompt(
        ctx.capabilities_text, blob_path=config.chunk_system_prompt_blob, **pk,
    )

    aggregated_fee: list[dict] = []
    aggregated_date: list[dict] = []
    aggregated_diversity: list[dict] = []
    aggregated_best_lead: list[dict] = []
    aggregated_cross_sell: list[dict] = []
    aggregated_capabilities: list[dict] = []
    chunk_summaries: list[dict] = []
    previous_summary = ""
    fed_context_messages: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        logger.info(
            "Chunk %s pages=%s tokens_est=%s",
            index,
            chunk.pages,
            chunk.token_estimate,
        )
        previous_payload = {
            "summary": previous_summary,
            "fee": aggregated_fee,
            "date": aggregated_date,
            "best_lead_org": aggregated_best_lead,
            "cross_sell_opps": aggregated_cross_sell,
            "capabilities_for_rfp": aggregated_capabilities,
            "diversity_allocation": aggregated_diversity,
        }
        has_previous = any(
            value
            for key, value in previous_payload.items()
            if key != "summary"
        ) or bool(previous_summary.strip())
        previous_extractions = (
            json.dumps(previous_payload, indent=2) if has_previous else ""
        )
        chunk_images = _select_images_for_pages(ctx.rfp_result.image_paths, chunk.pages)
        chunk_images = _limit_images(chunk_images, config.max_attached_images)
        user_message = build_chunk_user_prompt(
            chunk.text,
            previous_summary,
            previous_extractions,
            image_names=[path.name for path in chunk_images],
            part_label=f"RFP Part {index}",
            blob_path=config.chunk_user_prompt_blob,
            **pk,
        )
        part_header = (
            f"RFP PART {index} OF {len(chunks)}\n"
            f"PAGES: {chunk.pages}\n"
        )
        fed_context_messages.append(f"{part_header}{user_message}")

        chunk_result = chunk_extractor.extract_fields(
            chunk_system_prompt,
            user_message,
            chunk_images,
        )
        chunk_path = intermediate_dir / f"chunk_{index:02d}.json"
        chunk_path.write_text(json.dumps(chunk_result, indent=2), encoding="utf-8")

        chunk_summary = (chunk_result.get("summary") or "").strip()
        pages_covered = chunk.pages
        chunk_summaries.append(
            {
                "summary": chunk_summary,
                "pages": pages_covered,
            }
        )
        if chunk_summary:
            previous_summary = "\n".join([previous_summary, chunk_summary]).strip()

        aggregated_fee.extend(chunk_result.get("fee") or [])
        aggregated_date.extend(chunk_result.get("date") or [])
        diversity_entry = chunk_result.get("diversity_allocation")
        if _has_diversity_signal(diversity_entry):
            aggregated_diversity.append(diversity_entry)
        aggregated_best_lead.extend(chunk_result.get("best_lead_org") or [])
        aggregated_cross_sell.extend(chunk_result.get("cross_sell_opps") or [])
        aggregated_capabilities.extend(chunk_result.get("capabilities_for_rfp") or [])

    reconcile_candidates = json.dumps(
        {
            "fee": aggregated_fee,
            "date": aggregated_date,
            "diversity_allocation_candidates": aggregated_diversity,
            "best_lead_org_candidates": aggregated_best_lead,
            "cross_sell_opps_candidates": aggregated_cross_sell,
            "capabilities_for_rfp_candidates": aggregated_capabilities,
        },
        indent=2,
    )
    reconciliation_failures = _format_reconciliation_failures(
        aggregated_fee,
        aggregated_date,
        aggregated_diversity,
    )
    reconcile_user_message = build_reconcile_user_prompt(
        reconcile_candidates,
        json.dumps(chunk_summaries, indent=2),
        reconciliation_failures,
        blob_path=config.reconcile_user_prompt_blob,
        **pk,
    )
    reconcile_input_path = intermediate_dir / "reconcile_input.json"
    reconcile_input_path.write_text(
        json.dumps(
            {
                "chunk_summaries": chunk_summaries,
                "candidates": json.loads(reconcile_candidates),
                "reconciliation_failures": reconciliation_failures,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    fed_context_messages.append(f"RECONCILIATION\n{reconcile_user_message}")

    reconcile_extractor = AzureRfpExtractor.from_blob(
        endpoint=config.endpoint,
        model=config.model,
        account_url=config.storage_account_url,
        container=config.prompts_container,
        schema_blob_path=config.schema_blob_path,
        api_version=config.api_version,
    )
    reconcile_system = build_reconcile_system_prompt(
        ctx.capabilities_text, blob_path=config.reconcile_system_prompt_blob, **pk,
    )
    result = reconcile_extractor.extract_fields(
        reconcile_system,
        reconcile_user_message,
    )
    reconcile_output_path = intermediate_dir / "reconcile_output.json"
    reconcile_output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    _add_snippets(config, result, ctx.snippet_text, ctx.rfp_extractor.page_separator)

    fed_context_path = ctx.run_dir / "fed_context.txt"
    fed_context_path.write_text("\n\n".join(fed_context_messages), encoding="utf-8")

    output_path = ctx.output_dir / f"rfp_fields_{run_timestamp}.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    total_ms = round((time.perf_counter() - total_start) * 1000)
    logger.info(json.dumps({
        "event": "extraction_summary",
        "total_ms": total_ms,
        "chunks": len(chunks),
        "pages": len(ctx.pages),
        "model": config.model,
    }, default=str))

    return ExtractionArtifacts(
        timestamp=run_timestamp,
        output_path=output_path,
        fed_context_path=fed_context_path,
        assets_dir=ctx.assets_dir,
        result=result,
        rfp_pdf_path=ctx.rfp_pdf_path,
        stored_pdf_path=ctx.stored_pdf_path,
    )


def _select_images_for_pages(image_paths: list[Path], pages: list[int]) -> list[Path]:
    if not image_paths or not pages:
        return []
    page_set = set(pages)
    selected = []
    for path in image_paths:
        page_number = extract_page_from_filename(path.name)
        if page_number in page_set:
            selected.append(path)
    return selected


def _limit_images(image_paths: list[Path], max_images: int) -> list[Path]:
    if max_images <= 0:
        return []
    if len(image_paths) <= max_images:
        return image_paths
    def _priority(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if "table_" in name:
            return (0, name)
        if "image_" in name:
            return (1, name)
        return (2, name)

    sorted_paths = sorted(image_paths, key=_priority)
    return sorted_paths[:max_images]


def _has_diversity_signal(diversity_entry: dict | None) -> bool:
    if not isinstance(diversity_entry, dict):
        return False
    pages = diversity_entry.get("pages") or []
    if pages:
        return True
    return bool(diversity_entry.get("diversity_allocation"))


def _format_reconciliation_failures(
    fee_entries: list[dict],
    date_entries: list[dict],
    diversity_entries: list[dict],
) -> str:
    lines: list[str] = []
    fee_groups: dict[str, dict[str, set[int]]] = {}
    for entry in fee_entries:
        fee_type = (entry.get("fee_type") or "unknown").strip()
        fee_value = (entry.get("fee") or "").strip()
        pages = {int(p) for p in (entry.get("pages") or []) if isinstance(p, int)}
        fee_groups.setdefault(fee_type, {}).setdefault(fee_value, set()).update(pages)
    for fee_type, values in fee_groups.items():
        if len(values) > 1:
            lines.append(f"fee_type={fee_type} conflicts:")
            for value, pages in values.items():
                lines.append(f"- value={value} pages={sorted(pages)}")

    date_groups: dict[str, dict[str, set[int]]] = {}
    for entry in date_entries:
        date_type = (entry.get("date_type") or "unknown").strip()
        date_value = (entry.get("date") or "").strip()
        pages = {int(p) for p in (entry.get("pages") or []) if isinstance(p, int)}
        date_groups.setdefault(date_type, {}).setdefault(date_value, set()).update(pages)
    for date_type, values in date_groups.items():
        if len(values) > 1:
            lines.append(f"date_type={date_type} conflicts:")
            for value, pages in values.items():
                lines.append(f"- value={value} pages={sorted(pages)}")

    diversity_values = {}
    for entry in diversity_entries:
        if not isinstance(entry, dict):
            continue
        value = entry.get("diversity_allocation")
        pages = {int(p) for p in (entry.get("pages") or []) if isinstance(p, int)}
        diversity_values.setdefault(value, set()).update(pages)
    if len(diversity_values) > 1:
        lines.append("diversity_allocation conflicts:")
        for value, pages in diversity_values.items():
            lines.append(f"- value={value} pages={sorted(pages)}")

    if not lines:
        return "None"
    return "\n".join(lines)
