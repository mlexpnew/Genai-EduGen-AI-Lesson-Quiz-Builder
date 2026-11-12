"""HTTP API for ATS integrations.

    uvicorn hirelens.api:app --port 8000

Resumes are processed in memory and never stored. Set HIRELENS_API_KEYS to require keys.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile

from . import __version__
from .service import as_dicts, screen

MAX_FILES, MAX_BYTES = 300, 5 * 1024 * 1024
app = FastAPI(
    title="HireLens",
    version=__version__,
    description="Explainable, blind resume screening. Recommendations for a human recruiter.",
)


def auth(x_api_key: str = Header(default="")) -> None:
    keys = {k.strip() for k in os.getenv("HIRELENS_API_KEYS", "").split(",") if k.strip()}
    if keys and x_api_key not in keys:
        raise HTTPException(401, "missing or invalid X-API-Key")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/v1/screen", dependencies=[Depends(auth)])
async def screen_endpoint(job_description: str = Form(...),
                          resumes: list[UploadFile] = File(...)) -> dict:  # fmt: skip
    if not resumes or len(resumes) > MAX_FILES:
        raise HTTPException(400, f"send 1 to {MAX_FILES} resumes")
    files = []
    for f in resumes:
        data = await f.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, f"{f.filename} is larger than 5 MB")
        if not (f.filename or "").lower().endswith((".pdf", ".docx", ".txt")):
            raise HTTPException(415, f"{f.filename}: send PDF, DOCX or TXT")
        files.append((f.filename, data))
    jd, results = screen(job_description, files)
    return {
        "job": {"title": jd.title, "must_have": sorted(jd.must_have),
                "nice_to_have": sorted(jd.nice_to_have), "min_years": jd.min_years},
        "candidates": as_dicts(results),
        "note": "Recommendations only. A recruiter reviews every candidate.",
    }  # fmt: skip
