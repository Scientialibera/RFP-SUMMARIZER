from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken


PAGE_MARKER_PATTERN = re.compile(r"PAGE NUMBER TO REFERENCE:\s*(\d+)")


@dataclass(frozen=True)
class RfpChunk:
    text: str
    pages: list[int]
    token_estimate: int


def split_pages(rfp_text: str, separator: str) -> list[str]:
    if not rfp_text:
        return []
    token = f"\n{separator}\n"
    parts = rfp_text.split(token)
    return [part.strip() for part in parts if part.strip()]


def extract_page_number(page_text: str) -> int | None:
    match = PAGE_MARKER_PATTERN.search(page_text)
    if not match:
        return None
    return int(match.group(1))


@lru_cache(maxsize=4)
def _get_encoder(model: str | None) -> tiktoken.Encoding:
    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            pass
    return tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str, model: str | None = None) -> int:
    if not text:
        return 0
    encoder = _get_encoder(model)
    return len(encoder.encode(text))


def build_chunks(
    pages: list[str],
    separator: str,
    max_tokens: int,
    model: str | None = None,
) -> list[RfpChunk]:
    if not pages:
        return []
    if max_tokens <= 0:
        joined = f"\n{separator}\n".join(pages)
        page_numbers = [p for p in (extract_page_number(page) for page in pages) if p]
        return [
            RfpChunk(
                text=joined,
                pages=page_numbers,
                token_estimate=estimate_tokens(joined, model),
            )
        ]

    chunks: list[RfpChunk] = []
    current_pages: list[str] = []
    current_page_numbers: list[int] = []
    current_tokens = 0

    for page in pages:
        page_tokens = estimate_tokens(page, model)
        if current_pages and current_tokens + page_tokens > max_tokens:
            chunk_text = f"\n{separator}\n".join(current_pages)
            chunks.append(
                RfpChunk(
                    text=chunk_text,
                    pages=current_page_numbers,
                    token_estimate=current_tokens,
                )
            )
            current_pages = []
            current_page_numbers = []
            current_tokens = 0

        current_pages.append(page)
        page_number = extract_page_number(page)
        if page_number is not None:
            current_page_numbers.append(page_number)
        current_tokens += page_tokens

    if current_pages:
        chunk_text = f"\n{separator}\n".join(current_pages)
        chunks.append(
            RfpChunk(
                text=chunk_text,
                pages=current_page_numbers,
                token_estimate=current_tokens,
            )
        )

    return chunks


def extract_page_from_filename(filename: str) -> int | None:
    match = re.search(r"_page_(\d+)\.png$", filename)
    if not match:
        return None
    return int(match.group(1))
