"""
Heuristic analysis of handwritten / OCR-noisy exam answers.

Lightweight signals only (no LLM): length, math symbols, steps, keywords.
Used to award fair partial credit when embedding similarity is low.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.services.text_utils import keyword_overlap_score

logger = logging.getLogger(__name__)

# Mathematical & scientific notation common in OCR output
MATH_SYMBOL_RE = re.compile(
    r"[+\-*/=^±∫∑∏√∂∇∞≈≠≤≥≡∈∪∩"
    r"()\[\]{}|]"
)
DIGIT_RE = re.compile(r"\d")
EQUATION_LINE_RE = re.compile(
    r"(?:[=+\-*/^]|d[a-z]/d[a-z]|\b(?:sin|cos|tan|log|exp|lim)\b)",
    re.I,
)
STEP_LINE_RE = re.compile(
    r"^\s*(?:\d+[\.\):]|(?:=>|→|therefore|hence|thus)\b)",
    re.I | re.MULTILINE,
)

# Rubric vocabulary often missed by OCR — short STEM tokens still count
STEM_TOKEN_RE = re.compile(
    r"\b(?:pde|ode|ux|uy|u_xx|fourier|integral|derivative|gradient|"
    r"laplace|boundary|eigen|matrix|vector|scalar|partial|solution|"
    r"equation|hyperbolic|elliptic|parabolic|series|coefficient)\b",
    re.I,
)


@dataclass
class AnswerQuality:
    """Signals extracted from one student answer region."""

    char_count: int
    word_count: int
    digit_count: int
    math_symbol_count: int
    equation_line_count: int
    step_hint_count: int
    stem_token_count: int
    keyword_best: float  # max overlap vs rubric key points
    content_score: float  # 0–1 overall “substantive answer”
    is_truly_blank: bool
    is_handwritten_math: bool


def _count_words(text: str) -> int:
    return len(re.findall(r"[a-zA-Z]{2,}", text))


def analyze_answer(
    text: str,
    *,
    ocr_confidence: float,
    rubric_key_points: list[str] | None = None,
    blank_min_chars: int = 3,
) -> AnswerQuality:
    """
    Score how much usable content exists in an OCR answer (handwriting-tolerant).
    """
    raw = text or ""
    stripped = raw.strip()
    alnum = sum(1 for c in stripped if c.isalnum())

    if alnum < blank_min_chars:
        return AnswerQuality(
            char_count=len(stripped),
            word_count=0,
            digit_count=0,
            math_symbol_count=0,
            equation_line_count=0,
            step_hint_count=0,
            stem_token_count=0,
            keyword_best=0.0,
            content_score=0.0,
            is_truly_blank=True,
            is_handwritten_math=False,
        )

    word_count = _count_words(stripped)
    digit_count = len(DIGIT_RE.findall(stripped))
    math_symbol_count = len(MATH_SYMBOL_RE.findall(stripped))
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    equation_line_count = sum(1 for ln in lines if EQUATION_LINE_RE.search(ln))
    step_hint_count = len(STEP_LINE_RE.findall(stripped))
    stem_token_count = len(STEM_TOKEN_RE.findall(stripped))

    keyword_best = 0.0
    if rubric_key_points:
        for kp in rubric_key_points:
            keyword_best = max(keyword_best, keyword_overlap_score(stripped, kp))
            # Also match individual STEM-ish words from rubric
            for token in re.findall(r"[a-zA-Z]{4,}", kp):
                if token.lower() in stripped.lower():
                    keyword_best = max(keyword_best, 0.25)

    # Normalized sub-scores (tuned for handwritten exam sheets)
    length_score = min(1.0, alnum / 60.0)
    word_score = min(1.0, word_count / 12.0)
    math_density = min(1.0, math_symbol_count / max(len(stripped) / 25.0, 1.0))
    digit_score = min(1.0, digit_count / 8.0)
    equation_score = min(1.0, equation_line_count / 2.0)
    step_score = min(1.0, step_hint_count / 2.0)
    stem_score = min(1.0, stem_token_count / 2.0)
    keyword_score = min(1.0, keyword_best * 1.4)
    ocr_score = min(1.0, max(ocr_confidence, 0.2))

    content_score = (
        0.18 * length_score
        + 0.12 * word_score
        + 0.20 * math_density
        + 0.14 * digit_score
        + 0.14 * equation_score
        + 0.08 * step_score
        + 0.08 * stem_score
        + 0.06 * keyword_score
    )
    # Boost when multiple math signals agree (typical handwritten solution)
    math_signals = sum(
        1
        for s in (math_density, digit_score, equation_score)
        if s >= 0.35
    )
    if math_signals >= 2:
        content_score = min(1.0, content_score + 0.12)
    if word_count >= 6 and math_symbol_count >= 3:
        content_score = min(1.0, content_score + 0.08)

    content_score = min(1.0, content_score * (0.85 + 0.15 * ocr_score))

    is_handwritten_math = (
        content_score >= 0.28
        and (math_symbol_count >= 2 or equation_line_count >= 1 or digit_count >= 4)
    )

    return AnswerQuality(
        char_count=len(stripped),
        word_count=word_count,
        digit_count=digit_count,
        math_symbol_count=math_symbol_count,
        equation_line_count=equation_line_count,
        step_hint_count=step_hint_count,
        stem_token_count=stem_token_count,
        keyword_best=keyword_best,
        content_score=round(content_score, 3),
        is_truly_blank=False,
        is_handwritten_math=is_handwritten_math,
    )


def effort_based_marks(max_marks: float, quality: AnswerQuality) -> float:
    """
    Partial marks from content heuristics when rubric embedding match is weak.
    Never awards full marks on effort alone — caps below max unless rubric agrees.
    """
    if quality.is_truly_blank or quality.content_score < 0.12:
        return 0.0

    cs = quality.content_score
    # Tiered partial credit (demo-realistic)
    if cs >= 0.72:
        ratio = 0.72
    elif cs >= 0.55:
        ratio = 0.58
    elif cs >= 0.40:
        ratio = 0.45
    elif cs >= 0.28:
        ratio = 0.32
    else:
        ratio = 0.20

    # Small boost for strong keyword overlap despite OCR noise
    if quality.keyword_best >= 0.2:
        ratio = min(0.85, ratio + 0.12)

    marks = max_marks * ratio
    # Minimum partial for clearly non-blank handwritten math
    if quality.is_handwritten_math and cs >= 0.30:
        floor = max_marks * 0.25
        marks = max(marks, floor)

    return marks


def realistic_confidence(
    quality: AnswerQuality,
    ocr_confidence: float,
    marks_awarded: float,
    max_marks: float,
) -> float:
    """
    Map to a believable 0.40–0.85 band for readable handwritten answers.
    """
    if quality.is_truly_blank:
        return 0.88 if marks_awarded == 0 else 0.75

    mark_ratio = marks_awarded / max_marks if max_marks > 0 else 0.0
    base = (
        0.38
        + 0.28 * quality.content_score
        + 0.18 * min(ocr_confidence, 0.9)
        + 0.16 * mark_ratio
    )
    if quality.is_handwritten_math:
        base = max(base, 0.42 + 0.20 * quality.content_score)

    return round(min(0.85, max(0.32, base)), 3)
