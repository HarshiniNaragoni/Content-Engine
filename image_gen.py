"""
image_gen.py - Hero image generation.

Primary:  Hugging Face Inference API — FLUX.1-schnell (free tier).
Fallback: OpenAI GPT Image API — gpt-image-1 (paid, used if HF key absent).

The function returns either:
- A URL string  (GPT Image API path)
- A base64 data-URI string  (HF path — st.image() handles both)
"""

import base64
import requests
from config import HF_API_KEY, GPT_IMAGE_API_KEY, GPT_IMAGE_BASE_URL, DEFAULT_IMAGE_SIZE


# Hugging Face endpoint — use router (api-inference is blocked on this network)
_HF_FLUX_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "black-forest-labs/FLUX.1-schnell"
)

# Tone → visual style descriptor
_TONE_STYLE_MAP: dict[str, str] = {
    "playful":    "bright flat illustration, vibrant colours, fun and energetic",
    "premium":    "photorealistic, studio lighting, elegant and refined",
    "eco":        "watercolour style, natural earthy tones, organic textures",
    "bold":       "high-contrast graphic design, vivid bold colours, dynamic",
    "minimalist": "clean minimal composition, generous white space, simple shapes",
}
_DEFAULT_STYLE = "clean modern commercial photography, professional marketing"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_hero_image(brief: dict, tagline: str) -> str:
    """
    Generate a campaign hero image.

    Uses Hugging Face FLUX.1-schnell when HF_API_KEY is set (free).
    Falls back to OpenAI gpt-image-1 when only GPT_IMAGE_API_KEY is set.

    Args:
        brief:   Dict with keys 'product', 'audience', 'tone'.
        tagline: Campaign tagline — anchors the visual concept.

    Returns:
        Image URL or base64 data-URI string usable by st.image().

    Raises:
        RuntimeError: If no API key is configured or the call fails.
    """
    product = brief.get("product", "").strip()
    tone    = brief.get("tone",    "").strip().lower()
    prompt  = _build_image_prompt(product, tagline, tone)

    if HF_API_KEY:
        return _call_hf_flux(prompt)
    if GPT_IMAGE_API_KEY:
        return _call_gpt_image_api(prompt)

    raise RuntimeError(
        "No image API key configured. "
        "Add HF_API_KEY (free) or GPT_IMAGE_API_KEY to your .env file."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_image_prompt(product: str, tagline: str, tone: str) -> str:
    """
    Build the image prompt:  subject + style + composition + constraints.
    """
    style = _TONE_STYLE_MAP.get(tone, _DEFAULT_STYLE)
    return (
        f"A {style} hero marketing image for '{product}'. "
        f"Campaign concept: {tagline}. "
        f"Professional advertising photography. "
        f"Centred composition, shallow depth of field. "
        f"No text, no logos, no watermarks."
    )


def _call_hf_flux(prompt: str) -> str:
    """
    Call Hugging Face Inference API with FLUX.1-schnell.

    Returns a base64 PNG data-URI that st.image() can display directly.

    Raises:
        RuntimeError: On HTTP or API-level errors.
    """
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 4,   # schnell is optimised for 1-4 steps
            "width":  1024,
            "height": 576,              # 16:9 aspect ratio
        },
    }

    try:
        response = requests.post(
            _HF_FLUX_URL,
            headers=headers,
            json=payload,
            timeout=120,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            "Hugging Face image request timed out. Please try again."
        )
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Could not connect to Hugging Face. Check your internet connection."
        )

    if not response.ok:
        # HF returns JSON errors or plain text depending on the error type
        try:
            err = response.json()
            detail = err.get("error", str(err))
        except Exception:
            detail = response.text[:300]
        raise RuntimeError(
            f"Hugging Face API error {response.status_code}: {detail}"
        )

    # HF router returns raw image bytes (jpeg or png)
    content_type = response.headers.get("Content-Type", "image/jpeg")
    ext = "jpeg" if "jpeg" in content_type else "png"
    b64 = base64.b64encode(response.content).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"


def _call_gpt_image_api(prompt: str, size: str = DEFAULT_IMAGE_SIZE) -> str:
    """
    Call OpenAI Images API (gpt-image-1) — paid fallback.

    Returns a URL or base64 data-URI depending on what the API returns.

    Raises:
        RuntimeError: On HTTP or API-level errors.
    """
    headers = {
        "Authorization": f"Bearer {GPT_IMAGE_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":   "gpt-image-1",
        "prompt":  prompt,
        "n":       1,
        "size":    size,
        "quality": "standard",
    }

    try:
        response = requests.post(
            f"{GPT_IMAGE_BASE_URL}/images/generations",
            headers=headers,
            json=payload,
            timeout=120,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("GPT Image API request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Could not connect to the GPT Image API. Check your internet connection."
        )

    if not response.ok:
        try:
            error_detail = response.json().get("error", {}).get("message", response.text)
        except Exception:
            error_detail = response.text
        raise RuntimeError(
            f"GPT Image API error {response.status_code}: {error_detail}"
        )

    data = response.json()
    try:
        item = data["data"][0]
        if "url" in item:
            return item["url"]
        return f"data:image/png;base64,{item['b64_json']}"
    except (KeyError, IndexError) as exc:
        raise RuntimeError(
            f"Unexpected GPT Image API response: {data}"
        ) from exc
