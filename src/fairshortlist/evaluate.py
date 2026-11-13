"""Benchmark FairShortlist against how screening is usually done.

    python -m fairshortlist.evaluate --gate

Compares three rankers on the same resumes:
- keyword count: how many JD skills appear anywhere (classic ATS filter)
- TF-IDF similarity between JD and resume text (classic "AI match score")
- FairShortlist rubric

and checks fairness directly: swap every candidate's name and gender markers, re-score,
and measure the largest change (should be exactly 0).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

from . import taxonomy
from .parse import parse_jd, parse_resume, read_text
from .score import rank
from .synth import (
    DEV_TEMPLATES,
    HELD_OUT_TEMPLATES,
    JD_TEXT,
    KINDS,
    MUST,
    TODAY,
    generate,
    render_pdf,
    text,
    write,
)


def ndcg(relevance: list[int], k: int) -> float:
    rel = np.array(relevance[:k], dtype=float)
    ideal = np.sort(np.array(relevance, dtype=float))[::-1][:k]
    disc = 1 / np.log2(np.arange(2, k + 2))
    dcg = float((rel * disc[: len(rel)]).sum())
    idcg = float((ideal * disc[: len(ideal)]).sum())
    return round(dcg / idcg, 4) if idcg else 0.0


def ranking_metrics(order: list[str], qualified: dict[str, bool]) -> dict:
    rel = [int(qualified[f]) for f in order]
    r = sum(rel)
    return {"r_precision": round(sum(rel[:r]) / r, 4) if r else None, "ndcg_at_10": ndcg(rel, 10)}


def run(n: int, seed: int, templates: list[str]) -> dict:
    cands = generate(n, seed, templates)
    truth = {c.file: c for c in cands}
    qualified = {c.file: c.qualified for c in cands}
    jd = parse_jd(JD_TEXT)
    with tempfile.TemporaryDirectory() as tmp:
        write(Path(tmp), cands)
        texts = {c.file: read_text((Path(tmp) / c.file).read_bytes(), c.file) for c in cands}
    resumes = [parse_resume(texts[f], f, TODAY) for f in texts]

    # Rankers
    hl = rank(resumes, jd)
    order_hl = [a.source for a in hl]
    jd_skills = jd.must_have | jd.nice_to_have
    kw = sorted(texts, key=lambda f: (-len(taxonomy.find(texts[f]) & jd_skills), f))
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    files = list(texts)
    vec = TfidfVectorizer(stop_words="english").fit([JD_TEXT] + [texts[f] for f in files])
    sims = cosine_similarity(vec.transform([JD_TEXT]), vec.transform([texts[f] for f in files]))[0]
    tfidf = [files[i] for i in np.argsort(-sims)]
    rankers = {
        "keyword_count": ranking_metrics(kw, qualified),
        "tfidf_similarity": ranking_metrics(tfidf, qualified),
        "fairshortlist": ranking_metrics(order_hl, qualified),
    }

    # Decisions
    short = {a.source for a in hl if a.decision == "shortlist"}
    q = {f for f, v in qualified.items() if v}
    decisions = {
        "shortlist_precision": round(len(short & q) / len(short), 4) if short else None,
        "shortlist_recall": round(len(short & q) / len(q), 4) if q else None,
    }
    by_kind: dict[str, dict] = defaultdict(lambda: {"n": 0, "shortlisted": 0, "rank_sum": 0})
    for pos, a in enumerate(hl, 1):
        k = truth[a.source].kind
        by_kind[k]["n"] += 1
        by_kind[k]["shortlisted"] += a.decision == "shortlist"
        by_kind[k]["rank_sum"] += pos
    kinds = {k: {"shortlisted": f"{v['shortlisted']}/{v['n']}",
                 "mean_rank": round(v["rank_sum"] / v["n"], 1)}
             for k, v in sorted(by_kind.items(), key=lambda kv: KINDS.index(kv[0]))}  # fmt: skip

    # Parsing accuracy: must-have skills demonstrated, and years of experience
    tp = fp = fn = 0
    year_err = []
    for r in resumes:
        c = truth[r.source]
        want = set(c.demonstrated) & set(MUST)
        got = set(r.skills_demonstrated) & set(MUST)
        tp, fp, fn = tp + len(want & got), fp + len(got - want), fn + len(want - got)
        year_err.append(abs(r.years_experience - c.years))
    parsing = {
        "skill_precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "skill_recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "years_mae": round(float(np.mean(year_err)), 2),
    }

    # Fairness: swap names and gender, re-render, re-parse, re-score
    swapped = []
    for c in cands:
        first, last = c.name.split()
        flipped = "male" if c.gender == "female" else "female"
        other = replace(c, name=f"{last} {first}", gender=flipped)
        swapped.append(parse_resume(read_text(render_pdf(text(other)), c.file), c.file, TODAY))
    base = {a.source: a.score for a in hl}
    deltas = [abs(base[a.source] - a.score) for a in rank(swapped, jd)]
    def leaked(r) -> bool:
        names = truth[r.source].name.split()
        pat = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b", re.I)
        return bool(pat.search(r.text_redacted)) or "@" in r.text_redacted

    leaks = sum(leaked(r) for r in resumes)
    fairness = {"max_score_change_after_name_gender_swap": round(max(deltas), 4),
                "resumes_with_name_or_email_after_redaction": leaks}  # fmt: skip

    return {
        "candidates": n, "qualified": len(q), "templates": templates, "rankers": rankers,
        "decisions": decisions, "by_kind": kinds, "parsing": parsing, "fairness": fairness,
    }  # fmt: skip


def report_markdown(dev: dict, held: dict) -> str:
    pct = lambda v: "n/a" if v is None else f"{v * 100:.0f}%"  # noqa: E731
    out = [
        f"### FairShortlist benchmark ({dev['candidates']} resumes, {dev['qualified']} qualified, "
        f"layouts: {', '.join(dev['templates'])})",
        "",
        "| Ranker | R-precision | NDCG@10 |",
        "|---|---|---|",
        *[f"| {k} | {pct(v['r_precision'])} | {v['ndcg_at_10']:.2f} |"
          for k, v in dev["rankers"].items()],
        "",
        "| Candidate type | Shortlisted | Mean rank |",
        "|---|---|---|",
        *[f"| {k} | {v['shortlisted']} | {v['mean_rank']} |" for k, v in dev["by_kind"].items()],
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Shortlist precision / recall | {pct(dev['decisions']['shortlist_precision'])} / "
        f"{pct(dev['decisions']['shortlist_recall'])} |",
        f"| Must-have skill extraction precision / recall | "
        f"{pct(dev['parsing']['skill_precision'])} / {pct(dev['parsing']['skill_recall'])} |",
        f"| Years of experience, mean absolute error | {dev['parsing']['years_mae']} years |",
        f"| Largest score change after swapping name and gender | "
        f"{dev['fairness']['max_score_change_after_name_gender_swap']} |",
        f"| Resumes with name or email left after redaction | "
        f"{dev['fairness']['resumes_with_name_or_email_after_redaction']} |",
        "",
        f"### Held-out layout ({', '.join(held['templates'])}: never seen while building)",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| FairShortlist R-precision | {pct(held['rankers']['fairshortlist']['r_precision'])} |",
        f"| Shortlist precision / recall | {pct(held['decisions']['shortlist_precision'])} / "
        f"{pct(held['decisions']['shortlist_recall'])} |",
        f"| Skill extraction precision / recall | {pct(held['parsing']['skill_precision'])} / "
        f"{pct(held['parsing']['skill_recall'])} |",
        f"| Years MAE | {held['parsing']['years_mae']} years |",
        f"| Score change after name and gender swap | "
        f"{held['fairness']['max_score_change_after_name_gender_swap']} |",
    ]  # fmt: skip
    return "\n".join(out) + "\n"


GATES = {"r_precision": 0.9, "shortlist_precision": 0.9}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Benchmark FairShortlist")
    p.add_argument("--n", type=int, default=120)
    p.add_argument("--seed", type=int, default=3)
    p.add_argument("--out", default="eval_results")
    p.add_argument("--gate", action="store_true")
    a = p.parse_args(argv)
    dev = run(a.n, a.seed, DEV_TEMPLATES)
    held = run(60, a.seed + 1, HELD_OUT_TEMPLATES)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps({"dev": dev, "held_out": held}, indent=2))
    md = report_markdown(dev, held)
    (out / "report.md").write_text(md)
    print(md)
    if a.gate:
        bad = []
        if (dev["rankers"]["fairshortlist"]["r_precision"] or 0) < GATES["r_precision"]:
            bad.append("r_precision")
        if (dev["decisions"]["shortlist_precision"] or 0) < GATES["shortlist_precision"]:
            bad.append("shortlist_precision")
        if dev["fairness"]["max_score_change_after_name_gender_swap"] > 0:
            bad.append("fairness")
        if bad:
            print(f"below gate: {bad}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
