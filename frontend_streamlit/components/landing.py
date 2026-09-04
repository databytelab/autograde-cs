"""
The unauthenticated landing page.

Kept in its own module because it is the only part of the app that is a
marketing surface rather than a tool: it has its own design tokens, its own
page width, and no application chrome. Everything here is presentational -
the only interactive elements are the two calls to action, which open the
real authentication dialog.

Streamlit notes that shaped this file:
  * `st.markdown(..., unsafe_allow_html=True)` renders HTML but strips
    <script>, so every visual is static HTML + CSS. A blank line inside an
    HTML string makes the markdown parser wrap fragments in <p>, so the
    templates below deliberately contain none.
  * ui.py ships a shared rule, `.stApp p, [data-testid="stMarkdownContainer"] p
    {font-size:16.5px}`, whose specificity (0,1,1) beats a bare class. Every
    text rule here is therefore prefixed with `.stApp` (0,2,0) so the type
    scale below actually applies - without that, paragraphs silently render
    at 16.5px and the hero overflows the first viewport.
  * Custom widgets cannot be wrapped in an arbitrary <div>, so anything that
    needs a border (the workflow, the review panel) is drawn as one HTML
    block rather than assembled from Streamlit primitives.
  * `st.dialog` is a fragment: widgets inside it rerun only the dialog, so
    the modal stays open while the user types.
"""
from __future__ import annotations

import streamlit as st

from frontend_streamlit.components import api_client

