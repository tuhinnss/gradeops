"""Tests for handwritten-answer heuristics (no ML deps)."""

from app.services.answer_quality import analyze_answer, effort_based_marks


def test_content_score_for_math():
    q = analyze_answer(
        "u(x,t) = integral cos(s) ds  sin(x+ct) - sin(x-ct)",
        ocr_confidence=0.5,
        rubric_key_points=["D Alembert wave equation"],
    )
    assert q.content_score > 0.25
    assert q.is_handwritten_math
    assert effort_based_marks(4.0, q) > 0


def test_effort_marks_tiers():
    q = analyze_answer(
        "xux + yuy = u-1  gradient  orthogonal  PDE 2x 2y",
        ocr_confidence=0.6,
        rubric_key_points=["orthogonal surfaces PDE"],
    )
    m = effort_based_marks(4.0, q)
    assert m >= 1.0


def test_blank_no_effort_marks():
    q = analyze_answer("  ", ocr_confidence=0.5)
    assert q.is_truly_blank
    assert effort_based_marks(4.0, q) == 0.0
