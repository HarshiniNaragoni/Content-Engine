"""
adapter.py - Multi-Channel Adaptation for the Content Engine.

Exposes one public function:

    adapt_campaign(brief, original_results, target_channel) -> dict

Rewrites tagline, blog intro, and social posts for a chosen channel
without touching hero image or promotional video.

Reuses _call_openrouter() from text_gen.py — no new HTTP code.
"""

import json
from text_gen import _call_openrouter

# ---------------------------------------------------------------------------
# Channel definitions
# Each entry describes the audience, voice, constraints, and content
# guidelines the model must follow when adapting for that channel.
# ---------------------------------------------------------------------------
CHANNELS: dict[str, dict] = {
    "Gen-Z TikTok": {
        "label":       "Gen-Z TikTok",
        "audience":    "Gen-Z users aged 16-24 on TikTok",
        "voice":       "ultra-casual, energetic, trend-aware, uses Gen-Z slang lightly",
        "tagline":     "Max 8 words. Punchy. Can use emojis. No corporate language.",
        "blog":        "~150 words. Short punchy paragraphs. Hook in first sentence. Conversational.",
        "social": {
            "twitter":   "Max 240 chars. Hype tone. 2-3 trending hashtags. Include an emoji.",
            "instagram": "Max 300 chars. Visual storytelling. 4-5 hashtags. Emoji-friendly.",
            "linkedin":  "Max 200 chars. Keep it light but still professional. No hashtags.",
        },
    },
    "B2B LinkedIn": {
        "label":       "B2B LinkedIn",
        "audience":    "Business professionals, decision-makers, B2B buyers",
        "voice":       "professional, data-driven, authoritative, results-focused",
        "tagline":     "Max 10 words. No slang. Emphasise ROI or business value.",
        "blog":        "~200 words. Business case framing. Include a value proposition. Formal tone.",
        "social": {
            "twitter":   "Max 280 chars. Professional insight. One relevant hashtag.",
            "instagram": "Max 400 chars. Professional storytelling. 2-3 industry hashtags.",
            "linkedin":  "Max 700 chars. Thought leadership. Data points if relevant. No hashtags.",
        },
    },
    "Facebook Parents": {
        "label":       "Facebook Parents",
        "audience":    "Parents aged 28-45 on Facebook",
        "voice":       "warm, trustworthy, family-oriented, reassuring",
        "tagline":     "Max 10 words. Warm and relatable. Family or safety angle.",
        "blog":        "~200 words. Relatable everyday scenarios. Reassuring tone. Easy to read.",
        "social": {
            "twitter":   "Max 280 chars. Friendly and warm. 1-2 family hashtags.",
            "instagram": "Max 500 chars. Emotional storytelling. 3-4 family-friendly hashtags.",
            "linkedin":  "Max 300 chars. Community-oriented. No hashtags.",
        },
    },
    "Instagram Lifestyle": {
        "label":       "Instagram Lifestyle",
        "audience":    "Lifestyle enthusiasts aged 22-35 on Instagram",
        "voice":       "aspirational, aesthetic, visually descriptive, inspiring",
        "tagline":     "Max 10 words. Evocative and aesthetic. Inspires a feeling or vision.",
        "blog":        "~180 words. Sensory language. Paint a picture. Aspirational ending.",
        "social": {
            "twitter":   "Max 260 chars. Aesthetic and inspiring. 2 niche hashtags.",
            "instagram": "Max 600 chars. Rich visual storytelling. 5 lifestyle hashtags. Emojis welcome.",
            "linkedin":  "Max 250 chars. Polished lifestyle angle. No hashtags.",
        },
    },
    "Email Newsletter": {
        "label":       "Email Newsletter",
        "audience":    "Existing subscribers who opted in for brand updates",
        "voice":       "friendly, direct, personal, value-focused",
        "tagline":     "Max 10 words. Acts as an email subject line. Drives curiosity or urgency.",
        "blog":        "~220 words. Personal opener. Clear value statement. Ends with a CTA.",
        "social": {
            "twitter":   "Max 280 chars. Teaser for the newsletter content. One CTA.",
            "instagram": "Max 400 chars. Behind-the-scenes or exclusive feel. 2-3 hashtags.",
            "linkedin":  "Max 400 chars. Professional summary of the newsletter theme. No hashtags.",
        },
    },
}


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

def _tagline_system(channel: dict) -> str:
    return (
        f"You are a creative director adapting a campaign for {channel['label']}. "
        f"Target audience: {channel['audience']}. "
        f"Voice: {channel['voice']}. "
        f"Tagline rules: {channel['tagline']} "
        "Output ONLY the tagline. No quotes, no labels, no explanation."
    )


