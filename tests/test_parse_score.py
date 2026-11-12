from datetime import date

import pytest

from hirelens import taxonomy
from hirelens.parse import experience_years, parse_jd, parse_resume, redact
from hirelens.score import assess, rank
from hirelens.synth import JD_TEXT

TODAY = date(2026, 11, 12)

RESUME = """Priya Sharma
priya.sharma@example.com | +91 9876543210 | linkedin.com/in/priyas
Summary
She builds LLM products.
Skills
Python, Docker, Kubernetes, LangGraph
Experience
AI Engineer, Finlytics  Jan 2024 - Present
- Designed a RAG pipeline over policy documents using LLMs
- Built REST services with FastAPI; containerized with Docker
Data Engineer, Paysure  03/2021 - 12/2023
- Wrote Python ETL jobs and SQL models
Education
B.Tech Computer Science, 2020
Date of Birth: 01/02/1998
Gender: Female
"""


def test_taxonomy_aliases_and_boundaries():
    assert taxonomy.find("k8s and containerized apps") == {"kubernetes", "docker"}
    assert taxonomy.find("Java services") == {"java"} and "java" not in taxonomy.find("JavaScript")
    assert taxonomy.find("FastAPI") >= {"fastapi", "rest api", "python"}  # implications


def test_redaction_removes_identity():
    r = redact(RESUME)
    for leaked in ("Priya", "Sharma", "@", "9876543210", "linkedin", "Female", "1998", "She "):
        assert leaked not in r


def test_experience_merges_and_counts_months():
    years, roles = experience_years(["Jan 2024 - Present", "03/2021 - 12/2023"], TODAY)
    assert years == round((35 + 34) / 12, 1) and len(roles) == 2
    overlap, _ = experience_years(["Jan 2022 - Dec 2022", "Jun 2022 - Dec 2022"], TODAY)
    assert overlap == 1.0  # parallel jobs are not double counted


def test_demonstrated_vs_listed():
    r = parse_resume(RESUME, "p.pdf", TODAY)
    assert {"rag", "llm", "fastapi", "docker", "python"} <= set(r.skills_demonstrated)
    assert {"kubernetes", "langgraph"} <= r.skills_listed  # only in the skills list


def test_jd_sections_and_years():
    jd = parse_jd(JD_TEXT)
    assert {"python", "llm", "rag", "fastapi", "docker"} <= jd.must_have
    assert {"langgraph", "aws", "kubernetes", "vector database"} <= jd.nice_to_have
    assert jd.min_years == 2.0


def test_assessment_explains_itself():
    a = assess(parse_resume(RESUME, "p.pdf", TODAY), parse_jd(JD_TEXT))
    assert a.decision == "shortlist" and a.meets_requirements
    assert any("RAG pipeline" in s for s in a.strengths)
    assert a.interview_questions and sum(a.breakdown.values()) == pytest.approx(a.score, abs=0.2)


def test_missing_must_have_cannot_be_shortlisted():
    no_docker = RESUME.replace("; containerized with Docker", "").replace("Docker, ", "")
    a = assess(parse_resume(no_docker, "p.pdf", TODAY), parse_jd(JD_TEXT))
    assert a.decision != "shortlist" and any("docker" in g for g in a.gaps)


def test_ranking_puts_requirement_meeting_candidates_first():
    junior = RESUME.replace("03/2021 - 12/2023", "").replace("Jan 2024", "Jun 2026")
    ranked = rank([parse_resume(junior, "junior", TODAY), parse_resume(RESUME, "senior", TODAY)],
                  parse_jd(JD_TEXT))  # fmt: skip
    assert [a.source for a in ranked] == ["senior", "junior"]
    assert ranked[1].decision == "review"
