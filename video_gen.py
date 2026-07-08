"""
video_gen.py - Promotional video generation.

Primary:  ModelsLab image-to-video API (free credits on signup).
Fallback: Runway Gen4 Turbo (paid, key_ prefix required).

If the hero image is a base64 data-URI it is automatically uploaded to
freeimage.host (free, no auth) before being passed to the video API.
"""

import re
import time
import base64 as _base64
import requests
from config import MODELSLAB_API_KEY, RUNWAY_API_KEY, RUNWAY_BASE_URL, DEFAULT_VIDEO_DURATION

_ML_IMG2VIDEO_URL   = "https://modelslab.com/api/v6/video/img2video"
_ML_FETCH_URL       = "https://modelslab.com/api/v6/video/fetch/{request_id}"
_RUNWAY_API_VERSION = "2024-11-06"
_POLL_INTERVAL      = 5
_POLL_TIMEOUT       = 300

_TONE_MOTION: dict[str, str] = {
    "playful":    "Gentle bouncy camera movement. Bright colours pulse softly. Lively feel.",
    "premium":    "Slow cinematic push-in. Soft studio light shifts gently. Elegant atmosphere.",
    "eco":        "Soft slow pan. Warm golden light filters through. Peaceful organic feel.",
    "bold":       "Dynamic fast push-in. High-contrast light flares. Powerful intense motion.",
    "minimalist": "Barely perceptible slow zoom. Clean stark lighting. Calm uncluttered.",
}
_DEFAULT_MOTION = "Slow cinematic push-in. Soft light shifts gently. Background mostly still."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_promo_video(brief: dict, image_url: str) -> str:
    """
    Generate a short promotional video from the campaign hero image.

    If image_url is a base64 data-URI it is automatically uploaded to a
    public host before being sent to the video generation API.

    Args:
        brief:     Dict with keys 'product', 'audience', 'tone'.
        image_url: URL or base64 data-URI of the hero image.

    Returns:
        A URL string pointing to the generated video.

    Raises:
        RuntimeError: If no API key is configured, upload or job fails.
    """
    if not MODELSLAB_API_KEY and not RUNWAY_API_KEY:
        raise RuntimeError(
            "No video API key configured. "
            "Add MODELSLAB_API_KEY (free) or RUNWAY_API_KEY to your .env file."
        )

    # Upload base64 data-URI to get a real public URL
    if image_url.startswith("data:"):
        image_url = _upload_base64_to_url(image_url)

    motion_prompt = _build_motion_prompt(brief)

    if MODELSLAB_API_KEY:
        return _modelslab_img2video(image_url, motion_prompt)

    return _runway_img2video(image_url, motion_prompt)


# ---------------------------------------------------------------------------
# Base64 → public URL  (freeimage.host, no auth required)
# ---------------------------------------------------------------------------

