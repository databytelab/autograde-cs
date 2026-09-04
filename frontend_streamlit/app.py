"""
AutoGrade CS - Streamlit MVP Frontend

Run with:
    streamlit run frontend_streamlit/app.py

The FastAPI backend must be running too:
    uvicorn backend.main:app --reload
"""
from __future__ import annotations

import streamlit as st

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path, so the project
# root has to be added before any `frontend_streamlit.*` import works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import (
    grading_key_hint,
    grading_ready,
    page_link,
    page_setup,
    render_locked_sidebar,
    render_sidebar,
)

page_setup("Home")


# ---------------------------------------------------------------------
# Signed in
# ---------------------------------------------------------------------
if st.session_state.get("token"):
    user = st.session_state["user"]
    render_sidebar(user)

    st.title("AutoGrade CS")
    st.markdown(
        "<p style='font-size:1.15rem; line-height:1.55; color:#6b675f; "
        "margin:-2px 0 14px 0;'>AI-assisted grading for CS assignments "
        "&mdash; you stay in control of every grade.</p>",
        unsafe_allow_html=True,
    )

    st.success(f"Signed in as **{user['name']}**")

    status = api_client.health()
    if status and not grading_ready(status):
        key_hint = grading_key_hint(status)
        provider = status.get("llm_provider", "the AI")
        st.warning(
            f"**Grading is disabled.** The {provider} backend is not configured. "
            f"Set `{key_hint}` in your `.env` file (or switch `LLM_PROVIDER`) and "
            "restart the server. Everything else - uploading, similarity "
            "detection, export - works without it."
        )

    st.subheader("Where to start")
    columns = st.columns(5)
    with columns[0]:
        page_link("pages/dashboard.py", label="Dashboard", icon=":material/space_dashboard:")
        st.caption("See every course and how grading is going.")
    with columns[1]:
        page_link("pages/new_assignment.py", label="New assignment", icon=":material/note_add:")
        st.caption("Create a course or assignment and write its rubric.")
    with columns[2]:
        page_link("pages/upload_grade.py", label="Upload & grade", icon=":material/upload_file:")
        st.caption("Upload student files and run the grader.")
    with columns[3]:
        page_link("pages/review_results.py", label="Review results", icon=":material/fact_check:")
        st.caption("Read the feedback, adjust scores, approve grades.")
    with columns[4]:
        page_link("pages/export.py", label="Export", icon=":material/download:")
        st.caption("Download CSV, Excel, PDF, or push to Canvas.")

    st.divider()
    with st.expander("How grading works"):
        st.markdown(
            """
            1. **Parse** - your students' `.ipynb`, `.html` and `.py` files are
               broken into cells, code, prose, outputs and figures.
            2. **Grade** - each submission goes to the model once, together with
               your rubric. The model scores every criterion and writes
               feedback and its reasoning.
            3. **Verify** - AutoGrade recomputes every total itself, clamps any
               score above a criterion's maximum, and fills in any criterion
               the model skipped. The model never does arithmetic that counts.
            4. **Review** - you read the feedback, override anything you
               disagree with, and approve. The AI's original scores are kept
               alongside your changes, so the record always shows both.

            Nothing is pushed to Canvas or handed to a student until you
            finalize it.
            """
        )

    st.stop()


