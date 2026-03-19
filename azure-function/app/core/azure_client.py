from __future__ import annotations

import base64
import json
import logging
import time
from functools import lru_cache
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI

from app.core.retry import retry_external_call

logger = logging.getLogger("rfp_function.openai")

_credential = DefaultAzureCredential()


@lru_cache(maxsize=4)
def _download_schema(account_url: str, container: str, blob_path: str) -> dict:
    client = BlobServiceClient(account_url=account_url, credential=_credential)
    blob = client.get_blob_client(container, blob_path)
    raw = blob.download_blob().readall().decode("utf-8")
    return json.loads(raw)


class AzureRfpExtractor:
    def __init__(
        self,
        endpoint: str,
        model: str,
        schema: dict | None = None,
        schema_path: Path | None = None,
        api_version: str = "2025-01-01-preview",
    ) -> None:
        token_provider = get_bearer_token_provider(
            _credential,
            "https://cognitiveservices.azure.com/.default",
        )
        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version,
            azure_ad_token_provider=token_provider,
        )
        self.model = model
        if schema is not None:
            self.schema = schema
        elif schema_path is not None:
            self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        else:
            raise ValueError("Either schema or schema_path must be provided.")

    @classmethod
    def from_blob(
        cls,
        endpoint: str,
        model: str,
        account_url: str,
        container: str,
        schema_blob_path: str,
        api_version: str = "2025-01-01-preview",
    ) -> "AzureRfpExtractor":
        schema = _download_schema(account_url, container, schema_blob_path)
        return cls(endpoint=endpoint, model=model, schema=schema, api_version=api_version)

    def extract_fields(
        self,
        system_prompt: str,
        user_message: str,
        image_paths: list[Path] | None = None,
    ) -> dict:
        tools = [{"type": "function", "function": self.schema}]
        user_content = self._build_user_content(user_message, image_paths or [])

        start = time.perf_counter()
        response = retry_external_call(
            self.client.chat.completions.create
        )(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            tools=tools,
            tool_choice={
                "type": "function",
                "function": {"name": self.schema["name"]},
            },
        )
        elapsed_ms = round((time.perf_counter() - start) * 1000)

        usage = response.usage
        logger.info(json.dumps({
            "event": "openai_api_call",
            "model": self.model,
            "elapsed_ms": elapsed_ms,
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
        }, default=str))

        choices = response.choices or []
        if not choices:
            raise ValueError("Model returned no choices.")

        message = choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            raise ValueError("Model response did not include a tool call.")

        arguments = tool_calls[0].function.arguments
        if not arguments:
            raise ValueError("Tool call returned empty arguments.")
        return json.loads(arguments)

    def _build_user_content(
        self,
        user_message: str,
        image_paths: list[Path],
    ) -> list[dict]:
        content: list[dict] = [{"type": "text", "text": user_message}]
        for path in image_paths:
            image_bytes = path.read_bytes()
            encoded = base64.b64encode(image_bytes).decode("ascii")
            content.append(
                {"type": "text", "text": f"Image attachment: {path.name}"}
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                }
            )
        return content