# ---------------------------------------------------------------------
# Design tokens
#
# Deliberately narrow: the warm neutral ground and single terracotta accent
# already belong to the app (see .streamlit/config.toml). `--ag-accent-deep`
# exists because the accent itself only reaches ~3:1 on the cream ground -
# fine for borders and large type, not for small text - so accented small
# text uses the deeper tone instead. The muted/faint greys are set to clear
# 4.5:1 on the cream background.
#
# The vertical rhythm is budgeted so branding, headline, lede, the four
# steps and both CTAs total ~540px and clear the fold at 1366x768.
# ---------------------------------------------------------------------
_CSS = """
<style>
:root{
  --ag-bg:#FAF9F5; --ag-surface:#FFFFFF; --ag-surface-2:#F3F1E9;
  --ag-ink:#26241F; --ag-muted:#5E584E; --ag-faint:#756E61;
  --ag-line:#E4DFD3; --ag-line-strong:#CFC7B6;
  --ag-accent:#CC785C; --ag-accent-deep:#A5573A; --ag-accent-soft:#F7EBE4;
  --ag-ok:#2F6B47; --ag-warn:#8C6318;
  --ag-s1:4px; --ag-s2:8px; --ag-s3:12px; --ag-s4:16px; --ag-s5:24px;
  --ag-s6:32px; --ag-s7:44px; --ag-s8:60px;
  --ag-r-sm:6px; --ag-r-md:10px; --ag-r-lg:12px;
  --ag-icon:60px; --ag-num-h:14px; --ag-num-gap:10px;
  --ag-icon-center:calc(var(--ag-num-h) + var(--ag-num-gap) + var(--ag-icon)/2);
  --ag-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
/* One page width for every section. No application chrome: the workflow
   sidebar and the Streamlit toolbar belong to the signed-in app, and the
   toolbar alone costs ~45px of the first viewport. */
/* 1240 box - 2x20 padding = a 1200px content grid that the hero, the
   workflow and the review panel all share. Streamlit's default side
   padding is ~80px, which would otherwise leave only 1040px of content. */
div[data-testid="stMainBlockContainer"], .block-container{
  max-width:1240px !important; padding-top:30px !important; padding-bottom:36px !important;
  padding-left:20px !important; padding-right:20px !important;
}
section[data-testid="stSidebar"], div[data-testid="stSidebarCollapsedControl"],
header[data-testid="stHeader"]{display:none !important}

/* The two real buttons on the page. */
.stApp .stButton>button{padding:10px 20px; font-size:1rem; font-weight:600;
  border-radius:var(--ag-r-sm); min-height:46px}
.stApp .stButton>button:focus-visible{outline:2px solid var(--ag-accent-deep); outline-offset:2px}

/* ---------- hero ---------- */
.ag-hero{text-align:center}
.ag-brand{display:inline-flex; align-items:center; gap:9px; margin-bottom:var(--ag-s4)}
.ag-brand svg{color:var(--ag-accent); display:block}
.stApp .ag-brand b{font-size:1.05rem; font-weight:700; letter-spacing:-.01em; color:var(--ag-ink)}
/* Element + two classes (0,2,1): Streamlit styles headings with its own
   emotion class + element rule (0,1,1), which otherwise wins and drops the
   headline back to 2.75rem. */
.stApp h1.ag-title{font-size:clamp(2.1rem, 1.1rem + 2.6vw, 3.5rem); font-weight:800;
  line-height:1.08; letter-spacing:-.028em; color:var(--ag-ink);
  margin:0 auto var(--ag-s3); max-width:780px; text-wrap:balance; padding:0}
.stApp .ag-lede{font-size:1.15rem; line-height:1.5; color:var(--ag-muted);
  margin:0 auto; max-width:640px}

/* ---------- auth view ---------- */
.ag-auth{text-align:center; margin-bottom:var(--ag-s5)}
.stApp h1.ag-auth__title{font-size:2rem; font-weight:800; letter-spacing:-.022em;
  line-height:1.15; color:var(--ag-ink); margin:var(--ag-s4) 0 var(--ag-s2); padding:0}
.stApp .ag-auth__sub{font-size:1.05rem; line-height:1.55; color:var(--ag-muted);
  margin:0 auto; max-width:46ch}

/* ---------- workflow ---------- */
.ag-flow{display:grid; grid-template-columns:repeat(4,1fr); gap:0;
  max-width:1100px; margin:var(--ag-s6) auto var(--ag-s5)}
.ag-step{position:relative; text-align:center; padding:0 var(--ag-s4)}
.ag-step:not(:last-child)::after{content:""; position:absolute;
  top:var(--ag-icon-center); left:100%; width:calc(100% - 150px);
  transform:translate(-50%,-50%); border-top:1px solid var(--ag-line-strong)}
.stApp .ag-step__num{height:var(--ag-num-h); line-height:var(--ag-num-h);
  margin-bottom:var(--ag-num-gap); font-family:var(--ag-mono); font-size:.78rem;
  font-weight:600; letter-spacing:.1em; color:var(--ag-faint)}
.ag-step__icon{width:var(--ag-icon); height:var(--ag-icon); margin:0 auto var(--ag-s3);
  display:flex; align-items:center; justify-content:center; background:var(--ag-surface);
  border:1px solid var(--ag-line); border-radius:var(--ag-r-md); color:var(--ag-accent)}
.stApp h3.ag-step__title{font-size:1.1rem; font-weight:700; color:var(--ag-ink);
  margin:0 0 6px; line-height:1.35; padding:0}
.stApp .ag-step__desc{font-size:1rem; line-height:1.5; color:var(--ag-muted);
  margin:0 auto; max-width:30ch}

/* ---------- section headings ---------- */
.ag-rule{height:1px; background:var(--ag-line); border:0; margin:var(--ag-s7) 0 0}
.stApp h2.ag-h2{font-size:1.6rem; font-weight:700; letter-spacing:-.018em; color:var(--ag-ink);
  margin:var(--ag-s7) 0 var(--ag-s2); text-align:center; padding:0}
.stApp .ag-sub{font-size:1.05rem; line-height:1.55; color:var(--ag-muted); text-align:center;
  margin:0 auto var(--ag-s5); max-width:60ch}
.stApp .ag-eyebrow{font-size:.74rem; font-weight:700; letter-spacing:.09em;
  text-transform:uppercase; color:var(--ag-faint); margin:0 0 var(--ag-s3)}

/* ---------- instructor review panel ---------- */
.ag-panel{background:var(--ag-surface); border:1px solid var(--ag-line);
  border-radius:var(--ag-r-lg); overflow:hidden;
  box-shadow:0 1px 2px rgba(38,36,31,.04), 0 8px 24px -18px rgba(38,36,31,.28)}
.ag-panel__bar{display:flex; align-items:center; justify-content:space-between;
  padding:10px var(--ag-s5); background:var(--ag-surface-2);
  border-bottom:1px solid var(--ag-line)}
.stApp .ag-panel__bar span{font-size:.74rem; font-weight:700; letter-spacing:.09em;
  text-transform:uppercase; color:var(--ag-faint)}
.stApp .ag-tag{color:var(--ag-accent-deep) !important; background:var(--ag-accent-soft);
  padding:2px 9px; border-radius:var(--ag-r-sm)}
.ag-panel__head{display:flex; align-items:flex-start; justify-content:space-between;
  gap:var(--ag-s5); flex-wrap:wrap; padding:var(--ag-s5) var(--ag-s5) var(--ag-s4)}
.stApp .ag-assign{font-size:1.18rem; font-weight:700; color:var(--ag-ink); margin:0 0 5px;
  letter-spacing:-.012em}
.stApp .ag-stu{font-size:.95rem; color:var(--ag-muted); margin:0}
.stApp .ag-stu code{font-family:var(--ag-mono); font-size:.88rem; color:var(--ag-faint);
  background:none; padding:0}
.ag-scorebox{text-align:right; white-space:nowrap}
.stApp .ag-scorebox b{display:block; font-size:2rem; font-weight:800; color:var(--ag-ink);
  line-height:1; font-variant-numeric:tabular-nums; letter-spacing:-.02em}
.stApp .ag-scorebox b i{font-style:normal; font-size:.95rem; font-weight:600; color:var(--ag-faint)}
.stApp .ag-scorebox em{display:block; font-style:normal; margin-top:6px; font-size:.76rem;
  font-weight:700; letter-spacing:.07em; text-transform:uppercase; color:var(--ag-accent-deep)}
.ag-panel__strip{display:flex; align-items:center; gap:var(--ag-s3); flex-wrap:wrap;
  padding:10px var(--ag-s5); background:var(--ag-bg);
  border-top:1px solid var(--ag-line); border-bottom:1px solid var(--ag-line)}
.stApp .ag-st{display:inline-flex; align-items:center; gap:7px; font-size:.88rem;
  font-weight:600; color:var(--ag-muted)}
.ag-st::before{content:""; width:7px; height:7px; border-radius:50%;
  background:var(--ag-line-strong); flex:0 0 auto}
.stApp .ag-st--ok{color:var(--ag-ok)} .ag-st--ok::before{background:var(--ag-ok)}
.stApp .ag-st--warn{color:var(--ag-warn)} .ag-st--warn::before{background:var(--ag-warn)}
.ag-panel__body{padding:var(--ag-s5)}

/* rubric rows: one grid, so every row lines up on the same three columns */
.ag-row{display:grid; grid-template-columns:1fr 96px 168px; align-items:center;
  gap:var(--ag-s4); padding:14px var(--ag-s4); border:1px solid var(--ag-line);
  border-radius:var(--ag-r-md); margin-bottom:var(--ag-s2)}
.stApp .ag-row__name{font-size:1rem; font-weight:700; color:var(--ag-ink); margin:0 0 3px}
.stApp .ag-row__ev{font-size:.92rem; line-height:1.45; color:var(--ag-muted); margin:0}
.stApp .ag-row__score{text-align:right; font-size:1.05rem; font-weight:700; color:var(--ag-ink);
  font-variant-numeric:tabular-nums; margin:0}
.stApp .ag-row__score i{font-style:normal; font-size:.85rem; font-weight:600; color:var(--ag-faint)}

/* summary + instructor actions, side by side */
.ag-split{display:grid; grid-template-columns:1.35fr 1fr; gap:0;
  border-top:1px solid var(--ag-line)}
.ag-split>div{padding:var(--ag-s5)}
.ag-split>div+div{border-left:1px solid var(--ag-line); background:var(--ag-bg)}
.stApp .ag-fb{font-size:.95rem; line-height:1.6; color:var(--ag-muted); margin:0 0 var(--ag-s3)}
.stApp .ag-fb:last-child{margin-bottom:0}
.stApp .ag-fb b{color:var(--ag-ink); font-weight:700}
.ag-final{display:flex; align-items:center; gap:var(--ag-s3); margin-bottom:var(--ag-s2)}
.stApp .ag-final span{font-size:.95rem; color:var(--ag-muted)}
.ag-final__box{display:inline-flex; align-items:center; justify-content:center;
  min-width:76px; padding:9px 12px; border:1px solid var(--ag-line-strong);
  border-radius:var(--ag-r-sm); background:var(--ag-surface); font-size:1.05rem;
  font-weight:700; color:var(--ag-ink); font-variant-numeric:tabular-nums}
.ag-actions{display:flex; gap:var(--ag-s2); margin-top:var(--ag-s4); flex-wrap:wrap}
.ag-btn{display:inline-flex; align-items:center; justify-content:center; padding:9px 16px;
  border-radius:var(--ag-r-sm); font-size:.94rem; font-weight:600; border:1px solid}
.ag-btn--primary{background:var(--ag-accent); border-color:var(--ag-accent); color:#FFFFFF}
.ag-btn--ghost{background:var(--ag-surface); border-color:var(--ag-line-strong); color:var(--ag-ink)}
.stApp .ag-micro{font-size:.86rem; line-height:1.5; color:var(--ag-faint); margin:var(--ag-s3) 0 0}

/* ---------- footer ---------- */
.stApp .ag-footer{margin-top:var(--ag-s7); padding-top:var(--ag-s5);
  border-top:1px solid var(--ag-line); text-align:center;
  font-size:.9rem; line-height:1.6; color:var(--ag-faint)}

/* ---------- narrow screens ---------- */
@media (max-width:820px){
  div[data-testid="stMainBlockContainer"], .block-container{padding-top:24px !important}
  .ag-flow{grid-template-columns:1fr; gap:var(--ag-s5); max-width:480px;
    margin-top:var(--ag-s5)}
  .ag-step{display:grid; grid-template-columns:var(--ag-icon) 1fr;
    grid-template-areas:"icon num" "icon title" "icon desc";
    column-gap:var(--ag-s4); row-gap:3px; text-align:left; padding:0}
  .ag-step::after{display:none}
  .ag-step__icon{grid-area:icon; margin:0; align-self:start}
  .stApp .ag-step__num{grid-area:num; height:auto; line-height:1.2; margin:0}
  .stApp .ag-step__title{grid-area:title; margin:0}
  .stApp .ag-step__desc{grid-area:desc; max-width:none}
  .ag-row{grid-template-columns:1fr auto; row-gap:var(--ag-s2)}
  .ag-row__main{grid-column:1 / -1}
  .stApp .ag-row__score{text-align:left}
  .ag-split{grid-template-columns:1fr}
  .ag-split>div+div{border-left:0; border-top:1px solid var(--ag-line)}
  .ag-panel__head{gap:var(--ag-s3)}
  .ag-scorebox{text-align:left}
}
</style>
"""