# ---------------------------------------------------------------------
# Signed out - the landing page
# ---------------------------------------------------------------------
# The animated hero. Everything here is pure CSS (Streamlit strips <script>
# from injected HTML), so it animates in the browser and needs no JavaScript.
# Classes are `ag-` prefixed so they never collide with Streamlit's own.
#
#   - a live "grading batch" card whose student, score and bars cycle, and
#     whose counter climbs 18 -> 19 -> 20 in step with them, so the number
#     means "submissions graded so far", not a static decoration;
#   - a four-step pipeline connected by a single rail centred on the icons,
#     each icon lighting up 01 -> 04 in turn;
#   - a smooth sweeping progress bar instead of a blinking dot.
#
# On a wide page the card floats into the top-right corner; below ~900px of
# hero width (a CSS container query) it drops in-flow, centred, so nothing
# ever overlaps the headline. `prefers-reduced-motion` disables all of it.
_HERO = """
<style>
.ag-hero{position:relative; container-type:inline-size; max-width:940px;
  margin:6px auto 2px; padding:6px 6px 0}
.ag-band{display:flex; flex-direction:column; align-items:center; text-align:center}
.ag-intro{max-width:560px}
.ag-eyebrow{font-size:.72rem; font-weight:700; letter-spacing:.15em;
  text-transform:uppercase; color:#B0603C}
.ag-h1{font-weight:800; font-size:2.05rem; line-height:1.08; letter-spacing:-.02em;
  color:#2A2723; margin:.45rem 0 .5rem; text-wrap:balance}
.ag-sub{color:#6E685E; font-size:1.02rem; line-height:1.55; margin:0}

.ag-live{width:min(320px,100%); margin:22px auto 4px; background:#fff;
  border:1px solid #E7E2D6; border-radius:14px; text-align:left;
  box-shadow:0 16px 34px -22px rgba(60,48,30,.5); padding:13px 15px}
.ag-lh{display:flex; align-items:center; gap:8px; font-size:.73rem; color:#6E685E;
  font-weight:600; margin-bottom:10px}
.ag-lh .ag-actv{color:#CC785C; display:inline-flex}
.ag-count{margin-left:auto; font-family:ui-monospace,Menlo,Consolas,monospace;
  color:#2A2723; font-weight:600; font-size:.73rem; display:inline-grid}
.ag-count span{grid-area:1/1; white-space:nowrap; opacity:0;
  animation:ag-fade 9s ease-in-out infinite}
.ag-n1{animation-delay:0s}.ag-n2{animation-delay:3s}.ag-n3{animation-delay:6s}
.ag-prog{height:3px; background:#F1EEE6; border-radius:99px; overflow:hidden;
  margin-bottom:12px}
.ag-prog>span{display:block; height:100%; width:38%; background:#CC785C;
  border-radius:99px; animation:ag-march 2.3s linear infinite}
.ag-stack{position:relative; height:72px}
.ag-card{position:absolute; inset:0; opacity:0; animation:ag-swap 9s ease-in-out infinite}
.ag-c1{animation-delay:0s}.ag-c2{animation-delay:3s}.ag-c3{animation-delay:6s}
.ag-crow{display:flex; justify-content:space-between; align-items:flex-start; gap:10px}
.ag-nm{font-size:.88rem; font-weight:700; color:#2A2723}
.ag-fl{font-size:.68rem; color:#928B7E; margin-top:2px;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.ag-sc{font-weight:800; font-size:1.4rem; color:#3F7A56; line-height:1}
.ag-bars{display:flex; gap:6px; margin-top:12px}
.ag-bt{height:6px; flex:1; background:#F1EEE6; border-radius:99px; overflow:hidden; display:block}
.ag-bf{display:block; height:100%; border-radius:99px;
  background:linear-gradient(90deg,#CC785C,#E2A487);
  transform:scaleX(0); transform-origin:left; animation:ag-grow 9s ease-out infinite}
.ag-c1 .ag-bf{animation-delay:0s}.ag-c2 .ag-bf{animation-delay:3s}.ag-c3 .ag-bf{animation-delay:6s}
.w100{width:100%}.w95{width:95%}.w90{width:90%}.w85{width:85%}.w75{width:75%}

.ag-pipe{position:relative; display:grid; grid-template-columns:repeat(4,1fr);
  gap:0; max-width:780px; margin:28px auto 2px}
.ag-rail{position:absolute; top:27px; left:12.5%; right:12.5%; height:2px;
  background:repeating-linear-gradient(90deg,#CC785C 0 7px,transparent 7px 15px);
  opacity:.42; animation:ag-ants 1.1s linear infinite}
.ag-step{position:relative; text-align:center; padding:0 10px}
.ag-ic{position:relative; z-index:1; width:54px; height:54px; margin:0 auto 13px;
  background:#fff; border:1px solid #E7E2D6; border-radius:15px; display:flex;
  align-items:center; justify-content:center; color:#CC785C;
  box-shadow:0 8px 18px -12px rgba(60,48,30,.4); animation:ag-glow 8s ease-in-out infinite}
.ag-s1 .ag-ic{animation-delay:0s}.ag-s2 .ag-ic{animation-delay:2s}
.ag-s3 .ag-ic{animation-delay:4s}.ag-s4 .ag-ic{animation-delay:6s}
.ag-step h4{font-weight:700; font-size:1rem; color:#2A2723; margin:0 0 3px}
.ag-num{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.72rem;
  color:#B0603C; font-weight:700; margin-right:6px}
.ag-step p{font-size:.82rem; color:#6E685E; margin:0 auto; max-width:20ch; line-height:1.42}

@container (min-width:760px){
  .ag-band{flex-direction:row; align-items:center; justify-content:center;
    text-align:left; gap:30px; max-width:880px; margin:0 auto}
  .ag-intro{flex:1 1 auto; max-width:520px}
  .ag-live{margin:0; width:230px; flex:0 0 230px}
}
@keyframes ag-ants{to{background-position:15px 0}}
@keyframes ag-glow{0%,10%,100%{box-shadow:0 8px 18px -12px rgba(60,48,30,.4); border-color:#E7E2D6}
  15%,22%{box-shadow:0 0 0 4px #F6E7DF,0 8px 18px -10px rgba(204,120,92,.5); border-color:#CC785C}}
@keyframes ag-march{0%{transform:translateX(-150%)}100%{transform:translateX(380%)}}
@keyframes ag-fade{0%{opacity:0}5%{opacity:1}30%{opacity:1}36%{opacity:0}100%{opacity:0}}
@keyframes ag-swap{0%{opacity:0; transform:translateY(7px)}5%{opacity:1; transform:none}
  30%{opacity:1; transform:none}36%{opacity:0; transform:translateY(-5px)}100%{opacity:0}}
@keyframes ag-grow{0%,5%{transform:scaleX(0)}18%{transform:scaleX(1)}
  33%{transform:scaleX(1)}38%{transform:scaleX(0)}100%{transform:scaleX(0)}}
@media (prefers-reduced-motion:reduce){
  .ag-rail,.ag-ic,.ag-prog>span,.ag-card,.ag-count span,.ag-bf{animation:none!important}
  .ag-card{opacity:1}.ag-c2,.ag-c3{display:none}
  .ag-count span{opacity:0}.ag-n1{opacity:1}
  .ag-bf{transform:scaleX(1)}
}
</style>
<div class="ag-hero">
  <div class="ag-band">
  <div class="ag-intro">
    <div class="ag-eyebrow">AI grading for CS courses</div>
    <div class="ag-h1">From a folder of notebooks to a graded gradebook.</div>
    <div class="ag-sub">Watch it work, then take over &mdash; you approve every grade
      before anything reaches a student.</div>
  </div>

  <div class="ag-live" aria-hidden="true">
    <div class="ag-lh">
      <span class="ag-actv"><svg width="15" height="15" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2.2" stroke-linecap="round"
        stroke-linejoin="round"><path d="M3 12h4l2 6 4-15 2 9h6"/></svg></span>
      Grading batch
      <span class="ag-count"><span class="ag-n1">18 / 30</span><span class="ag-n2">19 / 30</span><span class="ag-n3">20 / 30</span></span>
    </div>
    <div class="ag-prog"><span></span></div>
    <div class="ag-stack">
      <div class="ag-card ag-c1">
        <div class="ag-crow"><div><div class="ag-nm">Alex Rivera</div>
          <div class="ag-fl">decision_tree.ipynb</div></div><div class="ag-sc">94</div></div>
        <div class="ag-bars"><span class="ag-bt"><span class="ag-bf w100"></span></span><span class="ag-bt"><span class="ag-bf w90"></span></span><span class="ag-bt"><span class="ag-bf w100"></span></span></div>
      </div>
      <div class="ag-card ag-c2">
        <div class="ag-crow"><div><div class="ag-nm">Mei Tanaka</div>
          <div class="ag-fl">lab2_dtree.html</div></div><div class="ag-sc">88</div></div>
        <div class="ag-bars"><span class="ag-bt"><span class="ag-bf w90"></span></span><span class="ag-bt"><span class="ag-bf w75"></span></span><span class="ag-bt"><span class="ag-bf w100"></span></span></div>
      </div>
      <div class="ag-card ag-c3">
        <div class="ag-crow"><div><div class="ag-nm">Sam Okafor</div>
          <div class="ag-fl">dt_lab.ipynb</div></div><div class="ag-sc">91</div></div>
        <div class="ag-bars"><span class="ag-bt"><span class="ag-bf w100"></span></span><span class="ag-bt"><span class="ag-bf w85"></span></span><span class="ag-bt"><span class="ag-bf w95"></span></span></div>
      </div>
    </div>
  </div>
  </div>

  <div class="ag-pipe">
    <div class="ag-rail"></div>
    <div class="ag-step ag-s1">
      <div class="ag-ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/>
        <path d="M12 3v12"/></svg></div>
      <h4><span class="ag-num">01</span>Upload</h4>
      <p>A Canvas .zip or a stack of notebooks</p>
    </div>
    <div class="ag-step ag-s2">
      <div class="ag-ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3v3M12 18v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M3 12h3M18 12h3"/>
        <circle cx="12" cy="12" r="3.4"/></svg></div>
      <h4><span class="ag-num">02</span>AI grades</h4>
      <p>Each one scored against your rubric</p>
    </div>
    <div class="ag-step ag-s3">
      <div class="ag-ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 11l3 3 8-8"/><path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9"/></svg></div>
      <h4><span class="ag-num">03</span>You review</h4>
      <p>Adjust and approve &mdash; nothing is final until you do</p>
    </div>
    <div class="ag-step ag-s4">
      <div class="ag-ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3v12"/><path d="M8 7l4-4 4 4"/>
        <path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></svg></div>
      <h4><span class="ag-num">04</span>Push to Canvas</h4>
      <p>Scores and feedback, on the right scale</p>
    </div>
  </div>
</div>
"""

