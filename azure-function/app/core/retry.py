from __future__ import annotations

import logging
import time
from typing import Callable, Iterable

from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from requests import RequestException

logger = logging.getLogger("rfp_function.retry")


def retry_external_call(
    func: Callable[..., object],
    *,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
    retry_exceptions: Iterable[type[BaseException]] | None = None,
) -> Callable[..., object]:
    exceptions = tuple(retry_exceptions) if retry_exceptions else _default_retry_exceptions()

    def wrapper(*args, **kwargs):
        attempt = 0
        while True:
            try:
                return func(*args, **kwargs)
            except exceptions as exc:
                attempt += 1
                if _is_auth_error(exc) or attempt > max_retries:
                    raise
                sleep_for = backoff_seconds * (2 ** (attempt - 1))
                logger.info(
                    "Retrying external call after error=%s attempt=%s wait=%.1fs",
                    type(exc).__name__,
                    attempt,
                    sleep_for,
                )
                time.sleep(sleep_for)

    return wrapper


def _default_retry_exceptions() -> tuple[type[BaseException], ...]:
    return (
        ServiceRequestError,
        ServiceResponseError,
        HttpResponseError,
        APIConnectionError,
        APITimeoutError,
        APIError,
        RateLimitError,
        RequestException,
    )


def _is_auth_error(exc: BaseException) -> bool:
    if isinstance(exc, (ClientAuthenticationError, AuthenticationError, PermissionDeniedError)):
        return True
    if isinstance(exc, HttpResponseError):
        status = getattr(exc, "status_code", None)
        if status in {401, 403}:
            return True
    return False