# Lucide icons, one family throughout: 24x24, stroke 1.75, round caps.
_ICON_ATTRS = ('viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"')


def _icon(paths: str, size: int = 24) -> str:
    return f'<svg width="{size}" height="{size}" {_ICON_ATTRS}>{paths}</svg>'


_CAP = ('<path d="M22 10 12 5 2 10l10 5 10-5Z"/>'
        '<path d="M6 12v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5"/><path d="M22 10v6"/>')
_UPLOAD = ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
           '<path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>')
_SPARKLE = ('<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3'
            'L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>'
            '<path d="M5 3v4"/><path d="M3 5h4"/><path d="M18 17v4"/><path d="M16 19h4"/>')
_REVIEW = ('<rect width="8" height="4" x="8" y="2" rx="1"/>'
           '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
           '<path d="m9 14 2 2 4-4"/>')
_EXPORT = ('<path d="M15 3h6v6"/><path d="M10 14 21 3"/>'
           '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>')

# Descriptions are held to 49-51 characters so all four wrap to exactly two
# lines at every desktop width - no column reads as fuller or emptier than
# its neighbours, and none of them is left looking unfinished.
_STEPS = (
    ("01", _UPLOAD, "Upload",
     "A Canvas ZIP, or loose .ipynb, .html and .py files."),
    ("02", _SPARKLE, "AI grades",
     "Scored against your rubric, criterion by criterion."),
    ("03", _REVIEW, "You review",
     "Change any score you disagree with, then approve."),
    ("04", _EXPORT, "Export / Canvas",
     "Straight to Canvas, or CSV, Excel and PDF export."),
)

