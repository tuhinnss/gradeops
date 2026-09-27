"""Evaluation engine correctness: marks come from rubric evidence, not effort."""

import hashlib
import re

import numpy as np
import pytest

from app.schemas.rubric import PartialCreditRule, RubricItem
from app.services import embeddings
from app.services.evaluation_engine import EvaluationEngine
from app.services.plagiarism_detector import PlagiarismDetector


class BagOfWordsEncoder:
    """Deterministic stand-in for a sentence-embedding model (no downloads)."""

    dims = 512

    def encode(self, sentences, **_kwargs):
        out = np.zeros((len(sentences), self.dims), dtype=np.float32)
        for row, text in enumerate(sentences):
            for word in re.findall(r"[a-z]{3,}", text.lower()):
                idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dims
                out[row, idx] += 1.0
        return out


@pytest.fixture(params=["semantic", "lexical"])
def engine(request, monkeypatch):
    if request.param == "semantic":
        embeddings.set_embedding_model(BagOfWordsEncoder())
    else:
        embeddings.set_embedding_model(None)
        monkeypatch.setattr(embeddings, "_load_failed", True)
    yield EvaluationEngine()
    embeddings.set_embedding_model(None)


NEWTON = RubricItem(
    question_number="Q1",
    max_marks=4,
    key_points=[
        "Newton's second law states force equals mass times acceleration",
        "Acceleration is proportional to net force",
    ],
)


def test_long_effortful_but_irrelevant_answer_gets_no_marks(engine):
    answer = (
        "1. Let x = 2y + 3z and integrate: dx/dt = 4t^2 + 7 => x = 4/3 t^3 + 7t + C\n"
        "2. Therefore y = sin(t) + cos(t), derivative = cos(t) - sin(t)\n"
        "3. Hence z = log(t) + 12 and the matrix determinant equals 42"
    )
    result = engine.evaluate_answer(answer, NEWTON, ocr_confidence=0.9)
    assert result.marks_awarded == 0
    # Substantive working that matches nothing is surfaced for a human instead.
    assert result.requires_manual_grading
    assert result.confidence <= 0.45
    assert "verify manually" in result.justification


def test_matching_answer_earns_criterion_marks(engine):
    answer = (
        "Newton's second law: the net force equals mass times acceleration. "
        "The acceleration is proportional to the net force applied."
    )
    result = engine.evaluate_answer(answer, NEWTON, ocr_confidence=0.9)
    assert result.marks_awarded == 4
    assert len(result.key_points_matched) == 2
    assert [c.status for c in result.criteria] == ["met", "met"]
    assert result.ai_marks_awarded == result.marks_awarded


def test_half_answer_earns_half_marks(engine):
    answer = "Newton's second law states force equals mass times acceleration."
    result = engine.evaluate_answer(answer, NEWTON, ocr_confidence=0.9)
    assert 2 <= result.marks_awarded < 4
    assert result.key_points_missed or result.key_points_partial


def test_no_key_points_requires_manual_grading(engine):
    item = RubricItem(question_number="Q2", max_marks=5, key_points=[])
    result = engine.evaluate_answer("A long answer with lots of working = 42 + 7", item)
    assert result.marks_awarded == 0
    assert result.requires_manual_grading
    assert result.confidence <= 0.2


def test_partial_rule_is_a_floor_not_a_bonus(engine):
    item = RubricItem(
        question_number="Q3",
        max_marks=5,
        key_points=["Correct formula for kinetic energy half m v squared", "Correct final numeric answer with units joules"],
        partial_credit_rules=[PartialCreditRule(condition="Correct formula for kinetic energy half m v squared", marks=2)],
    )
    answer = "Correct formula for kinetic energy: half m v squared."
    result = engine.evaluate_answer(answer, item, ocr_confidence=0.9)
    # Key point share is 2.5; the matching partial rule (2) must not stack on top.
    assert result.marks_awarded == 2.5


