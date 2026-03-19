from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass(frozen=True)
class PdfExtractionResult:
    text: str
    image_paths: list[Path]


class PdfTextExtractor:
    def __init__(
        self,
        page_separator: str | None = None,
        include_page_markers: bool = False,
    ) -> None:
        self.page_separator = page_separator or "##############################"
        self.include_page_markers = include_page_markers

    def extract_text(self, pdf_path: Path) -> str:
        return self._extract(pdf_path).text

    def extract_text_with_tables(
        self,
        pdf_path: Path,
        min_table_rows: int = 2,
        min_table_cols: int = 2,
    ) -> str:
        return self._extract(
            pdf_path,
            image_output_dir=None,
            export_table_images=False,
            export_page_images=False,
            min_table_rows=min_table_rows,
            min_table_cols=min_table_cols,
            include_table_text=True,
        ).text

    def extract_with_assets(
        self,
        pdf_path: Path,
        image_output_dir: Path,
        export_table_images: bool,
        export_page_images: bool,
        min_table_rows: int = 2,
        min_table_cols: int = 2,
        include_table_text: bool = True,
    ) -> PdfExtractionResult:
        return self._extract(
            pdf_path,
            image_output_dir=image_output_dir,
            export_table_images=export_table_images,
            export_page_images=export_page_images,
            min_table_rows=min_table_rows,
            min_table_cols=min_table_cols,
            include_table_text=include_table_text,
        )

    def _extract(
        self,
        pdf_path: Path,
        image_output_dir: Path | None = None,
        export_table_images: bool = False,
        export_page_images: bool = False,
        min_table_rows: int = 2,
        min_table_cols: int = 2,
        include_table_text: bool = True,
    ) -> PdfExtractionResult:
        pages = []
        image_paths: list[Path] = []
        table_counter = 0
        image_counter = 0

        if image_output_dir:
            image_output_dir.mkdir(parents=True, exist_ok=True)

        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                page_text = (page.extract_text() or "").strip()
                table_text = self._tables_to_text(
                    page,
                    min_table_rows,
                    min_table_cols,
                    include_table_text,
                )

                if table_text:
                    if page_text:
                        page_text = f"{page_text}\n\nTABLES:\n{table_text}"
                    else:
                        page_text = f"TABLES:\n{table_text}"

                if self.include_page_markers:
                    marker = f"PAGE NUMBER TO REFERENCE: {page_index}"
                    page_text = f"{marker}\n{page_text}".strip()

                pages.append(page_text)

                page_table_count = (
                    self._count_tables(page, min_table_rows, min_table_cols)
                    if export_table_images
                    else 0
                )
                page_image_count = 1 if (export_page_images and page.images) else 0
                if (page_table_count or page_image_count) and image_output_dir:
                    parts = []
                    if page_image_count:
                        start = image_counter + 1
                        end = image_counter + page_image_count
                        image_counter = end
                        image_range = (
                            f"image_{start}" if start == end else f"image_{start}_{end}"
                        )
                        parts.append(image_range)
                    if page_table_count:
                        start = table_counter + 1
                        end = table_counter + page_table_count
                        table_counter = end
                        table_range = (
                            f"table_{start}" if start == end else f"table_{start}_{end}"
                        )
                        parts.append(table_range)
                    filename = f"{'_'.join(parts)}_page_{page_index}.png"
                    image_path = image_output_dir / filename
                    self._save_page_image(page, image_path)
                    image_paths.append(image_path)
                    if page_image_count and page_table_count:
                        note_label = "IMAGE AND TABLE ATTACHMENT"
                    elif page_table_count:
                        note_label = "TABLE ATTACHMENT"
                    else:
                        note_label = "IMAGE ATTACHMENT"
                    page_note = f"{note_label}: {filename}"
                    if page_text:
                        page_text = f"{page_text}\n\n{page_note}"
                    else:
                        page_text = page_note
                    pages[-1] = page_text

        return PdfExtractionResult(
            text=f"\n{self.page_separator}\n".join(pages),
            image_paths=image_paths,
        )

    def _tables_to_text(
        self,
        page: pdfplumber.page.Page,
        min_rows: int,
        min_cols: int,
        include_table_text: bool,
    ) -> str:
        tables = page.extract_tables() or []
        formatted = []
        for table_index, table in enumerate(tables, start=1):
            row_count, col_count = self._table_dimensions(table)
            is_table = row_count >= min_rows and col_count >= min_cols
            if include_table_text:
                if not is_table:
                    continue
            else:
                if is_table:
                    continue
            rows = []
            for row in table:
                if not row:
                    continue
                cells = [(cell or "").strip() for cell in row]
                rows.append(" | ".join(cells).strip())
            if rows:
                table_block = "\n".join(rows)
                formatted.append(f"TABLE {table_index}:\n{table_block}")
        return "\n\n".join(formatted)

    def _count_tables(
        self,
        page: pdfplumber.page.Page,
        min_rows: int,
        min_cols: int,
    ) -> int:
        tables = page.find_tables() or []
        count = 0
        for table in tables:
            row_count, col_count = self._table_dimensions(table)
            if row_count >= min_rows and col_count >= min_cols:
                count += 1
        return count

    @staticmethod
    def _table_dimensions(table) -> tuple[int, int]:
        if hasattr(table, "rows"):
            rows = table.rows or []
            row_count = len(rows)
            col_count = max(
                (len(getattr(row, "cells", []) or []) for row in rows),
                default=0,
            )
            return row_count, col_count
        rows = table or []
        row_count = len(rows)
        col_count = max((len(row or []) for row in rows), default=0)
        return row_count, col_count

    def _save_page_image(self, page: pdfplumber.page.Page, output_path: Path) -> None:
        page_image = page.to_image(resolution=150)
        page_image.save(str(output_path), format="PNG")
