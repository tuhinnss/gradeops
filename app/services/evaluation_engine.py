"""Rubric-evidence evaluation for handwritten exams (OCR-tolerant).

Marks are awarded only for rubric criteria that are evidenced in the answer text:

* each key point is worth ``max_marks / n``; a strong match earns the full share,
  a moderate match earns half;
* partial-credit rules act as floors (an answer matching "partial explanation → 2"
  receives at least 2), they are not added on top of key-point marks;
* negative conditions deduct only on a strong match (avoids OCR false positives).

Length, symbol density and other "effort" heuristics never add marks. They are
used as evidence that the answer may contain relevant work the matcher could not
recognise (typically OCR or phrasing mismatch); such answers get a low
confidence and ``requires_manual_grading`` so the TA queue surfaces them.

Similarity is evidence, not correctness: every AI result is provisional until a
human reviewer approves or overrides it.
"""

import logging
from dataclasses import dataclass

from app.config import get_settings
from app.schemas.evaluation import CriterionScore, QuestionResult
from app.schemas.rubric import RubricItem
from app.services.answer_quality import (
    AnswerQuality,
    analyze_answer,
    effort_based_marks,
    realistic_confidence,
)
from app.services.embeddings import encode_normalized
from app.services.ocr.ocr_service import OCRService
from app.services.text_utils import (
    adjust_ocr_confidence,
    clean_ocr_text,
    keyword_overlap_score,
    round_marks,
)

logger = logging.getLogger(__name__)

# Semantic (sentence-embedding cosine) thresholds. all-MiniLM-L6-v2 scores
# paraphrases ~0.6–0.8, same-topic text ~0.3–0.5 and unrelated text < 0.25.
FULL_SEMANTIC = 0.55
PARTIAL_SEMANTIC = 0.40
# Keyword overlap = share of the criterion's content words present in the answer.
FULL_KEYWORD = 0.60
PARTIAL_KEYWORD = 0.35
SUPPORT_KEYWORD = 0.25
# Word overlap without semantic agreement is not trusted on its own.
MIN_SEMANTIC_FOR_KEYWORD_MATCH = 0.30

PARTIAL_POINT_WEIGHT = 0.5
PENALTY_FRACTION = 0.15
MAX_PENALTY_FRACTION = 0.4

# Confidence caps for results that need a closer human look.
LEXICAL_CONFIDENCE_CAP = 0.5
EVIDENCE_GAP_CONFIDENCE_CAP = 0.45
MANUAL_GRADING_CONFIDENCE = 0.2


@dataclass
class KeyPointScore:
    point: str
    similarity: float | None
    keyword_score: float
    combined: float
    matched: bool
    partial: bool


def _classify(sem: float | None, kw: float) -> tuple[bool, bool]:
    """Return (full match, partial match) for one criterion."""
    if sem is None:  # lexical fallback: keyword overlap is the only evidence
        matched = kw >= FULL_KEYWORD
        return matched, (not matched and kw >= PARTIAL_KEYWORD)
    matched = (
        sem >= FULL_SEMANTIC
        or (sem >= PARTIAL_SEMANTIC and kw >= SUPPORT_KEYWORD)
        or (kw >= FULL_KEYWORD and sem >= MIN_SEMANTIC_FOR_KEYWORD_MATCH)
    )
    partial = not matched and (
        sem >= PARTIAL_SEMANTIC
        or (kw >= PARTIAL_KEYWORD and sem >= MIN_SEMANTIC_FOR_KEYWORD_MATCH)
    )
    return matched, partial


def _strong_match(sem: float | None, kw: float) -> bool:
    """Bar for partial-credit rules and penalties (higher than key points)."""
    if sem is None:
        return kw >= FULL_KEYWORD
    return sem >= FULL_SEMANTIC and kw >= PARTIAL_KEYWORD


