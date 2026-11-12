import io

import pytest
from openpyxl import load_workbook

from hirelens.cli import main
from hirelens.evaluate import run
from hirelens.service import screen, workbook
from hirelens.synth import DEV_TEMPLATES, JD_TEXT, TODAY, generate, render_pdf, text


def files(n=12):
    return [(c.file, render_pdf(text(c))) for c in generate(n, seed=8)]


def test_screen_and_workbook():
    jd, results = screen(JD_TEXT, files(), TODAY)
    assert len(results) == 12 and results[0].score >= results[-1].score
    wb = load_workbook(io.BytesIO(workbook(jd, results)))
    assert wb["Shortlist"].max_row == 3 + 12


def test_docx_and_txt_inputs():
    import docx

    d = docx.Document()
    body = text(generate(1, seed=2)[0])
    for line in body.splitlines():
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    _, results = screen(JD_TEXT, [("a.docx", buf.getvalue()), ("b.txt", body.encode())], TODAY)
    assert results[0].score == results[1].score  # same content, same score, any format


def test_cli(tmp_path, capsys):
    (tmp_path / "jd.txt").write_text(JD_TEXT)
    folder = tmp_path / "r"
    folder.mkdir()
    for name, data in files(6):
        (folder / name).write_bytes(data)
    assert main([str(tmp_path / "jd.txt"), str(folder), "--out", str(tmp_path / "s.xlsx")]) == 0
    assert "6 resumes" in capsys.readouterr().out


def test_benchmark_fairness_and_quality():
    r = run(36, 5, DEV_TEMPLATES)
    assert r["fairness"]["max_score_change_after_name_gender_swap"] == 0
    assert r["fairness"]["resumes_with_name_or_email_after_redaction"] == 0
    assert r["rankers"]["hirelens"]["r_precision"] > r["rankers"]["tfidf_similarity"]["r_precision"]


def test_api():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from hirelens.api import app

    c = TestClient(app)
    r = c.post("/v1/screen", data={"job_description": JD_TEXT},
               files=[("resumes", (n, d, "application/pdf")) for n, d in files(3)])  # fmt: skip
    assert r.status_code == 200 and len(r.json()["candidates"]) == 3
    bad = c.post("/v1/screen", data={"job_description": JD_TEXT},
                 files=[("resumes", ("x.exe", b"MZ", "application/octet-stream"))])  # fmt: skip
    assert bad.status_code == 415


def test_streamlit_app():
    pytest.importorskip("streamlit")
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    at.run()
    at.button[0].click().run()
    assert not at.exception and len(at.metric) == 3
