"""JD Optimizer — rewrite job descriptions for inclusivity and brand voice."""

from __future__ import annotations

import html
import json
import re

import streamlit as st

from llm import PROVIDERS, OptimizerError, optimize
from prompts import CULTURE_PROFILES, PROMPT_VERSION, ROLE_LEVELS, build_user_message
from samples import DEMO_RESULT, DEMO_SAMPLE, SAMPLE_JDS
from factcheck import check as fact_check
from scoring import score

MAX_CHARS = 12_000
MAX_RUNS_PER_SESSION = 10  # protects the owner's API key on a public demo

CATEGORIES = {
    "masculine_coded": ("Masculine-coded", "#6366f1"),
    "feminine_coded": ("Feminine-coded", "#db2777"),
    "age": ("Age signal", "#d97706"),
    "ability": ("Ability", "#0891b2"),
    "inflated_requirements": ("Inflated requirements", "#7c3aed"),
    "exclusionary_language": ("Exclusionary language", "#dc2626"),
    "tone": ("Tone", "#64748b"),
}

st.set_page_config(page_title="JD Optimizer", page_icon="✍️", layout="wide")

st.markdown(
    """
<style>
.badge {display: inline-block; padding: 1px 8px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 600; color: white; margin-right: 6px;}
.change {padding: 0.6rem 0; border-bottom: 1px solid rgba(128,128,128,0.2);}
.change .old {text-decoration: line-through; opacity: 0.7;}
.change .reason {opacity: 0.75; font-size: 0.88rem; margin-top: 2px;}
</style>
""",
    unsafe_allow_html=True,
)


# ---------- helpers ----------

JD_BOX_CSS = """<style>
.jd-box {white-space: pre-wrap; line-height: 1.6; font-size: 0.95rem;
         padding: 1rem; border-radius: 0.5rem; font-family: inherit;
         border: 1px solid rgba(128,128,128,0.3);}
.jd-box mark {padding: 0 2px; border-radius: 3px; color: inherit;}
</style>"""


def shrink_headings(md: str) -> str:
    """Render '# Title' / '## Section' at a readable size inside the panel."""
    return re.sub(r"^(#{1,3}) ", lambda m: "#" * (len(m.group(1)) + 3) + " ", md, flags=re.M)


def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:  # no secrets file configured
        return default


def highlight(text: str, changes: list[dict]) -> str:
    """Return HTML for `text` with each changed phrase highlighted."""
    escaped = html.escape(text)
    # Longest phrases first so shorter ones don't split longer matches.
    for c in sorted(changes, key=lambda c: -len(c["original"])):
        phrase = html.escape(c["original"])
        if phrase and phrase in escaped:
            _, color = CATEGORIES[c["category"]]
            tip = html.escape(c["reason"], quote=True)
            escaped = escaped.replace(
                phrase,
                f'<mark style="background:{color}33;border-bottom:2px solid {color}" '
                f'title="{tip}">{phrase}</mark>',
                1,
            )
    return f'{JD_BOX_CSS}<div class="jd-box">{escaped}</div>'


def load_sample() -> None:
    choice = st.session_state.sample_choice
    if choice in SAMPLE_JDS:
        st.session_state.jd = SAMPLE_JDS[choice]


def run_demo() -> None:
    st.session_state.jd = SAMPLE_JDS[DEMO_SAMPLE]
    st.session_state.sample_choice = DEMO_SAMPLE
    st.session_state.culture = "startup_casual"
    st.session_state.result = DEMO_RESULT
    st.session_state.original = SAMPLE_JDS[DEMO_SAMPLE]
    st.session_state.is_demo = True


# ---------- sidebar ----------

gemini_key = get_secret("GEMINI_API_KEY")
anthropic_key = get_secret("ANTHROPIC_API_KEY")
provider = get_secret("PROVIDER", "gemini" if gemini_key or not anthropic_key else "anthropic")
if provider not in PROVIDERS:
    provider = "gemini"
provider_label = PROVIDERS[provider]["label"]
server_key = gemini_key if provider == "gemini" else anthropic_key
model = get_secret("MODEL", PROVIDERS[provider]["default_model"])
st.session_state.setdefault("runs", 0)

