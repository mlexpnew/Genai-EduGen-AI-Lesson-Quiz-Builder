"""Transparent scoring rubric. Every point traces to a line in the resume.

    must-have skills demonstrated   50 pts  (listed only: 40% credit)
    nice-to-have skills             15 pts
    years of experience vs minimum  25 pts
    evidence depth                  10 pts  (share of matched skills backed by work evidence)

Decisions are recommendations for a recruiter, never automatic rejections: a human
reviews every candidate, and each decision comes with the reasons behind it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .parse import JobDescription, Resume

LISTED_CREDIT = 0.4
SHORTLIST_AT, REVIEW_AT = 70.0, 50.0


@dataclass
class Assessment:
    source: str
    score: float
    decision: str  # shortlist | review | not_a_fit
    breakdown: dict[str, float]
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)
    interview_questions: list[str] = field(default_factory=list)
    years_experience: float = 0.0
    meets_requirements: bool = False


QUESTIONS = {
    "default": "Tell us about a time you used {skill} in production. What broke, and how "
               "did you fix it?",
    "missing": "This role needs {skill}. How would you get productive with it in your first "
               "month, and what similar tools have you used?",
    "listed": "You list {skill} but no project shows it yet. Walk us through something you "
              "built with it.",
}  # fmt: skip


def assess(r: Resume, jd: JobDescription) -> Assessment:
    must = jd.must_have or set()
    demo = set(r.skills_demonstrated)
    listed = r.skills_listed

    must_points = sum(1.0 if s in demo else LISTED_CREDIT if s in listed else 0.0 for s in must)
    must_score = 50.0 * must_points / len(must) if must else 50.0
    nice = jd.nice_to_have
    nice_score = 15.0 * len(nice & (demo | listed)) / len(nice) if nice else 15.0
    exp_score = 25.0 if jd.min_years <= 0 else 25.0 * min(1.0, r.years_experience / jd.min_years)
    matched = (must | nice) & (demo | listed)
    depth = 10.0 * len(matched & demo) / len(matched) if matched else 0.0
    total = round(must_score + nice_score + exp_score + depth, 1)

    missing = sorted(must - demo - listed)
    only_listed = sorted((must & listed) - demo)
    gaps = [f"No evidence of {s}" for s in missing]
    gaps += [f"{s} listed in skills, not shown in any role or project" for s in only_listed]
    if jd.min_years and r.years_experience < jd.min_years:
        gaps.append(f"{r.years_experience:g} years of experience vs {jd.min_years:g} required")
    strengths = [f"{s} used in work: \"{r.skills_demonstrated[s][0][:90]}\""
                 for s in sorted(must & demo)][:5]  # fmt: skip
    if jd.min_years and r.years_experience >= jd.min_years:
        strengths.append(f"{r.years_experience:g} years of experience (needs {jd.min_years:g})")

    # Points rank candidates; hard requirements gate the decision, like a recruiter's
    # knockout questions: no shortlist without every must-have and the minimum years.
    meets = not missing and (not jd.min_years or r.years_experience >= jd.min_years)
    hard_gap = must and len(missing) > len(must) / 2
    if hard_gap or total < REVIEW_AT:
        decision = "not_a_fit"
    elif meets and total >= SHORTLIST_AT:
        decision = "shortlist"
    else:
        decision = "review"

    questions = [QUESTIONS["missing"].format(skill=s) for s in missing[:2]]
    questions += [QUESTIONS["listed"].format(skill=s) for s in only_listed[:2]]
    questions += [QUESTIONS["default"].format(skill=s) for s in sorted(must & demo)[:1]]
    return Assessment(
        source=r.source,
        score=total,
        decision=decision,
        breakdown={"must_have": round(must_score, 1), "nice_to_have": round(nice_score, 1),
                   "experience": round(exp_score, 1), "evidence_depth": round(depth, 1)},
        strengths=strengths,
        gaps=gaps,
        evidence={s: r.skills_demonstrated[s][0] for s in sorted(matched & demo)},
        interview_questions=questions[:4],
        years_experience=r.years_experience,
        meets_requirements=meets,
    )  # fmt: skip


def rank(resumes: list[Resume], jd: JobDescription) -> list[Assessment]:
    """Candidates meeting every requirement first, then by score."""
    return sorted(
        (assess(r, jd) for r in resumes),
        key=lambda a: (not a.meets_requirements, -a.score, a.source),
    )