# The worked example. Scores sum exactly to the headline total
# (24+25+23+22 = 94/100) - a preview that does not add up reads as fake the
# moment anyone checks it. Every row carries evidence and a status, so no
# row looks unfinished next to another.
_RUBRIC = (
    ("Data Preparation", "24", "25",
     "Stratified split with no leakage; missing values handled before encoding.",
     "Minor deduction", ""),
    ("Model Implementation", "25", "25",
     "Depth swept 1&ndash;12 under cross-validation, best model refit on full train set.",
     "Full marks", " ag-st--ok"),
    ("Evaluation", "23", "25",
     "Accuracy, precision and recall all reported; CV mean given without its spread.",
     "Minor deduction", ""),
    ("Interpretation", "22", "25",
     "Tree plot is readable, but overfitting is not linked to the train/test gap.",
     "Review suggested", " ag-st--warn"),
)


def _hero() -> None:
    st.markdown(
        '<div class="ag-hero">'
        f'<span class="ag-brand">{_icon(_CAP, 22)}<b>AutoGrade CS</b></span>'
        '<h1 class="ag-title">From a folder of notebooks to a graded gradebook.</h1>'
        '<p class="ag-lede">Four steps from submission to grade &mdash; and you '
        'approve every result before a student sees it.</p>'
        '</div>',
        unsafe_allow_html=True,
    )


