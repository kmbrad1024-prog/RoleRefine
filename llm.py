"""Claude API wrapper: sends the prompt and returns validated JSON."""

from __future__ import annotations

import json
import re

import anthropic

from prompts import SYSTEM_PROMPT

DEFAULT_MODEL = "claude-sonnet-5"
VALID_CATEGORIES = {
    "masculine_coded", "feminine_coded", "age", "ability",
    "inflated_requirements", "exclusionary_language", "tone",
}
RETRY_MESSAGE = (
    "Your last response was not valid JSON. "
    "Return only the JSON object, with no other text."
)


class OptimizerError(Exception):
    pass


def parse_response(text: str) -> dict:
    """Extract and validate the JSON object from the model's reply."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
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


def optimize(user_message: str, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": user_message}]

    for attempt in range(2):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
        except anthropic.AuthenticationError as e:
            raise OptimizerError("The API key was rejected. Check that it's correct.") from e
        except anthropic.RateLimitError as e:
            raise OptimizerError("Rate limit reached. Wait a minute and try again.") from e
        except anthropic.APIError as e:
            raise OptimizerError(f"The Claude API returned an error: {e}") from e

        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            return parse_response(text)
        except (ValueError, json.JSONDecodeError):
            if attempt == 0:
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": RETRY_MESSAGE},
                ]
    raise OptimizerError("The model didn't return a readable result. Please try again.")
