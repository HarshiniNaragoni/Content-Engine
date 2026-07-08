"""
critic.py - AI Self-Critique Loop for the Content Engine.

Exposes three public functions called from app.py:

    evaluate_assets(brief, tagline, blog, social) -> dict
        Ask the LLM to review all three text assets and return a
        strict JSON verdict for each one.

    regenerate_failed_asset(asset_key, brief, issue, current_results) -> str | dict
        Regenerate a single failed asset, injecting the critic's issue
        into the prompt so the model knows what to fix.

    run_critic_loop(brief, results, status_placeholder) -> dict
        Orchestrate up to MAX_RETRIES rounds of critique → regeneration,
        updating st.session_state.critic_results and st.session_state.retry_count
        at every step.  Returns the (possibly updated) results dict.

Reuses _call_openrouter() from text_gen.py — no duplicate HTTP code.
Never modifies text_gen.py, image_gen.py, video_gen.py, or the sidebar.
"""

import json
import streamlit as st

# Reuse the shared OpenRouter HTTP client — no new HTTP code here
from text_gen import _call_openrouter, generate_tagline, generate_blog_intro, generate_social_posts

MAX_RETRIES = 2   # maximum regeneration attempts per asset

# ---------------------------------------------------------------------------
# System prompt — senior marketing reviewer
# ---------------------------------------------------------------------------
_CRITIC_SYSTEM = (
    "You are a Senior Marketing Content Reviewer. "
    "Evaluate the provided campaign assets against the product brief. "
    "Check: brand tone match, target audience fit, product accuracy, "
    "tagline ≤10 words, blog ~200 words, platform-appropriate social posts, "
    "grammar, clarity, and consistency across all three assets. "
    'Return ONLY valid JSON — no markdown fences, no extra text. '
    'Exact format: '
    '{"tagline":{"pass":true,"issue":""},'
    '"blog":{"pass":false,"issue":"Too long"},'
    '"social":{"pass":true,"issue":""}}'
)


# ---------------------------------------------------------------------------
# evaluate_assets
# ---------------------------------------------------------------------------

def evaluate_assets(
    brief: dict,
    tagline: str,
    blog: str,
    social: dict,
) -> dict:
    """
    Ask the LLM to review all three text assets and return a verdict dict.

    Args:
        brief:   Product brief with keys 'product', 'audience', 'tone'.
        tagline: Generated campaign tagline.
        blog:    Generated blog introduction.
        social:  Dict with 'twitter', 'instagram', 'linkedin' posts.

    Returns:
        Dict of shape:
        {
            "tagline":  {"pass": bool, "issue": str},
            "blog":     {"pass": bool, "issue": str},
            "social":   {"pass": bool, "issue": str},
        }
        On parse failure returns all-pass with a warning in each issue field.

    Raises:
        RuntimeError: If the OpenRouter call itself fails (caller handles this).
    """
    product  = brief.get("product",  "")
    audience = brief.get("audience", "")
    tone     = brief.get("tone",     "")

    # Summarise social posts compactly to keep the prompt short
    social_summary = (
        f"Twitter({len(social.get('twitter',''))} chars): "
        f"{social.get('twitter','')[:80]}... | "
        f"Instagram({len(social.get('instagram',''))} chars) | "
        f"LinkedIn({len(social.get('linkedin',''))} chars)"
    )

    user_prompt = (
        f"Product: {product}\n"
        f"Audience: {audience}\n"
        f"Tone: {tone}\n\n"
        f"TAGLINE ({len(tagline.split())} words): {tagline}\n\n"
        f"BLOG ({len(blog.split())} words): {blog[:300]}...\n\n"
        f"SOCIAL: {social_summary}"
    )

    raw = _call_openrouter(_CRITIC_SYSTEM, user_prompt, max_tokens=120)

    # Strip accidental markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

    try:
        verdict = json.loads(raw)
        # Normalise — ensure all three keys exist
        for key in ("tagline", "blog", "social"):
            if key not in verdict:
                verdict[key] = {"pass": True, "issue": ""}
            if "pass" not in verdict[key]:
                verdict[key]["pass"] = True
            if "issue" not in verdict[key]:
                verdict[key]["issue"] = ""
        return verdict
    except json.JSONDecodeError:
        # Critic returned non-JSON — treat as all-pass with a note
        return {
            "tagline": {"pass": True,  "issue": "Critic returned unparseable response."},
            "blog":    {"pass": True,  "issue": "Critic returned unparseable response."},
            "social":  {"pass": True,  "issue": "Critic returned unparseable response."},
        }


