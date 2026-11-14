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