def test_blank_answer_zero(engine):
    result = engine.evaluate_answer("   ", NEWTON)
    assert result.is_blank and result.marks_awarded == 0


def test_lexical_fallback_is_marked_and_capped(monkeypatch):
    embeddings.set_embedding_model(None)
    monkeypatch.setattr(embeddings, "_load_failed", True)
    engine = EvaluationEngine()
    answer = "Newton's second law states force equals mass times acceleration. Acceleration is proportional to net force."
    result = engine.evaluate_answer(answer, NEWTON, ocr_confidence=0.95)
    assert result.scoring_method == "lexical"
    assert result.confidence <= 0.5
    assert "keyword matching only" in result.justification


def test_similarity_flags_use_neutral_wording(monkeypatch):
    embeddings.set_embedding_model(None)
    monkeypatch.setattr(embeddings, "_load_failed", True)
    text = "The derivative of x squared is two x by the power rule applied directly"
    flags = PlagiarismDetector().detect(
        [
            {"student_id": "S1", "answers": [{"question_number": "Q1", "extracted_text": text}]},
            {"student_id": "S2", "answers": [{"question_number": "Q1", "extracted_text": text}]},
            {"student_id": "S3", "answers": [{"question_number": "Q1", "extracted_text": "Completely different reasoning about integrals of sine"}]},
        ]
    )
    assert len(flags) == 1
    flag = flags[0]
    assert {flag.student_id_a, flag.student_id_b} == {"S1", "S2"}
    assert "plagiar" not in flag.note.lower()
    assert "review required" in flag.note.lower()
    assert flag.excerpt_a


def test_annotator_handles_full_width_rubric_regions(tmp_path):
    """Regression: full-width regions used to push the comment box off the page."""
    import fitz

    from app.config import get_settings
    from app.schemas.evaluation import QuestionResult
    from app.services.pdf_annotator import PDFAnnotator

    src = tmp_path / "sheet.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Q1. force equals mass times acceleration")
    doc.save(src)
    zoom = get_settings().pdf_dpi / 72.0
    width_px, height_px = page.rect.width * zoom, page.rect.height * zoom
    region = {"question_number": "Q1", "page_index": 0, "bbox": {"x0": 0, "y0": 0, "x1": width_px, "y1": height_px / 2}}
    result = QuestionResult(question="Q1", marks_awarded=3, max_marks=4, justification="Met: F=ma", confidence=0.7)
    out = PDFAnnotator().annotate(src, [result], [region], tmp_path / "out.pdf", "S1")
    with fitz.open(out) as annotated:
        text = annotated[0].get_text()
    assert "3.0/4" in text and "Met: F=ma" in text and "Total: 3.0/4.0" in text


def test_answers_that_both_follow_the_reference_are_not_flagged(monkeypatch):
    embeddings.set_embedding_model(None)
    monkeypatch.setattr(embeddings, "_load_failed", True)
    reference = "Breadth first search uses a queue and visits the graph level by level"
    textbook = "Breadth first search uses a queue and visits the graph level by level."
    copied = "My own idea: we colour nodes grey then black and keep a parent array for paths."
    subs = [
        {"student_id": "S1", "answers": [{"question_number": "Q4", "extracted_text": textbook}]},
        {"student_id": "S2", "answers": [{"question_number": "Q4", "extracted_text": textbook}]},
        {"student_id": "S3", "answers": [{"question_number": "Q4", "extracted_text": copied}]},
        {"student_id": "S4", "answers": [{"question_number": "Q4", "extracted_text": copied}]},
    ]
    flags = PlagiarismDetector().detect(subs, references={"Q4": reference})
    # Two correct textbook answers converge on the reference: expected, not flagged.
    # Two identical *unusual* answers are still a potential match.
    assert [{f.student_id_a, f.student_id_b} for f in flags] == [{"S3", "S4"}]
    # Without a reference (legacy callers) both pairs are flagged as before.
    assert len(PlagiarismDetector().detect(subs)) == 2