def _upload_base64_to_url(data_uri: str) -> str:
    """Upload a base64 data-URI to freeimage.host and return a public URL."""
    match = re.match(r"data:image/(\w+);base64,(.+)", data_uri, re.DOTALL)
    if not match:
        raise RuntimeError("Unrecognised data-URI format.")

    ext       = match.group(1)
    img_bytes = _base64.b64decode(match.group(2))

    try:
        r = requests.post(
            "https://freeimage.host/api/1/upload",
            data={"key": "6d207e02198a847aa98d0a2a901485a5",
                  "action": "upload", "format": "json"},
            files={"source": (f"hero.{ext}", img_bytes, f"image/{ext}")},
            timeout=60,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Image upload timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to image host. Check your connection.")

    if not r.ok:
        raise RuntimeError(f"Image upload error {r.status_code}: {r.text[:200]}")

    data = r.json()
    url  = data.get("image", {}).get("url", "")
    if not url:
        raise RuntimeError(f"Image upload returned no URL. Response: {data}")
    return url


# ---------------------------------------------------------------------------
# Motion prompt builder
# ---------------------------------------------------------------------------

def _build_motion_prompt(brief: dict) -> str:
    tone   = brief.get("tone", "").strip().lower()
    motion = _TONE_MOTION.get(tone, _DEFAULT_MOTION)
    return f"{motion} Professional marketing video quality. No text or overlays."


# ---------------------------------------------------------------------------
# ModelsLab
# ---------------------------------------------------------------------------

def _modelslab_img2video(image_url: str, prompt: str) -> str:
    payload = {
        "key":                 MODELSLAB_API_KEY,
        "prompt":              prompt,
        "negative_prompt":     "blurry, low quality, text, watermark, logo",
        "init_image":          image_url,
        "height":              512,
        "width":               912,
        "num_frames":          25,
        "num_inference_steps": 20,
        "guidance_scale":      7.5,
        "output_type":         "mp4",
        "webhook":             None,
        "track_id":            None,
    }
    try:
        r = requests.post(_ML_IMG2VIDEO_URL,
                          headers={"Content-Type": "application/json"},
                          json=payload, timeout=60)
    except requests.exceptions.Timeout:
        raise RuntimeError("ModelsLab video request timed out.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to ModelsLab.")

    if not r.ok:
        try:
            detail = r.json().get("message", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(f"ModelsLab API error {r.status_code}: {detail}")

    data   = r.json()
    status = data.get("status", "")

    if status == "success":
        output = data.get("output", [])
        if output:
            return output[0]

    if status == "processing":
        rid = data.get("id") or data.get("request_id")
        if not rid:
            raise RuntimeError(f"ModelsLab returned processing but no ID. Response: {data}")
        return _modelslab_poll(str(rid))

    raise RuntimeError(f"ModelsLab error: {data.get('message', data)}")


def _modelslab_poll(request_id: str) -> str:
    fetch_url = _ML_FETCH_URL.format(request_id=request_id)
    deadline  = time.time() + _POLL_TIMEOUT

    while time.time() < deadline:
        try:
            r = requests.post(fetch_url,
                              headers={"Content-Type": "application/json"},
                              json={"key": MODELSLAB_API_KEY}, timeout=30)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"ModelsLab polling error: {exc}") from exc

        if not r.ok:
            raise RuntimeError(f"ModelsLab fetch error {r.status_code}: {r.text[:200]}")

        data   = r.json()
        status = data.get("status", "")

        if status == "success":
            output = data.get("output", [])
            if not output:
                raise RuntimeError("ModelsLab succeeded but returned no output URL.")
            return output[0]

        if status == "error":
            raise RuntimeError(f"ModelsLab job failed: {data.get('message', data)}")

        time.sleep(_POLL_INTERVAL)

    raise RuntimeError(f"ModelsLab timed out after {_POLL_TIMEOUT}s. ID: {request_id}")


# ---------------------------------------------------------------------------
# Runway fallback
# ---------------------------------------------------------------------------

def _runway_img2video(image_url: str, prompt: str) -> str:
    if not RUNWAY_API_KEY:
        raise RuntimeError("RUNWAY_API_KEY is not set.")

    headers = {
        "Authorization":    f"Bearer {RUNWAY_API_KEY}",
        "Content-Type":     "application/json",
        "X-Runway-Version": _RUNWAY_API_VERSION,
    }
    payload = {
        "model":       "gen4_turbo",
        "promptImage": image_url,
        "promptText":  prompt,
        "ratio":       "1280:768",
        "duration":    DEFAULT_VIDEO_DURATION,
    }
    try:
        r = requests.post(f"{RUNWAY_BASE_URL}/image_to_video",
                          headers=headers, json=payload, timeout=60)
    except requests.exceptions.Timeout:
        raise RuntimeError("Runway request timed out.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to Runway.")

    if not r.ok:
        try:
            detail = r.json().get("error", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(f"Runway API error {r.status_code}: {detail}")

    task_id = r.json().get("id")
    if not task_id:
        raise RuntimeError(f"Runway returned no task ID. Response: {r.json()}")

    deadline = time.time() + _POLL_TIMEOUT
    while time.time() < deadline:
        try:
            poll = requests.get(f"{RUNWAY_BASE_URL}/tasks/{task_id}",
                                headers=headers, timeout=30)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Runway polling failed: {exc}") from exc

        if not poll.ok:
            raise RuntimeError(f"Runway polling error {poll.status_code}: {poll.text[:200]}")

        pdata  = poll.json()
        status = pdata.get("status", "")

        if status == "SUCCEEDED":
            output = pdata.get("output", [])
            if not output:
                raise RuntimeError("Runway succeeded but returned no output URL.")
            return output[0]

        if status in ("FAILED", "CANCELLED"):
            reason = pdata.get("failure", pdata.get("error", "Unknown"))
            raise RuntimeError(f"Runway job {status.lower()}: {reason}")

        time.sleep(_POLL_INTERVAL)

    raise RuntimeError(f"Runway timed out after {_POLL_TIMEOUT}s. Task: {task_id}")
