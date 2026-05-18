"""Verify sectioned rubric PDF parses to 12 questions / 25 marks.

Run: python -m scripts.debug_section_rubric
"""
from pathlib import Path

from app.services.rubric_parser import RubricParser

PDF = Path("sample pdfs/sample pdf new/MID-EXAM_28-02-2023_Final-Solutions.pdf")


def main() -> None:
    if not PDF.exists():
        print(f"Missing {PDF}")
        return
    schema = RubricParser().parse_file(PDF, "pdf")
    total = sum(i.max_marks for i in schema.items)
    print(f"Questions: {len(schema.items)}, Total: {total}")
    for item in schema.items:
        print(f"  {item.question_number}: {item.max_marks} marks")
    ok = len(schema.items) == 12 and total == 25.0
    print("PASS" if ok else "FAIL (expected 12 questions, 25 marks)")


if __name__ == "__main__":
    main()
