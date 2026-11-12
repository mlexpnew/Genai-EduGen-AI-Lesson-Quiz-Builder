"""Resume and job description parsing.

Resumes are redacted before anything is scored: name, contact details, links, date of
birth, gender and marital markers are removed, so the scorer never sees them. Skills
are split into "demonstrated" (used in a dated role or project) and "listed" (only in a
skills section), because a keyword list is not evidence of experience.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date

from . import taxonomy

_MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTHS = {m: i for i, m in enumerate(_MONTH_NAMES, 1)}
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_POINT = rf"(?:{_MON}\s*'?\d{{2,4}}|\d{{1,2}}[/.-]\d{{4}}|\d{{4}})"
_END = rf"(?:{_POINT}|present|current|now|till date|to date|ongoing)"
DATE_RANGE = re.compile(rf"({_POINT})\s*(?:-|–|—|to|until)\s*({_END})", re.I)

SECTION_WORDS = {
    "skills": ("skills", "technical skills", "core competencies", "tech stack", "tools",
               "technical toolkit", "toolkit", "technologies", "stack"),
    "experience": ("experience", "work experience", "employment", "professional experience",
                   "work history", "internships", "career history", "career",
                   "employment history", "relevant experience"),
    "projects": ("projects", "key projects", "academic projects", "personal projects",
                 "selected work", "side projects", "portfolio"),
    "education": ("education", "academics", "qualifications", "academic background"),
    "summary": ("summary", "profile", "objective", "about me"),
    "other": ("certifications", "achievements", "awards", "languages", "interests", "hobbies",
              "publications", "personal details", "declaration"),
}  # fmt: skip

PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
    (re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){10}\b"), "[phone]"),
    (re.compile(r"(?:https?://|www\.)\S+|(?:linkedin|github)\.com/\S+", re.I), "[link]"),
    (re.compile(r"\b(?:date of birth|dob|d\.o\.b)\b.*", re.I), "[dob]"),
    (re.compile(r"\b(?:age)\s*[:\-]?\s*\d{2}\b", re.I), "[age]"),
    (re.compile(r"\b(?:gender|sex|marital status|nationality|religion)\b.*", re.I), "[personal]"),
    (re.compile(r"\b(?:he|she|him|her|his|hers|mr|mrs|ms|miss)\b\.?", re.I), "[x]"),
]


@dataclass
class Resume:
    source: str
    text_redacted: str
    skills_demonstrated: dict[str, list[str]] = field(default_factory=dict)
    skills_listed: set[str] = field(default_factory=set)
    years_experience: float = 0.0
    roles: list[tuple[date, date]] = field(default_factory=list)
    education: list[str] = field(default_factory=list)

    @property
    def all_skills(self) -> set[str]:
        return set(self.skills_demonstrated) | self.skills_listed


@dataclass
class JobDescription:
    title: str
    must_have: set[str]
    nice_to_have: set[str]
    min_years: float


def read_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    if name.endswith(".docx"):
        import docx

        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    return data.decode("utf-8", errors="replace")


def redact(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and len(lines[0].split()) <= 5 and not taxonomy.find(lines[0]):
        lines[0] = "[name]"  # first line of a resume is almost always the candidate's name
    out = "\n".join(lines)
    for pat, repl in PII:
        out = pat.sub(repl, out)
    return out


def _section_of(line: str) -> str | None:
    s = re.sub(r"[^a-z ]", "", line.lower()).strip()
    if len(s.split()) > 4:
        return None
    for sec, words in SECTION_WORDS.items():
        if s in words:
            return sec
    return None


def _point(s: str, end: bool, today: date) -> date | None:
    s = s.strip().lower().replace("'", " ")
    if s in ("present", "current", "now", "till date", "to date", "ongoing"):
        return today
    m = re.match(rf"({_MON})\s*(\d{{2,4}})", s)
    if m:
        year = int(m.group(2))
        year += 2000 if year < 100 else 0
        return date(year, MONTHS[m.group(1)[:3]], 1)
    m = re.match(r"(\d{1,2})[/.-](\d{4})", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return date(int(m.group(2)), int(m.group(1)), 1)
    if re.fullmatch(r"\d{4}", s):
        return date(int(s), 12 if end else 1, 1)
    return None


def experience_years(lines: list[str], today: date) -> tuple[float, list[tuple[date, date]]]:
    """Merge overlapping role dates, so two parallel jobs are not double counted."""
    spans = []
    for line in lines:
        for a, b in DATE_RANGE.findall(line):
            start, end = _point(a, False, today), _point(b, True, today)
            if start and end and start <= end <= today and start.year >= 1980:
                spans.append((start, end))
    merged: list[list[date]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    months = sum((e.year - s.year) * 12 + e.month - s.month + 1 for s, e in merged)
    return round(months / 12, 1), [(s, e) for s, e in merged]


def parse_resume(text: str, source: str = "", today: date | None = None) -> Resume:
    today = today or date.today()
    red = redact(text)
    lines = red.splitlines()
    section = "summary"
    by_section: dict[str, list[str]] = {}
    for line in lines:
        sec = _section_of(line)
        if sec:
            section = sec
            continue
        # Header-free fallback: a line with a date range opens a role block, whatever the
        # section is called (or if there is no heading at all)
        if section in ("summary", "skills", "other") and DATE_RANGE.search(line):
            section = "experience"
        by_section.setdefault(section, []).append(line)
    work = by_section.get("experience", []) + by_section.get("projects", [])
    demonstrated = taxonomy.find_in_lines(work)
    listed = taxonomy.find(" ".join(by_section.get("skills", []) + by_section.get("summary", [])))
    years, roles = experience_years(by_section.get("experience", []), today)
    degree = re.compile(
        r"\b(b\.?tech|b\.?e|bca|mca|m\.?tech|b\.?sc|m\.?sc|mba|phd|bachelor|master)", re.I
    )
    edu = [ln.strip() for ln in by_section.get("education", []) if degree.search(ln)]
    return Resume(source=source, text_redacted=red, skills_demonstrated=demonstrated,
                  skills_listed=listed - set(demonstrated), years_experience=years,
                  roles=roles, education=edu)  # fmt: skip


MUST_HDR = re.compile(r"(must[- ]have|requirements|required|what you.?ll need|qualifications|"
                      r"you have|minimum)", re.I)  # fmt: skip
NICE_HDR = re.compile(r"(nice[- ]to[- ]have|preferred|bonus|good to have|plus|desirable)", re.I)
YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:-\s*\d+\s*)?(?:years|yrs)", re.I)


def parse_jd(text: str) -> JobDescription:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    title = lines[0].strip() if lines else "Role"
    mode, must, nice = "must", set(), set()
    for line in lines[1:]:
        is_header = len(line.split()) <= 6 and line.rstrip().endswith(":") or len(line.split()) <= 4
        if is_header and NICE_HDR.search(line):
            mode = "nice"
            continue
        if is_header and MUST_HDR.search(line):
            mode = "must"
            continue
        (must if mode == "must" else nice).update(taxonomy.find(line))
    years = [float(m) for m in YEARS.findall(text)]
    return JobDescription(title=title, must_have=must, nice_to_have=nice - must,
                          min_years=min(years) if years else 0.0)  # fmt: skip