def _workflow() -> None:
    steps = "".join(
        '<div class="ag-step">'
        f'<div class="ag-step__num">{num}</div>'
        f'<div class="ag-step__icon">{_icon(paths)}</div>'
        f'<h3 class="ag-step__title">{title}</h3>'
        f'<p class="ag-step__desc">{desc}</p>'
        '</div>'
        for num, paths, title, desc in _STEPS
    )
    st.markdown(f'<div class="ag-flow">{steps}</div>', unsafe_allow_html=True)


def _preview() -> None:
    """
    A still of the real review screen.

    Mirrors pages/review_results.py on purpose - an AI-proposed score per
    criterion sitting beside an editable final score, and the same
    Adjust / Approve pair - so what a visitor sees here is what they get
    after signing in. It is a picture, not a control: the buttons and score
    fields are spans, so nothing inside is focusable or clickable.
    """
    rows = "".join(
        '<div class="ag-row">'
        '<div class="ag-row__main">'
        f'<p class="ag-row__name">{name}</p>'
        f'<p class="ag-row__ev">{evidence}</p>'
        '</div>'
        f'<p class="ag-row__score">{score}<i>&thinsp;/&thinsp;{out_of}</i></p>'
        f'<span class="ag-st{status_class}">{status}</span>'
        '</div>'
        for name, score, out_of, evidence, status, status_class in _RUBRIC
    )
    st.markdown(
        '<div class="ag-panel">'
        '<div class="ag-panel__bar"><span>Review results</span>'
        '<span class="ag-tag">Example</span></div>'
        '<div class="ag-panel__head">'
        '<div><p class="ag-assign">Assignment 2 &middot; Decision Tree Classification</p>'
        '<p class="ag-stu">Alex Rivera &middot; <code>decision_tree.ipynb</code></p></div>'
        '<div class="ag-scorebox"><b>94<i>&thinsp;/&thinsp;100</i></b>'
        '<em>AI proposed score</em></div>'
        '</div>'
        '<div class="ag-panel__strip">'
        '<span class="ag-st ag-st--warn">Awaiting instructor approval</span>'
        '</div>'
        '<div class="ag-panel__body">'
        '<p class="ag-eyebrow">Rubric</p>'
        f'{rows}'
        '</div>'
        '<div class="ag-split">'
        '<div><p class="ag-eyebrow">AI feedback summary</p>'
        '<p class="ag-fb"><b>Strengths.</b> A correct, well-sequenced pipeline. The '
        'depth sweep is genuine model selection rather than a single fit, and the '
        'evaluation reports more than accuracy alone.</p>'
        '<p class="ag-fb"><b>To improve.</b> Report the spread of the '
        'cross-validation scores, not just their mean, and connect the chosen tree '
        'depth to the train/test gap in the discussion.</p></div>'
        '<div><p class="ag-eyebrow">Instructor review</p>'
        '<div class="ag-final"><span>Final score</span>'
        '<span class="ag-final__box">94</span><span>/ 100</span></div>'
        '<div class="ag-actions"><span class="ag-btn ag-btn--ghost">Adjust score</span>'
        '<span class="ag-btn ag-btn--primary">Approve grade</span></div>'
        '<p class="ag-micro">The model proposes; you decide. Nothing reaches the '
        'student, the gradebook or Canvas until you approve it.</p></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def _faq() -> None:
    with st.expander("Do I stay in control of every grade?"):
        st.markdown(
            "Yes. The model proposes scores and writes feedback; nothing is "
            "final until you approve it. AutoGrade also recomputes every total "
            "itself from the per-criterion scores, clamps anything above a "
            "criterion's maximum, and fills in criteria the model skipped &mdash; "
            "so the number you see is arithmetic done in plain Python, not by "
            "the model."
        )
    with st.expander("What does the grader actually read?"):
        st.markdown(
            "Jupyter notebooks (`.ipynb`), exported HTML, and plain `.py` files, "
            "either uploaded directly or unpacked from a Canvas *Download "
            "Submissions* ZIP. Each file is split into code, written prose, "
            "execution output (including errors and whether a cell was ever run) "
            "and figures &mdash; both PNG and SVG plots are detected, and you "
            "choose per batch whether to send them to the model."
        )
    with st.expander("Can I override a score the AI proposed?"):
        st.markdown(
            "On any criterion, at any time before you approve. The AI's original "
            "score is kept alongside your change and an optional note explaining "
            "it, so the record always shows both numbers rather than quietly "
            "replacing one with the other."
        )
    with st.expander("Which AI provider is used, and where does my data go?"):
        st.markdown(
            "Your choice, set by the `LLM_PROVIDER` setting on your own server: "
            "**OpenAI** (default), **Claude**, or any OpenAI-compatible endpoint "
            "&mdash; including a local model such as Qwen, which keeps every "
            "submission on hardware you control. Submissions are sent only to the "
            "provider you configure, and AutoGrade stores files and grades in its "
            "own database."
        )
    with st.expander("How do approved grades reach Canvas?"):
        st.markdown(
            "Connect a Canvas API token, match your roster, and push approved "
            "grades and per-criterion comments straight into the gradebook. "
            "Scores are sent as percentages, so a rubric marked out of 100 lands "
            "correctly on a Canvas assignment worth 6 points, or any other value. "
            "Prefer files? Export CSV, Canvas-ready CSV, Excel, or a per-student "
            "PDF feedback packet."
        )


# Authentication is a separate view, not a modal.
#
# The obvious approach - calling an `st.dialog` function straight from the
# button click - is broken for a form that can fail. Streamlit only keeps
# the modal open for the rerun in which that button reads True; a failed
# sign-in triggers another rerun where the button is False, so the dialog
# silently closes and takes its own error message with it. The user sees a
# password rejected as "nothing happened".
#
# Driving the view from session state instead means the form survives any
# number of failed attempts and the error stays on screen. It also gives
# Enter-to-submit and a real back affordance for free.
def _goto(view: str | None) -> None:
    """Switch between the marketing page and the auth view."""
    if view is None:
        st.session_state.pop("ag_view", None)
    else:
        st.session_state["ag_view"] = view
    st.rerun()


def _auth_view(view: str) -> None:
    """The sign-in / create-account page."""
    signing_in = view == "signin"
    st.markdown(
        '<div class="ag-auth">'
        f'<span class="ag-brand">{_icon(_CAP, 22)}<b>AutoGrade CS</b></span>'
        f'<h1 class="ag-auth__title">{"Welcome back" if signing_in else "Create your account"}</h1>'
        f'<p class="ag-auth__sub">{"Sign in to pick up grading where you left off."if signing_in else "Set up an account to start grading with your own rubrics."}</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    _, middle, _ = st.columns([1, 1.15, 1])
    with middle:
        with st.container(border=True):
            if signing_in:
                with st.form("ag_sign_in"):
                    email = st.text_input("Email", placeholder="you@university.edu")
                    password = st.text_input("Password", type="password")
                    submitted = st.form_submit_button(
                        "Sign in", type="primary", use_container_width=True)
                if submitted:
                    if not email.strip() or not password:
                        st.error("Enter your email and your password.")
                    elif api_client.login(email.strip(), password):
                        _goto(None)
                    # A failed call has already reported itself on the page.
            else:
                with st.form("ag_sign_up"):
                    name = st.text_input("Full name")
                    email = st.text_input("Email", key="ag_new_email",
                                          placeholder="you@university.edu")
                    password = st.text_input("Password", type="password",
                                             key="ag_new_password",
                                             help="8-72 characters.")
                    role = st.selectbox(
                        "Role", ["professor", "ta"],
                        help="TAs can grade and leave notes. Only professors "
                             "can approve a grade or delete a course.",
                    )
                    submitted = st.form_submit_button(
                        "Create account", type="primary", use_container_width=True)
                if submitted:
                    if not name.strip():
                        st.error("Please enter your name.")
                    elif not email.strip():
                        st.error("Please enter your email address.")
                    elif len(password) < 8:
                        st.error("Your password must be at least 8 characters.")
                    elif api_client.register(email.strip(), name.strip(),
                                             password, role):
                        _goto(None)

        switch, back = st.columns(2)
        if signing_in:
            if switch.button("Create an account", use_container_width=True):
                _goto("signup")
        else:
            if switch.button("I already have an account", use_container_width=True):
                _goto("signin")
        if back.button("Back", use_container_width=True):
            _goto(None)


def _cta() -> None:
    """The two calls to action, centred under the workflow."""
    _, primary, secondary, _ = st.columns([2, 1.05, 1.05, 2])
    if primary.button("Sign in to start", type="primary",
                      use_container_width=True):
        _goto("signin")
    if secondary.button("Create account", use_container_width=True):
        _goto("signup")


def render_landing() -> None:
    """The whole signed-out page: either the pitch, or the auth view."""
    st.markdown(_CSS, unsafe_allow_html=True)

    # Only surfaced when it is actually broken - a landing page has no
    # business showing a green "everything is fine" status box. Signing in
    # cannot work while this is showing, so it is worth the interruption.
    if api_client.health() is None:
        st.error(
            f"The backend at `{api_client.API_BASE}` is not responding, so "
            "signing in will fail. Start it with "
            "`uvicorn backend.main:app --reload`."
        )

    view = st.session_state.get("ag_view")
    if view in ("signin", "signup"):
        _auth_view(view)
        return

    _hero()
    _workflow()
    _cta()

    st.markdown('<hr class="ag-rule">', unsafe_allow_html=True)
    st.markdown(
        '<h2 class="ag-h2">See what you review before a grade is published.</h2>'
        '<p class="ag-sub">Every score below was proposed by the model. This is '
        'the screen where you check it, change it, and decide.</p>',
        unsafe_allow_html=True,
    )
    _preview()

    st.markdown('<hr class="ag-rule">', unsafe_allow_html=True)
    st.markdown(
        '<h2 class="ag-h2">Built for instructor control.</h2>'
        '<p class="ag-sub">The parts most people ask about before they trust a '
        'grader with a class.</p>',
        unsafe_allow_html=True,
    )
    _faq()

    st.markdown(
        '<div class="ag-footer">AutoGrade CS &mdash; AI-assisted grading for '
        'computer science courses.<br>Grades are proposed by a model and '
        'approved by an instructor.</div>',
        unsafe_allow_html=True,
    )
