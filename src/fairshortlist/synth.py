"""Synthetic benchmark: resume PDFs with known answers.

Real resumes cannot be published. The generator writes candidates of six kinds that
recruiters meet every day, with a ground-truth label from a stated rule: a candidate is
qualified when every must-have skill is used in a dated role or project AND experience
meets the minimum. The benchmark tests whether a screener recovers that from messy
documents. It does not claim the rule is the right hiring policy.

    strong          all must-haves used at work, enough years          qualified
    alias_writer    same, written with aliases (k8s, containerized)     qualified
    keyword_stuffer lists every skill, work shows none of them          not qualified
    junior          right skills in projects, too few years             not qualified
    near_miss       one must-have missing                               not qualified
    adjacent        related role (analyst), core AI skills missing      not qualified
"""

from __future__ import annotations

import io
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

TODAY = date(2026, 11, 12)

JD_TEXT = """AI Engineer (LLM Applications)
We are hiring an engineer to build production LLM features for our fintech platform.
Requirements:
- 2+ years building software in Python
- Hands-on with LLMs and RAG pipelines in production
- Build and ship REST services with FastAPI
- Package services with Docker
Nice to have:
- LangGraph or other agent frameworks
- AWS deployment experience
- Vector databases such as FAISS or Pinecone
- Kubernetes
"""

FIRST = ["Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Sneha", "Arjun", "Kavya", "Rahul",
         "Divya", "Karthik", "Meera", "Imran", "Fatima", "Joseph", "Sara", "Harpreet", "Neha"]
LAST = ["Sharma", "Iyer", "Reddy", "Khan", "Das", "Nair", "Singh", "Patel", "Menon", "Gupta",
        "Fernandes", "Bose", "Kulkarni", "Hussain"]  # fmt: skip
COMPANIES = ["Finlytics", "Quantro Labs", "Paysure", "DataNest", "Cloudmint", "Zeno Health",
             "Brightpath Retail", "Orbit Logistics"]  # fmt: skip

WORK = {  # skill -> a bullet that shows it being used, plus an alias variant
    "python": ("Wrote Python services processing 2M events a day",
               "Built backend jobs in python3 with typed data models"),
    "llm": ("Integrated LLMs (Gemini, GPT) for document question answering",
            "Shipped large language models features for support automation"),
    "rag": ("Designed a RAG pipeline with reranking and citation checks",
            "Built a retrieval-augmented generation service over policy documents"),
    "fastapi": ("Built REST services with FastAPI and Pydantic validation",
                "Exposed model endpoints via FastAPI with async workers"),
    "docker": ("Packaged every service with Docker for staging and production",
               "Containerized APIs and set up multi-stage images"),
    "langgraph": ("Orchestrated multi-step agents with LangGraph",
                  "Built a LangGraph planner and checker agent loop"),
    "aws": ("Deployed APIs on AWS (EC2, S3, Lambda)",
            "Ran inference on Amazon Web Services with autoscaling"),
    "vector database": ("Indexed 500k chunks in FAISS with metadata filters",
                        "Managed a Pinecone index for semantic search"),
    "kubernetes": ("Ran workloads on Kubernetes with HPA",
                   "Operated k8s deployments for model serving"),
    "sql": ("Wrote SQL for weekly revenue reporting", "Optimised SQL queries on PostgreSQL"),
    "excel": ("Maintained Excel models with pivot tables", "Automated advanced Excel reports"),
    "power bi": ("Built Power BI dashboards for sales leadership",
                 "Published PowerBI reports for finance"),
    "pandas": ("Cleaned datasets with pandas", "Wrangled data in pandas and numpy"),
}  # fmt: skip
MUST = ["python", "llm", "rag", "fastapi", "docker"]
NICE = ["langgraph", "aws", "vector database", "kubernetes"]
MIN_YEARS = 2.0
KINDS = ["strong", "alias_writer", "keyword_stuffer", "junior", "near_miss", "adjacent"]