render_locked_sidebar()
st.markdown(_HERO, unsafe_allow_html=True)

status = api_client.health()
if status is None:
    st.error(
        f"The backend at `{api_client.API_BASE}` is not responding.\n\n"
        "Start it in another terminal:\n\n"
        "```\nuvicorn backend.main:app --reload\n```"
    )
    st.stop()

# ---------------------------------------------------------------------
# Sign in / create account - the real, working form, right under the hero
# ---------------------------------------------------------------------
st.divider()
st.subheader("Get started")

sign_in, sign_up = st.tabs(["Sign in", "Create an account"])

with sign_in:
    with st.form("sign_in"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            if api_client.login(email, password):
                st.rerun()

with sign_up:
    with st.form("sign_up"):
        new_name = st.text_input("Full name")
        new_email = st.text_input("Email", key="new_email")
        new_password = st.text_input(
            "Password", type="password", key="new_password",
            help="8-72 characters.",
        )
        role = st.selectbox(
            "Role", ["professor", "ta"],
            help="TAs can grade and leave notes. Only professors can approve "
                 "a grade or delete a course.",
        )
        if st.form_submit_button("Create account", type="primary"):
            if not new_name.strip():
                st.error("Please enter your name.")
            elif len(new_password) < 8:
                st.error("Password must be at least 8 characters.")
            elif api_client.register(new_email, new_name, new_password, role):
                st.rerun()

# ---------------------------------------------------------------------
# How it works - in-depth, so a newcomer understands it before signing up
# ---------------------------------------------------------------------
st.divider()
st.subheader("How AutoGrade works")
st.markdown(
    "AutoGrade reads what your students actually submitted &mdash; their code, "
    "the output it produced, and the figures it drew &mdash; and grades it "
    "against **your** rubric. It is an assistant, not an autopilot: it proposes "
    "grades and writes the feedback, and **you approve every one** before it "
    "counts. Here is the full picture."
)

steps = st.columns(4)
_STEPS = [
    ("1 · Upload",
     "Drop a folder of `.ipynb`, `.html` or `.py` files, or a single `.zip` "
     "straight from Canvas's *Download Submissions*. Names and student IDs "
     "are read from the files; you can correct any of them."),
    ("2 · AI grades",
     "Each submission goes to the model once, with your rubric. It scores "
     "every criterion, writes per-criterion feedback, and explains its "
     "reasoning. An optional instructor solution makes correctness checks "
     "markedly sharper."),
    ("3 · You review",
     "Read the feedback, override any score you disagree with, and approve. "
     "The AI's original numbers are kept next to your changes, so the record "
     "always shows both."),
    ("4 · Push to Canvas",
     "Export CSV, Excel, or a PDF feedback packet &mdash; or push scores and "
     "comments straight into the Canvas gradebook. Percentages are rescaled to "
     "whatever the assignment is worth there."),
]
for column, (title, body) in zip(steps, _STEPS):
    with column:
        st.markdown(f"**{title}**")
        st.caption(body)

st.markdown("")  # a little breathing room

with st.expander("Why you can trust the number"):
    st.markdown(
        """
        The model is good at judgement, and deliberately kept away from the
        arithmetic that decides a grade:

        - **AutoGrade recomputes every total itself** from the per-criterion
          scores. The model's own sum is never used.
        - **Scores are clamped** to each criterion's maximum, so a stray
          "12 / 10" can't happen.
        - **Missing criteria are filled in**, not silently dropped, so a
          rubric always adds up to the weight you set.
        - **Letter grades and percentages** come from one place in the code,
          identical for every student.

        The result: the AI writes the feedback and proposes the scores, but the
        grade you see is computed by plain, auditable Python.
        """
    )

with st.expander("What the grader actually reads"):
    st.markdown(
        """
        Submissions are parsed into structured pieces before the model sees
        them:

        - **Code** cells and their **execution output** &mdash; including
          errors and whether a cell was ever run.
        - **Prose** (markdown / written answers) for discussion questions.
        - **Figures** &mdash; both raster plots (PNG) and vector ones (SVG) are
          detected, and can optionally be sent to the model so it can judge a
          plot, not just the code that claims to draw it.

        You choose per batch whether to send figures (they cost a little more
        per submission).
        """
    )

with st.expander("Beyond grading: similarity, export, and Canvas"):
    st.markdown(
        """
        - **Similarity check** &mdash; every pair of submissions is compared on
          normalised tokens *and* AST structure, so renaming variables doesn't
          hide a copy. A flag is a prompt to look, never a verdict.
        - **Export** &mdash; CSV, Canvas-ready CSV, Excel, or a per-student PDF
          feedback packet, in one click.
        - **Canvas** &mdash; connect with an API token to pull your roster,
          match students, and push approved grades and comments back. Nothing
          is written to a student record until you finalize it.
        """
    )

with st.expander("Bring your own model"):
    st.markdown(
        """
        The grader is provider-agnostic. Set `LLM_PROVIDER` in the backend's
        `.env`:

        - **OpenAI** (default) &mdash; set `OPENAI_API_KEY`.
        - **Claude** (Anthropic) &mdash; set `ANTHROPIC_API_KEY`.
        - **Local** &mdash; point `LOCAL_BASE_URL` at any OpenAI-compatible
          server (e.g. a local Qwen model) to keep every submission on your own
          hardware.

        Grading behaves the same way whichever you choose.
        """
    )
