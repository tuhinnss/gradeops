"""Tests for evaluation engine."""

import pytest

from app.schemas.rubric import RubricItem
from app.services.evaluation_engine import EvaluationEngine
from app.services.ocr.ocr_service import OCRService


@pytest.fixture(scope="module")
def engine():
    return EvaluationEngine()


def test_blank_answer_zero_marks(engine):
    item = RubricItem(
        question_number="Q1",
        max_marks=5,
        key_points=["Point A", "Point B"],
    )
    result = engine.evaluate_answer("  ", item)
    assert result.is_blank
    assert result.marks_awarded == 0


def test_matching_answer_gets_marks(engine):
    item = RubricItem(
        question_number="Q1",
        max_marks=4,
        key_points=[
            "Newton's second law states force equals mass times acceleration",
            "Acceleration is proportional to net force",
        ],
    )
    answer = (
        "According to Newton's second law, the net force on an object equals "
        "its mass multiplied by acceleration. Greater force produces greater acceleration."
    )
    result = engine.evaluate_answer(answer, item, ocr_confidence=0.9)
    assert result.marks_awarded > 0
    assert result.confidence > 0


def test_ocr_blank_detection():
    ocr = OCRService()
    assert ocr.is_blank("")
    assert ocr.is_blank("  ")
    assert not ocr.is_blank("This is a valid answer with content.")