with st.sidebar:
    st.header("About")
    st.write(
        "JD Optimizer rewrites job descriptions to reach a wider talent pool. "
        "It flags gender-coded, age-coded and exclusionary language, trims "
        "inflated requirements and matches your company's voice."
    )
    st.markdown(
        "**How it works:** an AI model (Google Gemini or Anthropic Claude) "
        "rewrites the text using an engineered prompt; the scorecard is "
        "computed separately in code, based on "
        "[Gaucher, Friesen & Kay (2011)](https://doi.org/10.1037/a0022530)."
    )
    st.divider()
    user_key = ""
    if not server_key:
        st.subheader("API key")
        user_key = st.text_input(
            f"Your {provider_label} API key", type="password",
            help="Used only for this session and never stored.",
        )
        st.caption("No key? Click **See a demo result** to explore the app.")
    else:
        left = MAX_RUNS_PER_SESSION - st.session_state.runs
        st.caption(f"Free runs left this session: {left}")
    st.caption(f"Model: {provider_label} `{model}` · Prompt {PROMPT_VERSION}")

api_key = user_key or server_key


# ---------- inputs ----------

st.title("✍️ JD Optimizer")
st.write(
    "Paste a job description, choose your company's voice, and get an inclusive "
    "rewrite with every change explained."
)

st.selectbox(
    "Start from a sample (optional)",
    ["—"] + list(SAMPLE_JDS),
    key="sample_choice",
    on_change=load_sample,
)
jd_text = st.text_area("Job description", key="jd", height=280,
                       placeholder="Paste the full job description here…")
if provider == "gemini":
    st.caption("Live results use Google's Gemini free tier, where Google may use inputs "
               "to improve its products. Don't paste confidential job postings.")

c1, c2, c3 = st.columns(3)
culture = c1.selectbox("Culture profile", list(CULTURE_PROFILES),
                       format_func=CULTURE_PROFILES.get, key="culture")
role_level = c2.selectbox("Role level", ROLE_LEVELS)
company = c3.text_input("Company name (optional)")
custom_voice = ""
if culture == "custom":
    custom_voice = st.text_area(
        "Describe your company's voice",
        placeholder="e.g. Friendly and plain-spoken, a little playful, never corporate. "
                    "Or paste your 'About us' text.",
        height=90,
    )

b1, b2, _ = st.columns([1, 1, 3])
optimize_clicked = b1.button("Optimize", type="primary", use_container_width=True)
b2.button("See a demo result", on_click=run_demo, use_container_width=True)

if optimize_clicked:
    if not jd_text.strip():
        st.warning("Paste a job description first.")
    elif len(jd_text) > MAX_CHARS:
        st.warning(f"That's too long. Please keep it under {MAX_CHARS:,} characters.")
    elif not api_key:
        st.warning("The live demo isn't set up with an API key. Add your own in the sidebar, or try the demo result.")
    elif server_key and not user_key and st.session_state.runs >= MAX_RUNS_PER_SESSION:
        st.warning("You've used all the free runs for this session. Add your own API key in the sidebar to continue.")
    elif culture == "custom" and not custom_voice.strip():
        st.warning("Describe your company's voice, or pick a preset profile.")
    else:
        message = build_user_message(jd_text, culture, role_level, company, custom_voice)
        with st.spinner("Reviewing and rewriting… this usually takes 20–40 seconds, or up to a minute when the free model is busy."):
            try:
                st.session_state.result = optimize(message, api_key, provider, model)
                st.session_state.original = jd_text
                st.session_state.is_demo = False
                if not user_key:
                    st.session_state.runs += 1
            except OptimizerError as e:
                st.error(str(e))


# ---------- results ----------

