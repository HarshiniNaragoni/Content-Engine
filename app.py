"""
app.py - Streamlit UI entry point.

Responsibilities:
- Render the application layout and sidebar input form
- Orchestrate five sequential AI generation calls on button click
- Display each asset inside its dedicated card as soon as it is ready
- Show a loading indicator only for the card currently being generated
- Display per-card errors without stopping the rest of the pipeline
- Persist all results in st.session_state until the next generation run
"""

import streamlit as st
from config import APP_TITLE, APP_ICON

# Suppress the harmless WinError 10054 asyncio noise on Windows
import asyncio, sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — dark professional theme (do not modify layout or colours)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Hide Streamlit chrome — keep header so sidebar toggle stays accessible */
    #MainMenu, footer { visibility: hidden; }
    header [data-testid="stToolbar"] { visibility: hidden; }
    header[data-testid="stHeader"] {
        background: transparent !important;
        box-shadow: none !important;
    }

    .stApp { background: #0f1117; }

    /* ── Page header ── */
    .ce-header {
        background: linear-gradient(135deg, #1a1d2e 0%, #16213e 50%, #0f3460 100%);
        border-bottom: 1px solid #2d3561;
        padding: 2rem 2.5rem 1.5rem;
        margin: -1rem -1rem 1.5rem -1rem;
    }
    .ce-header h1 { font-size: 2.2rem; font-weight: 700; color: #fff; margin: 0 0 .3rem; letter-spacing: -.5px; }
    .ce-header p  { font-size: 1.05rem; color: #8b9ec7; margin: 0; }
    .ce-header .accent { color: #4f8ef7; }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: #13151f !important;
        border-right: 1px solid #1e2235 !important;
        min-width: 280px !important;
        max-width: 320px !important;
        transform: none !important;
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
        left: 0 !important;
        position: relative !important;
    }

    /* Force sidebar content wrapper to be visible */
    section[data-testid="stSidebar"] > div {
        display: block !important;
        visibility: visible !important;
        width: 280px !important;
    }

    /* Always show the sidebar toggle arrow */
    button[data-testid="collapsedControl"] {
        visibility: visible !important;
        display: flex !important;
        opacity: 1 !important;
    }
    section[data-testid="stSidebar"] .stMarkdown h2 {
        color: #c8d3f0; font-size: .75rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 1rem;
    }
    section[data-testid="stSidebar"] label {
        color: #8b9ec7 !important; font-size: .82rem !important; font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] .stTextInput input,
    section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] {
        background: #1a1d2e !important; border: 1px solid #2d3561 !important;
        color: #e0e6f7 !important; border-radius: 8px !important;
    }
    section[data-testid="stSidebar"] .stTextInput input:focus {
        border-color: #4f8ef7 !important;
        box-shadow: 0 0 0 2px rgba(79,142,247,.2) !important;
    }
    section[data-testid="stSidebar"] .stButton button {
        width: 100%; background: linear-gradient(135deg, #4f8ef7 0%, #2563eb 100%);
        color: #fff; border: none; border-radius: 10px; padding: .65rem 1rem;
        font-size: .95rem; font-weight: 600; cursor: pointer;
        transition: opacity .2s, transform .1s; margin-top: .5rem;
    }
    section[data-testid="stSidebar"] .stButton button:hover { opacity: .88; transform: translateY(-1px); }
    section[data-testid="stSidebar"] .stButton button:disabled {
        background: #2d3561; color: #555e80; cursor: not-allowed; transform: none;
    }

    /* ── Status badge ── */
    .status-badge {
        display: inline-flex; align-items: center; gap: .4rem;
        padding: .35rem .75rem; border-radius: 20px; font-size: .78rem;
        font-weight: 500; margin-top: .75rem;
    }
    .status-idle    { background: #1e2235; color: #6b7db3; border: 1px solid #2d3561; }
    .status-running { background: #1a2a1a; color: #4ade80; border: 1px solid #166534; }
    .status-done    { background: #1a2235; color: #60a5fa; border: 1px solid #1d4ed8; }

    /* ── Section labels ── */
    .section-label {
        font-size: .7rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 1.8px; color: #4f8ef7; margin-bottom: .6rem;
    }

    /* ── Asset cards ── */
    .asset-card {
        background: #13151f; border: 1px solid #1e2235; border-radius: 14px;
        padding: 1.25rem 1.4rem; margin-bottom: 1.1rem; transition: border-color .2s;
    }
    .asset-card:hover { border-color: #2d3561; }
    .asset-card-header { display: flex; align-items: center; gap: .55rem; margin-bottom: .75rem; }
    .asset-card-icon   { font-size: 1.15rem; }
    .asset-card-title  { font-size: .88rem; font-weight: 600; color: #c8d3f0; }
    .asset-card-technique {
        margin-left: auto; font-size: .68rem; color: #4f8ef7;
        background: #1a2444; border: 1px solid #2d3f6e;
        border-radius: 10px; padding: .18rem .55rem; font-weight: 500;
    }

    /* ── Card content states ── */
    .waiting-text  { color: #3d4666; font-size: .85rem; font-style: italic; padding: .5rem 0; }
    .error-text    { color: #f87171; font-size: .82rem; line-height: 1.6; padding: .4rem 0; }

    /* ── Media placeholders ── */
    .media-placeholder {
        background: #0d0f1a; border: 2px dashed #1e2235; border-radius: 12px;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        padding: 3rem 1rem; min-height: 220px; color: #3d4666; gap: .5rem;
    }
    .media-placeholder-icon { font-size: 2.5rem; }
    .media-placeholder-text { font-size: .82rem; font-style: italic; }

    /* ── Dividers ── */
    .ce-divider { border: none; border-top: 1px solid #1e2235; margin: .5rem 0 1rem; }

    /* ── Spinner ── */
    .stSpinner > div { border-top-color: #4f8ef7 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state — initialise once
# ---------------------------------------------------------------------------
for _key, _default in [
    ("generated",      False),
    ("generating",     False),
    ("active_step",    None),
    ("results",        {}),
    ("errors",         {}),
    ("critic_results", {}),
    ("retry_count",    {}),
    ("adapted_results", None),   # output from Multi-Channel Adaptation
]:
    if _key not in st.session_state:
        st.session_state[_key] = _default


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _card_shell(icon: str, title: str, technique: str) -> str:
    """Return the opening HTML for an asset card header."""
    return (
        f'<div class="asset-card">'
        f'<div class="asset-card-header">'
        f'<span class="asset-card-icon">{icon}</span>'
        f'<span class="asset-card-title">{title}</span>'
        f'<span class="asset-card-technique">{technique}</span>'
        f'</div>'
    )


def _render_text_card(
    icon: str, title: str, technique: str,
    result_key: str, step_name: str,
    content_fn,
) -> None:
    """
    Render a text-based asset card with three states:
    - Loading  : spinner + generating message (only when this step is active)
    - Error    : red error message
    - Result   : content rendered by content_fn(value)
    - Waiting  : default placeholder
    """
    is_active = st.session_state.active_step == step_name
    has_result = result_key in st.session_state.results
    has_error  = result_key in st.session_state.errors

    if is_active:
        with st.spinner(f"Generating {title.lower()}…"):
            st.markdown(
                _card_shell(icon, title, technique)
                + '<p class="waiting-text">🔄 Generating…</p></div>',
                unsafe_allow_html=True,
            )
    elif has_error:
        st.markdown(
            _card_shell(icon, title, technique)
            + f'<p class="error-text">⚠️ {st.session_state.errors[result_key]}</p></div>',
            unsafe_allow_html=True,
        )
    elif has_result:
        content_fn(st.session_state.results[result_key])
    else:
        st.markdown(
            _card_shell(icon, title, technique)
            + '<p class="waiting-text">⏳ Waiting for generation…</p></div>',
            unsafe_allow_html=True,
        )


def _render_media_card(
    icon: str, title: str, technique: str,
    result_key: str, step_name: str,
    media_fn,
    placeholder_icon: str,
) -> None:
    """Render an image or video card with the same three-state logic."""
    is_active = st.session_state.active_step == step_name
    has_result = result_key in st.session_state.results
    has_error  = result_key in st.session_state.errors

    if is_active:
        with st.spinner(f"Generating {title.lower()}…"):
            st.markdown(
                _card_shell(icon, title, technique)
                + f'<div class="media-placeholder">'
                f'<span class="media-placeholder-icon">{placeholder_icon}</span>'
                f'<span class="media-placeholder-text">🔄 Generating…</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
    elif has_error:
        err_txt = st.session_state.errors[result_key]
        # Friendly display for out-of-credits (not a code error)
        if "credits" in err_txt.lower() or "top up" in err_txt.lower():
            icon_display = "💳"
            color = "#facc15"
        else:
            icon_display = placeholder_icon
            color = "#f87171"
        st.markdown(
            _card_shell(icon, title, technique)
            + f'<div class="media-placeholder">'
            f'<span class="media-placeholder-icon">{icon_display}</span>'
            f'<p style="color:{color};font-size:.82rem;text-align:center;padding:0 1rem;">{err_txt}</p>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    elif has_result:
        st.markdown(_card_shell(icon, title, technique), unsafe_allow_html=True)
        media_fn(st.session_state.results[result_key])
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            _card_shell(icon, title, technique)
            + f'<div class="media-placeholder">'
            f'<span class="media-placeholder-icon">{placeholder_icon}</span>'
            f'<span class="media-placeholder-text">⏳ Waiting for generation…</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="ce-header">
        <h1>🚀 AI Content Engine</h1>
        <p>One Brief <span class="accent">→</span> Five Creative Assets Out</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar — input form
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 📋 Product Brief")
    st.markdown('<hr class="ce-divider">', unsafe_allow_html=True)

    product_name = st.text_input(
        "Product Name",
        placeholder="e.g. AquaFlow Pro",
        help="The name of the product you are promoting.",
    )
    target_audience = st.text_input(
        "Target Audience",
        placeholder="e.g. Outdoor enthusiasts aged 25–40",
        help="Who is this campaign for?",
    )
    brand_tone = st.selectbox(
        "Brand Tone",
        options=["", "playful", "premium", "eco", "bold", "minimalist"],
        format_func=lambda x: "Select a tone…" if x == "" else x.capitalize(),
        help="Controls the voice and style for all five assets.",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    form_complete = bool(
        product_name.strip() and target_audience.strip() and brand_tone
    )
    generate_btn = st.button(
        "⚡ Generate Campaign Suite",
        disabled=not form_complete,
        use_container_width=True,
    )

    # Status badge
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Status**")
    if st.session_state.generating:
        st.markdown(
            '<div class="status-badge status-running">🟢 Generating assets…</div>',
            unsafe_allow_html=True,
        )
    elif st.session_state.generated:
        st.markdown(
            '<div class="status-badge status-done">✅ Suite complete</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-badge status-idle">⚪ Awaiting input</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Main area — two-column layout
# ---------------------------------------------------------------------------
left_col, right_col = st.columns([1.1, 0.9], gap="large")

# ── LEFT — Text assets ──────────────────────────────────────────────────────
with left_col:
    st.markdown('<p class="section-label">📝 Text Assets</p>', unsafe_allow_html=True)

    # Card 1 — Campaign Tagline
    def _render_tagline(value: str) -> None:
        st.markdown(
            _card_shell("📣", "Campaign Tagline", "Few-shot prompting")
            + f'<p style="color:#e0e6f7;font-size:1.1rem;font-weight:600;">"{value}"</p>'
            + "</div>",
            unsafe_allow_html=True,
        )

    _render_text_card(
        "📣", "Campaign Tagline", "Few-shot prompting",
        "tagline", "tagline", _render_tagline,
    )

    # Card 2 — Blog Introduction
    def _render_blog(value: str) -> None:
        st.markdown(
            _card_shell("📝", "Blog Introduction", "Role-based prompting")
            + f'<p style="color:#b0bdd8;font-size:.88rem;line-height:1.7;">{value}</p>'
            + "</div>",
            unsafe_allow_html=True,
        )

    _render_text_card(
        "📝", "Blog Introduction", "Role-based prompting",
        "blog", "blog", _render_blog,
    )

    # Card 3 — Social Media Posts
    def _render_social(value: dict) -> None:
        platform_labels = {
            "twitter":   "𝕏 Twitter / X",
            "instagram": "📸 Instagram",
            "linkedin":  "💼 LinkedIn",
        }
        rows = "".join(
            f'<div style="margin-bottom:.85rem;">'
            f'<span style="font-size:.7rem;font-weight:600;text-transform:uppercase;'
            f'letter-spacing:1px;color:#4f8ef7;">{platform_labels.get(k, k)}</span>'
            f'<p style="color:#b0bdd8;font-size:.84rem;margin:.25rem 0 0;line-height:1.6;">{v}</p>'
            f'</div>'
            for k, v in value.items()
        )
        st.markdown(
            _card_shell("📱", "Social Media Posts", "Structured output")
            + rows + "</div>",
            unsafe_allow_html=True,
        )

    _render_text_card(
        "📱", "Social Media Posts", "Structured output",
        "social", "social", _render_social,
    )

# ── RIGHT — Visual assets ───────────────────────────────────────────────────
with right_col:
    st.markdown('<p class="section-label">🎨 Visual Assets</p>', unsafe_allow_html=True)

    # Card 4 — Hero Image
    _render_media_card(
        "🎨", "Hero Image", "GPT Image API",
        "image_url", "image",
        lambda url: st.image(url, use_container_width=True),
        "🖼️",
    )

    # Card 5 — Promotional Video
    _render_media_card(
        "🎬", "Promotional Video", "Runway API",
        "video_url", "video",
        lambda url: st.video(url),
        "🎥",
    )

# ---------------------------------------------------------------------------
# Self-Critique Section — rendered below the two-column asset cards
# Only shown after generation is complete and critic results exist
# ---------------------------------------------------------------------------
if st.session_state.generated and st.session_state.critic_results:
    st.markdown("<br>", unsafe_allow_html=True)

    # Section header
    st.markdown(
        """
        <div style="
            border-top: 1px solid #2d3561;
            border-bottom: 1px solid #2d3561;
            padding: .75rem 0;
            margin-bottom: 1.2rem;
            text-align: center;
        ">
            <span style="font-size:.7rem;font-weight:700;letter-spacing:2.5px;
                         text-transform:uppercase;color:#4f8ef7;">
                🤖 &nbsp; Self-Critique &nbsp; 🤖
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    critic = st.session_state.critic_results

    # Show a critic-level error if the whole evaluation failed
    if "_error" in critic:
        st.warning(f"⚠️ Critic evaluation failed: {critic['_error']}")

    # Render three review cards side by side
    c1, c2, c3 = st.columns(3, gap="medium")

    def _critique_card(container, label: str, key: str) -> None:
        """Render a single critique result card inside the given column."""
        verdict = critic.get(key, {})
        passed  = verdict.get("pass", True)
        issue   = verdict.get("issue", "")

        retry_n = st.session_state.retry_count.get(key, 0)

        if passed:
            badge_html = '<span style="color:#4ade80;font-weight:700;">PASS ✅</span>'
        else:
            badge_html = '<span style="color:#f87171;font-weight:700;">FAIL ❌</span>'

        # Build status line
        if "Validated after regeneration" in issue:
            status_html = f'<p style="color:#4ade80;font-size:.78rem;margin:.4rem 0 0;">{issue}</p>'
        elif "Maximum retries reached" in issue:
            status_html = (
                '<p style="color:#f87171;font-size:.78rem;margin:.4rem 0 0;">'
                'Maximum retries reached. Manual review recommended.</p>'
            )
        elif "Auto Regenerating" in issue or retry_n > 0:
            status_html = (
                f'<p style="color:#facc15;font-size:.78rem;margin:.4rem 0 0;">'
                f'🔄 Auto Regenerating… Retry {retry_n} of 2</p>'
            )
        elif issue and not passed:
            status_html = (
                f'<p style="color:#f87171;font-size:.78rem;margin:.4rem 0 0;">'
                f'Issue: {issue}</p>'
            )
        else:
            status_html = ""

        with container:
            st.markdown(
                f'<div class="asset-card" style="min-height:110px;">'
                f'<div class="asset-card-header">'
                f'<span class="asset-card-title">{label}</span>'
                f'</div>'
                f'{badge_html}'
                f'{status_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

    _critique_card(c1, "📣 Campaign Tagline",   "tagline")
    _critique_card(c2, "📝 Blog Introduction",  "blog")
    _critique_card(c3, "📱 Social Media Posts", "social")


# ---------------------------------------------------------------------------
# Multi-Channel Adaptation — below Self-Critique, only when generated
# ---------------------------------------------------------------------------
if st.session_state.generated and st.session_state.results:
    from adapter import CHANNELS, adapt_campaign

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Section header ─────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="
            border-top: 1px solid #2d3561;
            border-bottom: 1px solid #2d3561;
            padding: .75rem 0;
            margin-bottom: 1.2rem;
            text-align: center;
        ">
            <span style="font-size:.7rem;font-weight:700;letter-spacing:2.5px;
                         text-transform:uppercase;color:#4f8ef7;">
                📡 &nbsp; Multi-Channel Adaptation &nbsp; 📡
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Controls ───────────────────────────────────────────────────────────
    adapt_col1, adapt_col2 = st.columns([2, 1], gap="medium")
    with adapt_col1:
        selected_channel = st.selectbox(
            "Target Channel",
            options=list(CHANNELS.keys()),
            help="Rewrite the text assets for a specific distribution channel.",
            key="channel_select",
        )
    with adapt_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        adapt_btn = st.button(
            "🔄 Adapt Campaign",
            use_container_width=True,
            key="adapt_btn",
        )

    # ── Run adaptation when button clicked ────────────────────────────────
    if adapt_btn:
        brief_for_adapt = {
            "product":  product_name,
            "audience": target_audience,
            "tone":     brand_tone,
        }
        with st.spinner(f"Adapting campaign for {selected_channel}…"):
            try:
                st.session_state.adapted_results = adapt_campaign(
                    brief_for_adapt,
                    st.session_state.results,
                    selected_channel,
                )
            except Exception as exc:
                st.session_state.adapted_results = {"_error": str(exc)}

    # ── Display adapted results ────────────────────────────────────────────
    adapted = st.session_state.adapted_results
    if adapted:
        if "_error" in adapted:
            st.markdown(
                f'<p class="error-text">⚠️ Adaptation failed: {adapted["_error"]}</p>',
                unsafe_allow_html=True,
            )
        else:
            channel_label = selected_channel

            st.markdown(
                f'<p class="section-label">✨ Adapted for: {channel_label}</p>',
                unsafe_allow_html=True,
            )

            adapted_left, adapted_right_spacer = st.columns([1.1, 0.9], gap="large")

            with adapted_left:
                # Adapted Tagline
                st.markdown(
                    _card_shell("📣", "Adapted Tagline", channel_label)
                    + f'<p style="color:#e0e6f7;font-size:1.1rem;font-weight:600;">'
                    f'"{adapted["tagline"]}"</p></div>',
                    unsafe_allow_html=True,
                )

                # Adapted Blog
                st.markdown(
                    _card_shell("📝", "Adapted Blog Introduction", channel_label)
                    + f'<p style="color:#b0bdd8;font-size:.88rem;line-height:1.7;">'
                    f'{adapted["blog"]}</p></div>',
                    unsafe_allow_html=True,
                )

                # Adapted Social Posts
                social_adapted = adapted.get("social", {})
                platform_labels = {
                    "twitter":   "𝕏 Twitter / X",
                    "instagram": "📸 Instagram",
                    "linkedin":  "💼 LinkedIn",
                }
                rows = "".join(
                    f'<div style="margin-bottom:.85rem;">'
                    f'<span style="font-size:.7rem;font-weight:600;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#4f8ef7;">{platform_labels.get(k, k)}</span>'
                    f'<p style="color:#b0bdd8;font-size:.84rem;margin:.25rem 0 0;'
                    f'line-height:1.6;">{v}</p></div>'
                    for k, v in social_adapted.items() if v
                )
                st.markdown(
                    _card_shell("📱", "Adapted Social Posts", channel_label)
                    + rows + "</div>",
                    unsafe_allow_html=True,
                )

            with adapted_right_spacer:
                # Keep the right column empty — visual assets are unchanged
                st.markdown(
                    '<div class="asset-card" style="min-height:80px;">'
                    '<div class="asset-card-header">'
                    '<span class="asset-card-icon">🖼️</span>'
                    '<span class="asset-card-title">Hero Image</span>'
                    '<span class="asset-card-technique">Unchanged</span>'
                    '</div>'
                    '<p class="waiting-text">Original hero image applies to all channels.</p>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div class="asset-card" style="min-height:80px;">'
                    '<div class="asset-card-header">'
                    '<span class="asset-card-icon">🎬</span>'
                    '<span class="asset-card-title">Promotional Video</span>'
                    '<span class="asset-card-technique">Unchanged</span>'
                    '</div>'
                    '<p class="waiting-text">Original promotional video applies to all channels.</p>'
                    '</div>',
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# Generation trigger — reset state and rerun into the orchestration block
# ---------------------------------------------------------------------------
if generate_btn and form_complete:
    st.session_state.generating     = True
    st.session_state.generated      = False
    st.session_state.active_step    = None
    st.session_state.results        = {}
    st.session_state.errors         = {}
    st.session_state.critic_results = {}
    st.session_state.retry_count    = {}
    st.session_state.adapted_results = None   # clear previous adaptation
    st.rerun()

# ---------------------------------------------------------------------------
# Sequential orchestration — runs all five steps in one pass.
# active_step drives which card shows a spinner on the NEXT render.
# ---------------------------------------------------------------------------
if st.session_state.generating:
    from text_gen  import generate_tagline, generate_blog_intro, generate_social_posts
    from image_gen import generate_hero_image
    from video_gen import generate_promo_video

    brief = {
        "product":  product_name,
        "audience": target_audience,
        "tone":     brand_tone,
    }

    # ── Step 1 — Campaign Tagline ──────────────────────────────────────────
    st.session_state.active_step = "tagline"
    try:
        st.session_state.results["tagline"] = generate_tagline(brief)
    except Exception as exc:
        st.session_state.errors["tagline"] = str(exc)

    # ── Step 2 — Blog Introduction ─────────────────────────────────────────
    st.session_state.active_step = "blog"
    tagline_value = st.session_state.results.get("tagline", "")
    try:
        st.session_state.results["blog"] = generate_blog_intro(brief, tagline_value)
    except Exception as exc:
        st.session_state.errors["blog"] = str(exc)

    # ── Step 3 — Social Media Posts ────────────────────────────────────────
    st.session_state.active_step = "social"
    try:
        st.session_state.results["social"] = generate_social_posts(brief)
    except Exception as exc:
        st.session_state.errors["social"] = str(exc)

    # ── Self-Critique Loop — runs after all three text assets are ready ────
    # Runs only when at least tagline was generated (not errored).
    # Updates st.session_state.results in place with any regenerated assets.
    if "tagline" not in st.session_state.errors:
        from critic import run_critic_loop
        _critic_status = st.empty()   # live status placeholder shown during critique
        st.session_state.results = run_critic_loop(
            brief,
            st.session_state.results,
            _critic_status,
        )

    # ── Step 4 — Hero Image ────────────────────────────────────────────────
    st.session_state.active_step = "image"
    tagline_value = st.session_state.results.get("tagline", "")
    try:
        st.session_state.results["image_url"] = generate_hero_image(brief, tagline_value)
    except Exception as exc:
        st.session_state.errors["image_url"] = str(exc)

    # ── Step 5 — Promotional Video ─────────────────────────────────────────
    st.session_state.active_step = "video"
    image_url_value = st.session_state.results.get("image_url", "")
    try:
        st.session_state.results["video_url"] = generate_promo_video(brief, image_url_value)
    except Exception as exc:
        err_msg = str(exc)
        # Show a friendly message for out-of-credits errors instead of a red crash
        if any(w in err_msg.lower() for w in ["credits", "subscribe", "fund", "wallet"]):
            st.session_state.errors["video_url"] = (
                "Video generation requires credits. "
                "Top up at modelslab.com/dashboard or add a Runway API key (key_...) to .env."
            )
        else:
            st.session_state.errors["video_url"] = err_msg

    # ── All steps done — mark complete and rerender ────────────────────────
    st.session_state.generating  = False
    st.session_state.generated   = True
    st.session_state.active_step = None
    st.rerun()
