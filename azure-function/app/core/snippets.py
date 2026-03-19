import re
from concurrent.futures import ThreadPoolExecutor

from app.core.chunking import extract_page_number, split_pages


class SnippetGenerator:
    def __init__(self, snippet_size: int) -> None:
        if snippet_size <= 0:
            raise ValueError("snippet_size must be positive.")
        self.snippet_size = snippet_size

    def top_snippets(
        self,
        value_text: str,
        chunks: list[dict],
        top_n: int,
        allowed_pages: set[int] | None = None,
        page_overlap: int = 0,
    ) -> list[str]:
        if top_n <= 0:
            return []
        target_words = self._normalize_words(value_text, include_numeric=False)
        allow_numeric = False
        if not target_words:
            target_words = self._normalize_words(value_text, include_numeric=True)
            allow_numeric = True
        if not target_words:
            return []
        allowed = _expand_pages(allowed_pages or set(), page_overlap)
        return self._snippets_from_pages(
            chunks,
            target_words,
            top_n,
            allowed,
            allow_numeric,
        )

    def _snippet_from_chunk(
        self,
        chunk: dict,
        target_words: set[str],
        allow_numeric: bool,
    ) -> str:
        normalized_words = (
            chunk["normalized_words"]
            if allow_numeric
            else chunk["normalized_non_numeric_words"]
        )
        if not normalized_words:
            return ""
        match_indexes = [
            idx
            for idx, word in enumerate(normalized_words)
            if word and word in target_words
        ]
        if not match_indexes:
            return ""
        best_window = None
        best_score = -1
        for idx in match_indexes:
            start = max(0, idx - self.snippet_size)
            end = min(len(chunk["words"]), idx + self.snippet_size + 1)
            score = sum(
                1
                for word in normalized_words[start:end]
                if word and word in target_words
            )
            if score > best_score:
                best_score = score
                best_window = (start, end)
        if not best_window:
            return ""
        start, end = best_window
        return " ".join(chunk["words"][start:end])

    def _snippets_from_pages(
        self,
        chunks: list[dict],
        target_words: set[str],
        top_n: int,
        allowed_pages: set[int],
        allow_numeric: bool,
    ) -> list[str]:
        filtered_chunks = _filter_chunks_by_pages(chunks, allowed_pages)
        if not filtered_chunks:
            return []
        scored = []
        for chunk in filtered_chunks:
            normalized = (
                chunk["normalized"] if allow_numeric else chunk["normalized_non_numeric"]
            )
            score = len(target_words & normalized)
            scored.append((score, chunk["index"], chunk))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if not scored or scored[0][0] == 0:
            return []
        snippets = []
        for score, _, chunk in scored[:top_n]:
            if score == 0:
                continue
            snippet = self._snippet_from_chunk(chunk, target_words, allow_numeric)
            if snippet:
                snippets.append(snippet)
        return snippets

    @staticmethod
    def _normalize_words(text: str, include_numeric: bool) -> set[str]:
        words = {word.lower() for word in re.findall(r"[A-Za-z0-9']+", text)}
        if include_numeric:
            return words
        return {word for word in words if not word.isdigit()}


def build_page_chunks(
    rfp_text: str,
    page_separator: str,
    fallback_chunk_size: int,
) -> list[dict]:
    pages = split_pages(rfp_text, page_separator)
    chunks: list[dict] = []
    page_numbers = []
    for index, page in enumerate(pages, start=1):
        page_number = extract_page_number(page)
        if page_number is not None:
            page_numbers.append(page_number)
        chunks.append(_build_chunk(page, [page_number] if page_number else [], index))
    if any(page_numbers):
        return chunks
    return _build_word_chunks(rfp_text, fallback_chunk_size)


def _build_chunk(text: str, pages: list[int], index: int) -> dict:
    words, normalized_words, normalized_non_numeric_words = _tokenize_words(text)
    return {
        "index": index,
        "pages": [page for page in pages if isinstance(page, int)],
        "words": words,
        "normalized_words": normalized_words,
        "normalized_non_numeric_words": normalized_non_numeric_words,
        "normalized": {word for word in normalized_words if word},
        "normalized_non_numeric": {
            word for word in normalized_non_numeric_words if word
        },
    }


def _build_word_chunks(text: str, chunk_size: int) -> list[dict]:
    if chunk_size <= 0:
        return []
    words, normalized_words, normalized_non_numeric_words = _tokenize_words(text)
    chunks: list[dict] = []
    for start in range(0, len(words), chunk_size):
        end = min(len(words), start + chunk_size)
        chunk_words = words[start:end]
        chunk_norm_words = normalized_words[start:end]
        chunk_norm_non_numeric = normalized_non_numeric_words[start:end]
        chunks.append(
            {
                "index": start // chunk_size,
                "pages": [],
                "words": chunk_words,
                "normalized_words": chunk_norm_words,
                "normalized_non_numeric_words": chunk_norm_non_numeric,
                "normalized": {word for word in chunk_norm_words if word},
                "normalized_non_numeric": {
                    word for word in chunk_norm_non_numeric if word
                },
            }
        )
    return chunks


