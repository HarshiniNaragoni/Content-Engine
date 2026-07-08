"""
text_gen.py - Text asset generation via OpenRouter API.

Uses google/gemma-4-31b-it:free as the primary model (free tier, no token cost).
Falls back to liquid/lfm-2.5-1.2b-instruct:free on 429 rate-limit responses.
All prompts are kept compact to stay within free-tier context limits.
"""

import json
import time
import requests
from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    DEFAULT_TEXT_MODEL,
    FALLBACK_TEXT_MODEL,
)


# ---------------------------------------------------------------------------
# Tagline — one compact few-shot example per tone
# ---------------------------------------------------------------------------
_TAGLINE_EXAMPLES: dict[str, tuple[str, str]] = {
    "playful":    ("SnapToy | Kids",       "Build It, Break It, Dream It"),
    "premium":    ("AuraWatch | Execs",    "Time Refined for Those Who Lead"),
    "eco":        ("TerraBottle | Green",  "Drink Deep, Leave No Trace"),
    "bold":       ("TitanShoe | Athletes", "Built for Those Who Never Stop"),
    "minimalist": ("PureLine | Designers", "Nothing Extra, Everything Essential"),
}
_TAGLINE_DEFAULT_EXAMPLE = ("SwiftApp | Pros", "Work Smarter, Live Fuller")

_TAGLINE_SYSTEM = (
    "Creative director. Output ONE tagline only. "
    "Max 10 words. No hashtags. No quotes. Match tone."
)

# ---------------------------------------------------------------------------
# Blog — compact role-based system prompt
# ---------------------------------------------------------------------------
_BLOG_SYSTEM = (
    "You are a content strategist. Write a ~200-word blog introduction. "
    "Match the tone. Weave in the tagline naturally. "
    "Output ONLY the blog text, no headings."
)

