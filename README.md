# HireLens

![CI](https://github.com/mlexpnew/hirelens/actions/workflows/ci.yml/badge.svg?branch=main)

**Blind, explainable resume screening for recruiters and staffing firms.**
Paste a job description, drop in a folder of resumes (PDF, DOCX, TXT). Get a ranked shortlist where every decision shows its evidence, its gaps, and interview questions that probe those gaps. Names, contact details, age and gender are removed before anything is scored.

## Why not a keyword ATS or an "AI match score"?

Keyword filters reward candidates who paste every buzzword into a skills list. Text-similarity scores reward resumes that *sound* like the job description. Both miss what a recruiter actually checks: has this person **used** the required skills in real work, for long enough?

| Ranker (120 resumes, 40 qualified) | Qualified candidates in the top 40 (R-precision) | NDCG@10 |
|---|---|---|
| Keyword count (classic ATS filter) | 30% | 0.23 |
| TF-IDF similarity ("AI match score") | 42% | 0.73 |
| **HireLens** | **100%** | **1.00** |

| Candidate type | What they look like | Shortlisted by HireLens |
|---|---|---|
| Strong | every must-have used at work, enough years | 20 / 20 |
| Alias writer | same, written as "k8s", "containerized", "retrieval-augmented generation" | 20 / 20 |
| Keyword stuffer | lists every skill, work shows none | 0 / 20 |
| Junior | right skills in projects, too few years | 0 / 20 (sent to review) |
| Near miss | one must-have missing | 0 / 20 (sent to review) |
| Adjacent | analyst profile, core AI skills missing | 0 / 20 |

## Fair by construction, and tested

Hiring is high-risk AI under the EU AI Act: decisions must be explainable, and humans must stay in control. HireLens is built for that.

| Check | Result |
|---|---|
| Score change after swapping every candidate's name and gender, re-rendering and re-parsing the PDFs | **0.0** |
| Resumes with name or email left after redaction | **0** |
| Model that decides | None: a published rubric. No black box, no LLM choosing who gets hired |
| Final decision | Always a recruiter. Output is shortlist / review / not a fit, with reasons |

Redaction removes the name line, email, phone, links, date of birth, age, gender, marital status, nationality, religion and pronouns before parsing.

## How a candidate is scored

| Part | Points | Rule |
|---|---|---|
| Must-have skills | 50 | Full credit when used in a dated role or project; 40% when only listed |
| Nice-to-have skills | 15 | Any evidence |
| Experience | 25 | Years from merged role dates (parallel jobs are not double counted) vs the minimum |
| Evidence depth | 10 | Share of matched skills backed by actual work |

Points rank; requirements gate. Like a recruiter's knockout questions, nobody is shortlisted without every must-have and the minimum years; near-misses go to **review**, not the bin. Each result carries strengths quoted from the resume ("RAG used in work: *Designed a RAG pipeline with reranking…*"), gaps ("Docker listed in skills, not shown in any role"), and interview questions aimed at those gaps.

## Try it

```bash
pip install -e ".[app]" && streamlit run app.py         # sample resumes preloaded
```

```bash
pip install -e .
hirelens data/job_description.txt data/samples --out shortlist.xlsx
# 12 resumes: 4 shortlist, 6 review, 2 not a fit -> shortlist.xlsx
```

```bash
pip install -e ".[api]" && uvicorn hirelens.api:app     # or docker build -t hirelens . && docker run -p 8000:8000 hirelens
curl -F job_description="$(cat data/job_description.txt)" -F resumes=@data/samples/cand_001.pdf localhost:8000/v1/screen
```

## The benchmark, and how it kept me honest

Real resumes cannot be published, so `python -m hirelens.evaluate` generates resume PDFs of the six kinds above, in several layouts, with known answers. The label follows a stated rule (every must-have used at work, minimum years met). The benchmark tests whether HireLens recovers that from messy documents; it does not claim the rule is the right hiring policy for every role. CI runs it on every push and fails below 90% R-precision or on **any** fairness change.

One layout is always held out: written before HireLens ever ran on it.

| Round | Finding | Fix |
|---|---|---|
| 1 | R-precision 75%: juniors and near-misses shortlisted on points | Requirements gate the decision; candidates meeting all requirements rank first |
| 1 | "Name leaked" in 3 resumes | False alarm: surname "Das" matched inside "**Das**hboards"; check now uses word boundaries |
| 1 | Held-out "career" layout: skills recall 0% | Parsing depended on section headings ("Career History" unknown). Roles are now detected from date ranges, whatever the heading |
| 2 | 4 near-misses still shortlisted | Benchmark bug: they "lacked Python" while showing FastAPI work. FastAPI now implies Python and REST APIs; generator fixed |
| 2 | New held-out "timeline" layout (no headings, `Jun '22 – now` dates) | 100% R-precision, 100% skill recall, 0.0 years error on first run |

## Limitations

- Skill matching uses a curated taxonomy (52 skills, aliases, implications). Roles outside tech and data need taxonomy entries.
- Text-based PDFs and DOCX only; scanned resumes need OCR first.
- Years of experience come from dates on the resume; unexplained gaps are not judged.
- Synthetic benchmark: real resumes are messier. Validate on your own labelled sample before relying on scores.

## Project layout

```
src/hirelens/taxonomy.py   skills, aliases, implications, word-boundary matching
src/hirelens/parse.py      redaction, sections, date ranges, demonstrated vs listed skills, JD parsing
src/hirelens/score.py      rubric, gates, strengths, gaps, interview questions
src/hirelens/service.py    screening + Excel shortlist
src/hirelens/synth.py      synthetic resume generator (6 candidate kinds, 4 layouts)
src/hirelens/evaluate.py   rankers compared, fairness swap test, held-out layout, CI gate
src/hirelens/api.py        FastAPI service
app.py                     Streamlit demo
```