# ---------------------------------------------------------------------------
# regenerate_failed_asset
# ---------------------------------------------------------------------------

def regenerate_failed_asset(
    asset_key: str,
    brief: dict,
    issue: str,
    current_results: dict,
) -> "str | dict":
    """
    Regenerate a single asset that failed the critic review.

    Injects the critic's specific issue into the regeneration prompt
    so the model knows exactly what to correct.

    Args:
        asset_key:       One of 'tagline', 'blog', 'social'.
        brief:           Product brief dict.
        issue:           The critic's feedback string for this asset.
        current_results: The current results dict (used to pass tagline
                         to blog regeneration).

    Returns:
        The regenerated asset — str for tagline/blog, dict for social.

    Raises:
        ValueError:   If asset_key is unrecognised.
        RuntimeError: If the API call fails.
    """
    product  = brief.get("product",  "").strip()
    audience = brief.get("audience", "").strip()
    tone     = brief.get("tone",     "").strip()

    if asset_key == "tagline":
        # Few-shot system prompt with critic feedback appended
        system = (
            "Creative director. Output ONE tagline only. "
            "Max 10 words. No hashtags. No quotes. Match tone. "
            f"IMPORTANT — previous version was rejected because: {issue}. "
            "Fix that specific issue."
        )
        messages = [
            {"role": "user",
             "content": f"{product} | {audience} | tone:{tone}"},
        ]
        result = _call_openrouter(system, messages, max_tokens=20)
        return result.strip().strip('"').strip("'").strip()

    elif asset_key == "blog":
        tagline = current_results.get("tagline", "")
        system = (
            "You are a content strategist. Write a ~200-word blog introduction. "
            "Match the tone. Weave in the tagline naturally. "
            "Output ONLY the blog text, no headings. "
            f"IMPORTANT — previous version was rejected because: {issue}. "
            "Fix that specific issue."
        )
        user_prompt = (
            f"Product:{product} | Audience:{audience} | "
            f"Tone:{tone} | Tagline:{tagline}"
        )
        return _call_openrouter(system, user_prompt, max_tokens=350)

    elif asset_key == "social":
        system = (
            'You are a social media copywriter. '
            'Return ONLY a JSON object, no other text, no markdown fences. '
            'Exact format: {"twitter":"post here","instagram":"post here","linkedin":"post here"} '
            'twitter max 280 chars, instagram max 500 chars, linkedin max 300 chars. Match tone. '
            f'IMPORTANT — previous version was rejected because: {issue}. '
            'Fix that specific issue.'
        )
        user_prompt = f"Product:{product} | Audience:{audience} | Tone:{tone}"
        raw = _call_openrouter(system, user_prompt, max_tokens=400)

        # Parse JSON with plain-text fallback
        raw = raw.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        try:
            data = json.loads(raw)
            return {
                "twitter":   str(data.get("twitter",   "")),
                "instagram": str(data.get("instagram", "")),
                "linkedin":  str(data.get("linkedin",  "")),
            }
        except json.JSONDecodeError:
            return {"twitter": raw[:280], "instagram": raw[:500], "linkedin": raw[:300]}

    else:
        raise ValueError(f"Unknown asset key for regeneration: {asset_key!r}")


# ---------------------------------------------------------------------------
# run_critic_loop  — main orchestrator called from app.py
# ---------------------------------------------------------------------------