result = st.session_state.get("result")
if result:
    original = st.session_state.original
    rewritten = result["rewritten_jd"]
    st.divider()

    if st.session_state.get("is_demo"):
        st.info("**Demo mode:** this is a pre-written example result for the sample "
                "Software Engineer posting. Add an API key to optimize your own.")

    if not rewritten.strip():
        st.warning(result["summary"] or "The input doesn't look like a job description.")
        st.stop()

    st.subheader("Summary")
    st.write(result["summary"])

    fc = fact_check(original, rewritten, result["changes"])
    st.subheader("Fact check")
    if fc.ok:
        st.success("No dropped facts found. Working conditions, pay terms, numbers and "
                   "the reporting line all carried over.")
    else:
        st.warning("**Review before posting:** the rewrite may have dropped these facts "
                   "from the original. Add them back, reworded if needed.")
        for w in fc.warnings:
            note = "Logged as a change." if w.logged else "Not in the change log."
            st.markdown(f"- **{w.fact}** ({w.category}): {w.detail} _{note}_")
    st.caption("Checked in code by comparing the original and the rewrite, not by the AI.")

    before, after = score(original), score(rewritten)
    st.subheader("Scorecard")
    m = st.columns(5)
    m[0].metric("Masculine-coded words", after.masculine_count,
                after.masculine_count - before.masculine_count, delta_color="inverse")
    m[1].metric("Feminine-coded words", after.feminine_count,
                after.feminine_count - before.feminine_count, delta_color="off")
    m[2].metric("Other flagged phrases", after.other_count,
                after.other_count - before.other_count, delta_color="inverse")
    m[3].metric("Required qualifications", after.required_count,
                after.required_count - before.required_count, delta_color="inverse")
    m[4].metric("Reading grade level", after.reading_grade,
                round(after.reading_grade - before.reading_grade, 1), delta_color="off",
                help="Flesch-Kincaid grade. Grade 8 or below reaches the widest audience.")
    st.caption(f"Overall wording: **{before.balance_label}** → **{after.balance_label}**. "
               "Arrows show the change from the original. Counts are computed in code, "
               "not by the AI.")

    changes = result["changes"]
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Side by side", f"Changes ({len(changes)})",
         f"Suggestions ({len(result['suggestions'])})", "Export"]
    )

    with tab1:
        left, right = st.columns(2)
        left.markdown("**Original** · hover a highlight to see why")
        with left:
            st.html(highlight(original, changes))
        right.markdown("**Optimized**")
        with right.container(border=True):
            st.markdown(shrink_headings(rewritten))

    with tab2:
        if not changes:
            st.write("No changes needed. This description is already in good shape.")
        present = [k for k in CATEGORIES if any(c["category"] == k for c in changes)]
        chosen = st.multiselect("Filter by category", present, default=present,
                                format_func=lambda k: CATEGORIES[k][0])
        for c in changes:
            if c["category"] not in chosen:
                continue
            label, color = CATEGORIES[c["category"]]
            new = (f'→ <b>{html.escape(c["replacement"])}</b>' if c["replacement"]
                   else "→ <i>removed</i>")
            st.markdown(
                f'<div class="change"><span class="badge" style="background:{color}">{label}</span>'
                f'<span class="old">{html.escape(c["original"])}</span> {new}'
                f'<div class="reason">{html.escape(c["reason"])}</div></div>',
                unsafe_allow_html=True,
            )

    with tab3:
        for s in result["suggestions"] or ["Nothing else to add."]:
            st.markdown(f"- {s}")

    with tab4:
        st.write("Copy the rewrite with the button in the top-right of the box below.")
        st.code(rewritten, language=None, wrap_lines=True)
        d1, d2 = st.columns(2)
        d1.download_button("Download rewrite (.md)", rewritten,
                           file_name="optimized_job_description.md", use_container_width=True)
        report = {"original": original, **result, "prompt_version": PROMPT_VERSION,
                  "model": f"{provider}:{model}",
                  "scores": {"before": before.__dict__, "after": after.__dict__},
                  "fact_check": {"length_change": round(fc.length_change, 3),
                                 "warnings": [w.__dict__ for w in fc.warnings]}}
        d2.download_button("Download full report (.json)",
                           json.dumps(report, indent=2, default=str),
                           file_name="jd_optimizer_report.json", use_container_width=True)

st.divider()
st.caption("JD Optimizer is a writing assistant, not legal advice. A person should "
           "always review the final job description before it's posted.")
