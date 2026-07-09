"""
config.py - Configuration and environment variable management.

Responsibilities:
- Load environment variables from .env
- Expose API keys and settings as constants
- Validate required configuration on startup
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
GPT_IMAGE_API_KEY: str  = os.getenv("GPT_IMAGE_API_KEY", "")   # OpenAI (paid)
HF_API_KEY: str         = os.getenv("HF_API_KEY", "")           # Hugging Face (free)
RUNWAY_API_KEY: str     = os.getenv("RUNWAY_API_KEY", "")
MODELSLAB_API_KEY: str  = os.getenv("MODELSLAB_API_KEY", "")    # ModelsLab (free credits)

# --- API Base URLs ---
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
GPT_IMAGE_BASE_URL: str = "https://api.openai.com/v1"
RUNWAY_BASE_URL: str = "https://api.dev.runwayml.com/v1"

# --- Model Defaults ---
# Primary: Google Gemma 4 31B — free tier, no per-token cost, reliable
DEFAULT_TEXT_MODEL: str = os.getenv("DEFAULT_TEXT_MODEL", "deepseek/deepseek-v4-flash")
# Fallback used automatically if primary returns a 429 rate-limit
FALLBACK_TEXT_MODEL: str = "liquid/lfm-2.5-1.2b-instruct:free"
DEFAULT_IMAGE_SIZE: str = "1024x1024"
DEFAULT_VIDEO_DURATION: int = 8  # seconds

# --- App Settings ---
APP_TITLE: str = "AI Content Engine"
APP_ICON: str = "🚀"


def validate_config() -> list[str]:
    """
    Check that all required API keys are present.
    Returns a list of missing key names (empty list means all OK).
    """
    missing = []
    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if not GPT_IMAGE_API_KEY:
        missing.append("GPT_IMAGE_API_KEY")
    if not RUNWAY_API_KEY:
        missing.append("RUNWAY_API_KEY")
    return missing
