"""Semantic + heuristic evaluation for handwritten exams (OCR-tolerant)."""

import logging
import re
from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer, util

from app.config import get_settings
from app.schemas.evaluation import QuestionResult
from app.schemas.rubric import RubricItem
from app.services.answer_quality import (
    AnswerQuality,
    analyze_answer,
    effort_based_marks,
    realistic_confidence,
)
from app.services.ocr.ocr_service import OCRService
from app.services.text_utils import (
    adjust_ocr_confidence,
    clean_ocr_text,
    keyword_overlap_score,
    round_marks,
)

logger = logging.getLogger(__name__)

# Relaxed thresholds — handwritten OCR rarely matches typed rubric embeddings
FULL_MATCH = 0.38
PARTIAL_MATCH = 0.22
KEYWORD_BOOST = 0.18
SOFT_MATCH = 0.15


@dataclass
class KeyPointScore:
    point: str
    similarity: float
    keyword_score: float
    combined: float
    matched: bool
    partial: bool


class EvaluationEngine:
    """
    Award marks using rubric similarity + handwritten-answer heuristics.

    When OCR noise breaks embedding match, substantive math content still earns
    partial credit. Blanks remain at zero.
    """

    _model: SentenceTransformer | None = None

    def __init__(self):
        settings = get_settings()
        self.model_id = settings.embedding_model_id
        self.similarity_threshold = min(settings.similarity_threshold, FULL_MATCH)
        self.use_llm = settings.use_llm_reasoning and bool(settings.openai_api_key)
        self.ocr = OCRService()

    def _get_model(self) -> SentenceTransformer:
        if EvaluationEngine._model is None:
            logger.info("Loading embedding model: %s", self.model_id)
            EvaluationEngine._model = SentenceTransformer(self.model_id)
        return EvaluationEngine._model

    def _score_key_point(
        self, answer_emb, point: str, model: SentenceTransformer, answer_text: str
    ) -> KeyPointScore:
        point_emb = model.encode(point, convert_to_tensor=True)
        sem = float(util.cos_sim(answer_emb, point_emb)[0][0])
        kw = keyword_overlap_score(answer_text, point)
        combined = 0.55 * sem + 0.45 * kw

        matched = combined >= FULL_MATCH or (
            sem >= PARTIAL_MATCH and kw >= KEYWORD_BOOST
        )
        partial = not matched and (
            combined >= SOFT_MATCH or sem >= SOFT_MATCH or kw >= KEYWORD_BOOST
        )

        return KeyPointScore(
            point=point,
            similarity=sem,
            keyword_score=kw,
            combined=combined,
            matched=matched,
            partial=partial,
        )

    def evaluate_answer(
        self,
        student_text: str,
        rubric_item: RubricItem,
        ocr_confidence: float = 0.5,
    ) -> QuestionResult:
        q_label = rubric_item.question_number
        max_marks = rubric_item.max_marks
        student_text = clean_ocr_text(student_text)
        ocr_adj = adjust_ocr_confidence(ocr_confidence, student_text)

        quality = analyze_answer(
            student_text,
            ocr_confidence=ocr_adj,
            rubric_key_points=rubric_item.key_points,
            blank_min_chars=get_settings().blank_answer_min_chars,
        )

        # Truly blank — only case for zero marks with high confidence
        if quality.is_truly_blank or (
            self.ocr.is_blank(student_text) and quality.content_score < 0.15
        ):
            return QuestionResult(
                question=q_label,
                marks_awarded=0.0,
                max_marks=max_marks,
                justification=(
                    f"{q_label}: No readable handwritten work detected. "
                    "Answer treated as blank; no marks awarded."
                ),
                confidence=0.90,
                is_blank=True,
            )

        if not rubric_item.key_points:
            return self._evaluate_without_keypoints(
                student_text, rubric_item, ocr_adj, quality
            )

        model = self._get_model()
        answer_emb = model.encode(student_text, convert_to_tensor=True)

        key_scores: list[KeyPointScore] = [
            self._score_key_point(answer_emb, point, model, student_text)
            for point in rubric_item.key_points
        ]

        matched = [ks for ks in key_scores if ks.matched]
        partial = [ks for ks in key_scores if ks.partial]
        missed = [ks for ks in key_scores if not ks.matched and not ks.partial]

        n = max(len(rubric_item.key_points), 1)
        marks_per_point = max_marks / n
        rubric_marks = len(matched) * marks_per_point + len(partial) * (
            marks_per_point * 0.55
        )

        partial_bonus = self._apply_partial_rules(student_text, rubric_item, model)
        negative_deduction = self._apply_negative_conditions(
            student_text, rubric_item, model
        )

        rubric_marks = max(0.0, rubric_marks + partial_bonus - negative_deduction)

        # Heuristic partial credit for handwritten math (OCR-tolerant)
        effort_marks = effort_based_marks(max_marks, quality)

        # Blend: take the better of rubric alignment vs demonstrated working
        if rubric_marks < effort_marks * 0.5 and quality.is_handwritten_math:
            marks_awarded = effort_marks
        else:
            marks_awarded = max(rubric_marks, effort_marks * 0.75)

        # Cap: effort alone cannot exceed 85% of max
        if rubric_marks < marks_per_point * 0.5:
            marks_awarded = min(marks_awarded, max_marks * 0.85)

        marks_awarded = round_marks(max(0.0, min(max_marks, marks_awarded)))

        confidence = realistic_confidence(
            quality, ocr_adj, marks_awarded, max_marks
        )

        justification = self._build_justification(
            rubric_item,
            matched,
            partial,
            missed,
            marks_awarded,
            negative_deduction,
            quality,
        )

        if self.use_llm:
            justification = self._enhance_with_llm(
                student_text, rubric_item, marks_awarded, justification
            )

        logger.debug(
            "%s marks=%.1f/%.1f content=%.2f rubric=%.1f effort=%.1f kw=%.2f",
            q_label,
            marks_awarded,
            max_marks,
            quality.content_score,
            rubric_marks,
            effort_marks,
            quality.keyword_best,
        )

        return QuestionResult(
            question=q_label,
            marks_awarded=marks_awarded,
            max_marks=max_marks,
            justification=justification,
            confidence=confidence,
            is_blank=False,
            key_points_matched=[ks.point for ks in matched],
            key_points_missed=[ks.point for ks in missed],
            negative_triggers=(
                rubric_item.negative_conditions[:2] if negative_deduction > 0 else []
            ),
        )

    def _evaluate_without_keypoints(
        self,
        student_text: str,
        rubric_item: RubricItem,
        ocr_confidence: float,
        quality: AnswerQuality,
    ) -> QuestionResult:
        """Score questions with no rubric bullets using content heuristics only."""
        marks = round_marks(
            min(
                rubric_item.max_marks * 0.85,
                effort_based_marks(rubric_item.max_marks, quality),
            )
        )
        confidence = realistic_confidence(
            quality, ocr_confidence, marks, rubric_item.max_marks
        )
        justification = (
            f"{rubric_item.question_number}: {marks:.1f} / {rubric_item.max_marks:.1f} marks. "
            "Graded on visible mathematical working and OCR-readable content "
            f"(content strength {quality.content_score:.0%})."
        )
        return QuestionResult(
            question=rubric_item.question_number,
            marks_awarded=marks,
            max_marks=rubric_item.max_marks,
            justification=justification,
            confidence=confidence,
        )

    def _apply_partial_rules(
        self, student_text: str, rubric_item: RubricItem, model: SentenceTransformer
    ) -> float:
        bonus = 0.0
        if not rubric_item.partial_credit_rules:
            return bonus

        answer_emb = model.encode(student_text, convert_to_tensor=True)
        for rule in rubric_item.partial_credit_rules:
            if not rule.condition or rule.marks <= 0:
                continue
            rule_emb = model.encode(rule.condition, convert_to_tensor=True)
            sem = float(util.cos_sim(answer_emb, rule_emb)[0][0])
            kw = keyword_overlap_score(student_text, rule.condition)
            if sem >= SOFT_MATCH or kw >= KEYWORD_BOOST:
                bonus += min(rule.marks, rubric_item.max_marks * 0.5)
        return min(bonus, rubric_item.max_marks * 0.5)

    def _apply_negative_conditions(
        self, student_text: str, rubric_item: RubricItem, model: SentenceTransformer
    ) -> float:
        if not rubric_item.negative_conditions:
            return 0.0

        answer_emb = model.encode(student_text, convert_to_tensor=True)
        penalty_per = rubric_item.max_marks * 0.15
        deduction = 0.0

        for condition in rubric_item.negative_conditions:
            cond_emb = model.encode(condition, convert_to_tensor=True)
            sem = float(util.cos_sim(answer_emb, cond_emb)[0][0])
            kw = keyword_overlap_score(student_text, condition)
            # Higher bar for penalties — avoid false deductions on noisy OCR
            if sem >= FULL_MATCH and kw >= 0.35:
                deduction += penalty_per

        return min(deduction, rubric_item.max_marks * 0.4)

    def _build_justification(
        self,
        rubric_item: RubricItem,
        matched: list[KeyPointScore],
        partial: list[KeyPointScore],
        missed: list[KeyPointScore],
        marks: float,
        deduction: float,
        quality: AnswerQuality,
    ) -> str:
        ratio = marks / rubric_item.max_marks if rubric_item.max_marks else 0.0
        parts: list[str] = []

        if ratio >= 0.85:
            parts.append(
                f"{rubric_item.question_number}: Strong response ({marks:.1f}/{rubric_item.max_marks:.1f}). "
                "Key ideas align well with the marking scheme."
            )
        elif ratio >= 0.5:
            parts.append(
                f"{rubric_item.question_number}: Satisfactory ({marks:.1f}/{rubric_item.max_marks:.1f}). "
                "Core ideas present with some gaps or OCR ambiguity."
            )
        elif marks > 0:
            parts.append(
                f"{rubric_item.question_number}: Partial credit ({marks:.1f}/{rubric_item.max_marks:.1f}). "
            )
            if quality.is_handwritten_math:
                parts.append(
                    "Handwritten mathematical working is visible "
                    f"(symbols/steps detected; content score {quality.content_score:.0%}). "
                    "Exact rubric phrasing match limited by OCR — partial marks awarded for demonstrated effort."
                )
            else:
                parts.append(
                    "Some relevant content identified; answer incomplete versus rubric."
                )
        else:
            parts.append(
                f"{rubric_item.question_number}: Minimal credit ({marks:.1f}/{rubric_item.max_marks:.1f}). "
                "Response does not meet rubric criteria."
            )

        if matched:
            parts.append(
                "Criteria met: "
                + "; ".join(ks.point[:55] for ks in matched[:2])
                + ("." if len(matched) <= 2 else f" (+{len(matched) - 2} more).")
            )
        elif partial and marks > 0:
            parts.append(
                "Partial alignment: "
                + "; ".join(ks.point[:50] for ks in partial[:2])
                + "."
            )
        elif missed and marks == 0:
            parts.append(
                "Expected topics not clearly identified in OCR text."
            )

        if deduction > 0:
            parts.append(f"Penalty: −{deduction:.1f} marks per rubric conditions.")

        return " ".join(parts)

    def _enhance_with_llm(
        self,
        student_text: str,
        rubric_item: RubricItem,
        marks: float,
        base_justification: str,
    ) -> str:
        try:
            from openai import OpenAI

            settings = get_settings()
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an exam grader. Refine the justification to be clear and "
                            "professional in 2-3 sentences. Do not change the marks."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question: {rubric_item.question_number}\n"
                            f"Max marks: {rubric_item.max_marks}\n"
                            f"Awarded: {marks}\n"
                            f"Key points: {rubric_item.key_points}\n"
                            f"Student answer: {student_text[:1500]}\n"
                            f"Draft justification: {base_justification}"
                        ),
                    },
                ],
                max_tokens=200,
                temperature=0.2,
            )
            return response.choices[0].message.content or base_justification
        except Exception as exc:
            logger.warning("LLM reasoning failed, using template: %s", exc)
            return base_justification

    def evaluate_all(
        self,
        answers: list[dict],
        rubric_items: list[RubricItem],
    ) -> list[QuestionResult]:
        """
        One result per rubric question; totals sum cleanly for the API response.
        """
        from app.services.text_utils import merge_answers_by_question

        rubric_q = [r.question_number for r in rubric_items]
        merged = merge_answers_by_question(answers, rubric_q)
        answer_map = {a["question_number"].upper(): a for a in merged}

        results: list[QuestionResult] = []
        for item in rubric_items:
            label = item.question_number.upper()
            ans = answer_map.get(label)
            if not ans:
                results.append(
                    self.evaluate_answer("", item, ocr_confidence=0.0)
                )
                continue

            text = ans.get("extracted_text", "")
            ocr_conf = float(ans.get("ocr_confidence", 0.5))

            # Do not trust OCR is_blank alone — handwriting may be misclassified
            if ans.get("is_blank") and len(clean_ocr_text(text)) > 20:
                logger.debug(
                    "%s: OCR flagged blank but text len=%d — re-evaluating",
                    label,
                    len(text),
                )

            results.append(
                self.evaluate_answer(text, item, ocr_confidence=ocr_conf)
            )

        return results