@dataclass
class Candidate:
    file: str
    kind: str
    template: str
    name: str
    gender: str
    qualified: bool
    years: float
    demonstrated: list[str]
    listed: list[str]
    roles: list[dict] = field(default_factory=list)  # company, start, end, bullets


def _roles(rng, years: float, skills: list[str], alias: bool, analyst: bool = False) -> list[dict]:
    months = round(years * 12)
    n = 1 if months <= 18 else 2
    split = [months] if n == 1 else [months - months // 2, months // 2]
    end_y, end_m = TODAY.year, TODAY.month
    roles = []
    for i, length in enumerate(split):  # most recent first
        start_total = end_y * 12 + end_m - 1 - (length - 1)
        sy, sm = divmod(start_total, 12)
        title = "Data Analyst" if analyst else ("AI Engineer" if i == 0 else "Software Engineer")
        mine = skills[i::n] or skills[:1]
        bullets = [WORK[s][1 if alias else 0] for s in mine]
        end = None if i == 0 else date(end_y, end_m, 1)
        roles.append({"company": rng.choice(COMPANIES), "title": title,
                      "start": date(sy, sm + 1, 1), "end": end, "bullets": bullets})  # fmt: skip
        gap = rng.randint(1, 3)  # small break between jobs
        prev = start_total - gap
        end_y, end_m = divmod(prev, 12)
        end_m += 1
    return roles


def make(idx: int, kind: str, template: str, rng: random.Random) -> Candidate:
    gender = rng.choice(["female", "male"])
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    nice = rng.sample(NICE, rng.randint(0, 3))
    alias = kind == "alias_writer"
    projects: list[str] = []
    if kind in ("strong", "alias_writer"):
        years = round(rng.uniform(2.5, 7), 1)
        demo, listed = MUST + nice, MUST + nice
    elif kind == "keyword_stuffer":
        years = round(rng.uniform(3, 6), 1)
        demo, listed = ["excel", "power bi", "sql"], MUST + NICE + ["excel", "power bi"]
    elif kind == "junior":
        years = round(rng.uniform(0.4, 1.4), 1)
        demo, listed = MUST + nice, MUST
    elif kind == "near_miss":
        years = round(rng.uniform(2.5, 6), 1)
        # never drop python alone: FastAPI work already proves Python
        dropped = rng.choice([m for m in MUST if m != "python"])
        demo = [s for s in MUST if s != dropped] + nice
        listed = demo
    else:  # adjacent
        years = round(rng.uniform(3, 7), 1)
        demo, listed = ["python", "sql", "pandas", "power bi"], ["python", "sql", "pandas"]
    if kind == "junior":  # skills shown in projects, a short internship as the only role
        roles = _roles(rng, years, ["python"], alias)
        projects = [WORK[s][0] for s in demo]
    else:
        roles = _roles(rng, years, demo, alias, analyst=kind in ("adjacent", "keyword_stuffer"))
    c = Candidate(
        file=f"cand_{idx:03d}.pdf", kind=kind, template=template, name=name, gender=gender,
        qualified=kind in ("strong", "alias_writer"), years=years,
        demonstrated=sorted(set(demo)), listed=sorted(set(listed)), roles=roles,
    )  # fmt: skip
    c.roles[0]["projects"] = projects
    return c


def _fmt_date(d: date | None, style: str) -> str:
    if d is None:
        return {"classic": "Present", "modern": "Present", "career": "Till Date",
                "timeline": "now"}[style]  # fmt: skip
    return {"classic": f"{d:%b %Y}", "modern": f"{d:%m/%Y}", "career": f"{d:%B %Y}",
            "timeline": f"{d:%b '%y}"}[style]  # fmt: skip


def text(c: Candidate) -> str:
    if c.template == "timeline":
        return _timeline(c)
    t = c.template
    pron = "She" if c.gender == "female" else "He"
    h = {  # section headers per template; "career" is the held-out style
        "classic": ("SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION"),
        "modern": ("Profile", "Technical Skills", "Work Experience", "Personal Projects",
                   "Education"),
        "career": ("About Me", "Technical Toolkit", "Career History", "Selected Work",
                   "Academic Background"),
    }[t]  # fmt: skip
    first, last = c.name.split()
    lines = [
        c.name,
        f"{first.lower()}.{last.lower()}@example.com | +91 98{abs(hash(c.file)) % 10**8:08d} | "
        f"linkedin.com/in/{first.lower()}{last.lower()}",
        h[0],
        f"{pron} is an engineer who enjoys building reliable software.",
        h[1],
        ", ".join(_label(s) for s in c.listed),
        h[2],
    ]
    for r in c.roles:
        lines.append(f"{r['title']}, {r['company']}  {_fmt_date(r['start'], t)} - "
                     f"{_fmt_date(r['end'], t)}")  # fmt: skip
        lines += [f"- {b}" for b in r["bullets"]]
    projects = c.roles[0].get("projects") or []
    if projects:
        lines.append(h[3])
        lines += [f"- {p}" for p in projects]
    lines += [h[4], "B.Tech in Computer Science, 2019", "Personal details",
              f"Date of Birth: 0{abs(hash(c.name)) % 9 + 1}/05/1997",
              f"Gender: {c.gender.title()}  Marital Status: Single"]  # fmt: skip
    return "\n".join(lines)


def _timeline(c: Candidate) -> str:
    """Held-out layout: no section headings for roles, short dates, inline labels."""
    first, last = c.name.split()
    pron = "she/her" if c.gender == "female" else "he/him"
    lines = [f"{c.name} ({pron})", f"{first.lower()}{last[0].lower()}@example.org",
             "Stack: " + " / ".join(_label(s) for s in c.listed), ""]  # fmt: skip
    for r in c.roles:
        lines.append(f"{_fmt_date(r['start'], 'timeline')} – {_fmt_date(r['end'], 'timeline')} | "
                     f"{r['title']} @ {r['company']}")  # fmt: skip
        lines += [f"• {b}" for b in r["bullets"]]
    projects = c.roles[0].get("projects") or []
    if projects:
        lines.append("Side projects:")
        lines += [f"• {p}" for p in projects]
    lines += ["Edu: BCA, Bangalore University, 2020", f"Gender: {c.gender.title()}"]
    return "\n".join(lines)


def _label(skill: str) -> str:
    return {"llm": "LLMs", "rag": "RAG", "fastapi": "FastAPI", "aws": "AWS", "sql": "SQL",
            "power bi": "Power BI", "vector database": "Vector databases"}.get(
        skill, skill.title())  # fmt: skip


def render_pdf(body: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 805
    for i, line in enumerate(body.splitlines()):
        bold = i == 0 or (len(line.split()) <= 3 and not line.startswith("-"))
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 12 if i == 0 else 9.5)
        c.drawString(40, y, line[:110])
        y -= 16 if bold else 13
        if y < 50:
            c.showPage()
            y = 805
    c.save()
    return buf.getvalue()


# "career" was the first held-out layout; it exposed reliance on section headings (see
# README) and joined the dev set once fixed. "timeline" is the new held-out layout.
DEV_TEMPLATES = ["classic", "modern", "career"]
HELD_OUT_TEMPLATES = ["timeline"]


def generate(n: int = 120, seed: int = 3, templates: list[str] | None = None) -> list[Candidate]:
    rng = random.Random(seed)
    templates = templates or DEV_TEMPLATES
    return [make(i, KINDS[i % len(KINDS)], templates[(i // len(KINDS)) % len(templates)], rng)
            for i in range(1, n + 1)]  # fmt: skip


def write(out: Path, cands: list[Candidate]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for c in cands:
        (out / c.file).write_bytes(render_pdf(text(c)))
    (out / "job_description.txt").write_text(JD_TEXT)
    (out / "truth.jsonl").write_text("".join(json.dumps(asdict(c), default=str) + "\n"
                                             for c in cands))  # fmt: skip
