from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Optional, Type, Union

from dotenv import load_dotenv

class LLMError(RuntimeError):
    pass

def _load_env() -> None:
    load_dotenv()

def _get_api_key(provider: str) -> str:
    _load_env()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise LLMError("OPENAI_API_KEY is not set. Please add it to .env")
        return api_key
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set. Please add it to .env")
        return api_key
    return ""

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
    return "rate limit" in text or "429" in text or "rate_limit_exceeded" in text or "quota" in text

def _parse_retry_after_seconds(exc: Exception) -> float:
    text = str(exc).lower()
    ms_match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)ms", text)
    if ms_match:
        return max(0.2, float(ms_match.group(1)) / 1000.0)
    sec_match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", text)
    if sec_match:
        return max(0.2, float(sec_match.group(1)))
    return 1.0

def _query_openai(
    api_key: str,
    model_name: str,
    prompt: str,
    system_role: str,
    temperature: float,
    timeout: float
) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    messages = [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt},
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        response_format={"type": "json_object"},
        timeout=timeout,
    )
    return response.choices[0].message.content or "{}"

def _query_gemini(
    api_key: str,
    model_name: str,
    prompt: str,
    system_role: str,
    temperature: float
) -> str:
    # Use google-genai library as intended
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    
    config = types.GenerateContentConfig(
        system_instruction=system_role,
        response_mime_type="application/json",
    )
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=config,
    )
    return response.text or "{}"

def query_llm(
    prompt: str,
    system_role: str,
    model_schema: Optional[Type[Any]] = None,
    model: Union[str, Dict[str, str], None] = None,
    temperature: float = 0.3,
    max_retries: int = 6,
    request_timeout: float = 45.0,
) -> Dict[str, Any]:
    """Query LLM Provider (OpenAI or Gemini) and return a JSON dict.
    
    `model` can be a string (OpenAI model name) for backward compatibility,
    or a dict `{ "provider": "openai" | "gemini", "model": str }`.
    """
    
    # Resolve provider and model_name
    provider = "openai"
    model_name = "gpt-4o-mini"
    
    if isinstance(model, dict):
        provider = model.get("provider", "openai").lower()
        model_name = model.get("model", "gpt-4o-mini")
    elif isinstance(model, str):
        provider = "openai"
        model_name = model
    else:
        # Fallback to env or default
        model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
    api_key = _get_api_key(provider)

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            if provider == "gemini":
                content = _query_gemini(api_key, model_name, prompt, system_role, temperature)
            else:
                content = _query_openai(api_key, model_name, prompt, system_role, temperature, request_timeout)
                
            data = _extract_json(content)
            if model_schema is not None:
                return _validate_schema(model_schema, data)
            return data
            
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= max_retries - 1:
                break

            if _is_rate_limit_error(exc):
                sleep_for = _parse_retry_after_seconds(exc) + min(2.0, attempt * 0.3)
            else:
                sleep_for = min(2.0, 0.5 + attempt * 0.2)
            time.sleep(sleep_for)

    raise LLMError(f"LLM request to {provider} ({model_name}) failed: {last_error}")
