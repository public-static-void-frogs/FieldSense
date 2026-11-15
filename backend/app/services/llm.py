import asyncio
import json
import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"


def llm_available(config: Settings) -> bool:
    return config.gemini_enabled and bool(config.gemini_api_key.strip())


async def stream_gemini(
    config: Settings,
    system_instruction: str,
    contents: list[dict],
    max_output_tokens: int = 300,
    timeout: float = 12,
):
    """Stream Gemini text as NDJSON: {"delta": ...} lines, then {"done": true} on success.

    On any upstream failure the stream ends without a done event so clients can detect it.
    """
    generation = {"maxOutputTokens": max_output_tokens}
    if config.gemini_model.startswith("gemini-2.5-"):
        generation["thinkingConfig"] = {"thinkingBudget": 0}
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": generation,
    }
    has_text = False
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                GEMINI_URL.format(model=config.gemini_model),
                params={"alt": "sse"},
                headers={"x-goog-api-key": config.gemini_api_key.strip()},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:])
                    for candidate in event.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            delta = part.get("text")
                            if isinstance(delta, str) and delta and not part.get("thought"):
                                has_text = has_text or bool(delta.strip())
                                yield json.dumps({"delta": delta}) + "\n"
                        if has_text and candidate.get("finishReason") == "STOP":
                            yield '{"done":true}\n'
                            return
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Gemini stream failed: %s", type(error).__name__)


class GeminiError(Exception):
    """The upstream model call failed or ended abnormally."""


RETRY_STATUSES = (429, 500, 503)


class _UpstreamStatus(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


async def _status_error(response: httpx.Response) -> _UpstreamStatus:
    """The error of a failed response with Gemini's own message (never the request or key)."""
    body = await response.aread()
    try:
        message = json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = body[:200].decode("utf-8", "replace")
    return _UpstreamStatus(response.status_code, str(message)[:300])


async def gemini_round(
    config: Settings,
    system_instruction: str,
    contents: list[dict],
    tools: list[dict] | None = None,
    max_output_tokens: int = 600,
    timeout: float = 30,
):
    """One streamed model turn that may call tools. Does not touch ``stream_gemini``.

    Yields ``("text", delta)`` and ``("call", {"name", "args"})`` in arrival order, then exactly
    one ``("end", {"finish": reason, "parts": [...]})`` where ``parts`` are the model's visible
    parts (text merged, function calls kept verbatim so thought signatures survive) to replay
    in the next request. Raises GeminiError on upstream failure.
    """
    generation = {"maxOutputTokens": max_output_tokens}
    if config.gemini_model.startswith("gemini-2.5-"):
        generation["thinkingConfig"] = {"thinkingBudget": 0}
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": generation,
    }
    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]
    parts, finish, has_call = [], None, False
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    GEMINI_URL.format(model=config.gemini_model),
                    params={"alt": "sse"},
                    headers={"x-goog-api-key": config.gemini_api_key.strip()},
                    json=payload,
                ) as response:
                    if response.is_error:
                        raise await _status_error(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        event = json.loads(line[5:])
                        for candidate in event.get("candidates", []):
                            for part in candidate.get("content", {}).get("parts", []):
                                if part.get("thought"):
                                    continue
                                call = part.get("functionCall")
                                text = part.get("text")
                                if isinstance(call, dict) and isinstance(call.get("name"), str):
                                    has_call = True
                                    parts.append(part)
                                    args = call.get("args")
                                    yield (
                                        "call",
                                        {
                                            "name": call["name"],
                                            "args": args if isinstance(args, dict) else {},
                                        },
                                    )
                                elif isinstance(text, str) and text:
                                    if parts and set(parts[-1]) == {"text"}:
                                        parts[-1] = {"text": parts[-1]["text"] + text}
                                    else:
                                        parts.append({"text": text})
                                    yield "text", text
                            finish = candidate.get("finishReason") or finish
            break
        except _UpstreamStatus as error:
            # Overload and rate limits are usually gone a moment later; nothing was sent yet.
            if attempt == 0 and error.status in RETRY_STATUSES and not parts:
                await asyncio.sleep(1.5)
                continue
            raise GeminiError(str(error)) from error
        except (httpx.HTTPError, ValueError) as error:
            raise GeminiError(type(error).__name__) from error
    if finish is None and not has_call:
        raise GeminiError("stream ended without a finish reason")
    yield "end", {"finish": finish, "parts": parts}