def _tokenize_words(text: str) -> tuple[list[str], list[str], list[str]]:
    words = text.split()
    normalized = []
    normalized_non_numeric = []
    for word in words:
        cleaned = re.findall(r"[A-Za-z0-9']+", word)
        token = cleaned[0].lower() if cleaned else ""
        normalized.append(token)
        normalized_non_numeric.append("" if token.isdigit() else token)
    return words, normalized, normalized_non_numeric


def _expand_pages(pages: set[int], overlap: int) -> set[int]:
    if not pages:
        return set()
    if overlap <= 0:
        return set(pages)
    expanded = set()
    for page in pages:
        if page <= 0:
            continue
        for offset in range(-overlap, overlap + 1):
            candidate = page + offset
            if candidate > 0:
                expanded.add(candidate)
    return expanded


def _filter_chunks_by_pages(chunks: list[dict], allowed_pages: set[int]) -> list[dict]:
    if not allowed_pages:
        return chunks
    filtered = []
    for chunk in chunks:
        if not chunk["pages"]:
            continue
        if set(chunk["pages"]) & allowed_pages:
            filtered.append(chunk)
    return filtered


def add_snippets_to_result(
    result: dict,
    generator: SnippetGenerator,
    chunks: list[dict],
    top_n_by_field: dict[str, int],
    page_overlap: int,
) -> None:
    all_pages = _collect_pages(result)
    summary_text = result.get("summary", "")
    fee_items = result.get("fee", [])
    date_items = result.get("date", [])
    best_lead_items = result.get("best_lead_org", [])
    cross_sell_items = result.get("cross_sell_opps", [])
    capabilities_items = result.get("capabilities_for_rfp", [])
    diversity = result.get("diversity_allocation", {})

    with ThreadPoolExecutor() as executor:
        summary_future = executor.submit(
            generator.top_snippets,
            summary_text,
            chunks,
            top_n_by_field.get("summary", 0),
            all_pages,
            page_overlap,
        )
        fee_futures = [
            executor.submit(
                generator.top_snippets,
                fee_item.get("fee", ""),
                chunks,
                top_n_by_field.get("fee", 0),
                _pages_from_item(fee_item),
                page_overlap,
            )
            for fee_item in fee_items
        ]
        date_futures = [
            executor.submit(
                generator.top_snippets,
                date_item.get("date", ""),
                chunks,
                top_n_by_field.get("date", 0),
                _pages_from_item(date_item),
                page_overlap,
            )
            for date_item in date_items
        ]
        best_lead_futures = [
            executor.submit(
                generator.top_snippets,
                item.get("reason", ""),
                chunks,
                top_n_by_field.get("best_lead_org", 0),
                _pages_from_item(item),
                page_overlap,
            )
            for item in best_lead_items
        ]
        cross_sell_futures = [
            executor.submit(
                generator.top_snippets,
                item.get("reason", ""),
                chunks,
                top_n_by_field.get("cross_sell_opps", 0),
                _pages_from_item(item),
                page_overlap,
            )
            for item in cross_sell_items
        ]
        capabilities_futures = [
            executor.submit(
                generator.top_snippets,
                item.get("reason", ""),
                chunks,
                top_n_by_field.get("capabilities_for_rfp", 0),
                _pages_from_item(item),
                page_overlap,
            )
            for item in capabilities_items
        ]
        diversity_future = executor.submit(
            generator.top_snippets,
            diversity.get("reason", ""),
            chunks,
            top_n_by_field.get("diversity_allocation", 0),
            _pages_from_item(diversity),
            page_overlap,
        )

        result["summary"] = {
            "summary": summary_text,
            "snippets": summary_future.result(),
        }
        for fee_item, future in zip(fee_items, fee_futures):
            fee_item["snippets"] = future.result()
        for date_item, future in zip(date_items, date_futures):
            date_item["snippets"] = future.result()
        for item, future in zip(best_lead_items, best_lead_futures):
            item["snippets"] = future.result()
        for item, future in zip(cross_sell_items, cross_sell_futures):
            item["snippets"] = future.result()
        for item, future in zip(capabilities_items, capabilities_futures):
            item["snippets"] = future.result()
        diversity["snippets"] = diversity_future.result()
        result["diversity_allocation"] = diversity




def _pages_from_item(item: dict) -> set[int]:
    pages = item.get("pages") or []
    parsed: set[int] = set()
    for page in pages:
        if isinstance(page, int):
            parsed.add(page)
            continue
        if isinstance(page, str):
            for token in re.split(r"[,;\s]+", page.strip()):
                if token.isdigit():
                    parsed.add(int(token))
    return parsed


def _collect_pages(result: dict) -> set[int]:
    pages: set[int] = set()
    for collection_key in [
        "fee",
        "date",
        "best_lead_org",
        "cross_sell_opps",
        "capabilities_for_rfp",
    ]:
        for entry in result.get(collection_key, []) or []:
            pages.update(_pages_from_item(entry))
    diversity = result.get("diversity_allocation") or {}
    pages.update(_pages_from_item(diversity))
    return pages
