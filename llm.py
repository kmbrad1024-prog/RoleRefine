"""Model wrapper: sends the prompt to Gemini or Claude and returns validated JSON.

The same system prompt and JSON schema are used for both providers, so the
rest of the app doesn't need to know which model produced the result.
"""

from __future__ import annotations

import json
import re
import sys

from prompts import SYSTEM_PROMPT

PROVIDERS = {
    "gemini": {"label": "Google Gemini", "default_model": "gemini-3.5-flash"},
    "anthropic": {"label": "Anthropic Claude", "default_model": "claude-sonnet-5"},
}
MAX_OUTPUT_TOKENS = 8000
VALID_CATEGORIES = {
    "masculine_coded", "feminine_coded", "age", "ability",
    "inflated_requirements", "exclusionary_language", "tone",
}
RETRY_MESSAGE = (
    "Your last response was not valid JSON. "
    "Return only the JSON object, with no other text."
)

# Friendly messages shown to visitors; raw API errors are never displayed.
MSG_AUTH = "The demo's API key isn't working right now. Click **See a demo result** to see how the tool works."
MSG_BUDGET = "The live demo has reached its usage limit for now. Click **See a demo result** to see how the tool works, or try again later."
MSG_RATE = "The live demo is busy. Wait a minute and try again, or click **See a demo result**."
MSG_OTHER = "Something went wrong while contacting the AI model. Please try again, or click **See a demo result**."
MSG_UNREADABLE = "The model didn't return a readable result. Please try again."


class OptimizerError(Exception):
    pass


def _log(provider: str, err: Exception) -> None:
    """Record the real cause in the server logs (never shown to visitors, never includes the key)."""
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    detail = getattr(err, "message", None) or str(err)
    print(f"[jd-optimizer] {provider} error {type(err).__name__} {code}: {detail}"[:1000],
          file=sys.stderr, flush=True)


def parse_response(text: str) -> dict:
    """Extract and validate the JSON object from the model's reply."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found")
    data = json.loads(cleaned[start : end + 1])

    if not isinstance(data.get("rewritten_jd"), str):
        raise ValueError("Missing 'rewritten_jd'")
    changes = []
    for c in data.get("changes") or []:
        if not isinstance(c, dict) or not c.get("original"):
            continue
        cat = c.get("category", "tone")
        changes.append({
            "original": str(c["original"]),
            "replacement": str(c.get("replacement", "")),
            "category": cat if cat in VALID_CATEGORIES else "tone",
            "reason": str(c.get("reason", "")),
        })
    return {
        "rewritten_jd": data["rewritten_jd"],
        "changes": changes,
        "suggestions": [str(s) for s in data.get("suggestions") or []],
        "summary": str(data.get("summary", "")),
    }


# ---------- providers ----------

def _call_gemini(messages: list[dict], api_key: str, model: str) -> str:
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=api_key)
    contents = [
        types.Content(role="user" if m["role"] == "user" else "model",
                      parts=[types.Part(text=m["content"])])
        for m in messages
    ]
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
    except errors.APIError as e:
        _log("gemini", e)
        text = str(e).lower()
        if e.code == 429:
            raise OptimizerError(MSG_BUDGET if "quota" in text or "per day" in text else MSG_RATE) from e
        if e.code in (401, 403) or "api key" in text:
            raise OptimizerError(MSG_AUTH) from e
        raise OptimizerError(MSG_OTHER) from e
    except Exception as e:  # network problems and similar
        _log("gemini", e)
        raise OptimizerError(MSG_OTHER) from e
    return response.text or ""


def _call_anthropic(messages: list[dict], api_key: str, model: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except anthropic.AuthenticationError as e:
        raise OptimizerError(MSG_AUTH) from e
    except anthropic.RateLimitError as e:
        raise OptimizerError(MSG_RATE) from e
    except anthropic.BadRequestError as e:
        _log("anthropic", e)
        if "credit balance" in str(e).lower():
            raise OptimizerError(MSG_BUDGET) from e
        raise OptimizerError(MSG_OTHER) from e
    except Exception as e:
        _log("anthropic", e)
        raise OptimizerError(MSG_OTHER) from e
    return "".join(b.text for b in response.content if b.type == "text")


_CALLERS = {"gemini": _call_gemini, "anthropic": _call_anthropic}


def optimize(user_message: str, api_key: str, provider: str = "gemini", model: str | None = None) -> dict:
    if provider not in _CALLERS:
        raise OptimizerError(MSG_OTHER)
    model = model or PROVIDERS[provider]["default_model"]
    messages = [{"role": "user", "content": user_message}]

    for attempt in range(2):
        text = _CALLERS[provider](messages, api_key, model)
        try:
            return parse_response(text)
        except (ValueError, json.JSONDecodeError) as e:
            _log(provider, e)
            if attempt == 0:
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": RETRY_MESSAGE},
                ]
    raise OptimizerError(MSG_UNREADABLE)
