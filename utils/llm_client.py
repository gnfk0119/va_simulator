from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Optional, Type

from dotenv import load_dotenv


class LLMError(RuntimeError):
    pass


def _load_env() -> None:
    load_dotenv()


def _get_api_key() -> str:
    _load_env()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMError("OPENAI_API_KEY is not set. Please add it to .env")
    return api_key


def _extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _validate_schema(schema: Type[Any], data: Dict[str, Any]) -> Dict[str, Any]:
    # Support Pydantic v1 and v2
    if hasattr(schema, "model_validate"):
        obj = schema.model_validate(data)
        return obj.model_dump()
    obj = schema.parse_obj(data)
    return obj.dict()


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "rate limit" in text or "429" in text or "rate_limit_exceeded" in text


def _parse_retry_after_seconds(exc: Exception) -> float:
    text = str(exc).lower()
    # Example: "Please try again in 330ms."
    ms_match = re.search(r"try again in\\s+([0-9]+(?:\\.[0-9]+)?)ms", text)
    if ms_match:
        return max(0.2, float(ms_match.group(1)) / 1000.0)

    sec_match = re.search(r"try again in\\s+([0-9]+(?:\\.[0-9]+)?)s", text)
    if sec_match:
        return max(0.2, float(sec_match.group(1)))

    return 1.0


def query_llm(
    prompt: str,
    system_role: str,
    model_schema: Optional[Type[Any]] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_retries: int = 6,
    request_timeout: float = 45.0,
) -> Dict[str, Any]:
    """Query OpenAI and return a JSON dict.

    The model is instructed to return JSON only via response_format.
    """
    from openai import OpenAI

    api_key = _get_api_key()
    client = OpenAI(api_key=api_key)
    model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    messages = [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt},
    ]

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                timeout=request_timeout,
            )
            content = response.choices[0].message.content or "{}"
            data = _extract_json(content)
            if model_schema is not None:
                return _validate_schema(model_schema, data)
            return data
        except Exception as exc:  # noqa: BLE001 - surface error on final retry
            last_error = exc
            if attempt >= max_retries - 1:
                break

            if _is_rate_limit_error(exc):
                sleep_for = _parse_retry_after_seconds(exc) + min(2.0, attempt * 0.3)
            else:
                sleep_for = min(2.0, 0.5 + attempt * 0.2)
            time.sleep(sleep_for)

    raise LLMError(f"LLM request failed: {last_error}")
