"""Debug rubric parse for sample Quiz2 PDF.

Run from project root:
  python -m scripts.debug_quiz_rubric
"""
from pathlib import Path

from app.services.rubric_parser import RubricParser

PDF = Path("sample pdfs/Quiz2_MA201-2025-Solutions.pdf")

EXPECTED = {"Q1": 2, "Q2": 4, "Q3": 2, "Q4": 3, "Q5": 1, "Q6": 3}


def main() -> None:
    if not PDF.exists():
        print(f"Missing {PDF}")
        return
    schema = RubricParser().parse_file(PDF, "pdf")
    total = sum(i.max_marks for i in schema.items)
    print(f"Questions: {len(schema.items)}, Total: {total}")
    for item in schema.items:
        exp = EXPECTED.get(item.question_number)
        ok = "OK" if exp == item.max_marks else f"EXPECTED {exp}"
        print(f"  {item.question_number}: {item.max_marks} marks, {len(item.key_points)} key_points — {ok}")
    if total == 15 and len(schema.items) == 6:
        print("PASS: rubric matches expected 15 marks / 6 questions")
    else:
        print("FAIL: expected 6 questions, 15 marks")


if __name__ == "__main__":
    main()
