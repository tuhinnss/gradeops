"""Tests for parsing validation and deduplication."""

from pathlib import Path

import pytest

from app.schemas.rubric import RubricItem
from app.services.text_utils import (
    clean_ocr_text,
    find_question_blocks,
    merge_answers_by_question,
    normalize_question_label,
    parse_declared_exam_total,
    validate_rubric_items,
)


def test_normalize_rejects_q0():
    assert normalize_question_label(0) == ""
    assert normalize_question_label("0") == ""
    assert normalize_question_label(1) == "Q1"


def test_dedupe_rubric_no_q0_duplicates():
    items = [
        RubricItem(question_number="Q0", max_marks=5, key_points=["bad"]),
        RubricItem(question_number="Q0", max_marks=3, key_points=["dup"]),
        RubricItem(question_number="Q1", max_marks=5, key_points=["Newton law"]),
        RubricItem(question_number="Q2", max_marks=5, key_points=["Energy"]),
    ]
    validated = validate_rubric_items(items)
    labels = [i.question_number for i in validated]
    assert "Q0" not in labels
    assert labels == ["Q1", "Q2"]
    assert sum(i.max_marks for i in validated) == 10.0


def test_compound_marks_parsing():
    text = "6. Fourier series [2+1 Marks]\nSolution content here."
    blocks = find_question_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].question_number == "Q6"
    assert blocks[0].max_marks == 3.0


def test_declared_total():
    text = "QUIZ 2\nTotal Marks: 15\n1. First question [2 Marks]"
    assert parse_declared_exam_total(text) == 15.0


def test_find_question_blocks_no_spurious_splits():
    text = """
    Q1. Newton's laws [5]
    - Force equals mass times acceleration
    Q2. Energy (5 marks)
    - Kinetic energy formula
    Page 3 of 10
    2024 exam
    """
    blocks = find_question_blocks(text)
    assert len(blocks) == 2
    assert blocks[0].question_number == "Q1"
    assert blocks[0].max_marks == 5.0
    assert blocks[1].question_number == "Q2"


def test_merge_answers_keeps_longest():
    answers = [
        {"question_number": "Q1", "extracted_text": "hi", "ocr_confidence": 0.9},
        {
            "question_number": "Q1",
            "extracted_text": "Newton second law F equals ma with example",
            "ocr_confidence": 0.7,
        },
        {
            "question_number": "Q2",
            "extracted_text": "kinetic energy equals one half m v squared",
            "ocr_confidence": 0.8,
        },
    ]
    merged = merge_answers_by_question(answers, ["Q1", "Q2"])
    assert len(merged) == 2
    q1 = next(a for a in merged if a["question_number"] == "Q1")
    assert "Newton" in q1["extracted_text"]


def test_section_exam_twenty_five_marks():
    text = Path("outputs/debug_MID-EXAM_28-02-2023_Final-Solutions.txt").read_text(
        encoding="utf-8"
    )
    blocks = find_question_blocks(text)
    assert len(blocks) == 12
    assert sum(b.max_marks for b in blocks) == 25.0
    assert blocks[0].max_marks == 1.0
    assert blocks[6].max_marks == 1.0  # last of section I (7×1)
    assert blocks[7].max_marks == 2.0  # first of section II
    assert blocks[9].max_marks == 2.0
    assert blocks[10].max_marks == 6.0  # section III
    assert blocks[11].max_marks == 6.0


def test_clean_ocr_drops_noise_lines():
    raw = "||| \n\nQ1. Real answer here with content\n***"
    cleaned = clean_ocr_text(raw)
    assert "Q1" in cleaned
    assert "|||" not in cleaned
