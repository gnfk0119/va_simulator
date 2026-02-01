from __future__ import annotations

import json
import os
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


def query_llm(
    prompt: str,
    system_role: str,
    model_schema: Optional[Type[Any]] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_retries: int = 2,
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
    for _ in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = _extract_json(content)
            if model_schema is not None:
                return _validate_schema(model_schema, data)
            return data
        except Exception as exc:  # noqa: BLE001 - surface error on final retry
            last_error = exc

    raise LLMError(f"LLM request failed: {last_error}")