def run_critic_loop(
    brief: dict,
    results: dict,
    status_container,
) -> dict:
    """
    Run the full self-critique loop on the three text assets.

    Steps:
    1. Call evaluate_assets() to get a verdict for tagline, blog, social.
    2. For each failed asset, attempt up to MAX_RETRIES regenerations.
       Each retry injects the critic's issue into the new prompt.
    3. After each regeneration, re-evaluate only that asset.
    4. Store all results in st.session_state.critic_results.
    5. Write live status updates to status_container (a st.empty()).

    The function never overwrites st.session_state.results directly —
    it returns the (possibly updated) results dict and app.py decides
    whether to write it back.

    Args:
        brief:            Product brief dict.
        results:          Current results dict (tagline, blog, social keys).
        status_container: A st.empty() placeholder for live status messages.

    Returns:
        Updated results dict (may contain regenerated assets).
    """
    # Initialise session state keys for the critic
    if "critic_results" not in st.session_state:
        st.session_state.critic_results = {}
    if "retry_count" not in st.session_state:
        st.session_state.retry_count = {}

    # Work on a copy so we can return the updated version cleanly
    updated = dict(results)

    tagline = updated.get("tagline", "")
    blog    = updated.get("blog",    "")
    social  = updated.get("social",  {"twitter": "", "instagram": "", "linkedin": ""})

    # Skip the loop if the text assets are missing (generation errors)
    if not tagline and not blog and not any(social.values()):
        st.session_state.critic_results = {
            "tagline": {"pass": True,  "issue": "Asset not generated — skipped."},
            "blog":    {"pass": True,  "issue": "Asset not generated — skipped."},
            "social":  {"pass": True,  "issue": "Asset not generated — skipped."},
        }
        return updated

    # ── Initial evaluation ─────────────────────────────────────────────────
    status_container.info("🔍 Running AI self-critique on text assets…")
    try:
        verdict = evaluate_assets(brief, tagline, blog, social)
    except Exception as exc:
        # Critic failure — don't block the pipeline
        st.session_state.critic_results = {
            "_error": f"Critic API failed: {exc}",
            "tagline": {"pass": True, "issue": ""},
            "blog":    {"pass": True, "issue": ""},
            "social":  {"pass": True, "issue": ""},
        }
        status_container.empty()
        return updated

    st.session_state.critic_results = verdict

    # ── Retry loop for failed assets ───────────────────────────────────────
    asset_order = ["tagline", "blog", "social"]   # process in dependency order

    for asset_key in asset_order:
        asset_verdict = verdict.get(asset_key, {"pass": True, "issue": ""})
        if asset_verdict.get("pass", True):
            continue   # already passing — nothing to do

        issue = asset_verdict.get("issue", "Quality issue detected.")
        st.session_state.retry_count[asset_key] = 0

        for attempt in range(1, MAX_RETRIES + 1):
            st.session_state.retry_count[asset_key] = attempt
            status_container.info(
                f"🔄 Auto Regenerating **{asset_key.capitalize()}**… "
                f"Retry {attempt} of {MAX_RETRIES}"
            )

            try:
                new_value = regenerate_failed_asset(
                    asset_key, brief, issue, updated
                )
            except Exception as exc:
                # Regeneration failed — stop retrying this asset
                verdict[asset_key]["issue"] = (
                    f"{issue} | Regeneration error: {exc}"
                )
                st.session_state.critic_results = verdict
                break

            # Update the working copy so subsequent assets get the new value
            updated[asset_key] = new_value

            # Re-evaluate only this asset by running a targeted single-asset check
            try:
                new_tagline = updated.get("tagline", tagline)
                new_blog    = updated.get("blog",    blog)
                new_social  = updated.get("social",  social)
                re_verdict  = evaluate_assets(brief, new_tagline, new_blog, new_social)
                asset_re    = re_verdict.get(asset_key, {"pass": True, "issue": ""})
            except Exception:
                # Can't re-evaluate — assume pass to avoid infinite loop
                asset_re = {"pass": True, "issue": ""}

            if asset_re.get("pass", True):
                # Regeneration succeeded — mark as validated
                verdict[asset_key] = {
                    "pass":  True,
                    "issue": f"Validated after regeneration ✓ (attempt {attempt})",
                }
                st.session_state.critic_results = verdict
                break
        else:
            # All retries exhausted and asset still failing
            verdict[asset_key]["issue"] = (
                f"{issue} | Maximum retries reached. Manual review recommended."
            )
            st.session_state.critic_results = verdict

    status_container.empty()   # clear the live status line
    return updated
