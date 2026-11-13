"""FairShortlist demo (Streamlit).

    pip install -e ".[app]" && streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fairshortlist.service import screen, workbook  # noqa: E402
from fairshortlist.synth import JD_TEXT, TODAY, generate, render_pdf, text  # noqa: E402

st.set_page_config(page_title="FairShortlist", page_icon="🔎", layout="wide")
st.title("FairShortlist")
st.caption(
    "Blind, explainable resume screening. Names, contact details, age and gender are "
    "removed before scoring. Every decision shows its evidence; a recruiter decides."
)


@st.cache_data
def samples() -> list[tuple[str, bytes]]:
    return [(c.file, render_pdf(text(c))) for c in generate(18, seed=11)]


jd_text = st.text_area("Job description", JD_TEXT, height=230)
uploads = st.file_uploader("Resumes (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"],
                           accept_multiple_files=True)  # fmt: skip
files = [(u.name, u.getvalue()) for u in uploads] if uploads else samples()
if not uploads:
    st.info(f"Using {len(files)} sample resumes. Upload your own to screen them.")

if st.button("Screen candidates", type="primary"):
    jd, results = screen(jd_text, files, today=TODAY if not uploads else None)
    st.write(f"**Must-have:** {', '.join(sorted(jd.must_have)) or 'none found'} · "
             f"**Nice to have:** {', '.join(sorted(jd.nice_to_have)) or 'none'} · "
             f"**Minimum:** {jd.min_years:g} years")  # fmt: skip
    c1, c2, c3 = st.columns(3)
    for col, d, label in ((c1, "shortlist", "Shortlist"), (c2, "review", "Review"),
                          (c3, "not_a_fit", "Not a fit")):  # fmt: skip
        col.metric(label, sum(r.decision == d for r in results))
    for i, a in enumerate(results, 1):
        icon = {"shortlist": "🟢", "review": "🟡", "not_a_fit": "🔴"}[a.decision]
        with st.expander(f"{icon} #{i}  {a.source}  ·  {a.score:.0f}/100  ·  {a.decision}"):
            left, right = st.columns(2)
            left.write("**Strengths**")
            left.write("\n".join(f"- {s}" for s in a.strengths) or "-")
            right.write("**Gaps**")
            right.write("\n".join(f"- {g}" for g in a.gaps) or "-")
            st.write("**Interview questions**")
            st.write("\n".join(f"{n}. {q}" for n, q in enumerate(a.interview_questions, 1)))
            st.caption(f"Score breakdown: {a.breakdown}")
    st.download_button("Download shortlist (Excel)", workbook(jd, results), "shortlist.xlsx")
