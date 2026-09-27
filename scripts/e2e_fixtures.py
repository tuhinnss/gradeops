"""Generate fixture files for the browser E2E (frontend/e2e/workflow.cjs).

    python -m scripts.e2e_fixtures /tmp/gradeops-e2e

Writes a roster CSV, the sample rubric and three typed answer sheets whose
content matches the rubric to different degrees.
"""

import json
import shutil
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = ROOT / "samples" / "ds_midsem_rubric.json"


def sheet(path: Path, answers: dict[str, str]) -> None:
    doc = fitz.open()
    page = doc.new_page()
    h = (page.rect.height - 60) / len(answers)
    for i, (q, text) in enumerate(answers.items()):
        page.insert_textbox(fitz.Rect(50, 60 + i * h, 550, 50 + (i + 1) * h), f"{q}. {text}", fontsize=13)
    doc.save(path)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rubric = json.loads(RUBRIC.read_text())
    strong = {i["question_number"]: " ".join(f"{k}." for k in i["key_points"]) for i in rubric["items"]}
    weak = {
        "Q1": "A stack stores items and we push them.",
        "Q2": "Trees have nodes.",
        "Q3": "Two keys can land in the same bucket which is a collision.",
        "Q4": "BFS uses a queue and goes level by level.",
    }
    sheet(out / "E2E001_midsem.pdf", strong)
    sheet(out / "E2E002_midsem.pdf", weak)
    sheet(out / "E2E003_midsem.pdf", {**weak, "Q2": strong["Q2"]})
    (out / "roster.csv").write_text("student_id,name,email\nE2E001,Kavya Reddy,\nE2E002,Liam Fernandes,\nE2E003,Maya Joshi,\n")
    shutil.copy(RUBRIC, out / RUBRIC.name)
    print(f"Fixtures written to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/gradeops-e2e"))