class EvaluationEngine:
    """Award marks from rubric evidence; flag low-evidence answers for humans."""

    def __init__(self):
        settings = get_settings()
        self.use_llm = settings.use_llm_reasoning and bool(settings.openai_api_key)
        self.ocr = OCRService()

    @staticmethod
    def _similarities(answer: str, references: list[str]) -> list[float | None]:
        """Cosine similarity of the answer to each reference (None if no model)."""
        if not references:
            return []
        vectors = encode_normalized([answer, *references])
        if vectors is None:
            return [None] * len(references)
        return [float(v) for v in vectors[1:] @ vectors[0]]

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
                ai_marks_awarded=0.0,
            )

        if not rubric_item.key_points:
            return self._manual_grading_result(rubric_item, quality)

        rules = [r for r in rubric_item.partial_credit_rules if r.condition and r.marks > 0]
        negatives = [c for c in rubric_item.negative_conditions if c]
        references = [*rubric_item.key_points, *(r.condition for r in rules), *negatives]
        sims = self._similarities(student_text, references)
        lexical_only = bool(sims) and sims[0] is None
        kp_sims = sims[: len(rubric_item.key_points)]
        rule_sims = sims[len(rubric_item.key_points) : len(rubric_item.key_points) + len(rules)]
        neg_sims = sims[len(rubric_item.key_points) + len(rules) :]

        key_scores: list[KeyPointScore] = []
        for point, sem in zip(rubric_item.key_points, kp_sims, strict=True):
            kw = keyword_overlap_score(student_text, point)
            matched, partial = _classify(sem, kw)
            combined = kw if sem is None else 0.55 * sem + 0.45 * kw
            key_scores.append(KeyPointScore(point, sem, kw, combined, matched, partial))

        matched = [ks for ks in key_scores if ks.matched]
        partial = [ks for ks in key_scores if ks.partial]
        missed = [ks for ks in key_scores if not ks.matched and not ks.partial]

        marks_per_point = max_marks / max(len(rubric_item.key_points), 1)
        criteria: list[CriterionScore] = []
        for ks in key_scores:
            share = marks_per_point if ks.matched else marks_per_point * PARTIAL_POINT_WEIGHT if ks.partial else 0.0
            criteria.append(
                CriterionScore(
                    criterion=ks.point,
                    kind="key_point",
                    max_marks=round(marks_per_point, 2),
                    awarded=round(share, 2),
                    status="met" if ks.matched else "partial" if ks.partial else "missed",
                    semantic_similarity=None if ks.similarity is None else round(ks.similarity, 3),
                    keyword_overlap=round(ks.keyword_score, 3),
                )
            )
        key_point_marks = len(matched) * marks_per_point + len(partial) * marks_per_point * PARTIAL_POINT_WEIGHT

        # Partial-credit rules are floors, not bonuses.
        rule_floor = 0.0
        applied_rules: list[str] = []
        for rule, sem in zip(rules, rule_sims, strict=True):
            kw = keyword_overlap_score(student_text, rule.condition)
            applied = _strong_match(sem, kw)
            rule_marks = min(rule.marks, max_marks)
            if applied:
                rule_floor = max(rule_floor, rule_marks)
                applied_rules.append(rule.condition)
            criteria.append(
                CriterionScore(
                    criterion=rule.condition,
                    kind="partial_rule",
                    max_marks=rule_marks,
                    awarded=rule_marks if applied else 0.0,
                    status="applied" if applied else "not_applied",
                    semantic_similarity=None if sem is None else round(sem, 3),
                    keyword_overlap=round(kw, 3),
                )
            )

        deduction = 0.0
        triggered: list[str] = []
        for condition, sem in zip(negatives, neg_sims, strict=True):
            kw = keyword_overlap_score(student_text, condition)
            applied = _strong_match(sem, kw)
            if applied:
                deduction += max_marks * PENALTY_FRACTION
                triggered.append(condition)
            criteria.append(
                CriterionScore(
                    criterion=condition,
                    kind="penalty",
                    max_marks=round(max_marks * PENALTY_FRACTION, 2),
                    awarded=-round(max_marks * PENALTY_FRACTION, 2) if applied else 0.0,
                    status="applied" if applied else "not_applied",
                    semantic_similarity=None if sem is None else round(sem, 3),
                    keyword_overlap=round(kw, 3),
                )
            )
        deduction = min(deduction, max_marks * MAX_PENALTY_FRACTION)

        raw = max(key_point_marks, rule_floor) - deduction
        marks_awarded = round_marks(max(0.0, min(max_marks, raw)))

        # Effort is evidence for review, never for marks: substantive working that
        # the matcher could not tie to the rubric needs a human decision.
        effort_marks = effort_based_marks(max_marks, quality)
        evidence_gap = effort_marks - marks_awarded >= 0.25 * max_marks

        confidence = realistic_confidence(quality, ocr_adj, marks_awarded, max_marks)
        if lexical_only:
            confidence = min(confidence, LEXICAL_CONFIDENCE_CAP)
        if evidence_gap:
            confidence = min(confidence, EVIDENCE_GAP_CONFIDENCE_CAP)

        justification = self._build_justification(
            rubric_item, matched, partial, missed, marks_awarded, deduction,
            applied_rules, evidence_gap, lexical_only,
        )
        if self.use_llm:
            justification = self._enhance_with_llm(
                student_text, rubric_item, marks_awarded, justification
            )

        logger.debug(
            "%s marks=%.1f/%.1f kp=%.1f rule=%.1f penalty=%.1f effort=%.1f gap=%s lexical=%s",
            q_label, marks_awarded, max_marks, key_point_marks, rule_floor,
            deduction, effort_marks, evidence_gap, lexical_only,
        )

        return QuestionResult(
            question=q_label,
            marks_awarded=marks_awarded,
            max_marks=max_marks,
            justification=justification,
            confidence=round(confidence, 3),
            is_blank=False,
            key_points_matched=[ks.point for ks in matched],
            key_points_partial=[ks.point for ks in partial],
            key_points_missed=[ks.point for ks in missed],
            negative_triggers=triggered,
            criteria=criteria,
            requires_manual_grading=evidence_gap,
            ai_marks_awarded=marks_awarded,
            scoring_method="lexical" if lexical_only else "semantic",
        )

    def _manual_grading_result(
        self, rubric_item: RubricItem, quality: AnswerQuality
    ) -> QuestionResult:
        """No rubric criteria to compare against: the AI cannot judge correctness."""
        return QuestionResult(
            question=rubric_item.question_number,
            marks_awarded=0.0,
            max_marks=rubric_item.max_marks,
            justification=(
                f"{rubric_item.question_number}: The rubric has no key points for this "
                "question, so the AI cannot assess correctness. No marks were awarded "
                "automatically — manual grading required "
                f"(answer contains readable content, strength {quality.content_score:.0%})."
            ),
            confidence=MANUAL_GRADING_CONFIDENCE,
            requires_manual_grading=True,
            ai_marks_awarded=0.0,
        )

    @staticmethod
    def _build_justification(
        rubric_item: RubricItem,
        matched: list[KeyPointScore],
        partial: list[KeyPointScore],
        missed: list[KeyPointScore],
        marks: float,
        deduction: float,
        applied_rules: list[str],
        evidence_gap: bool,
        lexical_only: bool,
    ) -> str:
        q = rubric_item.question_number
        mx = rubric_item.max_marks
        ratio = marks / mx if mx else 0.0
        if ratio >= 0.85:
            parts = [f"{q}: Strong response ({marks:.1f}/{mx:.1f})."]
        elif ratio >= 0.5:
            parts = [f"{q}: Satisfactory ({marks:.1f}/{mx:.1f}); some rubric criteria not evidenced."]
        elif marks > 0:
            parts = [f"{q}: Partial credit ({marks:.1f}/{mx:.1f})."]
        else:
            parts = [f"{q}: No marks ({marks:.1f}/{mx:.1f}); rubric criteria were not identified in the answer text."]

        def _list(points: list[KeyPointScore]) -> str:
            shown = "; ".join(p.point[:60] for p in points[:3])
            return shown + (f" (+{len(points) - 3} more)" if len(points) > 3 else "")

        if matched:
            parts.append(f"Met: {_list(matched)}.")
        if partial:
            parts.append(f"Partially addressed: {_list(partial)}.")
        if missed:
            parts.append(f"Not found: {_list(missed)}.")
        if applied_rules:
            parts.append(f"Partial-credit rule applied: {applied_rules[0][:60]}.")
        if deduction > 0:
            parts.append(f"Penalty: −{deduction:.1f} marks per rubric conditions.")
        if evidence_gap:
            parts.append(
                "The answer contains substantive working that could not be matched to the "
                "rubric (possible OCR or phrasing mismatch) — verify manually."
            )
        if lexical_only:
            parts.append("Semantic model unavailable: keyword matching only.")
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
        """One result per rubric question; totals sum cleanly for the API response."""
        from app.services.text_utils import merge_answers_by_question

        rubric_q = [r.question_number for r in rubric_items]
        merged = merge_answers_by_question(answers, rubric_q)
        answer_map = {a["question_number"].upper(): a for a in merged}

        results: list[QuestionResult] = []
        for item in rubric_items:
            ans = answer_map.get(item.question_number.upper())
            if not ans:
                results.append(self.evaluate_answer("", item, ocr_confidence=0.0))
                continue
            text = ans.get("extracted_text", "")
            ocr_conf = float(ans.get("ocr_confidence", 0.5) or 0.5)
            results.append(self.evaluate_answer(text, item, ocr_confidence=ocr_conf))
        return results

