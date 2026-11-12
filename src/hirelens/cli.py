"""Screen a folder of resumes against a job description.

    hirelens job.txt resumes/ --out shortlist.xlsx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .service import as_dicts, screen, workbook

TYPES = (".pdf", ".docx", ".txt")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hirelens", description=__doc__.splitlines()[0])
    p.add_argument("job", help="job description (.txt)")
    p.add_argument("folder", help="folder of resumes (PDF, DOCX, TXT)")
    p.add_argument("--out", default="shortlist.xlsx")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    files = [(f.name, f.read_bytes()) for f in sorted(Path(a.folder).iterdir())
             if f.suffix.lower() in TYPES]  # fmt: skip
    if not files:
        print(f"no resumes in {a.folder}", file=sys.stderr)
        return 2
    jd, results = screen(Path(a.job).read_text(encoding="utf-8"), files)
    Path(a.out).write_bytes(workbook(jd, results))
    if a.json:
        print(json.dumps(as_dicts(results), indent=2, default=str))
    else:
        n = {d: sum(r.decision == d for r in results) for d in ("shortlist", "review", "not_a_fit")}
        print(f"{len(results)} resumes: {n['shortlist']} shortlist, {n['review']} review, "
              f"{n['not_a_fit']} not a fit -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