# ---------------------------------------------------------------------------
# Social — structured output prompt with explicit JSON example
# ---------------------------------------------------------------------------
_SOCIAL_SYSTEM = (
    'You are a social media copywriter. '
    'Return ONLY a JSON object, no other text, no markdown fences. '
    'Exact format: {"twitter":"post here","instagram":"post here","linkedin":"post here"} '
    'twitter max 280 chars, instagram max 500 chars, linkedin max 300 chars. Match tone.'
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_tagline(brief: dict) -> str:
    """
    Generate a campaign tagline using few-shot prompting.

    Uses one compact tone-matched example to stay within free-tier
    prompt token limits.

    Args:
        brief: Dict with keys 'product', 'audience', 'tone'.

    Returns:
        Tagline string — max 10 words, no hashtags, no quotes.

    Raises:
        ValueError:   If required brief fields are empty.
        RuntimeError: If the API call fails.
    """
    product  = brief.get("product",  "").strip()
    audience = brief.get("audience", "").strip()
    tone     = brief.get("tone",     "").strip().lower()

    if not product:
        raise ValueError("Product name is required.")
    if not audience:
        raise ValueError("Target audience is required.")

    ex_ctx, ex_tag = _TAGLINE_EXAMPLES.get(tone, _TAGLINE_DEFAULT_EXAMPLE)

    # One few-shot pair + the real request
    messages = [
        {"role": "user",      "content": ex_ctx},
        {"role": "assistant", "content": ex_tag},
        {"role": "user",      "content": f"{product} | {audience} | tone:{tone}"},
    ]

    result = _call_openrouter(_TAGLINE_SYSTEM, messages, max_tokens=20)
    return result.strip().strip('"').strip("'").strip()


def generate_blog_intro(brief: dict, tagline: str) -> str:
    """
    Generate a ~200-word blog introduction using role-based prompting.

    Args:
        brief:   Dict with keys 'product', 'audience', 'tone'.
        tagline: Campaign tagline from generate_tagline().

    Returns:
        ~200-word blog introduction string.

    Raises:
        RuntimeError: If the API call fails.
    """
    product  = brief.get("product",  "").strip()
    audience = brief.get("audience", "").strip()
    tone     = brief.get("tone",     "").strip()

    user_prompt = (
        f"Product:{product} | Audience:{audience} | "
        f"Tone:{tone} | Tagline:{tagline}"
    )
    return _call_openrouter(_BLOG_SYSTEM, user_prompt, max_tokens=350)


def generate_social_posts(brief: dict) -> dict[str, str]:
    """
    Generate platform-specific social posts using structured JSON output.

    Args:
        brief: Dict with keys 'product', 'audience', 'tone'.

    Returns:
        Dict with keys 'twitter', 'instagram', 'linkedin'.

    Raises:
        RuntimeError: If the API call fails or returns invalid JSON.
    """
    product  = brief.get("product",  "").strip()
    audience = brief.get("audience", "").strip()
    tone     = brief.get("tone",     "").strip()

    user_prompt = f"Product:{product} | Audience:{audience} | Tone:{tone}"
    raw = _call_openrouter(_SOCIAL_SYSTEM, user_prompt, max_tokens=400)

    # Strip accidental markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

    # Try JSON parse first
    try:
        data = json.loads(raw)
        return {
            "twitter":   str(data.get("twitter",   "")),
            "instagram": str(data.get("instagram", "")),
            "linkedin":  str(data.get("linkedin",  "")),
        }
    except json.JSONDecodeError:
        pass

    # Fallback: model returned labelled plain text — extract by label
    result = {"twitter": "", "instagram": "", "linkedin": ""}
    current_key = None
    current_lines: list[str] = []

    label_map = {
        "twitter":   "twitter",
        "x:":        "twitter",
        "instagram": "instagram",
        "linkedin":  "linkedin",
    }

    for line in raw.splitlines():
        lower = line.lower().strip().rstrip(":")
        matched = next((v for k, v in label_map.items() if lower.startswith(k)), None)
        if matched:
            if current_key and current_lines:
                result[current_key] = " ".join(current_lines).strip()
            current_key = matched
            # Content may be on the same line after the label
            rest = line.split(":", 1)[-1].strip() if ":" in line else ""
            current_lines = [rest] if rest else []
        elif current_key:
            current_lines.append(line.strip())

    if current_key and current_lines:
        result[current_key] = " ".join(current_lines).strip()

    # If we still got nothing useful, store the whole response in twitter
    if not any(result.values()):
        result["twitter"] = raw[:280]

    return result


# ---------------------------------------------------------------------------
# Internal — shared OpenRouter HTTP client with fallback on 429
# ---------------------------------------------------------------------------

def _call_openrouter(
    system_prompt: str,
    user_content: "str | list[dict]",
    model: str = DEFAULT_TEXT_MODEL,
    max_tokens: int = 100,
) -> str:
    """
    POST a chat completion to OpenRouter.

    Tries the primary model first. On a 429 rate-limit or null content
    response, waits 1 second and retries with FALLBACK_TEXT_MODEL.

    Args:
        system_prompt: System role instruction.
        user_content:  Plain string or pre-built message list (for few-shot).
        model:         Primary OpenRouter model identifier.
        max_tokens:    Token cap for the completion.

    Returns:
        Stripped response text.

    Raises:
        RuntimeError: On missing key, timeout, connection error, or API error.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if isinstance(user_content, str):
        messages.append({"role": "user", "content": user_content})
    else:
        messages.extend(user_content)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
    }

    # Try primary model, then fallback on 429 or null content
    models_to_try = [model]
    if model != FALLBACK_TEXT_MODEL:
        models_to_try.append(FALLBACK_TEXT_MODEL)

    last_error = "Unknown error"

    for attempt_model in models_to_try:
        payload = {
            "model":       attempt_model,
            "messages":    messages,
            "temperature": 0.7,
            "max_tokens":  max_tokens,
        }

        try:
            response = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
        except requests.exceptions.Timeout:
            raise RuntimeError("OpenRouter request timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Could not connect to OpenRouter. Check your internet connection."
            )

        if response.ok:
            data = response.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as exc:
                raise RuntimeError(
                    f"Unexpected OpenRouter response format: {data}"
                ) from exc

            # Some free models return null content — treat as unavailable
            if content is None:
                last_error = f"Model {attempt_model} returned empty content."
                time.sleep(1)
                continue

            return content.strip()

        # 429 rate-limit — try the next model
        if response.status_code == 429:
            try:
                last_error = (
                    response.json().get("error", {}).get("message", response.text)
                )
            except Exception:
                last_error = response.text
            time.sleep(1)
            continue

        # Any other HTTP error — raise immediately with detail
        try:
            error_detail = (
                response.json().get("error", {}).get("message", response.text)
            )
        except Exception:
            error_detail = response.text
        raise RuntimeError(
            f"OpenRouter API error {response.status_code}: {error_detail}"
        )

    raise RuntimeError(
        f"All models rate-limited or unavailable. Last error: {last_error}"
    )
