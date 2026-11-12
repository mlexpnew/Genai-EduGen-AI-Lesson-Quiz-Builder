"""One screening path for the CLI, API and app."""

from __future__ import annotations

import io
from dataclasses import asdict
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .parse import JobDescription, parse_jd, parse_resume, read_text
from .score import Assessment, rank

FILL = {"shortlist": "E3F4E8", "review": "FFF4D6", "not_a_fit": "FBE3E1"}


def screen(jd_text: str, files: list[tuple[str, bytes]], today: date | None = None
           ) -> tuple[JobDescription, list[Assessment]]:  # fmt: skip
    jd = parse_jd(jd_text)
    resumes = [parse_resume(read_text(data, name), name, today) for name, data in files]
    return jd, rank(resumes, jd)


def as_dicts(results: list[Assessment]) -> list[dict]:
    return [asdict(a) for a in results]


def workbook(jd: JobDescription, results: list[Assessment]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Shortlist"
    ws.append([f"{jd.title}  |  must-have: {', '.join(sorted(jd.must_have))}  |  "
               f"min {jd.min_years:g} years"])  # fmt: skip
    ws["A1"].font = Font(bold=True)
    ws.append([])
    head = ["Rank", "Candidate file", "Decision", "Score", "Years", "Strengths", "Gaps",
            "Interview questions"]  # fmt: skip
    ws.append(head)
    for c in ws[3]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
    for i, a in enumerate(results, 1):
        ws.append([i, a.source, a.decision, a.score, a.years_experience,
                   "\n".join(a.strengths), "\n".join(a.gaps),
                   "\n".join(a.interview_questions)])  # fmt: skip
        ws.cell(ws.max_row, 3).fill = PatternFill("solid", fgColor=FILL[a.decision])
        for col in (6, 7, 8):
            ws.cell(ws.max_row, col).alignment = Alignment(wrap_text=True, vertical="top")
    for col, width in zip("ABCDEFGH", (6, 22, 11, 7, 7, 60, 50, 60), strict=True):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A4"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