def _blog_system(channel: dict) -> str:
    return (
        f"You are a content writer adapting a blog introduction for {channel['label']}. "
        f"Target audience: {channel['audience']}. "
        f"Voice: {channel['voice']}. "
        f"Blog rules: {channel['blog']} "
        "Output ONLY the blog text. No headings, no labels."
    )


def _social_system(channel: dict) -> str:
    rules = channel["social"]
    return (
        f"You are a social media copywriter adapting posts for {channel['label']}. "
        f"Target audience: {channel['audience']}. "
        f"Voice: {channel['voice']}. "
        f"Twitter: {rules['twitter']} "
        f"Instagram: {rules['instagram']} "
        f"LinkedIn: {rules['linkedin']} "
        'Return ONLY valid JSON — no markdown fences, no extra text. '
        'Exact format: {"twitter":"...","instagram":"...","linkedin":"..."}'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def adapt_campaign(
    brief: dict,
    original_results: dict,
    target_channel: str,
) -> dict:
    """
    Rewrite the three text assets for a specific distribution channel.

    Hero image and promotional video are NOT regenerated — they are passed
    through unchanged from original_results.

    Args:
        brief:            Product brief with keys 'product', 'audience', 'tone'.
        original_results: The current st.session_state.results dict.
        target_channel:   One of the keys in CHANNELS.

    Returns:
        Dict with keys:
            tagline  (str)
            blog     (str)
            social   (dict: twitter, instagram, linkedin)
            image_url (str, passed through unchanged)
            video_url (str, passed through unchanged)

    Raises:
        ValueError:   If target_channel is not recognised.
        RuntimeError: If any OpenRouter call fails.
    """
    if target_channel not in CHANNELS:
        raise ValueError(
            f"Unknown channel: {target_channel!r}. "
            f"Choose from: {list(CHANNELS.keys())}"
        )

    channel  = CHANNELS[target_channel]
    product  = brief.get("product",  "").strip()
    audience = brief.get("audience", "").strip()
    tone     = brief.get("tone",     "").strip()

    # Original assets used as context so the model knows what to adapt
    orig_tagline = original_results.get("tagline", "")
    orig_blog    = original_results.get("blog",    "")
    orig_social  = original_results.get("social",  {})

    # ── Adapt Tagline ──────────────────────────────────────────────────────
    tagline_prompt = (
        f"Product: {product} | Audience: {audience} | Tone: {tone}\n"
        f"Original tagline: {orig_tagline}\n"
        f"Adapt this tagline for {target_channel}."
    )
    adapted_tagline = _call_openrouter(
        _tagline_system(channel), tagline_prompt, max_tokens=25
    ).strip().strip('"').strip("'").strip()

    # ── Adapt Blog ─────────────────────────────────────────────────────────
    blog_prompt = (
        f"Product: {product} | Audience: {audience} | Tone: {tone}\n"
        f"Campaign tagline: {adapted_tagline}\n"
        f"Original blog intro: {orig_blog[:200]}...\n"
        f"Adapt this blog introduction for {target_channel}."
    )
    adapted_blog = _call_openrouter(
        _blog_system(channel), blog_prompt, max_tokens=350
    )

    # ── Adapt Social Posts ─────────────────────────────────────────────────
    social_prompt = (
        f"Product: {product} | Audience: {audience} | Tone: {tone}\n"
        f"Campaign tagline: {adapted_tagline}\n"
        f"Adapt social posts for {target_channel}."
    )
    raw_social = _call_openrouter(
        _social_system(channel), social_prompt, max_tokens=400
    )

    # Parse JSON with plain-text fallback
    raw_social = raw_social.strip()
    if raw_social.startswith("```"):
        parts = raw_social.split("```")
        raw_social = parts[1].lstrip("json").strip() if len(parts) > 1 else raw_social

    try:
        social_data = json.loads(raw_social)
        adapted_social = {
            "twitter":   str(social_data.get("twitter",   "")),
            "instagram": str(social_data.get("instagram", "")),
            "linkedin":  str(social_data.get("linkedin",  "")),
        }
    except json.JSONDecodeError:
        # Model returned plain text — store in twitter, leave others empty
        adapted_social = {
            "twitter":   raw_social[:280],
            "instagram": "",
            "linkedin":  "",
        }

    # ── Pass visual assets through unchanged ──────────────────────────────
    return {
        "tagline":   adapted_tagline,
        "blog":      adapted_blog,
        "social":    adapted_social,
        "image_url": original_results.get("image_url", ""),
        "video_url": original_results.get("video_url", ""),
    }
